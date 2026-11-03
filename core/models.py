"""GPT 조회 결과(PRD 5절 F2) 스키마. 모르는 값은 None을 허용한다."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field

DealType = Literal["매매", "전세", "월세"]


def _to_int(v: Any) -> Any:
    """AI가 450.0이나 "650,000,000"처럼 줘도 정수로 받는다. 숫자로 못 바꾸는 문자열("모름")은 None."""
    if isinstance(v, str):
        v = v.replace(",", "").strip()
        if not v:
            return None
        try:
            v = float(v)
        except ValueError:
            return None
    if isinstance(v, float):
        return round(v)
    return v


def _to_score(v: Any) -> Any:
    v = _to_int(v)
    return None if v is None else max(1, min(5, int(v)))


Int = Annotated[Optional[int], BeforeValidator(_to_int)]
Score = Annotated[Optional[int], BeforeValidator(_to_score)]


class Price(BaseModel):
    sale: Int = None       # 매매가 (원)
    deposit: Int = None    # 보증금 (원)
    monthly: Int = None    # 월세 (원)
    unit: str = "KRW"
    basis: Optional[str] = None      # 산정 기준 설명
    range: Optional[str] = None      # 예: "6.2억~6.8억"


class Subway(BaseModel):
    station: str
    line: Optional[str] = None
    distance_m: Int = None
    walk_min: Int = None


class School(BaseModel):
    name: str
    level: Optional[str] = None      # 초/중/고
    distance_m: Int = None
    note: Optional[str] = None


class Commute(BaseModel):
    minutes: Int = None
    mode: Optional[str] = None


class PropertyInfo(BaseModel):
    name: str
    address: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    deal_type: DealType
    price: Price = Field(default_factory=Price)
    area_m2: Optional[float] = None
    built_year: Int = None
    households: Int = None
    subway: list[Subway] = Field(default_factory=list)
    schools: list[School] = Field(default_factory=list)
    school_district_score: Score = None
    commute: Commute = Field(default_factory=Commute)
    sources: list[str] = Field(default_factory=list)
    as_of: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None

