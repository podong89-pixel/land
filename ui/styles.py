"""디자인 토큰, 커스텀 CSS, HTML 조각, 표시용 포맷터.

디자인 원칙: 남색 기본 + 거래유형 3색만 강조. 그림자 대신 얇은 선, 카드 왼쪽 색 띠 = 거래유형.
점수는 어디서나 같은 '점수 링'으로 표시한다.
"""
from __future__ import annotations

from html import escape

import streamlit as st

from core.config import DEAL_COLORS

INK = "#1B2430"
MUTED = "#5B6675"
LINE = "#E3E7ED"
SURFACE = "#F4F6F9"
NAVY = "#1F4E79"
DEAL_TINTS = {"매매": "#EAF1FE", "전세": "#E8F6EE", "월세": "#FDF0E7"}

CSS = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');

html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {{
  font-family: "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo",
               "Malgun Gothic", sans-serif !important;
}}
.material-icons, .material-symbols-rounded, [data-testid="stIconMaterial"] {{
  font-family: "Material Symbols Rounded" !important;
}}
.block-container, [data-testid="stMainBlockContainer"] {{ padding-top: 4.2rem !important; max-width: 1360px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.02em; color: {INK}; }}
[data-testid="stMetricValue"] {{ font-size: 1.35rem; font-weight: 700;
  font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.82rem; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
[data-testid="stSidebar"] h2 {{ font-size: 1.25rem; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 0.25rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ padding: 0.55rem 1rem; }}
.stTabs [data-baseweb="tab"] p {{ font-size: 0.98rem; font-weight: 600; }}
[data-testid="stButtonGroup"] > div {{ flex-wrap: wrap !important; row-gap: 0.4rem; }}
:focus-visible {{ outline: 2px solid {NAVY} !important; outline-offset: 2px; }}

/* ---------- 앱 헤더 ---------- */
.im-header {{ display:flex; align-items:flex-end; justify-content:space-between;
  gap:1rem; flex-wrap:wrap; padding-bottom:0.9rem; margin-bottom:0.4rem;
  border-bottom: 2px solid {INK}; }}
.im-title {{ font-size:2rem; font-weight:800; letter-spacing:-0.04em; color:{INK};
  line-height:1; margin:0; }}
.im-sub {{ color:{MUTED}; font-size:0.92rem; margin-top:0.35rem; }}
.im-stats {{ display:flex; gap:1.4rem; flex-wrap:wrap; }}
.im-stat b {{ display:block; font-size:1.3rem; font-weight:800; color:{INK};
  font-variant-numeric: tabular-nums; line-height:1.1; }}
.im-stat span {{ color:{MUTED}; font-size:0.78rem; }}
.im-stat.best b {{ font-size:1.02rem; max-width:11rem; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; padding-top:0.2rem; }}
.im-stat.best .im-deal {{ font-size:0.68rem; padding:0 6px; vertical-align:1px; }}

/* ---------- 거래유형 배지 / 칩 ---------- */
.im-deal {{ display:inline-block; padding:1px 8px; border-radius:4px; font-size:0.74rem;
  font-weight:700; color:#fff; vertical-align:2px; }}
.im-chip {{ display:inline-block; padding:2px 9px; margin:2px 4px 2px 0; border-radius:999px;
  font-size:0.78rem; border:1px solid {LINE}; color:{INK}; background:#fff; }}
.im-chip.good {{ border-color:#B9D3EE; background:#EEF4FB; color:{NAVY}; }}
.im-chip.bad  {{ border-color:#F1CFC4; background:#FCF1EE; color:#9A3B1E; }}
.im-chip.temp {{ border-style:dashed; color:{MUTED}; }}

/* ---------- 점수 링 ---------- */
.im-ring {{ --p:0; --c:{NAVY}; position:relative; flex:none; border-radius:50%;
  background: conic-gradient(var(--c) calc(var(--p) * 1%), {LINE} 0); display:grid;
  place-items:center; }}
.im-ring::before {{ content:""; position:absolute; inset:5px; border-radius:50%; background:#fff; }}
.im-ring.temp {{ --c:#6F8FB3; }}
.im-ring b {{ position:relative; font-weight:800; color:{INK};
  font-variant-numeric: tabular-nums; letter-spacing:-0.03em; }}
.im-ring.empty {{ background:{LINE}; }}

/* ---------- 매물 카드 (리스트) ---------- */
.im-card {{ display:flex; align-items:center; gap:0.75rem; }}
.im-card .meta {{ min-width:0; flex:1; }}
.im-card .name {{ font-weight:700; color:{INK}; font-size:0.98rem; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.im-card .line {{ color:{MUTED}; font-size:0.8rem; margin-top:2px; }}
.im-card .price {{ color:{INK}; font-size:0.86rem; font-weight:600; margin-top:3px;
  font-variant-numeric: tabular-nums; }}
.im-done {{ color:#15803D; font-size:0.74rem; font-weight:700; margin-left:4px; }}
[class*="st-key-card_"] {{ border-left-width:4px !important; }}
{''.join(f'[class*="st-key-card_{k}_"] {{ border-left-color:{c} !important; }}' for k, c in
         (('mae', DEAL_COLORS['매매']), ('jeon', DEAL_COLORS['전세']), ('wol', DEAL_COLORS['월세'])))}
[class*="st-key-card_"][class*="_sel_"] {{ background:{SURFACE}; border-color:{NAVY} !important;
  box-shadow: inset 0 0 0 1px {NAVY}; }}

/* ---------- 상세 ---------- */
.im-detail-head {{ display:flex; align-items:center; gap:1rem; margin:0.2rem 0 0.6rem; }}
.im-detail-head h3 {{ margin:0; padding:0; font-size:1.45rem; }}
.im-detail-head .addr {{ color:{MUTED}; font-size:0.86rem; margin-top:3px; }}
.im-list {{ list-style:none; padding:0; margin:0.2rem 0 0; }}
.im-list li {{ padding:0.42rem 0; border-bottom:1px dashed {LINE}; font-size:0.9rem;
  display:flex; justify-content:space-between; gap:0.6rem; }}
.im-list li span.k {{ font-weight:600; color:{INK}; }}
.im-list li span.v {{ color:{MUTED}; text-align:right; font-variant-numeric: tabular-nums; }}
.im-list li small {{ display:block; color:{MUTED}; font-weight:400; }}
.im-section {{ font-weight:700; font-size:0.92rem; color:{INK}; margin:0.4rem 0 0.1rem; }}
.im-note {{ color:{MUTED}; font-size:0.78rem; line-height:1.5; margin-top:0.6rem;
  padding:0.6rem 0.8rem; background:{SURFACE}; border-radius:6px; }}

/* ---------- 순위 카드 ---------- */
.im-podium {{ padding:0.2rem 0; }}
.im-podium .rank {{ font-size:0.82rem; font-weight:700; color:{MUTED}; }}
.im-podium .row {{ display:flex; align-items:center; gap:0.9rem; margin-top:0.35rem; }}
.im-podium .name {{ font-size:1.08rem; font-weight:800; color:{INK}; line-height:1.25; }}
.im-podium .price {{ font-size:0.85rem; color:{MUTED}; margin-top:2px;
  font-variant-numeric: tabular-nums; }}
.im-podium .chips {{ margin-top:0.6rem; }}
.st-key-podium_1 {{ border-color:{NAVY} !important; border-width:2px !important; }}

/* ---------- 빈 상태 ---------- */
.im-empty {{ text-align:center; padding:2.2rem 1rem; border:1px dashed #C9D1DB;
  border-radius:10px; color:{MUTED}; background:#fff; }}
.im-empty b {{ display:block; color:{INK}; font-size:1.05rem; margin-bottom:0.3rem; }}

@media (max-width: 640px) {{
  .block-container, [data-testid="stMainBlockContainer"] {{ padding-left:1rem !important; padding-right:1rem !important; padding-top:3.4rem !important; }}
  .im-title {{ font-size:1.6rem; }}
  .im-stats {{ gap:1rem; }}
  .im-detail-head h3 {{ font-size:1.2rem; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; }} }}
</style>
"""

DEAL_KEYS = {"매매": "mae", "전세": "jeon", "월세": "wol"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ---------- 포맷터 ----------

def format_krw(won: int | float | None) -> str:
    """원 단위 금액을 '6억 5,000만원' 형식으로 변환한다."""
    if won is None:
        return "정보 없음"
    won = int(won)
    eok, rest = divmod(won, 100_000_000)
    man = rest // 10_000
    if eok and man:
        return f"{eok}억 {man:,}만원"
    if eok:
        return f"{eok}억원"
    return f"{man:,}만원"


def format_price(prop: dict) -> str:
    deal = prop.get("deal_type")
    if deal == "매매":
        return format_krw(prop.get("price_sale"))
    if deal == "전세":
        return format_krw(prop.get("deposit"))
    return f"보증금 {format_krw(prop.get('deposit'))} / 월 {format_krw(prop.get('monthly'))}"


def format_distance(distance_m: int | None, walk_min: int | None = None) -> str:
    """'450m (도보 7분)' 형식. 도보 분이 없으면 80m/분으로 추정."""
    if distance_m is None:
        return "거리 정보 없음"
    walk = walk_min if walk_min is not None else max(1, round(distance_m / 80))
    dist = f"{distance_m / 1000:.1f}km" if distance_m >= 1000 else f"{int(distance_m)}m"
    return f"{dist} (도보 {walk}분)"


# ---------- HTML 조각 ----------

def deal_badge(deal_type: str) -> str:
    color = DEAL_COLORS.get(deal_type, MUTED)
    return f"<span class='im-deal' style='background:{color}'>{escape(deal_type)}</span>"


def score_ring(total: float | None, provisional: bool = False, size: int = 52) -> str:
    """점수만큼 채워지는 원형 링. 잠정 점수는 옅은 색."""
    font = max(12, int(size * 0.32))
    if total is None:
        return (f"<div class='im-ring empty' style='width:{size}px;height:{size}px' "
                f"title='점수 없음'><b style='font-size:{font}px;color:{MUTED}'>–</b></div>")
    title = "잠정 점수 (임장 전, 자동 항목만)" if provisional else "종합 점수"
    return (f"<div class='im-ring{' temp' if provisional else ''}' "
            f"style='--p:{total:.1f};width:{size}px;height:{size}px' title='{title}' "
            f"role='img' aria-label='{title} {total:.1f}점'>"
            f"<b style='font-size:{font}px'>{total:.0f}</b></div>")


def chip(text: str, kind: str = "") -> str:
    return f"<span class='im-chip {kind}'>{escape(text)}</span>"


def empty_state(title: str, body: str) -> None:
    st.markdown(f"<div class='im-empty'><b>{escape(title)}</b>{escape(body)}</div>",
                unsafe_allow_html=True)
