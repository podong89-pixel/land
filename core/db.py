"""SQLite 저장소 (PRD 8절): properties / inspections / settings."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from core import config
from core.models import PropertyInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    region TEXT,
    lat REAL,
    lng REAL,
    deal_type TEXT NOT NULL CHECK (deal_type IN ('매매','전세','월세')),
    price_sale INTEGER,
    deposit INTEGER,
    monthly INTEGER,
    area_m2 REAL,
    built_year INTEGER,
    households INTEGER,
    subway_json TEXT DEFAULT '[]',
    schools_json TEXT DEFAULT '[]',
    school_district_score INTEGER,
    commute_min INTEGER,
    ai_raw_json TEXT,
    sources_json TEXT DEFAULT '[]',
    as_of TEXT,
    confidence TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspections (
    property_id INTEGER PRIMARY KEY REFERENCES properties(id) ON DELETE CASCADE,
    visited_on TEXT,
    sunlight INTEGER,
    water_pressure INTEGER,
    noise INTEGER,
    neighborhood INTEGER,
    first_impression INTEGER,
    pros_json TEXT DEFAULT '[]',
    cons_json TEXT DEFAULT '[]',
    memo TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

INSPECTION_COLUMNS = (
    "visited_on", "sunlight", "water_pressure", "noise",
    "neighborhood", "first_impression", "memo",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------- properties ----------

def _row_to_property(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["subway"] = json.loads(d.pop("subway_json") or "[]")
    d["schools"] = json.loads(d.pop("schools_json") or "[]")
    d["sources"] = json.loads(d.pop("sources_json") or "[]")
    return d


def add_property(info: PropertyInfo, raw: dict | None = None) -> int:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO properties (
                name, address, region, lat, lng, deal_type,
                price_sale, deposit, monthly, area_m2, built_year, households,
                subway_json, schools_json, school_district_score, commute_min,
                ai_raw_json, sources_json, as_of, confidence, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                info.name, info.address, info.region, info.lat, info.lng, info.deal_type,
                info.price.sale, info.price.deposit, info.price.monthly,
                info.area_m2, info.built_year, info.households,
                json.dumps([s.model_dump() for s in info.subway], ensure_ascii=False),
                json.dumps([s.model_dump() for s in info.schools], ensure_ascii=False),
                info.school_district_score, info.commute.minutes,
                json.dumps(raw or info.model_dump(), ensure_ascii=False),
                json.dumps(info.sources, ensure_ascii=False),
                info.as_of, info.confidence, now, now,
            ),
        )
        return int(cur.lastrowid)


def update_property(property_id: int, info: PropertyInfo, raw: dict | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE properties SET
                name=?, address=?, region=?, lat=?, lng=?, deal_type=?,
                price_sale=?, deposit=?, monthly=?, area_m2=?, built_year=?, households=?,
                subway_json=?, schools_json=?, school_district_score=?, commute_min=?,
                ai_raw_json=COALESCE(?, ai_raw_json), sources_json=?, as_of=?, confidence=?,
                updated_at=?
            WHERE id=?""",
            (
                info.name, info.address, info.region, info.lat, info.lng, info.deal_type,
                info.price.sale, info.price.deposit, info.price.monthly,
                info.area_m2, info.built_year, info.households,
                json.dumps([s.model_dump() for s in info.subway], ensure_ascii=False),
                json.dumps([s.model_dump() for s in info.schools], ensure_ascii=False),
                info.school_district_score, info.commute.minutes,
                json.dumps(raw, ensure_ascii=False) if raw else None,
                json.dumps(info.sources, ensure_ascii=False),
                info.as_of, info.confidence, _now(), property_id,
            ),
        )


def get_property(property_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM properties WHERE id=?", (property_id,)).fetchone()
    return _row_to_property(row) if row else None


def list_properties(deal_type: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM properties"
    params: tuple = ()
    if deal_type:
        sql += " WHERE deal_type=?"
        params = (deal_type,)
    sql += " ORDER BY created_at DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_property(r) for r in rows]


def find_duplicate(name: str, deal_type: str) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM properties WHERE name=? AND deal_type=?", (name.strip(), deal_type)
        ).fetchone()
    return int(row["id"]) if row else None


def delete_property(property_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM properties WHERE id=?", (property_id,))


def count_properties() -> int:
    with get_conn() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0])


# ---------- inspections ----------

def get_inspection(property_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM inspections WHERE property_id=?", (property_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["pros"] = json.loads(d.pop("pros_json") or "[]")
    d["cons"] = json.loads(d.pop("cons_json") or "[]")
    return d


def upsert_inspection(property_id: int, data: dict[str, Any]) -> None:
    """data: INSPECTION_COLUMNS 키 + pros(list) + cons(list). 없는 키는 NULL."""
    values = [data.get(c) for c in INSPECTION_COLUMNS]
    pros = json.dumps(data.get("pros") or [], ensure_ascii=False)
    cons = json.dumps(data.get("cons") or [], ensure_ascii=False)
    cols = ", ".join(INSPECTION_COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in INSPECTION_COLUMNS)
    with get_conn() as conn:
        conn.execute(
            f"""INSERT INTO inspections (property_id, {cols}, pros_json, cons_json, updated_at)
                VALUES (?, {", ".join("?" * len(INSPECTION_COLUMNS))}, ?, ?, ?)
                ON CONFLICT(property_id) DO UPDATE SET {updates},
                    pros_json=excluded.pros_json, cons_json=excluded.cons_json,
                    updated_at=excluded.updated_at""",
            (property_id, *values, pros, cons, _now()),
        )


# ---------- settings ----------

def get_setting(key: str, default: Any = None) -> Any:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
