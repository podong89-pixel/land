"""좌표 검증 및 지오코딩 폴백 (PRD 7절)."""
from __future__ import annotations

from core import config
from core.models import PropertyInfo

KOREA_LAT = (33.0, 39.0)
KOREA_LNG = (124.0, 132.0)
SEOUL_CENTER = (37.5665, 126.9780)


def is_in_korea(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    return KOREA_LAT[0] <= lat <= KOREA_LAT[1] and KOREA_LNG[0] <= lng <= KOREA_LNG[1]


def geocode(address: str) -> tuple[float, float] | None:
    """주소를 좌표로 변환한다 (Nominatim). 실패하면 None."""
    if not address or config.MOCK_AI:
        return None
    try:
        from geopy.geocoders import Nominatim

        loc = Nominatim(user_agent="imjang-note-app", timeout=10).geocode(
            address, country_codes="kr", language="ko"
        )
    except Exception:
        return None
    if loc and is_in_korea(loc.latitude, loc.longitude):
        return loc.latitude, loc.longitude
    return None


def ensure_coords(info: PropertyInfo) -> tuple[PropertyInfo, str | None]:
    """좌표가 없거나 한국 범위 밖이면 주소→단지명 순으로 지오코딩한다.

    반환: (보정된 정보, 사용자에게 보여줄 안내 메시지 또는 None)
    """
    if is_in_korea(info.lat, info.lng):
        return info, None
    for query in (info.address, f"{info.region or ''} {info.name}".strip()):
        coords = geocode(query or "")
        if coords:
            fixed = info.model_copy(update={"lat": coords[0], "lng": coords[1]})
            return fixed, "AI 좌표가 없거나 부정확해 주소 검색(Nominatim)으로 좌표를 보정했습니다."
    return info, "좌표를 찾지 못했습니다. 위도/경도를 직접 입력해야 지도에 표시됩니다."
