"""탭 1: 검색 바(F2) + 지도(F3) + 관심 매물 리스트/상세(F4)."""
from __future__ import annotations

from html import escape

import folium
import streamlit as st
from streamlit_folium import st_folium

from core import db, geo
from core.ai_client import AIError
from core.config import DEAL_TYPES
from core.models import PropertyInfo
from core.scoring import ScoreResult
from ui import detail_view
from ui.common import cached_lookup, score_all, select, selected_id
from ui.property_form import render_form
from ui.styles import DEAL_KEYS, deal_badge, empty_state, format_price, score_ring

# folium.Icon이 지원하는 색 이름으로 거래유형 색상 매핑 (매매=파랑, 전세=초록, 월세=주황)
MARKER_COLORS = {"매매": "blue", "전세": "green", "월세": "orange"}


def render(settings: dict) -> None:
    _search_bar(settings)
    _draft_preview()

    props = db.list_properties()
    if not props:
        empty_state("아직 관심 매물이 없습니다",
                    "위 검색창에 지역이나 아파트명을 입력해 첫 매물을 등록하세요. "
                    "둘러보기만 하려면 왼쪽 아래 '샘플 매물 3건 넣기'를 누르세요.")
        return
    scores = score_all(props, settings)
    if selected_id() not in {p["id"] for p in props}:
        select(props[0]["id"])

    col_map, col_side = st.columns([3, 2], gap="medium")
    with col_map:
        _map(props, scores)
    with col_side:
        _property_list(props, scores)
    st.divider()
    detail_view.render(selected_id(), settings, scores.get(selected_id()))


# ---------- 검색 · 등록 ----------

def _search_bar(settings: dict) -> None:
    with st.form("search_form", border=True):
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 1.3, 1.3], vertical_alignment="bottom")
        region = c1.text_input("지역", placeholder="예: 서울 마포구 아현동")
        apt = c2.text_input("아파트명", placeholder="예: 마포래미안푸르지오")
        deal = c3.selectbox("거래유형", DEAL_TYPES, index=1)
        do_ai = c4.form_submit_button("🔎 AI 조회", type="primary", width="stretch")
        do_manual = c5.form_submit_button("✍️ 직접 입력", width="stretch")

    if do_manual:
        _set_draft({"name": apt, "region": region, "deal_type": deal}, None)
    elif do_ai:
        if not (region.strip() or apt.strip()):
            st.warning("지역 또는 아파트명을 입력하세요.")
            return
        with st.spinner("AI가 최신 시세·지하철역·학군 정보를 찾고 있습니다… (20초 정도 걸립니다)"):
            try:
                data = cached_lookup(region.strip(), apt.strip(), deal,
                                     settings.get("work_address", ""))
            except AIError as e:
                st.error(str(e))
                st.info("아래 폼에 직접 입력해 등록할 수 있습니다.")
                _set_draft({"name": apt, "region": region, "deal_type": deal}, None)
                return
        info, geo_msg = geo.ensure_coords(PropertyInfo(**data))
        _set_draft(info.model_dump(), geo_msg)


def _set_draft(draft: dict, notice: str | None) -> None:
    st.session_state["draft"] = draft
    st.session_state["draft_notice"] = notice
    st.session_state["draft_nonce"] = st.session_state.get("draft_nonce", 0) + 1
    st.session_state.pop("dup_confirm", None)
    st.session_state.pop("pending_info", None)


def _draft_preview() -> None:
    draft = st.session_state.get("draft")
    if not draft:
        return
    with st.container(border=True):
        h1, h2 = st.columns([5, 1])
        h1.markdown("#### 📋 조회 결과 확인 · 수정 후 저장")
        if h2.button("취소", key="draft_cancel", width="stretch"):
            for k in ("draft", "pending_info", "dup_confirm", "draft_notice"):
                st.session_state.pop(k, None)
            st.rerun()
        if st.session_state.get("draft_notice"):
            st.info(st.session_state["draft_notice"])
        if draft.get("sources"):
            st.caption(f"출처: {', '.join(draft['sources'][:5])} · 기준: {draft.get('as_of') or '-'}"
                       f" · 신뢰도: {draft.get('confidence') or '-'}")
        st.caption("⚠️ AI 조회 정보는 실제와 다를 수 있습니다. 계약 전 실거래가·중개사 확인 필수.")

        info = render_form(draft, f"new_{st.session_state.get('draft_nonce', 0)}",
                           "⭐ 관심 매물에 저장")
        if info is not None:
            st.session_state["pending_info"] = info.model_dump()

    pending = st.session_state.get("pending_info")
    if not pending:
        return
    info = PropertyInfo(**pending)
    dup = db.find_duplicate(info.name, info.deal_type)
    if dup and not st.session_state.get("dup_confirm"):
        st.warning(f"'{info.name}' ({info.deal_type}) 매물이 이미 저장되어 있습니다.")
        b1, b2 = st.columns(2)
        if b1.button("그래도 추가 저장", key="dup_yes"):
            st.session_state["dup_confirm"] = True
            st.rerun()
        if b2.button("저장 취소", key="dup_no"):
            st.session_state.pop("pending_info", None)
            st.rerun()
        return
    if not geo.is_in_korea(info.lat, info.lng):
        info, _ = geo.ensure_coords(info)
    new_id = db.add_property(info, raw=draft)
    for k in ("draft", "pending_info", "dup_confirm", "draft_notice"):
        st.session_state.pop(k, None)
    select(new_id)
    st.toast(f"'{info.name}'을(를) 관심 매물에 저장했습니다.", icon="⭐")
    st.rerun()


# ---------- 지도 ----------

def _map(props: list[dict], scores: dict[int, ScoreResult]) -> None:
    located = [p for p in props if geo.is_in_korea(p.get("lat"), p.get("lng"))]
    # 비교가 목적이므로 항상 모든 매물이 보이게 맞추고, 선택 매물은 빨간 별 마커로만 구분한다.
    # (선택 매물로 확대하면 다른 마커가 화면 밖으로 나가 지도에서 바로 고를 수 없음)
    if located:
        center = (sum(p["lat"] for p in located) / len(located),
                  sum(p["lng"] for p in located) / len(located))
    else:
        center = geo.SEOUL_CENTER
    m = folium.Map(location=center, zoom_start=14 if len(located) == 1 else 11, tiles="OpenStreetMap")
    if len(located) > 1:
        m.fit_bounds([[min(p["lat"] for p in located), min(p["lng"] for p in located)],
                      [max(p["lat"] for p in located), max(p["lng"] for p in located)]],
                     padding=(40, 40))
    for p in located:
        r = scores.get(p["id"])
        score_txt = f"{r.total:.1f}점" if r and r.total is not None else "점수 없음"
        is_sel = p["id"] == selected_id()
        folium.Marker(
            (p["lat"], p["lng"]),
            # folium 툴팁은 HTML로 렌더링되므로 사용자/AI 입력은 반드시 escape (XSS 방지)
            tooltip=escape(f"{p['name']} · {p['deal_type']} {format_price(p)} · {score_txt}"),
            icon=folium.Icon(color="red" if is_sel else MARKER_COLORS[p["deal_type"]],
                             icon="star" if is_sel else "home", prefix="fa"),
        ).add_to(m)

    out = st_folium(m, height=480, width="100%", key="main_map",
                    returned_objects=["last_object_clicked"])
    click = (out or {}).get("last_object_clicked")
    # st_folium은 매 rerun마다 마지막 클릭을 다시 돌려주므로, 새 클릭일 때만 선택을 바꾼다.
    if click and click != st.session_state.get("last_map_click"):
        st.session_state["last_map_click"] = click
        hit = min(located, key=lambda p: (p["lat"] - click["lat"]) ** 2
                  + (p["lng"] - click["lng"]) ** 2, default=None)
        if hit and abs(hit["lat"] - click["lat"]) < 1e-4 and abs(hit["lng"] - click["lng"]) < 1e-4:
            if hit["id"] != selected_id():
                select(hit["id"])
                st.rerun()

    missing = len(props) - len(located)
    legend = " ".join(deal_badge(d) for d in DEAL_TYPES)
    legend += " <span class='im-deal' style='background:#D63E2A'>보는 중</span>"
    if missing:
        legend += f" <span class='im-chip temp'>좌표 없는 매물 {missing}건은 지도에 없음</span>"
    st.markdown(legend, unsafe_allow_html=True)


# ---------- 리스트 ----------

def _property_list(props: list[dict], scores: dict[int, ScoreResult]) -> None:
    sort = st.segmented_control("정렬", ["최근 등록", "점수 높은 순"], default="최근 등록",
                                key="list_sort", label_visibility="collapsed")
    if sort == "점수 높은 순":
        props = sorted(props, key=lambda p: -(scores[p["id"]].total or -1))
    with st.container(height=440, border=False):
        for p in props:
            r = scores.get(p["id"])
            visited = db.get_inspection(p["id"]) is not None
            is_sel = p["id"] == selected_id()
            card_key = f"card_{DEAL_KEYS[p['deal_type']]}_{'sel_' if is_sel else ''}{p['id']}"
            with st.container(border=True, key=card_key):
                c1, c2 = st.columns([5, 1.5], vertical_alignment="center")
                c1.markdown(
                    f"""<div class='im-card'>
                      {score_ring(r.total if r else None, r.provisional if r else False, 48)}
                      <div class='meta'>
                        <div class='name'>{escape(p['name'])}</div>
                        <div class='line'>{deal_badge(p['deal_type'])} {escape(p.get('region') or '')}
                          {"<span class='im-done'>✓ 임장 완료</span>" if visited else ''}</div>
                        <div class='price'>{escape(format_price(p))}</div>
                      </div></div>""",
                    unsafe_allow_html=True)
                c2.button("보는 중" if is_sel else "보기", key=f"sel_{p['id']}",
                          disabled=is_sel, width="stretch",
                          on_click=select, args=(p["id"],))
