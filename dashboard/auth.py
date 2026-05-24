import hashlib
import os
import secrets
import time

from dashboard.database import run_db, run_db_insert


CODE_EXPIRE = 300
SESSION_EXPIRE = 86400


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


async def create_login_code(
    user_id: str, username: str, lang: str = "en"
) -> tuple[str, str]:
    code = generate_code()
    now = time.time()
    await run_db_insert(
        "INSERT INTO login_codes (code, user_id, username, lang, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (code, user_id, username, lang, now, now + CODE_EXPIRE),
    )
    return code


async def validate_login_code(code: str) -> dict | None:
    rows = await run_db(
        "SELECT * FROM login_codes WHERE code = ? AND used = 0 AND expires_at > ?",
        (code, time.time()),
    )
    if not rows:
        return None
    row = rows[0]
    await run_db_insert("UPDATE login_codes SET used = 1 WHERE code = ?", (code,))
    return row


async def create_session(
    user_id: str, username: str, lang: str = "en", theme: str = "dark"
) -> str:
    session_id = secrets.token_hex(32)
    now = time.time()
    await run_db_insert(
        "INSERT INTO sessions (session_id, user_id, username, lang, theme, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, user_id, username, lang, theme, now, now + SESSION_EXPIRE),
    )
    return session_id


async def validate_session(session_id: str) -> dict | None:
    rows = await run_db(
        "SELECT * FROM sessions WHERE session_id = ? AND expires_at > ?",
        (session_id, time.time()),
    )
    if not rows:
        return None
    return rows[0]


async def update_session_lang(session_id: str, lang: str) -> None:
    await run_db_insert(
        "UPDATE sessions SET lang = ? WHERE session_id = ?", (lang, session_id)
    )


async def update_session_theme(session_id: str, theme: str) -> None:
    await run_db_insert(
        "UPDATE sessions SET theme = ? WHERE session_id = ?", (theme, session_id)
    )


async def delete_session(session_id: str) -> None:
    await run_db_insert("DELETE FROM sessions WHERE session_id = ?", (session_id,))


async def get_user_sessions(user_id: str) -> list[dict]:
    return await run_db(
        "SELECT * FROM sessions WHERE user_id = ? AND expires_at > ?",
        (user_id, time.time()),
    )
