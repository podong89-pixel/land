"""매물 정보 미리보기/수정 폼 (F2-3). 신규 등록과 기존 매물 수정에 공용."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from core.config import DEAL_TYPES
from core.models import PropertyInfo

MAN = 10_000


def _num(v: Any) -> Any:
    """data_editor의 NaN을 None으로."""
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def _int_or_none(v: Any) -> int | None:
    v = _num(v)
    return None if v is None else int(v)


def _rows(df: pd.DataFrame, required: str, ints: tuple[str, ...]) -> list[dict]:
    out = []
    for rec in df.to_dict("records"):
        if not str(_num(rec.get(required)) or "").strip():
            continue
        clean = {k: _num(v) for k, v in rec.items()}
        for k in ints:
            clean[k] = _int_or_none(clean.get(k))
        out.append(clean)
    return out


def render_form(draft: dict[str, Any], key: str, submit_label: str) -> PropertyInfo | None:
    """draft(PropertyInfo 형태 dict)로 폼을 그리고, 제출되면 검증된 PropertyInfo를 반환한다."""
    price = draft.get("price") or {}
    commute = draft.get("commute") or {}

    with st.form(key=f"form_{key}"):
        c1, c2, c3 = st.columns([2, 2, 1])
        name = c1.text_input("아파트명 *", value=draft.get("name") or "")
        region = c2.text_input("지역", value=draft.get("region") or "")
        deal = c3.selectbox("거래유형", DEAL_TYPES,
                            index=DEAL_TYPES.index(draft.get("deal_type") or "전세"))
        address = st.text_input("주소", value=draft.get("address") or "")

        st.markdown("**금액 (만원)** — 거래유형에 맞는 칸만 입력")
        p1, p2, p3 = st.columns(3)
        sale = p1.number_input("매매가", min_value=0, step=1000,
                               value=int((price.get("sale") or 0) // MAN))
        deposit = p2.number_input("보증금(전세/월세)", min_value=0, step=500,
                                  value=int((price.get("deposit") or 0) // MAN))
        monthly = p3.number_input("월세", min_value=0, step=10,
                                  value=int((price.get("monthly") or 0) // MAN))
        if price.get("range") or price.get("basis"):
            st.caption(f"AI 시세 범위: {price.get('range') or '-'} · 기준: {price.get('basis') or '-'}")

        d1, d2, d3, d4 = st.columns(4)
        area = d1.number_input("전용면적(㎡)", min_value=0.0, step=0.1,
                               value=float(draft.get("area_m2") or 0.0))
        built = d2.number_input("준공연도", min_value=0, max_value=2100, step=1,
                                value=int(draft.get("built_year") or 0))
        households = d3.number_input("세대수", min_value=0, step=10,
                                     value=int(draft.get("households") or 0))
        commute_min = d4.number_input("통근시간(분)", min_value=0, max_value=300, step=5,
                                      value=int(commute.get("minutes") or 0),
                                      help="AI 추정값. 0이면 '데이터 없음'으로 처리")

        g1, g2, g3 = st.columns(3)
        lat = g1.number_input("위도", value=float(draft.get("lat") or 0.0), format="%.6f")
        lng = g2.number_input("경도", value=float(draft.get("lng") or 0.0), format="%.6f")
        sds_opts = ["모름", 1, 2, 3, 4, 5]
        sds = g3.selectbox("학군 점수(1~5)", sds_opts,
                           index=sds_opts.index(draft.get("school_district_score") or "모름"))

        st.markdown("**인접 지하철역**")
        subway_df = st.data_editor(
            pd.DataFrame(draft.get("subway") or [],
                         columns=["station", "line", "distance_m", "walk_min"]),
            num_rows="dynamic", width="stretch", key=f"subway_{key}",
            column_config={
                "station": st.column_config.TextColumn("역명"),
                "line": st.column_config.TextColumn("노선"),
                "distance_m": st.column_config.NumberColumn("거리(m)", min_value=0, step=10),
                "walk_min": st.column_config.NumberColumn("도보(분)", min_value=0),
            })
        st.markdown("**근처 학교**")
        school_df = st.data_editor(
            pd.DataFrame(draft.get("schools") or [],
                         columns=["name", "level", "distance_m", "note"]),
            num_rows="dynamic", width="stretch", key=f"schools_{key}",
            column_config={
                "name": st.column_config.TextColumn("학교명"),
                "level": st.column_config.SelectboxColumn("구분", options=["초", "중", "고"]),
                "distance_m": st.column_config.NumberColumn("거리(m)", min_value=0, step=10),
                "note": st.column_config.TextColumn("비고"),
            })

        submitted = st.form_submit_button(submit_label, type="primary")

    if not submitted:
        return None
    if not name.strip():
        st.error("아파트명을 입력하세요.")
        return None
    price_ok = {"매매": sale > 0, "전세": deposit > 0, "월세": deposit > 0 or monthly > 0}[deal]
    if not price_ok:
        st.warning(f"{deal} 금액이 비어 있어 '예산 대비' 점수는 데이터 없음으로 처리됩니다.")

    try:
        return PropertyInfo(
            name=name.strip(), region=region.strip() or None, address=address.strip() or None,
            deal_type=deal,
            lat=lat or None, lng=lng or None,
            price={
                "sale": sale * MAN if deal == "매매" and sale else None,
                "deposit": deposit * MAN if deal != "매매" and deposit else None,
                "monthly": monthly * MAN if deal == "월세" and monthly else None,
                "basis": price.get("basis"), "range": price.get("range"),
            },
            area_m2=area or None, built_year=built or None, households=households or None,
            subway=_rows(subway_df, "station", ("distance_m", "walk_min")),
            schools=_rows(school_df, "name", ("distance_m",)),
            school_district_score=None if sds == "모름" else sds,
            commute={"minutes": commute_min or None, "mode": commute.get("mode")},
            sources=draft.get("sources") or [], as_of=draft.get("as_of"),
            confidence=draft.get("confidence"),
        )
    except ValidationError as e:
        st.error(f"입력값을 확인하세요: {e}")
        return None
