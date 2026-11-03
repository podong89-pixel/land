"""탭 3: 거래유형별 종합 점수 순위 + 점수 구성 누적 막대 (F5)."""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db
from core.config import DEAL_TYPES
from core.scoring import GROUPS, ITEMS, ScoreResult, strengths_weaknesses
from ui.common import score_all
from ui.styles import chip, deal_badge, empty_state, format_price, score_ring

# 그룹별 계열 색 — 같은 그룹 항목은 같은 색 계열의 명도 차이 (거래유형 3색과 겹치지 않게)
ITEM_COLORS = {
    "budget": "#1F4E79",
    "station": "#0E7C86", "commute": "#5FB3B9",
    "area": "#6D5BD0", "age": "#A99CF0",
    "school": "#C2417A",
    "sunlight": "#B7791F", "water_pressure": "#D69E2E", "noise": "#E8B04B",
    "neighborhood": "#F0C66B", "first_impression": "#F6D88F", "checklist": "#FAE7B5",
}
MEDALS = {1: "🥇 1위", 2: "🥈 2위", 3: "🥉 3위"}


def render(settings: dict) -> None:
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    counts = {d: len(db.list_properties(d)) for d in DEAL_TYPES}
    deal = c1.segmented_control("어떤 거래로 이사하나요?", DEAL_TYPES, default="전세", key="rank_deal",
                                format_func=lambda d: f"{d} {counts[d]}")
    deal = deal or "전세"
    c2.caption("왼쪽 '가중치'를 움직이면 순위가 바로 바뀝니다.")

    props = db.list_properties(deal)
    if not props:
        empty_state(f"{deal} 매물이 없습니다",
                    f"'지도 & 관심매물' 탭에서 거래유형을 {deal}(으)로 골라 매물을 등록하면 여기서 비교할 수 있습니다.")
        return

    scores = score_all(props, settings)
    ranked = sorted(props, key=lambda p: (scores[p["id"]].total is None,
                                          -(scores[p["id"]].total or 0)))

    _podium(ranked[:3], scores)

    st.markdown("#### 왜 이 점수일까요")
    st.caption("막대 전체 길이가 종합 점수이고, 각 조각은 항목 점수에 비중을 곱한 값입니다. "
               "조각에 마우스를 올리면 계산식이 보입니다.")
    _contribution_chart(ranked, scores)

    with st.expander(f"전체 순위표 ({len(ranked)}곳)"):
        rows = []
        for i, p in enumerate(ranked, 1):
            sr = scores[p["id"]]
            row = {"순위": i, "매물": p["name"], "금액": format_price(p), "종합": sr.total,
                   "상태": "잠정" if sr.provisional else "임장 완료"}
            for k, (label, kind, _) in ITEMS.items():
                v = sr.item_scores[k]
                row[label] = None if v is None else round(v)
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "종합": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f")})
        st.caption("항목 점수는 0~100점이며, 빈 칸은 데이터가 없어 계산에서 빠진 항목입니다. "
                   "채광부터 현장 체크까지는 임장 기록에서 직접 입력한 값입니다.")


def _podium(top: list[dict], scores: dict[int, ScoreResult]) -> None:
    cols = st.columns(3)
    for i, (col, p) in enumerate(zip(cols, top), 1):
        sr = scores[p["id"]]
        strong, weak = strengths_weaknesses(sr) if sr.total is not None else ([], [])
        chips = "".join(chip(s, "good") for s in strong) + "".join(chip(w, "bad") for w in weak)
        if sr.provisional:
            chips += chip("잠정 · 임장 전", "temp")
        with col.container(border=True, key=f"podium_{i}"):
            st.markdown(
                f"""<div class='im-podium'>
                  <div class='rank'>{MEDALS[i]}</div>
                  <div class='row'>{score_ring(sr.total, sr.provisional, 64 if i == 1 else 56)}
                    <div><div class='name'>{escape(p['name'])}</div>
                    <div class='price'>{deal_badge(p['deal_type'])} {escape(format_price(p))}</div></div>
                  </div>
                  <div class='chips'>{chips or "<span class='im-chip temp'>비교할 항목이 부족합니다</span>"}</div>
                </div>""",
                unsafe_allow_html=True)


def _contribution_chart(ranked: list[dict], scores: dict) -> None:
    names = [f"{i}. {p['name']}" for i, p in enumerate(ranked, 1)]
    fig = go.Figure()
    for k, (label, kind, group) in ITEMS.items():
        xs, custom = [], []
        for p in ranked:
            sr = scores[p["id"]]
            xs.append(sr.contributions[k])
            raw = sr.item_scores[k]
            custom.append([label, "자동" if kind == "auto" else "직접", GROUPS[group][0],
                           "-" if raw is None else f"{raw:.0f}",
                           f"{sr.item_weights[k] * 100:.1f}"])
        if not any(xs):
            continue
        fig.add_trace(go.Bar(
            y=names, x=xs, name=label, orientation="h",
            marker=dict(color=ITEM_COLORS[k], line=dict(color="#FFFFFF", width=1)),
            customdata=custom,
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[2]} (%{customdata[1]} 입력)<br>"
                          "%{customdata[3]}점 × 비중 %{customdata[4]}% = <b>%{x:.1f}점</b><extra></extra>",
        ))
    for name, p in zip(names, ranked):
        total = scores[p["id"]].total
        if total is not None:
            fig.add_annotation(x=total, y=name, text=f"<b>{total:.1f}</b>", showarrow=False,
                               xanchor="left", xshift=6, font=dict(size=14, color="#1B2430"))
    fig.update_layout(
        barmode="stack", bargap=0.35, height=max(260, 64 * len(ranked) + 130),
        font=dict(family="Pretendard Variable, Pretendard, Malgun Gothic, sans-serif",
                  color="#1B2430"),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        xaxis=dict(range=[0, 108], title=None, gridcolor="#E3E7ED", zeroline=False,
                   tickvals=[0, 20, 40, 60, 80, 100]),
        yaxis=dict(autorange="reversed", title=None),
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=12), traceorder="normal"),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#1F4E79", font=dict(color="#1B2430")),
        margin=dict(l=8, r=8, t=8, b=8),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
