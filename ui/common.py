"""UI 공용: 사용자 설정 로딩/저장, 선택 상태, 점수 일괄 계산, AI 조회 캐시."""
from __future__ import annotations

import copy
from typing import Any

import streamlit as st

from core import ai_client, db
from core.scoring import DEFAULT_WEIGHTS, ScoreResult, compute_score

SETTINGS_KEY = "user_settings"
DEFAULT_SETTINGS: dict[str, Any] = {
    "budget": {"매매": 1_000_000_000, "전세": 500_000_000,
               "월세_deposit": 50_000_000, "월세_monthly": 1_500_000},
    "work_address": "",
    "desired_area": 84.0,
    "weights": dict(DEFAULT_WEIGHTS),
    "custom_pros": [],
    "custom_cons": [],
}


def get_settings() -> dict[str, Any]:
    stored = db.get_setting(SETTINGS_KEY, {}) or {}
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for k, v in stored.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def save_settings(settings: dict[str, Any]) -> None:
    db.set_setting(SETTINGS_KEY, settings)


# ---------- 선택 상태 (지도 클릭 · 리스트 · 임장 탭 공유) ----------

def selected_id() -> int | None:
    return st.session_state.get("selected_id")


def select(property_id: int | None) -> None:
    st.session_state["selected_id"] = property_id


# ---------- 점수 ----------

def score_all(props: list[dict], settings: dict[str, Any]) -> dict[int, ScoreResult]:
    return {p["id"]: compute_score(p, db.get_inspection(p["id"]), settings) for p in props}


# ---------- AI 조회 (24h 캐시, 예외는 캐시되지 않음) ----------

@st.cache_data(ttl=86_400, show_spinner=False)
def cached_lookup(region: str, apt_name: str, deal_type: str, work_address: str) -> dict:
    return ai_client.lookup_property(region, apt_name, deal_type, work_address or None).model_dump()


def prop_to_info_dict(prop: dict[str, Any]) -> dict[str, Any]:
    """DB 행(dict)을 PropertyInfo 형태의 dict로 변환 (수정 폼 초기값용)."""
    return {
        "name": prop["name"], "address": prop.get("address"), "region": prop.get("region"),
        "lat": prop.get("lat"), "lng": prop.get("lng"), "deal_type": prop["deal_type"],
        "price": {"sale": prop.get("price_sale"), "deposit": prop.get("deposit"),
                  "monthly": prop.get("monthly")},
        "area_m2": prop.get("area_m2"), "built_year": prop.get("built_year"),
        "households": prop.get("households"), "subway": prop.get("subway") or [],
        "schools": prop.get("schools") or [],
        "school_district_score": prop.get("school_district_score"),
        "commute": {"minutes": prop.get("commute_min")},
        "sources": prop.get("sources") or [], "as_of": prop.get("as_of"),
        "confidence": prop.get("confidence"),
    }
