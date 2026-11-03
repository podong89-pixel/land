"""점수 산출 (PRD 6절).

- 항목별 원점수 0~100 (None = 데이터 없음)
- 가중치는 그룹 단위, 그룹 내에서는 '데이터가 있는' 항목끼리 균등 분배
- 데이터가 하나도 없는 그룹은 제외하고 나머지 그룹 가중치를 재정규화
- contribution = 원점수 × 항목 가중치, Σ contribution = 종합 점수
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# 항목 키 -> (표시명, 구분: auto/manual, 소속 그룹)
ITEMS: dict[str, tuple[str, str, str]] = {
    "budget": ("예산 대비", "auto", "budget"),
    "station": ("역까지 거리", "auto", "transport"),
    "commute": ("직장 통근시간", "auto", "transport"),
    "area": ("면적", "auto", "space"),
    "age": ("준공연차", "auto", "space"),
    "school": ("학군", "auto", "school"),
    "sunlight": ("채광", "manual", "field"),
    "water_pressure": ("수압", "manual", "field"),
    "noise": ("소음", "manual", "field"),
    "neighborhood": ("동네 분위기", "manual", "field"),
    "first_impression": ("집 안 첫인상", "manual", "field"),
    "checklist": ("현장 체크(장/단점)", "manual", "field"),
}

# 가중치 그룹 -> (표시명, 기본 가중치 %)
GROUPS: dict[str, tuple[str, int]] = {
    "budget": ("예산", 30),
    "transport": ("교통·통근", 25),
    "field": ("현장 느낌", 25),
    "space": ("면적·연식", 10),
    "school": ("학군", 10),
}

DEFAULT_WEIGHTS: dict[str, int] = {k: w for k, (_, w) in GROUPS.items()}

MANUAL_FIELDS = ("sunlight", "water_pressure", "noise", "neighborhood", "first_impression")
MONTHLY_TO_DEPOSIT = 100  # 월세 1원 = 보증금 100원으로 환산 (PRD 6.1)


@dataclass
class ScoreResult:
    total: float | None                       # 종합 점수 0~100
    item_scores: dict[str, float | None]      # 항목별 원점수 0~100 (None=데이터 없음)
    item_weights: dict[str, float]            # 항목별 정규화 가중치 (합 1.0)
    contributions: dict[str, float]           # 항목별 기여 점수 (합 = total)
    provisional: bool = False                 # 임장 전(직접 입력 없음) 잠정 점수 여부
    notes: list[str] = field(default_factory=list)


# ---------- 환산 함수 ----------

def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _linear(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """x0→y0, x1→y1 구간 선형 보간. 구간 밖은 끝값 유지."""
    if x <= x0:
        return y0
    if x >= x1:
        return y1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def effective_price(prop: dict[str, Any]) -> float | None:
    deal = prop.get("deal_type")
    if deal == "매매":
        return prop.get("price_sale")
    if deal == "전세":
        return prop.get("deposit")
    deposit, monthly = prop.get("deposit"), prop.get("monthly")
    if deposit is None and monthly is None:
        return None
    return (deposit or 0) + (monthly or 0) * MONTHLY_TO_DEPOSIT


def effective_budget(deal_type: str, settings: dict[str, Any]) -> float | None:
    b = settings.get("budget") or {}
    if deal_type == "월세":
        dep, mon = b.get("월세_deposit"), b.get("월세_monthly")
        if not dep and not mon:
            return None
        return (dep or 0) + (mon or 0) * MONTHLY_TO_DEPOSIT
    return b.get(deal_type) or None


def score_budget(price: float | None, budget: float | None) -> float | None:
    if price is None or not budget:
        return None
    r = price / budget
    if r <= 1.0:
        return _linear(r, 0.8, 100, 1.0, 70)
    return _linear(r, 1.0, 70, 1.2, 0)


def score_station(distance_m: float | None) -> float | None:
    return None if distance_m is None else _linear(distance_m, 300, 100, 1500, 0)


def score_commute(minutes: float | None) -> float | None:
    return None if minutes is None else _linear(minutes, 20, 100, 90, 0)


def score_area(area_m2: float | None, desired_m2: float | None) -> float | None:
    if area_m2 is None or not desired_m2:
        return None
    return _linear(area_m2, desired_m2 * 0.6, 0, desired_m2, 100)


def score_age(built_year: int | None, this_year: int | None = None) -> float | None:
    if built_year is None:
        return None
    age = (this_year or date.today().year) - built_year
    return _linear(age, 5, 100, 30, 20)


def score_school(district_score: int | None, schools: list[dict] | None) -> float | None:
    if district_score is None:
        return None
    s = _clamp(district_score, 1, 5)
    near_elem = any(
        "초" in (sc.get("level") or sc.get("name") or "")
        and sc.get("distance_m") is not None and sc["distance_m"] <= 500
        for sc in (schools or [])
    )
    return (s - 1) / 4 * 80 + (20 if near_elem else 0)


def score_rating(v: int | None) -> float | None:
    return None if v is None else (_clamp(v, 1, 5) - 1) / 4 * 100


def score_checklist(pros: list | None, cons: list | None) -> float | None:
    """장점 +5, 단점 -5 (기준 50). 하나도 체크하지 않았으면 평가 안 함(None)으로 본다."""
    if not pros and not cons:
        return None
    return _clamp(50 + (len(pros or []) - len(cons or [])) * 5)


# ---------- 공개 API ----------

def normalize_weights(group_weights: dict[str, float]) -> dict[str, float]:
    """그룹 가중치(슬라이더 값)를 합 1.0으로 정규화한다. 모두 0이면 균등 분배."""
    clean = {k: max(0.0, float(v or 0)) for k, v in group_weights.items()}
    total = sum(clean.values())
    if total <= 0:
        return {k: 1 / len(clean) for k in clean} if clean else {}
    return {k: v / total for k, v in clean.items()}


def nearest_station_m(prop: dict[str, Any]) -> float | None:
    ds = [s.get("distance_m") for s in prop.get("subway") or [] if s.get("distance_m") is not None]
    return min(ds) if ds else None


def item_scores(prop: dict[str, Any], inspection: dict[str, Any] | None,
                settings: dict[str, Any]) -> dict[str, float | None]:
    """매물/임장기록/사용자 설정으로 항목별 0~100 점수를 계산한다 (PRD 6.1)."""
    ins = inspection or {}
    scores: dict[str, float | None] = {
        "budget": score_budget(effective_price(prop),
                               effective_budget(prop.get("deal_type"), settings)),
        "station": score_station(nearest_station_m(prop)),
        "commute": score_commute(prop.get("commute_min")),
        "area": score_area(prop.get("area_m2"), settings.get("desired_area")),
        "age": score_age(prop.get("built_year")),
        "school": score_school(prop.get("school_district_score"), prop.get("schools")),
    }
    for f in MANUAL_FIELDS:
        scores[f] = score_rating(ins.get(f))
    scores["checklist"] = score_checklist(ins.get("pros"), ins.get("cons"))
    return scores


def compute_score(prop: dict[str, Any], inspection: dict[str, Any] | None,
                  settings: dict[str, Any]) -> ScoreResult:
    """누락 항목을 제외하고 가중치를 재정규화하여 종합 점수와 기여도를 계산한다 (PRD 6.3)."""
    scores = item_scores(prop, inspection, settings)
    raw_weights = settings.get("weights") or DEFAULT_WEIGHTS
    notes: list[str] = []

    available: dict[str, list[str]] = {g: [] for g in GROUPS}
    for key, (_, _, group) in ITEMS.items():
        if scores[key] is not None:
            available[group].append(key)
        else:
            notes.append(f"{ITEMS[key][0]}: 데이터 없음")

    live_groups = {g: raw_weights.get(g, 0) for g, keys in available.items() if keys}
    group_w = normalize_weights(live_groups)

    item_weights = {k: 0.0 for k in ITEMS}
    for g, w in group_w.items():
        for key in available[g]:
            item_weights[key] = w / len(available[g])

    contributions = {k: (scores[k] or 0.0) * item_weights[k] for k in ITEMS}
    total = round(sum(contributions.values()), 1) if group_w else None
    provisional = all(scores[k] is None for k in (*MANUAL_FIELDS, "checklist"))
    return ScoreResult(total, scores, item_weights, contributions, provisional, notes)


def strengths_weaknesses(result: ScoreResult, n: int = 2) -> tuple[list[str], list[str]]:
    """가중치가 있는 항목 중 원점수 상위 n개(강점)와 하위 1개(약점)의 표시명."""
    ranked = sorted(
        (k for k in ITEMS if result.item_scores[k] is not None and result.item_weights[k] > 0),
        key=lambda k: result.item_scores[k], reverse=True,
    )
    strong = [ITEMS[k][0] for k in ranked[:n] if result.item_scores[k] >= 60]
    weak = [ITEMS[k][0] for k in ranked[-1:] if result.item_scores[k] < 60]
    return strong, weak
