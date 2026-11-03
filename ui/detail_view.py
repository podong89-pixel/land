"""선택 매물 상세 (F4-3) + 항목별 점수(F5-1) + 재조회/수정/삭제 (F2-6)."""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from core import db, geo
from core.ai_client import AIError
from core.models import PropertyInfo
from core.scoring import GROUPS, ITEMS, ScoreResult, strengths_weaknesses
from ui.common import cached_lookup, prop_to_info_dict, select
from ui.property_form import render_form
from ui.styles import chip, deal_badge, format_distance, format_price, score_ring

CONFIDENCE_KO = {"high": "높음", "medium": "보통", "low": "낮음"}


def render(property_id: int | None, settings: dict, result: ScoreResult | None) -> None:
    prop = db.get_property(property_id) if property_id is not None else None
    if not prop:
        st.caption("지도에서 마커를 누르거나 목록에서 '보기'를 누르면 상세 정보가 여기에 나옵니다.")
        return

    total = result.total if result else None
    provisional = result.provisional if result else False
    chips = ""
    if result and total is not None:
        strong, weak = strengths_weaknesses(result)
        chips = "".join(chip(f"강점 {s}", "good") for s in strong)
        chips += "".join(chip(f"약점 {w}", "bad") for w in weak)
        if provisional:
            chips += chip("잠정 점수 · 임장 기록 전", "temp")
    st.markdown(
        f"""<div class='im-detail-head'>{score_ring(total, provisional, 68)}
          <div><h3>{escape(prop['name'])} {deal_badge(prop['deal_type'])}</h3>
          <div class='addr'>{escape(prop.get('address') or prop.get('region') or '주소 정보 없음')}</div>
          <div>{chips}</div></div></div>""",
        unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("금액", format_price(prop))
    m2.metric("전용면적", f"{prop['area_m2']:.1f}㎡ · {prop['area_m2'] / 3.3058:.0f}평"
              if prop.get("area_m2") else "정보 없음")
    m3.metric("준공", f"{prop['built_year']}년" if prop.get("built_year") else "정보 없음")
    m4.metric("직장까지", f"{prop['commute_min']}분" if prop.get("commute_min") else "정보 없음",
              help="AI가 대중교통 기준으로 추정한 시간입니다. '정보 수정'에서 고칠 수 있습니다.")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("<div class='im-section'>🚇 가까운 지하철역</div>", unsafe_allow_html=True)
        items = "".join(
            f"<li><span class='k'>{escape(s['station'])}<small>{escape(s.get('line') or '')}</small></span>"
            f"<span class='v'>{format_distance(s.get('distance_m'), s.get('walk_min'))}</span></li>"
            for s in prop["subway"]) or "<li><span class='v'>정보 없음</span></li>"
        st.markdown(f"<ul class='im-list'>{items}</ul>", unsafe_allow_html=True)
    with c2:
        sds = prop.get("school_district_score")
        stars = ("★" * sds + "☆" * (5 - sds)) if sds else "학군 점수 없음"
        st.markdown(f"<div class='im-section'>🏫 근처 학교 <span style='color:#B7791F'>{stars}</span></div>",
                    unsafe_allow_html=True)
        items = "".join(_school_li(s) for s in prop["schools"]) \
            or "<li><span class='v'>정보 없음</span></li>"
        st.markdown(f"<ul class='im-list'>{items}</ul>", unsafe_allow_html=True)

    if result:
        _score_table(result)

    sources = ", ".join(escape(s) for s in prop["sources"][:5]) or "-"
    st.markdown(
        f"<div class='im-note'>AI가 찾은 정보입니다. 기준 {escape(prop.get('as_of') or '-')}, "
        f"신뢰도 {CONFIDENCE_KO.get(prop.get('confidence'), '-')}. "
        f"실제와 다를 수 있으니 계약 전에 실거래가와 중개사를 통해 꼭 확인하세요.<br>"
        f"출처: {sources}</div>",
        unsafe_allow_html=True)

    _actions(prop, settings)


def _school_li(s: dict) -> str:
    note = f"<small>{escape(s['note'])}</small>" if s.get("note") else ""
    return (f"<li><span class='k'>{escape(s['name'])}{note}</span>"
            f"<span class='v'>{format_distance(s.get('distance_m'))}</span></li>")


def _score_table(result: ScoreResult) -> None:
    with st.expander("항목별 점수 보기"):
        rows = []
        for k, (label, kind, group) in ITEMS.items():
            sc = result.item_scores[k]
            rows.append({
                "항목": label,
                "입력": "자동" if kind == "auto" else "직접",
                "그룹": GROUPS[group][0],
                "점수": None if sc is None else round(sc, 1),
                "비중": result.item_weights[k] * 100,
                "기여": round(result.contributions[k], 1),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "점수": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "비중": st.column_config.NumberColumn(format="%.1f%%"),
        })
        st.caption("빈 점수는 데이터가 없다는 뜻이고, 그 비중은 같은 그룹의 다른 항목에 나눠집니다.")


def _actions(prop: dict, settings: dict) -> None:
    a1, a2, a3 = st.columns(3)
    if a1.button("AI로 다시 조회", icon=":material/refresh:", key=f"refresh_{prop['id']}",
                 width="stretch"):
        args = (prop.get("region") or "", prop["name"], prop["deal_type"],
                settings.get("work_address", ""))
        cached_lookup.clear(*args)  # 이 매물의 캐시만 비움 (다른 매물 캐시는 유지)
        with st.spinner("최신 시세와 주변 정보를 다시 찾는 중입니다…"):
            try:
                data = cached_lookup(*args)
            except AIError as e:
                st.error(str(e))
                return
        info, msg = geo.ensure_coords(PropertyInfo(**data))
        db.update_property(prop["id"], info, raw=data)
        st.toast("정보를 새로 조회했습니다." + (f" {msg}" if msg else ""), icon="🔄")
        st.rerun()

    if a2.button("정보 수정", icon=":material/edit:", key=f"edit_toggle_{prop['id']}",
                 width="stretch"):
        st.session_state["editing"] = None if st.session_state.get("editing") == prop["id"] else prop["id"]
    if a3.button("삭제", icon=":material/delete:", key=f"del_{prop['id']}", width="stretch"):
        st.session_state["confirm_delete"] = prop["id"]

    if st.session_state.get("confirm_delete") == prop["id"]:
        st.warning(f"'{prop['name']}'과(와) 임장 기록을 삭제합니다. 되돌릴 수 없습니다.")
        d1, d2 = st.columns(2)
        if d1.button("삭제하기", key=f"del_yes_{prop['id']}", type="primary"):
            db.delete_property(prop["id"])
            st.session_state.pop("confirm_delete", None)
            select(None)
            st.toast("삭제했습니다.")
            st.rerun()
        if d2.button("취소", key=f"del_no_{prop['id']}"):
            st.session_state.pop("confirm_delete", None)
            st.rerun()

    if st.session_state.get("editing") == prop["id"]:
        info = render_form(prop_to_info_dict(prop), f"edit_{prop['id']}", "수정 내용 저장")
        if info is not None:
            db.update_property(prop["id"], info)
            st.session_state.pop("editing", None)
            st.toast("수정 내용을 저장했습니다.", icon="💾")
            st.rerun()
