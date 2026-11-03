"""GPT 매물 정보 조회 (PRD 7절).

속도를 위해 두 호출을 동시에 보낸다.
- 시세 호출: 웹 검색 사용 (최신 시세·단지 기본정보)
- 위치 호출: 웹 검색 없음, reasoning effort low (좌표·지하철역·학교·학군·통근시간 추정)
전체 소요 시간은 두 호출 중 느린 쪽만큼이다 (측정: 단일 호출 약 50초 → 약 18초).
각 호출은 검증 실패 시 1회 재시도한다. 시세 호출이 실패하면 AIError → UI가 수동 입력 폼으로 전환,
위치 호출만 실패하면 해당 값은 비워 두고(좌표는 geo.ensure_coords가 보정) 시세 결과로 진행한다.
IMJANG_MOCK_AI=1 이면 네트워크 없이 결정적인 가짜 응답을 돌려준다(E2E 테스트용).
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from pydantic import ValidationError

from core import config
from core.models import DealType, PropertyInfo


class AIError(Exception):
    """사용자에게 그대로 보여줄 한국어 메시지를 담는 예외."""


COMMON_RULES = """JSON 객체 하나만 출력하세요. 설명 문장, 마크다운, 코드펜스는 금지합니다.
아파트명이 비어 있으면 해당 지역의 대표 아파트 단지 하나를 골라 조회하세요."""

PRICE_PROMPT = f"""당신은 한국 아파트 시장 전문 리서처입니다.
웹 검색으로 최신 시세(최근 실거래가, 호가, 네이버부동산·호갱노노·KB부동산·국토부 실거래가 등)와
단지 기본 정보를 확인하세요. {COMMON_RULES}

규칙:
- 금액은 원(KRW) 단위 정수. 예: 6억 5천만원 → 650000000
- 거래유형이 매매면 price.sale, 전세면 price.deposit, 월세면 price.deposit + price.monthly 를 채움
- 시세는 해당 거래유형의 대표 평형(없으면 84㎡ 내외) 기준 최근 시세 중간값, range는 "6.2억~6.8억"처럼 짧게
- basis는 60자 이내 한 문장 (예: "84㎡ 최근 3개월 실거래 중앙값")
- 시세(price)는 출처로 확인한 값만 쓰고, 확인 못 하면 null
- sources: 참고한 출처 URL 최대 5개 (설명 없이 URL만), as_of: 기준 연월(YYYY-MM), confidence: high|medium|low

스키마:
{{"name": str, "address": str|null, "region": str|null,
 "price": {{"sale": int|null, "deposit": int|null, "monthly": int|null, "unit": "KRW",
           "basis": str|null, "range": str|null}},
 "area_m2": float|null, "built_year": int|null, "households": int|null,
 "sources": [str], "as_of": str|null, "confidence": "high"|"medium"|"low"|null}}
"""

LOCATION_PROMPT = f"""당신은 한국 지리·교통·학군에 밝은 부동산 입지 분석가입니다.
알고 있는 지식으로 아래 값을 채우세요. 정확한 수치가 없어도 지도·주소 기준 합리적 추정치를 넣고 null은 최소화하세요.
{COMMON_RULES}

규칙:
- lat/lng: 단지 중심 좌표(WGS84, 소수 5자리)
- subway: 가까운 지하철역 최대 3개, 단지 중심→역까지 도보 거리(m)와 도보 분(80m/분 기준)
- schools: 근처 초/중/고 최대 4개와 대략 거리(m), 배정·학업성취도 등 특이사항은 note(40자 이내)
- school_district_score: 학원가·학업성취도·선호도를 종합한 학군 수준 1(약함)~5(최상) 정수
- commute: 직장 주소가 주어지면 대중교통 기준 예상 소요 분(정수), 없으면 null

스키마:
{{"lat": float|null, "lng": float|null,
 "subway": [{{"station": str, "line": str|null, "distance_m": int|null, "walk_min": int|null}}],
 "schools": [{{"name": str, "level": "초"|"중"|"고"|null, "distance_m": int|null, "note": str|null}}],
 "school_district_score": int|null,
 "commute": {{"minutes": int|null, "mode": str|null}}}}
"""

PRICE_KEYS = ("name", "address", "region", "price", "area_m2", "built_year", "households",
              "sources", "as_of", "confidence")
LOCATION_KEYS = ("lat", "lng", "subway", "schools", "school_district_score", "commute")


def _user_prompt(region: str, apt_name: str, deal_type: str, work_address: str | None) -> str:
    target = f"{region} {apt_name}".strip()
    return (
        f"오늘 날짜: {date.today().isoformat()}\n"
        f"조회 대상: {target}\n"
        f"거래유형: {deal_type}\n"
        f"직장 주소: {work_address or '없음'}"
    )


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON을 찾지 못했습니다.")
    return json.loads(text[start:end + 1])


def _friendly_error(e: Exception) -> AIError:
    import openai

    if isinstance(e, openai.AuthenticationError):
        return AIError("API 키가 올바르지 않습니다. .env의 OPENAI_API_KEY를 확인하세요.")
    if isinstance(e, openai.RateLimitError):
        return AIError("API 사용 한도를 초과했거나 요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    if isinstance(e, openai.NotFoundError):
        return AIError(f"모델 '{config.OPENAI_MODEL}'을(를) 사용할 수 없습니다. "
                       f".env의 OPENAI_MODEL을 확인하세요. (원문: {e})")
    if isinstance(e, openai.APIConnectionError | openai.APITimeoutError):
        return AIError("OpenAI 서버에 연결하지 못했습니다. 네트워크를 확인하세요.")
    if isinstance(e, openai.APIStatusError):
        return AIError(f"AI 조회 중 오류가 발생했습니다: {e}")
    return AIError(f"AI 조회 중 알 수 없는 오류: {e}")


def _call_openai(instructions: str, prompt: str, web_search: bool) -> str:
    import openai

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY, timeout=90)
    if web_search:
        kwargs = {"tools": [{"type": "web_search"}]}
    else:
        # 검색 없는 위치 추정은 추론 강도를 낮춰도 결과가 같고 약 2배 빠름 (측정: 31.9s → 16.3s)
        kwargs = {"reasoning": {"effort": "low"}}
    try:
        resp = client.responses.create(model=config.OPENAI_MODEL, instructions=instructions,
                                       input=prompt, **kwargs)
    except openai.BadRequestError as e:
        if "reasoning" not in kwargs or "reasoning" not in str(e).lower():
            raise
        # reasoning 옵션을 지원하지 않는 모델이면 옵션 없이 다시 호출
        resp = client.responses.create(model=config.OPENAI_MODEL, instructions=instructions,
                                       input=prompt)
    return resp.output_text


def _fetch_part(instructions: str, prompt: str, web_search: bool, keys: tuple[str, ...],
                deal_type: str) -> dict:
    """한 호출을 실행하고 해당 부분만 검증해 dict로 돌려준다. 검증 실패 시 1회 재시도.

    API 오류는 AIError, 두 번 다 형식이 틀리면 ValueError.
    """
    hint: str | None = None
    for _ in range(2):
        p = prompt if not hint else (
            f"{prompt}\n\n직전 응답이 스키마 검증에 실패했습니다: {hint}\nJSON 객체만 다시 출력하세요.")
        try:
            text = _call_openai(instructions, p, web_search)
        except Exception as e:  # openai 예외를 사용자 메시지로 변환
            raise _friendly_error(e) from e
        try:
            data = {k: v for k, v in _extract_json(text).items() if k in keys}
            # 부분만 검증 (나머지 필수 필드는 임시값)
            PropertyInfo(**{"name": "_", **data, "deal_type": deal_type})
            return data
        except (ValueError, ValidationError) as e:
            hint = str(e)[:500]
    raise ValueError(hint)


def _mock_response(region: str, apt_name: str, deal_type: str, work_address: str | None) -> dict:
    """입력값으로부터 결정적으로 만들어지는 가짜 응답."""
    seed = int(hashlib.md5(f"{region}|{apt_name}".encode()).hexdigest(), 16)
    name = apt_name.strip() or f"{region.split()[-1] if region.strip() else '샘플'} 테스트아파트"
    price = {"sale": None, "deposit": None, "monthly": None, "unit": "KRW",
             "basis": "MOCK 응답", "range": None}
    if deal_type == "매매":
        price["sale"] = 800_000_000 + (seed % 10) * 100_000_000
    elif deal_type == "전세":
        price["deposit"] = 400_000_000 + (seed % 8) * 50_000_000
    else:
        price["deposit"] = 50_000_000 + (seed % 5) * 10_000_000
        price["monthly"] = 1_000_000 + (seed % 6) * 200_000
    return {
        "name": name,
        "address": f"서울특별시 {region} (MOCK)",
        "region": region or "서울",
        "lat": 37.50 + (seed % 1000) / 10000,
        "lng": 126.90 + (seed // 1000 % 2000) / 10000,
        "deal_type": deal_type,
        "price": price,
        "area_m2": [59.9, 74.5, 84.9, 101.2][seed % 4],
        "built_year": 1995 + seed % 30,
        "households": 300 + seed % 3000,
        "subway": [{"station": "테스트역", "line": "2호선",
                    "distance_m": 200 + seed % 1200, "walk_min": 3 + seed % 15}],
        "schools": [{"name": "테스트초등학교", "level": "초",
                     "distance_m": 150 + seed % 800, "note": None}],
        "school_district_score": 1 + seed % 5,
        "commute": {"minutes": (15 + seed % 70) if work_address else None, "mode": "대중교통"},
        "sources": ["MOCK (IMJANG_MOCK_AI=1)"],
        "as_of": date.today().strftime("%Y-%m"),
        "confidence": "low",
    }


def lookup_property(region: str, apt_name: str, deal_type: DealType,
                    work_address: str | None = None) -> PropertyInfo:
    """지역/단지명/거래유형으로 시세·좌표·역·학군·통근시간을 조회한다.

    실패 시 사용자용 메시지를 담은 AIError를 던진다.
    """
    if not (region.strip() or apt_name.strip()):
        raise AIError("지역 또는 아파트명을 입력하세요.")

    if config.MOCK_AI:
        return PropertyInfo(**_mock_response(region, apt_name, deal_type, work_address))

    if not config.has_api_key():
        raise AIError("OPENAI_API_KEY가 설정되지 않아 AI 조회를 할 수 없습니다. 수동으로 입력하세요.")

    prompt = _user_prompt(region, apt_name, deal_type, work_address)
    with ThreadPoolExecutor(max_workers=2) as pool:
        price_f = pool.submit(_fetch_part, PRICE_PROMPT, prompt, True, PRICE_KEYS, deal_type)
        loc_f = pool.submit(_fetch_part, LOCATION_PROMPT, prompt, False, LOCATION_KEYS, deal_type)
        try:
            price = price_f.result()
        except ValueError:
            raise AIError("AI 응답 형식이 올바르지 않습니다. 수동 입력 폼에서 직접 입력하세요.") from None
        try:
            location = loc_f.result()
        except (AIError, ValueError):
            location = {}  # 위치 정보만 비우고 진행 (좌표는 지오코딩으로 보정)

    if not price.get("name"):
        price["name"] = apt_name.strip() or region.strip()
    return PropertyInfo(**price, **location, deal_type=deal_type)
