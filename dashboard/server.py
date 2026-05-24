import asyncio
import collections
import json
import os
import time
from pathlib import Path
from typing import Optional

import discord
import jinja2
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeSerializer

from services.ticket.config import TicketConfig
_ticket_config = TicketConfig.get_instance()

from dashboard.auth import (
    CODE_EXPIRE,
    create_login_code,
    create_session,
    delete_session,
    update_session_lang,
    update_session_theme,
    validate_login_code,
    validate_session,
)

LANG_NAMES = {"en": "English", "de": "Deutsch"}
ADMIN_ROLE_GROUPS = ["owner", "dev", "manager", "sr-admin", "admin"]

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

os.makedirs("logs", exist_ok=True)


def _load_role_config() -> dict:
    try:
        with open("role.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"roles": {}, "commands": {}}


def _load_tickets() -> dict:
    try:
        with open(_ticket_config.files.tickets_data, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_tickets(data: dict) -> None:
    with open(_ticket_config.files.tickets_data, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load_daily_status() -> None:
    pass


def get_bot_stats(client: discord.Bot) -> dict:
    guilds = client.guilds
    total_members = sum(g.member_count or 0 for g in guilds)
    uptime = time.time() - client.start_time if hasattr(client, "start_time") else 0
    return {
        "guild_count": len(guilds),
        "total_members": total_members,
        "uptime": uptime,
        "guilds": [
            {"name": g.name, "id": g.id, "members": g.member_count or 0, "icon": str(g.icon.url) if g.icon else None}
            for g in guilds
        ],
    }


def get_ticket_list() -> list[dict]:
    tickets = _load_tickets()
    result = []
    for key, data in tickets.items():
        if key == "_counter":
            continue
        result.append({
            "channel_id": key,
            "ticket_number": data.get("ticket_number", 0),
            "category": data.get("category", ""),
            "user_id": data.get("user_id", ""),
            "created_at": data.get("created_at", ""),
            "last_activity": data.get("last_activity", ""),
            "closed": data.get("closed", False),
        })
    result.sort(key=lambda t: t.get("ticket_number", 0), reverse=True)
    return result


def get_log_files() -> list[str]:
    log_dir = Path("logs")
    if not log_dir.exists():
        return []
    return sorted([f.name for f in log_dir.iterdir() if f.suffix == ".log"])


def read_log_file(filename: str, max_lines: int = 200) -> str:
    path = Path("logs") / filename
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        return "".join(lines[-max_lines:])


def get_config_files() -> list[str]:
    files = ["role.json", "blocked_words.json", "devcoder_config.json", "config/config.json"]
    return [f for f in files if Path(f).exists()]


def read_config_file(filename: str) -> str:
    path = Path(filename)
    if not path.exists():
        raise HTTPException(404, "Config file not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, indent=2)
    except json.JSONDecodeError:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


def user_has_admin_role(user: discord.Member) -> bool:
    role_config = _load_role_config()
    roles_cfg = role_config.get("roles", {})
    user_role_ids = {r.id for r in user.roles}
    for group_name in ADMIN_ROLE_GROUPS:
        group_ids = roles_cfg.get(group_name, [])
        if isinstance(group_ids, list):
            if any(rid in user_role_ids for rid in group_ids):
                return True
        else:
            if group_ids in user_role_ids:
                return True
    return False


def get_guild(client: discord.Bot, guild_id: int) -> Optional[discord.Guild]:
    return client.get_guild(guild_id)


def get_channel(client: discord.Bot, channel_id: int) -> Optional[discord.TextChannel]:
    for guild in client.guilds:
        ch = guild.get_channel(channel_id)
        if ch:
            return ch
    return None


async def _close_and_cleanup_dashboard(client: discord.Bot, channel_id: int) -> str:
    tickets = _load_tickets()
    key = str(channel_id)
    ticket = tickets.get(key)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.get("closed"):
        raise HTTPException(400, "Ticket already closed")

    ticket["closed"] = True
    _save_tickets(tickets)

    channel = get_channel(client, channel_id)
    if channel:
        try:
            await channel.send(_ticket_config.messages.dashboard_close)
            await asyncio.sleep(1)
            await channel.delete()
        except Exception:
            pass

    return "Ticket closed successfully"


def create_app(client: discord.Bot) -> FastAPI:
    app = FastAPI(title="DevCoder Dashboard")
    app.state.client = client
    app.state.secret = os.getenv("DASHBOARD_SECRET", "devcoder-dashboard-secret-key")
    app.state.serializer = URLSafeSerializer(app.state.secret)
    app.state.login_attempts: dict[str, list[float]] = {}
    app.state.cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"

    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    def _render(template_name: str, context: dict) -> HTMLResponse:
        return HTMLResponse(jinja_env.get_template(template_name).render(context))

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    async def _get_session_async(request: Request) -> dict | None:
        cookie = request.cookies.get("session")
        if not cookie:
            return None
        try:
            session_id = app.state.serializer.loads(cookie)
            return await validate_session(session_id)
        except Exception:
            return None

    async def _require_auth(request: Request) -> dict:
        session = await _get_session_async(request)
        if not session:
            raise HTTPException(303, detail="", headers={"Location": "/login"})
        return session

    def _get_user_context(session: dict) -> dict:
        user = client.get_user(int(session["user_id"])) if session.get("user_id") else None
        display_name = str(user) if user else session.get("username", "Unknown")
        avatar_url = (
            user.display_avatar.url
            if user and user.display_avatar
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        )
        return {
            "session": session,
            "lang": session.get("lang", "en"),
            "theme": session.get("theme", "dark"),
            "user_display_name": display_name,
            "user_avatar": avatar_url,
            "lang_name": LANG_NAMES.get(session.get("lang", "en"), "English"),
        }

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(
        request: Request,
        code: str = "",
        error: str = "",
        lang: str = "en",
    ):
        session = await _get_session_async(request)
        if session:
            return RedirectResponse(url="/dashboard", status_code=303)
        return _render(
            "login.html",
            {
                "request": request,
                "code": code,
                "error": error,
                "lang": lang if lang in ("en", "de") else "en",
                "lang_name": LANG_NAMES.get(lang, "English"),
                "code_expire": CODE_EXPIRE // 60,
                "LANG_NAMES": LANG_NAMES,
            },
        )

    @app.post("/login")
    async def login_submit(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        attempts = app.state.login_attempts.setdefault(client_ip, [])
        attempts[:] = [t for t in attempts if t > now - 60]
        if len(attempts) >= 5:
            return RedirectResponse(
                url=f"/login?error=Too+many+attempts.+Try+again+later.&lang=en&code=", status_code=303
            )
        attempts.append(now)

        form = await request.form()
        code = form.get("code", "").strip()
        lang = form.get("lang", "en")
        if lang not in ("en", "de"):
            lang = "en"
        if not code:
            return RedirectResponse(
                url=f"/login?error=Please+enter+a+code&lang={lang}&code=", status_code=303
            )
        data = await validate_login_code(code)
        if not data:
            return RedirectResponse(
                url=f"/login?error=Invalid+or+expired+code&lang={lang}&code={code}", status_code=303
            )
        session_id = await create_session(
            data["user_id"], data["username"], lang=lang
        )
        signed = app.state.serializer.dumps(session_id)
        resp = RedirectResponse(url="/dashboard", status_code=303)
        resp.set_cookie(
            key="session",
            value=signed,
            max_age=86400,
            httponly=True,
            secure=app.state.cookie_secure,
            samesite="lax",
        )
        return resp

    @app.get("/logout")
    async def logout(request: Request):
        cookie = request.cookies.get("session")
        if cookie:
            try:
                session_id = app.state.serializer.loads(cookie)
                await delete_session(session_id)
            except Exception:
                pass
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie("session")
        return resp

    @app.get("/api/session")
    async def api_session(request: Request):
        session = await _get_session_async(request)
        if not session:
            raise HTTPException(401, "Not authenticated")
        return {
            "user_id": session["user_id"],
            "username": session["username"],
            "lang": session["lang"],
            "theme": session["theme"],
        }

    @app.post("/api/session/lang")
    async def api_session_lang(request: Request):
        session = await _require_auth(request)
        data = await request.json()
        lang = data.get("lang", "en")
        if lang not in ("en", "de"):
            lang = "en"
        session_id = app.state.serializer.loads(request.cookies.get("session", ""))
        await update_session_lang(session_id, lang)
        return {"ok": True}

    @app.post("/api/session/theme")
    async def api_session_theme(request: Request):
        session = await _require_auth(request)
        data = await request.json()
        theme = data.get("theme", "dark")
        if theme not in ("dark", "light"):
            theme = "dark"
        session_id = app.state.serializer.loads(request.cookies.get("session", ""))
        await update_session_theme(session_id, theme)
        return {"ok": True}

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        session = await _require_auth(request)
        stats = get_bot_stats(client)
        tickets = get_ticket_list()
        open_tickets = [t for t in tickets if not t["closed"]]
        ctx = _get_user_context(session)
        return _render(
            "dashboard.html",
            {**ctx, "request": request, "stats": stats, "open_tickets": len(open_tickets), "total_tickets": len(tickets)},
        )

    @app.get("/tickets", response_class=HTMLResponse)
    async def tickets_page(request: Request, filter: str = "open"):
        session = await _require_auth(request)
        all_tickets = get_ticket_list()
        if filter == "open":
            ticket_list = [t for t in all_tickets if not t["closed"]]
        elif filter == "closed":
            ticket_list = [t for t in all_tickets if t["closed"]]
        else:
            ticket_list = all_tickets
        ctx = _get_user_context(session)
        return _render(
            "tickets.html",
            {**ctx, "request": request, "tickets": ticket_list, "filter": filter,
             "total_open": len([t for t in all_tickets if not t["closed"]]),
             "total_closed": len([t for t in all_tickets if t["closed"]])},
        )

    @app.post("/tickets/{channel_id}/close")
    async def ticket_close(request: Request, channel_id: int):
        session = await _require_auth(request)
        result = await _close_and_cleanup_dashboard(client, channel_id)
        return {"ok": True, "message": result}

    @app.post("/tickets/{channel_id}/add")
    async def ticket_add(request: Request, channel_id: int):
        session = await _require_auth(request)
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        channel = get_channel(client, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        member = channel.guild.get_member(user_id)
        if not member:
            raise HTTPException(404, "User not found in guild")
        try:
            await channel.set_permissions(member, read_messages=True, send_messages=True)
            return {"ok": True, "message": f"Added {member.display_name} to ticket"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/tickets/{channel_id}/remove")
    async def ticket_remove(request: Request, channel_id: int):
        session = await _require_auth(request)
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        channel = get_channel(client, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        member = channel.guild.get_member(user_id)
        if not member:
            raise HTTPException(404, "User not found in guild")
        try:
            await channel.set_permissions(member, overwrite=None)
            return {"ok": True, "message": f"Removed {member.display_name} from ticket"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request, file: str = ""):
        session = await _require_auth(request)
        log_files = get_log_files()
        selected_file = file if file in log_files else (log_files[0] if log_files else "")
        content = read_log_file(selected_file) if selected_file else "No logs available."
        ctx = _get_user_context(session)
        return _render(
            "logs.html",
            {**ctx, "request": request, "log_files": log_files, "selected_file": selected_file, "content": content},
        )

    @app.get("/api/logs/{filename}")
    async def api_logs(request: Request, filename: str, lines: int = 200):
        session = await _require_auth(request)
        log_files = get_log_files()
        if filename not in log_files:
            raise HTTPException(404, "Log file not found")
        content = read_log_file(filename, max_lines=lines)
        return {"filename": filename, "content": content}

    @app.get("/config", response_class=HTMLResponse)
    async def config_page(request: Request, file: str = ""):
        session = await _require_auth(request)
        config_files = get_config_files()
        selected_file = file if file in config_files else (config_files[0] if config_files else "")
        content = ""
        if selected_file:
            try:
                content = read_config_file(selected_file)
            except HTTPException:
                content = "File not found."
            except Exception:
                content = "Error reading file."
        ctx = _get_user_context(session)
        return _render(
            "config.html",
            {**ctx, "request": request, "config_files": config_files, "selected_file": selected_file, "content": content},
        )

    @app.get("/api/config/{filename:path}")
    async def api_config(request: Request, filename: str):
        session = await _require_auth(request)
        content = read_config_file(filename)
        return {"filename": filename, "content": content}

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        session = await _get_session_async(request)
        if session:
            return RedirectResponse(url="/dashboard", status_code=303)
        return _render("login.html", {"request": request, "code": "", "error": "", "lang": "en", "lang_name": LANG_NAMES["en"], "code_expire": CODE_EXPIRE // 60, "LANG_NAMES": LANG_NAMES})

    @app.get("/guest", response_class=HTMLResponse)
    async def guest_page(request: Request):
        return _render("guest.html", {"request": request})

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app
