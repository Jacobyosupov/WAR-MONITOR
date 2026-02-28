"""
מסד נתונים – SQLite לשמירת מנויים, היסטוריה, וכתבות שנשלחו
"""

import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "iran_bot.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            region      TEXT DEFAULT 'all',
            min_level   INTEGER DEFAULT 1,
            joined_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            active      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sent_articles (
            url         TEXT PRIMARY KEY,
            title       TEXT,
            sent_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS search_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            query       TEXT,
            searched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alerts_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            level       INTEGER,
            sent_to     INTEGER,
            sent_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
    print("✅ מסד נתונים אותחל")


# ── מנויים ──────────────────────────────────────────

def add_subscriber(user_id: int, username: str = ""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO subscribers (user_id, username, active)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET active=1
        """, (user_id, username or ""))


def remove_subscriber(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE subscribers SET active=0 WHERE user_id=?", (user_id,))


def get_subscribers(region: str = None, min_level: int = 1) -> list[int]:
    with get_conn() as conn:
        if region and region != "all":
            rows = conn.execute("""
                SELECT user_id FROM subscribers
                WHERE active=1 AND min_level<=? AND (region=? OR region='all')
            """, (min_level, region)).fetchall()
        else:
            rows = conn.execute("""
                SELECT user_id FROM subscribers
                WHERE active=1 AND min_level<=?
            """, (min_level,)).fetchall()
        return [r["user_id"] for r in rows]


def set_subscriber_region(user_id: int, region: str):
    with get_conn() as conn:
        conn.execute("UPDATE subscribers SET region=? WHERE user_id=?", (region, user_id))


def set_subscriber_level(user_id: int, level: int):
    with get_conn() as conn:
        conn.execute("UPDATE subscribers SET min_level=? WHERE user_id=?", (level, user_id))


def count_subscribers() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM subscribers WHERE active=1").fetchone()[0]


# ── כתבות שנשלחו ────────────────────────────────────

def was_sent(url: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM sent_articles WHERE url=?", (url,)).fetchone()
        return row is not None


def mark_sent(url: str, title: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_articles (url, title) VALUES (?, ?)",
            (url, title)
        )


def cleanup_old_articles(days: int = 7):
    """מחיקת כתבות ישנות מהמסד"""
    with get_conn() as conn:
        conn.execute("""
            DELETE FROM sent_articles
            WHERE sent_at < datetime('now', ?)
        """, (f"-{days} days",))


# ── היסטוריית חיפושים ───────────────────────────────

def log_search(user_id: int, query: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO search_history (user_id, query) VALUES (?, ?)",
            (user_id, query)
        )


def get_user_searches(user_id: int, limit: int = 5) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT query FROM search_history
            WHERE user_id=?
            ORDER BY searched_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [r["query"] for r in rows]
