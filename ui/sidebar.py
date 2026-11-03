"""사이드바: 사용자 설정(예산·직장·면적·가중치), 설정은 DB에 저장되어 재시작 후에도 유지 (F1)."""
from __future__ import annotations

import streamlit as st

from core import config, db
from core.scoring import GROUPS, normalize_weights
from core.seed import seed_samples
from ui.common import get_settings, save_settings
from ui.styles import format_krw

MAN = 10_000  # 만원


def _won_input(label: str, value_won: int | None, key: str, step: int = 1000) -> int:
    v = st.number_input(f"{label} (만원)", min_value=0, step=step,
                        value=int((value_won or 0) // MAN), key=key)
    return int(v) * MAN


def render() -> dict:
    """설정을 렌더링하고 현재 설정 dict를 반환한다."""
    settings = get_settings()
    new = {**settings, "budget": dict(settings["budget"]), "weights": dict(settings["weights"])}

    with st.sidebar:
        st.header("내 기준")
        st.caption("예산과 가중치를 바꾸면 모든 점수와 순위가 바로 다시 계산됩니다.")
        if config.MOCK_AI:
            st.info("MOCK AI 모드 (IMJANG_MOCK_AI=1)", icon="🧪")
        elif config.has_api_key():
            st.success(f"AI 연결됨 · {config.OPENAI_MODEL}", icon="🤖")
        else:
            st.warning("OPENAI_API_KEY가 없어 AI 조회를 쓸 수 없습니다. 수동 등록은 가능합니다.")

        with st.expander("💰 예산", expanded=False):
            b = new["budget"]
            b["매매"] = _won_input("매매가 상한", b.get("매매"), "set_budget_sale", 5000)
            b["전세"] = _won_input("전세 보증금 상한", b.get("전세"), "set_budget_jeonse", 1000)
            b["월세_deposit"] = _won_input("월세 보증금 상한", b.get("월세_deposit"), "set_budget_md", 500)
            b["월세_monthly"] = _won_input("월세 상한", b.get("월세_monthly"), "set_budget_mm", 10)
            st.caption(f"매매 {format_krw(b['매매'])} · 전세 {format_krw(b['전세'])} · "
                       f"월세 {format_krw(b['월세_deposit'])}/{format_krw(b['월세_monthly'])}")

        with st.expander("🏢 직장 · 희망 면적", expanded=False):
            new["work_address"] = st.text_input(
                "직장 주소", value=settings.get("work_address", ""), key="set_work",
                placeholder="예: 서울 중구 세종대로 110",
                help="AI가 통근시간을 추정할 때 사용합니다.")
            new["desired_area"] = st.number_input(
                "희망 전용면적 (㎡)", min_value=10.0, max_value=300.0, step=1.0,
                value=float(settings.get("desired_area") or 84.0), key="set_area")
            st.caption(f"≈ {new['desired_area'] / 3.3058:.1f}평")

        st.subheader("⚖️ 가중치")
        for g, (label, _) in GROUPS.items():
            new["weights"][g] = st.slider(label, 0, 100, int(settings["weights"].get(g, 0)),
                                          step=5, key=f"set_w_{g}")
        norm = normalize_weights(new["weights"])
        st.caption("정규화 비중: " + " · ".join(
            f"{GROUPS[g][0]} {norm[g] * 100:.0f}%" for g in GROUPS))
        if sum(new["weights"].values()) == 0:
            st.caption("⚠️ 모두 0이면 균등 분배됩니다.")

        if new != settings:
            save_settings(new)

        st.divider()
        count = db.count_properties()
        st.caption(f"저장된 매물: {count}건")
        if count == 0 and st.button("샘플 매물 3건 넣기", width="stretch"):
            added = seed_samples()
            st.toast(f"샘플 매물 {added}건을 추가했습니다.")
            st.rerun()
    return new
