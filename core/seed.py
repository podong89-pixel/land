"""DB가 비었을 때 넣는 샘플 매물 3건 (전세/매매/월세). 시세는 실제가 아닌 예시값."""
from __future__ import annotations

from core import db
from core.models import PropertyInfo

SAMPLE_NOTE = "샘플 데이터 (실제 시세 아님)"

SAMPLES: list[dict] = [
    {
        "name": "마포래미안푸르지오",
        "address": "서울특별시 마포구 아현동 777",
        "region": "서울 마포구 아현동",
        "lat": 37.5537, "lng": 126.9566,
        "deal_type": "전세",
        "price": {"deposit": 800_000_000, "basis": "예시값", "range": "7.5억~8.5억"},
        "area_m2": 84.9, "built_year": 2014, "households": 3885,
        "subway": [{"station": "아현역", "line": "2호선", "distance_m": 350, "walk_min": 5}],
        "schools": [{"name": "아현초등학교", "level": "초", "distance_m": 400}],
        "school_district_score": 3,
        "commute": {"minutes": 30, "mode": "대중교통"},
    },
    {
        "name": "래미안대치팰리스",
        "address": "서울특별시 강남구 대치동 1027",
        "region": "서울 강남구 대치동",
        "lat": 37.4946, "lng": 127.0633,
        "deal_type": "매매",
        "price": {"sale": 3_500_000_000, "basis": "예시값", "range": "33억~37억"},
        "area_m2": 84.9, "built_year": 2015, "households": 1608,
        "subway": [{"station": "대치역", "line": "3호선", "distance_m": 600, "walk_min": 9}],
        "schools": [{"name": "대곡초등학교", "level": "초", "distance_m": 250}],
        "school_district_score": 5,
        "commute": {"minutes": 40, "mode": "대중교통"},
    },
    {
        "name": "헬리오시티",
        "address": "서울특별시 송파구 가락동 913",
        "region": "서울 송파구 가락동",
        "lat": 37.4970, "lng": 127.1077,
        "deal_type": "월세",
        "price": {"deposit": 100_000_000, "monthly": 2_500_000, "basis": "예시값"},
        "area_m2": 59.9, "built_year": 2018, "households": 9510,
        "subway": [{"station": "송파역", "line": "8호선", "distance_m": 300, "walk_min": 4}],
        "schools": [{"name": "해누리초등학교", "level": "초", "distance_m": 350}],
        "school_district_score": 4,
        "commute": {"minutes": 45, "mode": "대중교통"},
    },
]


def seed_samples() -> int:
    """중복이 아닌 샘플만 추가하고 추가된 건수를 반환한다."""
    added = 0
    for s in SAMPLES:
        if db.find_duplicate(s["name"], s["deal_type"]):
            continue
        info = PropertyInfo(**s, sources=[SAMPLE_NOTE], as_of="샘플", confidence="low")
        db.add_property(info)
        added += 1
    return added
