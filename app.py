"""임장노트 Streamlit 진입점: `streamlit run app.py`"""
from html import escape

import streamlit as st

from core import db
from core.config import DEAL_TYPES
from ui import inspection_view, map_view, ranking_view, sidebar, styles
from ui.common import score_all

st.set_page_config(page_title="임장노트", page_icon="🏠", layout="wide")

db.init_db()
styles.inject_css()
settings = sidebar.render()


def header() -> None:
    props = db.list_properties()
    visited = sum(1 for p in props if db.get_inspection(p["id"]))
    scores = score_all(props, settings)
    # 예산 기준이 거래유형마다 달라 점수를 섞어 비교할 수 없으므로 거래유형별 1위를 따로 보여준다.
    best_html = ""
    for deal in DEAL_TYPES:
        cands = [p for p in props if p["deal_type"] == deal and scores[p["id"]].total is not None]
        if not cands:
            continue
        best = max(cands, key=lambda p: scores[p["id"]].total)
        best_html += (f"<div class='im-stat best' title='{escape(best['name'])}'>"
                      f"<b>{escape(best['name'])}</b>"
                      f"<span>{styles.deal_badge(deal)} 1위 · {scores[best['id']].total:.1f}점</span></div>")
    st.markdown(
        f"""<div class='im-header'>
          <div><div class='im-title'>임장노트</div>
               <div class='im-sub'>둘러본 집을 기록하고, 내 기준으로 점수를 매겨 이사 갈 곳을 고릅니다.</div></div>
          <div class='im-stats'>
            <div class='im-stat'><b>{len(props)}</b><span>관심 매물</span></div>
            <div class='im-stat'><b>{visited}</b><span>임장 완료</span></div>
            {best_html}
          </div></div>""",
        unsafe_allow_html=True)


header()
tab_map, tab_inspect, tab_rank = st.tabs(["🗺️ 지도 & 관심매물", "📝 임장 기록", "🏆 비교 & 순위"])
with tab_map:
    map_view.render(settings)
with tab_inspect:
    inspection_view.render(settings)
with tab_rank:
    ranking_view.render(settings)
