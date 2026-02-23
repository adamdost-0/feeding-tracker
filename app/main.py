from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

DB_PATH = Path("/data/feeding.db")

app = FastAPI(title="Breastfeeding Tracker")


class FeedIn(BaseModel):
    breast: str = Field(..., description="Breast side: 'L' or 'R'")
    start: str = Field(..., description="ISO 8601 datetime string")
    end: str = Field(..., description="ISO 8601 datetime string")


class FeedOut(BaseModel):
    id: int
    breast: str
    start: str
    end: str
    duration_minutes: int


class SummaryOut(BaseModel):
    day: str
    breast: str
    count: int
    total_minutes: int


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                breast TEXT NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedings_start ON feedings(start)"
        )
        conn.commit()


def parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid datetime format") from exc


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text()


def _normalize_breast(value: str) -> str:
    v = (value or "").strip().upper()
    if v not in {"L", "R"}:
        raise HTTPException(status_code=400, detail="Breast must be 'L' or 'R'")
    return v


@app.get("/api/feeds", response_model=List[FeedOut])
def list_feeds(days: int = 7) -> List[FeedOut]:
    cutoff = datetime.now() - timedelta(days=days)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, breast, start, end FROM feedings WHERE start >= ? ORDER BY start DESC",
            (cutoff.isoformat(timespec="minutes"),),
        ).fetchall()

    feeds: List[FeedOut] = []
    for r in rows:
        start_dt = parse_dt(r["start"])
        end_dt = parse_dt(r["end"])
        duration = max(0, int((end_dt - start_dt).total_seconds() // 60))
        feeds.append(
            FeedOut(
                id=r["id"],
                breast=_normalize_breast(r["breast"]),
                start=r["start"],
                end=r["end"],
                duration_minutes=duration,
            )
        )
    return feeds


@app.get("/api/summary", response_model=List[SummaryOut])
def summary(days: int = 7) -> List[SummaryOut]:
    cutoff = datetime.now().date() - timedelta(days=days - 1)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT breast, start, end FROM feedings WHERE start >= ?",
            (cutoff.isoformat(),),
        ).fetchall()

    # Bucket by day + breast
    buckets: dict[tuple[str, str], dict[str, int]] = {}
    for r in rows:
        breast = _normalize_breast(r["breast"])
        start_dt = parse_dt(r["start"])
        end_dt = parse_dt(r["end"])
        day = start_dt.date().isoformat()
        duration = max(0, int((end_dt - start_dt).total_seconds() // 60))
        key = (day, breast)
        if key not in buckets:
            buckets[key] = {"count": 0, "total_minutes": 0}
        buckets[key]["count"] += 1
        buckets[key]["total_minutes"] += duration

    result: list[SummaryOut] = []
    for i in range(days):
        day = (datetime.now().date() - timedelta(days=i)).isoformat()
        for breast in ("L", "R"):
            data = buckets.get((day, breast), {"count": 0, "total_minutes": 0})
            result.append(
                SummaryOut(day=day, breast=breast, count=data["count"], total_minutes=data["total_minutes"])
            )
    return result


@app.post("/api/feeds", response_model=FeedOut)
def create_feed(feed: FeedIn) -> FeedOut:
    breast = _normalize_breast(feed.breast)
    start_dt = parse_dt(feed.start)
    end_dt = parse_dt(feed.end)
    if end_dt < start_dt:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "INSERT INTO feedings (breast, start, end) VALUES (?, ?, ?)",
            (
                breast,
                start_dt.isoformat(timespec="minutes"),
                end_dt.isoformat(timespec="minutes"),
            ),
        )
        conn.commit()
        feed_id = cur.lastrowid

    duration = int((end_dt - start_dt).total_seconds() // 60)
    return FeedOut(
        id=feed_id,
        breast=breast,
        start=start_dt.isoformat(timespec="minutes"),
        end=end_dt.isoformat(timespec="minutes"),
        duration_minutes=duration,
    )


@app.delete("/api/feeds/{feed_id}")
def delete_feed(feed_id: int) -> dict:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute("DELETE FROM feedings WHERE id = ?", (feed_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Feed not found")
    return {"ok": True}
