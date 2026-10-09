"""
MicroMRR snapshot store — SQLite on disk. One row per day.
Snapshots power the 30-day trend and (later) expansion/contraction diffs.
"""
from __future__ import annotations

import os
import sqlite3
import time

DB_PATH = os.environ.get("MICROMRR_DB", os.path.join(os.path.dirname(__file__), "micromrr.db"))


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS snapshots (
               date TEXT PRIMARY KEY,
               mrr_cents INTEGER NOT NULL,
               subscribers INTEGER NOT NULL,
               churned_cents INTEGER NOT NULL DEFAULT 0,
               created_at INTEGER NOT NULL
           )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS settings (
               key TEXT PRIMARY KEY,
               value TEXT NOT NULL
           )"""
    )
    return con


def record_snapshot(mrr_cents: int, subscribers: int, churned_cents: int = 0,
                    day: str | None = None) -> None:
    day = day or time.strftime("%Y-%m-%d", time.gmtime())
    con = _conn()
    try:
        con.execute(
            "INSERT OR REPLACE INTO snapshots (date, mrr_cents, subscribers, churned_cents, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (day, mrr_cents, subscribers, churned_cents, int(time.time())),
        )
        con.commit()
    finally:
        con.close()


def get_snapshots(limit: int = 90) -> list[dict]:
    con = _conn()
    try:
        rows = con.execute(
            "SELECT date, mrr_cents, subscribers, churned_cents FROM snapshots"
            " ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        con.close()
    return [
        {"date": d, "mrr_cents": m, "subscribers": s, "churned_cents": c}
        for d, m, s, c in rows
    ]


def get_setting(key: str) -> str | None:
    con = _conn()
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    con = _conn()
    try:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        con.commit()
    finally:
        con.close()
