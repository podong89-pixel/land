"""환경변수 로딩과 앱 전역 상수."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY") or None
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL") or "gpt-6-astra"

# 테스트에서는 IMJANG_DB_PATH로 별도 DB를 지정한다.
DB_PATH: Path = Path(os.getenv("IMJANG_DB_PATH") or BASE_DIR / "data" / "imjang.db")
# E2E 테스트용: 실제 API 대신 고정 응답 사용
MOCK_AI: bool = os.getenv("IMJANG_MOCK_AI") == "1"

DEAL_TYPES = ("매매", "전세", "월세")
DEAL_COLORS = {"매매": "#2563EB", "전세": "#16A34A", "월세": "#EA580C"}

DEFAULT_PROS = [
    "역세권", "초품아", "대단지", "남향", "신축급", "주차 여유",
    "공원/산책로 인접", "학원가 인접", "대형마트 인접",
]
DEFAULT_CONS = [
    "언덕/경사", "도로 소음", "주차 부족", "구축 노후", "저층/조망 없음",
    "유흥가 인접", "엘리베이터 부족", "누수 흔적",
]

# 현장 평가(직접 입력) 항목: DB 컬럼명 -> 표시명
INSPECTION_FIELDS = {
    "sunlight": "채광",
    "water_pressure": "수압",
    "noise": "소음",
    "neighborhood": "동네 분위기",
    "first_impression": "집 안 첫인상",
}


def has_api_key() -> bool:
    return bool(OPENAI_API_KEY)
