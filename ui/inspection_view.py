"""탭 2: 임장 기록 — 장/단점 체크리스트, 현장 평가 1~5점, 임장일, 비고 (F4-4~F4-7)."""
from __future__ import annotations

from datetime import date

import streamlit as st

from core import db
from core.config import DEFAULT_CONS, DEFAULT_PROS, INSPECTION_FIELDS
from ui.common import save_settings, select, selected_id
from ui.styles import empty_state

RATING_HELP = {
    "sunlight": "1점 어두움, 5점 매우 밝음",
    "water_pressure": "1점 약함, 5점 매우 셈",
    "noise": "1점 매우 시끄러움, 5점 매우 조용함",
    "neighborhood": "1점 별로, 5점 아주 좋음",
    "first_impression": "1점 별로, 5점 아주 좋음",
}


def render(settings: dict) -> None:
    props = db.list_properties()
    if not props:
        empty_state("기록할 매물이 없습니다",
                    "'지도 & 관심매물' 탭에서 매물을 먼저 등록하면, 임장 후 느낀 점을 여기에 남길 수 있습니다.")
        return

    ids = [p["id"] for p in props]
    names = {p["id"]: f"{p['name']} · {p['deal_type']}" for p in props}
    current = selected_id() if selected_id() in ids else ids[0]
    pid = st.selectbox("임장 기록할 매물", ids, index=ids.index(current),
                       format_func=lambda i: names[i], key=f"ins_pick_{current}")
    if pid != selected_id():
        select(pid)

    ins = db.get_inspection(pid) or {}
    st.caption("✓ 임장 기록 있음, 마지막 저장 " + ins["updated_at"].replace("T", " ")[:16]
               if ins else "아직 임장 기록이 없습니다. 저장하기 전까지는 자동 항목만으로 잠정 점수를 냅니다.")

    _custom_items(settings)

    pros_opts = DEFAULT_PROS + [x for x in settings.get("custom_pros", []) if x not in DEFAULT_PROS]
    cons_opts = DEFAULT_CONS + [x for x in settings.get("custom_cons", []) if x not in DEFAULT_CONS]

    with st.form(f"inspection_form_{pid}"):
        visited = st.date_input(
            "임장일", value=date.fromisoformat(ins["visited_on"]) if ins.get("visited_on") else None,
            max_value=date.today(), format="YYYY-MM-DD", help="비워 두면 임장일 없이 저장됩니다.")

        c1, c2 = st.columns(2)
        with c1:
            pros = st.pills("👍 장점", pros_opts, selection_mode="multi",
                            default=[x for x in ins.get("pros", []) if x in pros_opts],
                            key=f"pros_{pid}")
        with c2:
            cons = st.pills("👎 단점", cons_opts, selection_mode="multi",
                            default=[x for x in ins.get("cons", []) if x in cons_opts],
                            key=f"cons_{pid}")

        st.markdown("**현장 평가** · 별을 눌러 1~5점, 다시 누르면 미입력")
        ratings = {}
        g1, g2 = st.columns(2, gap="large")
        for i, (field, label) in enumerate(INSPECTION_FIELDS.items()):
            cur = ins.get(field)
            ratings[field] = (g1 if i % 2 == 0 else g2).segmented_control(
                label, [1, 2, 3, 4, 5], format_func=lambda n: "★" * n,
                default=cur if cur in (1, 2, 3, 4, 5) else None,
                help=RATING_HELP[field], key=f"{field}_{pid}")

        memo = st.text_area("비고 (자유 의견)", value=ins.get("memo") or "", height=140,
                            placeholder="예: 남향이라 오후까지 밝음. 단지 앞 버스정류장 가까움. 엘리베이터 대기 김.",
                            max_chars=5000, key=f"memo_{pid}")
        submitted = st.form_submit_button("임장 기록 저장", type="primary", icon=":material/save:")

    if submitted:
        db.upsert_inspection(pid, {
            "visited_on": visited.isoformat() if visited else None,
            **{f: (None if v is None else int(v)) for f, v in ratings.items()},
            "pros": list(pros or []), "cons": list(cons or []),
            "memo": memo.strip() or None,
        })
        st.toast("임장 기록을 저장했습니다.", icon="💾")
        st.rerun()


def _custom_items(settings: dict) -> None:
    with st.expander("➕ 체크리스트 항목 추가"):
        c1, c2, c3 = st.columns([3, 1.2, 1], vertical_alignment="bottom")
        text = c1.text_input("항목명", key="custom_item_text", placeholder="예: 층간소음 걱정")
        kind = c2.radio("구분", ["장점", "단점"], horizontal=True, key="custom_item_kind")
        if c3.button("추가", width="stretch"):
            item = text.strip()
            key = "custom_pros" if kind == "장점" else "custom_cons"
            if item and item not in settings.get(key, []):
                settings[key] = [*settings.get(key, []), item]
                save_settings(settings)
                st.toast(f"{kind} 항목 '{item}'을(를) 추가했습니다.")
                st.rerun()
        if settings.get("custom_pros") or settings.get("custom_cons"):
            st.caption(f"사용자 항목 — 장점: {', '.join(settings.get('custom_pros', [])) or '-'} / "
                       f"단점: {', '.join(settings.get('custom_cons', [])) or '-'}")
