import asyncio
import sqlite3
import time
from pathlib import Path

DB_PATH = Path("dashboard/dashboard.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS login_codes (
            code TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            lang TEXT DEFAULT 'en',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            used INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            lang TEXT DEFAULT 'en',
            theme TEXT DEFAULT 'dark',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );
    """)
    conn.commit()
    conn.close()


async def run_db(query: str, params: tuple = ()) -> list[dict]:
    def _run():
        conn = _get_connection()
        cursor = conn.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.commit()
        conn.close()
        return rows
    return await asyncio.to_thread(_run)


async def run_db_insert(query: str, params: tuple = ()) -> None:
    def _run():
        conn = _get_connection()
        conn.execute(query, params)
        conn.commit()
        conn.close()
    await asyncio.to_thread(_run)


async def cleanup_expired() -> None:
    now = time.time()
    await run_db("DELETE FROM login_codes WHERE expires_at < ?", (now,))
    await run_db("DELETE FROM sessions WHERE expires_at < ?", (now,))
