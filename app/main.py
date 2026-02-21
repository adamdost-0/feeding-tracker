from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

DB_PATH = Path("/data/diaper.db")

app = FastAPI(title="Wet Diaper Tracker")


class EventIn(BaseModel):
    start: str = Field(..., description="ISO 8601 datetime string")
    end: str = Field(..., description="ISO 8601 datetime string")


class EventOut(BaseModel):
    id: int
    start: str
    end: str
    duration_minutes: int


class SummaryOut(BaseModel):
    day: str
    count: int
    total_minutes: int


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start TEXT NOT NULL,
                end TEXT NOT NULL
            )
            """
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


@app.get("/api/events", response_model=List[EventOut])
def list_events(days: int = 7) -> List[EventOut]:
    cutoff = datetime.now() - timedelta(days=days)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, start, end FROM events WHERE start >= ? ORDER BY start DESC",
            (cutoff.isoformat(timespec="minutes"),),
        ).fetchall()

    events: List[EventOut] = []
    for r in rows:
        start_dt = parse_dt(r["start"])
        end_dt = parse_dt(r["end"])
        duration = max(0, int((end_dt - start_dt).total_seconds() // 60))
        events.append(
            EventOut(id=r["id"], start=r["start"], end=r["end"], duration_minutes=duration)
        )
    return events


@app.get("/api/summary", response_model=List[SummaryOut])
def summary(days: int = 7) -> List[SummaryOut]:
    cutoff = datetime.now().date() - timedelta(days=days - 1)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT start, end FROM events WHERE start >= ?",
            (cutoff.isoformat(),),
        ).fetchall()

    buckets = {}
    for r in rows:
        start_dt = parse_dt(r["start"])
        end_dt = parse_dt(r["end"])
        day = start_dt.date().isoformat()
        duration = max(0, int((end_dt - start_dt).total_seconds() // 60))
        if day not in buckets:
            buckets[day] = {"count": 0, "total_minutes": 0}
        buckets[day]["count"] += 1
        buckets[day]["total_minutes"] += duration

    result = []
    for i in range(days):
        day = (datetime.now().date() - timedelta(days=i)).isoformat()
        data = buckets.get(day, {"count": 0, "total_minutes": 0})
        result.append(SummaryOut(day=day, count=data["count"], total_minutes=data["total_minutes"]))
    return result


@app.post("/api/events", response_model=EventOut)
def create_event(event: EventIn) -> EventOut:
    start_dt = parse_dt(event.start)
    end_dt = parse_dt(event.end)
    if end_dt < start_dt:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "INSERT INTO events (start, end) VALUES (?, ?)",
            (start_dt.isoformat(timespec="minutes"), end_dt.isoformat(timespec="minutes")),
        )
        conn.commit()
        event_id = cur.lastrowid

    duration = int((end_dt - start_dt).total_seconds() // 60)
    return EventOut(id=event_id, start=start_dt.isoformat(timespec="minutes"), end=end_dt.isoformat(timespec="minutes"), duration_minutes=duration)


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int) -> dict:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"ok": True}
