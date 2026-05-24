import discord
import os
import re
import dotenv
from datetime import datetime, timezone, timedelta
import random
import asyncio
import time
import json
import urllib.request
import urllib.error
from collections import defaultdict, deque
from zoneinfo import ZoneInfo

dotenv.load_dotenv()

TOKEN = os.getenv("TOKEN")
BOT_NAME = os.getenv("BOT_NAME", "DevCoderPrivatBot")

BUG_CHANNEL_ID = os.getenv("BUG_CHANNEL_ID")
if BUG_CHANNEL_ID:
    try:
        BUG_CHANNEL_ID = int(BUG_CHANNEL_ID.strip())
    except ValueError:
        print("WARNING: BUG_CHANNEL_ID in .env is not a valid number.")
        BUG_CHANNEL_ID = None

BLOCKED_WORDS_FILE = "blocked_words.json"
ANTI_LINK_INFRACTIONS_FILE = "anti_link_infractions.json"
ANTI_LINK_MAX_INFRACTIONS = 3
ANTI_LINK_TIMEOUT_DAYS = 3
DISCORD_INVITE_REGEX = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|dsc\.gg)/\S+", re.IGNORECASE)

def _load_blocked_words():
    try:
        with open(BLOCKED_WORDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return []


def _load_anti_link_infractions():
    try:
        with open(ANTI_LINK_INFRACTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {}


def _save_anti_link_infractions(data):
    with open(ANTI_LINK_INFRACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


DEVCODER_CONFIG_FILE = "devcoder_config.json"

def _load_devcoder_config():
    try:
        with open(DEVCODER_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"owner_ids": [], "current_status": "Idle", "monitor_enabled": True, "trigger_words": []}

def _save_devcoder_config(data):
    with open(DEVCODER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

_devcoder_config = _load_devcoder_config()


TICKET_CATEGORY_ID = os.getenv("TICKET_CATEGORY_ID")
if TICKET_CATEGORY_ID:
    try:
        TICKET_CATEGORY_ID = int(TICKET_CATEGORY_ID.strip())
    except ValueError:
        print("WARNING: TICKET_CATEGORY_ID in .env is not a valid number.")
        TICKET_CATEGORY_ID = None

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

ROLE_CONFIG_FILE = "role.json"
_role_config = None
_role_prefix_map = {}

def _load_role_config():
    global _role_config, _role_prefix_map
    try:
        with open(ROLE_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "roles" in data and "commands" in data:
                _role_config = data
                print(f"Loaded role config: {len(data.get('roles', {}))} role groups")
            else:
                print("WARNING: role.json has an invalid structure.")
                _role_config = {"roles": {}, "commands": {}}
    except FileNotFoundError:
        print("WARNING: role.json not found. Permission system disabled.")
        _role_config = {"roles": {}, "commands": {}}
    except Exception as e:
        print(f"WARNING: Could not load role.json: {e}")
        _role_config = {"roles": {}, "commands": {}}

    _rebuild_prefix_map()
    _debug_role_ids()
    return _role_config

def _rebuild_prefix_map():
    global _role_prefix_map
    _role_prefix_map = {}
    prefixes = _role_config.get("prefixes", {})
    roles = _role_config.get("roles", {})
    for group_name, prefix in prefixes.items():
        role_ids = roles.get(group_name, [])
        if isinstance(role_ids, list):
            for rid in role_ids:
                _role_prefix_map[rid] = prefix
        else:
            _role_prefix_map[role_ids] = prefix

def _get_role_ids_for_permission(command_name):
    if _role_config is None:
        _load_role_config()
    commands = _role_config.get("commands", {})
    roles = _role_config.get("roles", {})
    required_role_names = commands.get(command_name) or commands.get("default", [])
    role_ids = []
    for role_name in required_role_names:
        ids = roles.get(role_name, [])
        if isinstance(ids, list):
            role_ids.extend(ids)
        else:
            role_ids.append(ids)
    return role_ids

def _debug_role_ids():
    if _role_config:
        for group, ids in _role_config.get("roles", {}).items():
            print(f"  [{group}] IDs: {ids}")

async def require_permission(ctx, command_name):
    if _role_config is None:
        _load_role_config()

    if not _role_config.get("roles"):
        print(f"Permission: '{command_name}' → no roles configured, ALLOWED")
        return True

    role_ids = _get_role_ids_for_permission(command_name)

    if not role_ids:
        print(f"Permission: '{command_name}' → no role IDs found, ALLOWED")
        return True

    if ctx.guild is None or not hasattr(ctx.author, "roles"):
        try:
            await ctx.respond(
                "This command can only be used on a server with roles.",
                ephemeral=True
            )
        except Exception:
            pass
        return False

    user_role_ids = [r.id for r in ctx.author.roles]
    print(f"Permission: '{command_name}' → required={role_ids}, user={user_role_ids}")

    if any(role.id in role_ids for role in ctx.author.roles):
        print(f"Permission: '{command_name}' → GRANTED")
        return True

    print(f"Permission: '{command_name}' → DENIED")
    try:
        await ctx.respond(
            "You do not have permission for this command.",
            ephemeral=True
        )
    except Exception:
        pass
    return False

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Bot(intents=intents)
start_time = time.time()
DAILY_STATUS_FILE = "daily_message_status.json"
GERMAN_TZ = ZoneInfo("Europe/Berlin")

SPAM_MAX_MESSAGES = 5
SPAM_WINDOW_SECONDS = 6
SPAM_WARNING_COOLDOWN_SECONDS = 10
_message_timestamps = defaultdict(deque)
_last_spam_warning = {}


def _load_daily_status():
    try:
        with open(DAILY_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"WARNING: Could not load daily status: {e}")

def _save_daily_status(data):
    with open(DAILY_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@client.event
async def on_ready():
    global start_time
    _load_role_config()
    print("Bot is online!")
    start_time = time.time()
    client.start_time = start_time
    try:
        synced = await client.sync_commands()
    
        if synced is None:
            print("Commands synced (no return value).")
        else:
            print(f"Synced: {len(synced)} commands")

    except Exception as e:
        print(f"Sync error: {e}")

    today_de = datetime.now(GERMAN_TZ).date().isoformat()
    daily_status = _load_daily_status()
    changed = False

    for guild in client.guilds:
        print(f"- {guild.name}")
        guild_key = str(guild.id)
        if daily_status.get(guild_key) == today_de:
            continue

        channel = guild.system_channel
        if channel is None or not channel.permissions_for(guild.me).send_messages:
            channel = next((x for x in guild.text_channels if x.permissions_for(guild.me).send_messages), None)
        if channel:
            try:
                await channel.send(f"Coming soon \u2022 In development")
                daily_status[guild_key] = today_de
                changed = True
            except Exception as e:
                print(f"Error sending to {guild.name}: {e}")

    if changed:
        _save_daily_status(daily_status)

    # Start periodic patrols.
    asyncio.create_task(_nickname_patrol())
    asyncio.create_task(_ticket_inactivity_check())

    # Register persistent views for ticket system.
    client.add_view(TicketCreateView())
    client.add_view(TicketCloseView())

    # Apply nickname prefixes to all members on startup.
    for guild in client.guilds:
        for member in guild.members:
            await _update_nickname_prefix(member)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is None:
        return

    now = time.time()
    user_id = message.author.id
    timestamps = _message_timestamps[user_id]
    timestamps.append(now)

    while timestamps and now - timestamps[0] > SPAM_WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= SPAM_MAX_MESSAGES:
        try:
            await message.delete()
        except Exception as e:
            print(f"Could not delete spam message: {e}")
            return

        last_warning_time = _last_spam_warning.get(user_id, 0)
        if now - last_warning_time >= SPAM_WARNING_COOLDOWN_SECONDS:
            _last_spam_warning[user_id] = now
            try:
                await message.author.send(
                    "--------------------------------------------------------\n"
                    "                           GlazeSMP - AntiSPAM: \n"
                    "Please stop spamming. Your message has been deleted.\n"
                    "--------------------------------------------------------"
                )
            except Exception:
                try:
                    await message.channel.send(
                        f"{message.author.mention} please stop spamming.",
                        delete_after=5
                    )
                except Exception as send_error:
                    print(f"Could not send spam warning: {send_error}")

    # Blocked words check
    blocked_words = _load_blocked_words()
    if blocked_words and message.content:
        content_lower = message.content.lower()
        for word in blocked_words:
            if isinstance(word, str) and word.lower() in content_lower:
                try:
                    await message.delete()
                except:
                    pass
                try:
                    await message.author.send(
                        f"Your message in {message.channel.mention} was deleted because it contains a blocked word."
                    )
                except discord.Forbidden:
                    pass
                print(f"Blocked word '{word}' deleted from {message.author} in {message.guild.name}/{message.channel.name}")
                break

    # Anti-Discord invite link check
    if message.content and DISCORD_INVITE_REGEX.search(message.content):
        try:
            await message.delete()
        except:
            pass

        infractions = _load_anti_link_infractions()
        user_id_str = str(message.author.id)
        count = infractions.get(user_id_str, 0) + 1
        infractions[user_id_str] = count
        _save_anti_link_infractions(infractions)

        if count >= ANTI_LINK_MAX_INFRACTIONS:
            try:
                await message.author.timeout(
                    timedelta(days=ANTI_LINK_TIMEOUT_DAYS),
                    reason=f"Posted Discord invite link {count} times"
                )
            except:
                pass
            try:
                await message.author.send(
                    "--------------------------------------------------------\n"
                    "                           GlazeSMP - Warning: \n"
                    "You have been timed out for 3 days because you repeatedly "
                    "posted Discord invite links. This is not allowed.\n"
                    "--------------------------------------------------------"
                )
            except:
                pass
        else:
            try:
                await message.author.send(
                    "--------------------------------------------------------\n"
                    "                           GlazeSMP - Warning: \n"
                    "Please do not post Discord invite links. Your message has been deleted. "
                    f"This is warning {count}/{ANTI_LINK_MAX_INFRACTIONS}. "
                    "Repeated violations will result in a timeout.\n"
                    "--------------------------------------------------------"
                )
            except:
                pass

    # DevCoder trigger word monitoring
    global _devcoder_config
    if message.content and _devcoder_config.get("monitor_enabled", True):
        content_lower = message.content.lower()
        trigger_words = _devcoder_config.get("trigger_words", [])
        owner_ids = _devcoder_config.get("owner_ids", [])
        triggered = False
        if trigger_words:
            for word in trigger_words:
                if isinstance(word, str) and word.lower() in content_lower:
                    triggered = True
                    break
        if triggered and owner_ids:
            status = _devcoder_config.get("current_status", "Idle")
            embed = discord.Embed(
                title="DevCoder Trigger Alert",
                colour=0xff0000,
                timestamp=datetime.now()
            )
            embed.add_field(name="Message", value=message.content[:1000], inline=False)
            embed.add_field(name="Author", value=f"{message.author} (`{message.author.id}`)", inline=False)
            embed.add_field(name="Server", value=message.guild.name, inline=True)
            embed.add_field(name="Channel", value=f"#{message.channel.name} (`{message.channel.id}`)", inline=True)
            embed.add_field(name="Path", value=f"{message.guild.name} / #{message.channel.name}", inline=False)
            embed.set_footer(text=f"DevCoder is currently: {status}")
            for owner_id in owner_ids:
                owner = client.get_user(owner_id)
                if owner:
                    try:
                        await owner.send(embed=embed)
                    except:
                        pass

    # Ticket activity tracking
    tickets = _load_tickets()
    key = str(message.channel.id)
    if key in tickets and not tickets[key].get("closed"):
        if str(message.author.id) == tickets[key].get("user_id"):
            tickets[key]["last_activity"] = datetime.now(GERMAN_TZ).isoformat()
            tickets[key]["auto_close_warned"] = {}
            _save_tickets(tickets)

#------
#Nickname prefix system:
def _strip_prefix(name):
    # Remove any known prefix from the current config.
    for prefix in set(_role_prefix_map.values()):
        while name.startswith(prefix):
            name = name[len(prefix):].strip()
    # Remove any other bracketed prefix (old configs, manual, other bots).
    name = re.sub(r'^\[.+?\]\s*', '', name).strip()
    return name

async def _update_nickname_prefix(member: discord.Member):
    if not member.guild.me.guild_permissions.manage_nicknames:
        return

    matching = []
    for role_id, prefix in _role_prefix_map.items():
        role = discord.utils.get(member.roles, id=role_id)
        if role:
            matching.append((role, prefix))

    MAX_NICK = 32

    base_name = member.nick if member.nick else member.name
    stripped = _strip_prefix(base_name)

    if matching:
        matching.sort(key=lambda x: x[0].position, reverse=True)
        prefix = matching[0][1]
        max_name_len = MAX_NICK - len(prefix) - 1
        truncated = stripped[:max_name_len]
        new_nick = f"{prefix} {truncated}"
    else:
        new_nick = stripped[:MAX_NICK]

    if new_nick == (member.nick or member.name):
        return

    try:
        await member.edit(nick=new_nick)
    except discord.Forbidden:
        pass

async def _nickname_patrol():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(10)
        for guild in client.guilds:
            if not guild.me.guild_permissions.manage_nicknames:
                continue
            for member in guild.members:
                await _update_nickname_prefix(member)

@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles == after.roles:
        return
    await _update_nickname_prefix(after)

@client.event
async def on_member_join(member: discord.Member):
    auto_role = _role_config.get("auto_role", {}) if _role_config else {}
    if not auto_role.get("enabled"):
        return
    role_ids = auto_role.get("role_ids", [])
    if not role_ids:
        return

    for rid in role_ids:
        role = member.guild.get_role(rid)
        if role is None:
            print(f"Auto-role: role ID {rid} not found in {member.guild.name}")
            continue
        try:
            await member.add_roles(role)
            print(f"Auto-role: assigned '{role.name}' to {member}")
        except discord.Forbidden:
            print(f"Auto-role: missing permissions in {member.guild.name}")

    await _update_nickname_prefix(member)

#------
#Ticket System:

TICKET_FILE = "tickets.json"

def _load_tickets():
    try:
        with open(TICKET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {}

def _save_tickets(data):
    try:
        with open(TICKET_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"WARNING: Could not save tickets: {e}")

def _get_next_ticket_number():
    tickets = _load_tickets()
    n = tickets.get("_counter", 0) + 1
    tickets["_counter"] = n
    _save_tickets(tickets)
    return n


def _get_ticket_staff_role_ids():
    if _role_config is None:
        _load_role_config()
    roles = _role_config.get("roles", {})
    ticket_role_names = _role_config.get("commands", {}).get("ticket_staff", [])
    role_ids = []
    for name in ticket_role_names:
        ids = roles.get(name, [])
        if isinstance(ids, list):
            role_ids.extend(ids)
        else:
            role_ids.append(ids)
    return role_ids

def _load_ticket_categories():
    if _role_config is None:
        _load_role_config()
    return _role_config.get("ticket_categories", {}) if _role_config else {}


def _get_ticket_category_role_ids(category_key):
    cats = _load_ticket_categories()
    cat = cats.get(category_key, {})
    role_names = cat.get("roles", [])
    roles = _role_config.get("roles", {})
    role_ids = []
    for name in role_names:
        ids = roles.get(name, [])
        if isinstance(ids, list):
            role_ids.extend(ids)
        else:
            role_ids.append(ids)
    return role_ids


TRANSCRIPTS_DIR = "transcripts"


def _escape_md(text):
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def _create_transcript_md(channel_name, messages, ticket_data):
    staff_role_ids = _get_ticket_staff_role_ids()
    num = ticket_data.get("ticket_number", "")
    num_str = f" (#{num})" if num else ""
    lines = [f"# Ticket Transcript – {channel_name}{num_str}", ""]
    lines.append(f"- **Created:** {ticket_data.get('created_at', 'N/A')}")
    lines.append(f"- **Closed:** {ticket_data.get('closed_at', 'N/A')}")
    lines.append("---")
    for msg in messages:
        is_bot = msg.author.bot
        is_staff = any(r.id in staff_role_ids for r in msg.author.roles)
        if is_bot:
            badge = "🤖"
        elif is_staff:
            badge = "🛡️"
        else:
            badge = "👤"
        content = msg.content or ""
        lines.append("")
        lines.append(f"### {badge} {_escape_md(msg.author.display_name)}")
        lines.append(f"*{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        for line in content.split("\n"):
            lines.append(_escape_md(line))
        for att in msg.attachments:
            lines.append(f"- 📎 [{_escape_md(att.filename)}]({att.url})")
    lines.append("")
    lines.append("---")
    lines.append(f"*Transcript generated by {BOT_NAME}*")
    return "\n".join(lines)


def _create_gist(content, filename, description):
    if not GITHUB_TOKEN:
        return None
    payload = json.dumps({
        "description": description,
        "public": False,
        "files": {filename: {"content": content}},
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/gists",
        data=payload,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "DevCoderBot/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("html_url")
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code} {e.reason}")
    except Exception as e:
        print(f"GitHub API error: {e}")
    return None


async def _close_and_cleanup(channel, ticket_key, closed_by):
    tickets = _load_tickets()
    data = tickets.get(ticket_key)
    if not data or data.get("closed"):
        return

    now_dt = datetime.now(GERMAN_TZ)
    data["closed"] = True
    data["closed_at"] = now_dt.isoformat()
    data["closed_by"] = str(closed_by)
    data["auto_close_warned"] = {}
    _save_tickets(tickets)

    try:
        messages = []
        async for msg in channel.history(limit=None, oldest_first=True):
            messages.append(msg)
        if messages:
            md = _create_transcript_md(channel.name, messages, data)
            num = data.get("ticket_number", "")
            num_str = f"-{num}" if num else ""
            fname = f"transcript{num_str}-{channel.name}-{now_dt.strftime('%Y%m%d-%H%M%S')}.md"
            desc = f"Ticket Transcript – {channel.name}{num_str}"
            url = _create_gist(md, fname, desc)
            user = client.get_user(int(data["user_id"]))
            if user:
                if url:
                    try:
                        await user.send(
                            f"Your ticket `{channel.name}` has been closed."
                            f"\n📄 View transcript: {url}"
                        )
                    except discord.Forbidden:
                        print(f"Could not DM transcript to user {data['user_id']}")
                    except Exception as e:
                        print(f"Error sending transcript DM: {e}")
                else:
                    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
                    local = f"{TRANSCRIPTS_DIR}/{fname}"
                    with open(local, "w", encoding="utf-8") as f:
                        f.write(md)
                    try:
                        await user.send(
                            f"Your ticket `{channel.name}` has been closed."
                            f"\n(GitHub token not configured – transcript saved locally)",
                            file=discord.File(local)
                        )
                    except Exception as e:
                        print(f"Error sending transcript file: {e}")
                    os.remove(local)
    except Exception as e:
        print(f"Error creating transcript: {e}")

    embed = discord.Embed(
        title="Closing Ticket",
        description="This ticket will be deleted in 5 seconds.",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    try:
        await channel.send(embed=embed)
        await asyncio.sleep(5)
        await channel.delete()
    except Exception as e:
        print(f"Error deleting ticket channel: {e}")


class TicketCreateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="persistent:ticket_create")
    async def create_ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        tickets = _load_tickets()
        user_id = str(interaction.user.id)

        for ticket_data in tickets.values():
            if ticket_data.get("user_id") == user_id and not ticket_data.get("closed"):
                await interaction.followup.send("You already have an open ticket.", ephemeral=True)
                return

        guild = interaction.guild
        if TICKET_CATEGORY_ID is None:
            await interaction.followup.send("Ticket category not configured.", ephemeral=True)
            return
        category_ch = guild.get_channel(TICKET_CATEGORY_ID)
        if not category_ch or not isinstance(category_ch, discord.CategoryChannel):
            await interaction.followup.send("Ticket category not found. Please contact an admin.", ephemeral=True)
            return

        ticket_number = _get_next_ticket_number()
        channel_name = f"ticket-{interaction.user.name.lower().replace(' ', '-')}-{ticket_number}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }

        for role_id in _get_ticket_staff_role_ids():
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await guild.create_text_channel(channel_name, category=category_ch, overwrites=overwrites)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create channels.", ephemeral=True)
            return
        except Exception as e:
            print(f"Error creating ticket channel: {e}")
            await interaction.followup.send("Error creating ticket.", ephemeral=True)
            return

        now_iso = datetime.now(GERMAN_TZ).isoformat()
        tickets[str(channel.id)] = {
            "ticket_number": ticket_number,
            "category": "",
            "user_id": user_id,
            "channel_id": channel.id,
            "created_at": now_iso,
            "last_activity": now_iso,
            "auto_close_warned": {},
            "closed": False,
        }
        _save_tickets(tickets)

        embed = discord.Embed(
            title="Ticket Created",
            description=f"Hello {interaction.user.mention}!\nA team member will take care of you shortly.\n\nPlease describe your issue as accurately as possible.",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"{BOT_NAME} - Ticket System")

        close_view = TicketCloseView()
        await channel.send(f"{interaction.user.mention}", embed=embed, view=close_view)

        categories = _load_ticket_categories()
        if categories:
            msg = await channel.send("📋 **Please select a topic for your ticket:**")
            cat_view = TicketCategorySelectView(categories, msg, int(user_id))
            await msg.edit(view=cat_view)

        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories):
        options = []
        for key, cat in categories.items():
            options.append(discord.SelectOption(
                label=cat["label"],
                description=cat.get("description", ""),
                emoji=cat.get("emoji"),
                value=key,
            ))
        super().__init__(
            placeholder="Select a topic...",
            min_values=1, max_values=1,
            options=options,
        )

    async def callback(self, interaction):
        category_key = self.values[0]
        ticket_key = str(interaction.channel_id)
        print(f"Ticket category selected: {category_key} in channel {ticket_key}")

        await interaction.response.defer(ephemeral=True)

        role_ids = _get_ticket_category_role_ids(category_key)
        print(f"Category role IDs: {role_ids}")

        for rid in role_ids:
            role = interaction.guild.get_role(rid)
            if role:
                try:
                    await interaction.channel.set_permissions(
                        role, view_channel=True, send_messages=True, read_message_history=True
                    )
                    print(f"Set permissions for role {role.name} ({rid})")
                except Exception as e:
                    print(f"Error setting permissions for role {rid}: {e}")
            else:
                print(f"Role {rid} not found in guild")

        tickets = _load_tickets()
        if ticket_key in tickets:
            tickets[ticket_key]["category"] = category_key
            _save_tickets(tickets)

        try:
            await interaction.edit_original_message(view=None)
        except Exception as e:
            print(f"Error removing view: {e}")

        cat_label = next(
            (c["label"] for c in _load_ticket_categories().values() if c.get("label")),
            category_key,
        )
        await interaction.followup.send(f"Topic set to **{cat_label}**!", ephemeral=True)


class TicketCategorySelectView(discord.ui.View):
    def __init__(self, categories, msg, owner_id):
        super().__init__(timeout=300)
        self.msg = msg
        self.owner_id = owner_id
        if categories:
            self.add_item(TicketCategorySelect(categories))

    async def on_timeout(self):
        try:
            await self.msg.delete()
        except:
            pass
        user = client.get_user(self.owner_id)
        if user:
            try:
                await user.send(
                    "Please select a topic for your ticket using the dropdown in the ticket channel, or ask a staff member to set it."
                )
            except:
                pass


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="persistent:ticket_close")
    async def close_ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        ticket_key = str(interaction.channel_id)
        tickets = _load_tickets()
        ticket_data = tickets.get(ticket_key)

        if not ticket_data or ticket_data.get("closed"):
            await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
            return

        staff_role_ids = _get_ticket_staff_role_ids()
        user_roles = [r.id for r in interaction.user.roles]
        is_staff = any(rid in user_roles for rid in staff_role_ids)
        is_owner = str(interaction.user.id) == ticket_data.get("user_id")

        if not is_staff and not is_owner:
            await interaction.response.send_message("You don't have permission to close this ticket.", ephemeral=True)
            return

        await interaction.response.defer()
        await _close_and_cleanup(interaction.channel, ticket_key, interaction.user.id)


INACTIVITY_LIMIT = 48 * 3600

ticket = discord.SlashCommandGroup("ticket", "Ticket system commands")

@ticket.command(description="Create a ticket panel")
async def panel(ctx):
    if not await require_permission(ctx, "ticket"):
        return

    if TICKET_CATEGORY_ID is None:
        await ctx.respond("Ticket category not configured. Set TICKET_CATEGORY_ID in .env.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Ticket System",
        description="Click **Create Ticket** to open a new ticket.\n\nA team member will then take care of your request.",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"{BOT_NAME} - Ticket System")

    view = TicketCreateView()
    await ctx.respond(embed=embed, view=view)


@ticket.command(description="Close a ticket")
async def close(ctx):
    ticket_key = str(ctx.channel_id)
    tickets = _load_tickets()
    ticket_data = tickets.get(ticket_key)

    if not ticket_data or ticket_data.get("closed"):
        await ctx.respond("This is not an open ticket channel.", ephemeral=True)
        return

    staff_role_ids = _get_ticket_staff_role_ids()
    user_roles = [r.id for r in ctx.author.roles]
    is_staff = any(rid in user_roles for rid in staff_role_ids)
    is_owner = str(ctx.author.id) == ticket_data.get("user_id")

    if not is_staff and not is_owner:
        await ctx.respond("You don't have permission to close this ticket.", ephemeral=True)
        return

    await ctx.defer()
    await _close_and_cleanup(ctx.channel, ticket_key, ctx.author.id)


@ticket.command(description="Add a user to the ticket")
async def add(ctx, user: discord.Member):
    tickets = _load_tickets()
    ticket_key = str(ctx.channel_id)
    ticket_data = tickets.get(ticket_key)

    if not ticket_data or ticket_data.get("closed"):
        await ctx.respond("This is not an open ticket channel.", ephemeral=True)
        return

    staff_role_ids = _get_ticket_staff_role_ids()
    user_roles = [r.id for r in ctx.author.roles]
    if not any(rid in user_roles for rid in staff_role_ids):
        await ctx.respond("You don't have permission to manage this ticket.", ephemeral=True)
        return

    if str(user.id) == ticket_data.get("user_id"):
        await ctx.respond("You cannot remove the ticket creator.", ephemeral=True)
        return

    overwrites = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    await ctx.channel.set_permissions(user, overwrite=overwrites)
    await ctx.respond(f"{user.mention} has been added to the ticket.")


@ticket.command(description="Remove a user from the ticket")
async def remove(ctx, user: discord.Member):
    tickets = _load_tickets()
    ticket_key = str(ctx.channel_id)
    ticket_data = tickets.get(ticket_key)

    if not ticket_data or ticket_data.get("closed"):
        await ctx.respond("This is not an open ticket channel.", ephemeral=True)
        return

    staff_role_ids = _get_ticket_staff_role_ids()
    user_roles = [r.id for r in ctx.author.roles]
    if not any(rid in user_roles for rid in staff_role_ids):
        await ctx.respond("You don't have permission to manage this ticket.", ephemeral=True)
        return

    if str(user.id) == ticket_data.get("user_id"):
        await ctx.respond("You cannot remove the ticket creator.", ephemeral=True)
        return

    await ctx.channel.set_permissions(user, overwrite=None)
    await ctx.respond(f"{user.mention} has been removed from the ticket.")


client.add_application_command(ticket)


async def _ticket_inactivity_check():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(1800)
        tickets = _load_tickets()
        now_dt = datetime.now(GERMAN_TZ)
        now_ts = now_dt.timestamp()
        changed = False

        for key, data in list(tickets.items()):
            if data.get("closed"):
                continue

            channel = client.get_channel(data["channel_id"])
            if not channel:
                data["closed"] = True
                data["closed_at"] = now_dt.isoformat()
                data["closed_by"] = "auto"
                changed = True
                continue

            try:
                last_activity = datetime.fromisoformat(data.get("last_activity", data["created_at"]))
            except:
                last_activity = now_dt
            inactive_seconds = int(now_ts - last_activity.timestamp())

            if inactive_seconds >= INACTIVITY_LIMIT:
                await _close_and_cleanup(channel, key, "auto")
                changed = True
            else:
                remaining = INACTIVITY_LIMIT - inactive_seconds
                remaining_hours = remaining / 3600
                warned = data.get("auto_close_warned", {})
                user_mention = f"<@{data['user_id']}>"

                if remaining_hours <= 0.167 and not warned.get("10m"):
                    await channel.send(f"{user_mention} Your ticket will be closed in **10 minutes** due to inactivity.")
                    data.setdefault("auto_close_warned", {})["10m"] = True
                    changed = True
                elif remaining_hours <= 1 and not warned.get("1h"):
                    await channel.send(f"{user_mention} Your ticket will be closed in **1 hour** due to inactivity.")
                    data.setdefault("auto_close_warned", {})["1h"] = True
                    changed = True
                elif remaining_hours <= 4 and not warned.get("4h"):
                    await channel.send(f"{user_mention} Your ticket will be closed in **4 hours** due to inactivity.")
                    data.setdefault("auto_close_warned", {})["4h"] = True
                    changed = True

        if changed:
            _save_tickets(tickets)

#------
#Lists:
blocks = [
    "Stone",
    "Diamond Block",
    "Grass Block",
    "Oak Wood",
    "Gold Block",
    "Redstone Lamp",
    "Netherite Block"
]

mobs = [
    "Zombie",
    "Creeper",
    "Skeleton",
    "Enderman",
    "Villager",
    "Wither",
    "Pig"
]

minecraft_facts = [
    "Minecraft was developed by Markus 'Notch' Persson in 2009.",
    "The first public version of Minecraft was called 'Minecraft Classic'.",
    "Steve is the default character of Minecraft.",
    "Alex is the second default character, introduced in 2014.",
    "The Ender Dragon is the boss of the End.",
    "Ghasts can shoot fireballs that destroy blocks.",
    "Creepers explode when they get close to the player.",
    "Redstone can be used as a power source and logic system.",
    "Diamonds are one of the rarest materials in the game.",
    "There are over 60 different types of blocks in the game.",
    "Minecraft has different biomes like desert, jungle, and taiga.",
    "The Nether portal is built with obsidian.",
    "Ender pearls can be used to teleport.",
    "Wolves can be tamed and become pets.",
    "Iron golems protect villages from hostile mobs.",
    "Gold tools last less long than iron tools.",
    "The Nether fortress is necessary to find blaze rods.",
    "Slimes only spawn at night or in special slime chunks.",
    "The Sharpness enchantment increases weapon damage.",
    "Fish can be caught with a bucket.",
    "The End has no daylight, only end stone and end biomes.",
    "The map only shows explored areas.",
    "Sheep can be sheared with shears without killing them.",
    "Elytra can be used to glide over long distances.",
    "Netherite is stronger than diamond and does not burn in lava.",
    "Paper is crafted from sugar cane.",
    "Mushrooms only grow in low light or on special blocks.",
    "Chickens lay eggs that can be used for cakes or pies.",
    "There are 16 different colors of wool.",
    "Bees pollinate plants to enable faster growth.",
    "Buried treasure maps can reveal treasures in oceans.",
    "Minecarts can ride on rails and transport items.",
    "Horses can be tamed and ridden.",
    "Zombies burn in sunlight.",
    "Endermen can pick up and place blocks.",
    "The game has a hardcore mode where death is permanent.",
    "Cacti deal damage when touched.",
    "Bats only spawn in dark caves.",
    "The world is nearly infinite, but can be limited to 30 million blocks in Java.",
    "Signs can be used to display text in the world.",
    "The first Minecraft textures were very pixelated.",
    "Sponges can absorb water.",
    "A compass always points to your spawn point.",
    "Most mobs only spawn at light level 7 or lower.",
    "Ladders can be used to climb up and down vertically quickly.",
    "Torches prevent monsters from spawning nearby.",
    "Lava in the Nether is more dangerous than normal lava.",
    "The music in the game was composed by C418.",
    "There are hidden Easter eggs, like the Toast rabbit.",
    "The game world consists of chunks of 16x16 blocks.",
    "Villagers have different professions like blacksmith or farmer.",
    "Slime blocks can be used to build jumping mechanics.",
    "Potions can give temporary effects like healing or speed.",
    "The Wither is a boss that players can summon themselves.",
    "Enchanted books can be applied to tools or armor.",
    "Red flowers have different types, like poppy or tulip.",
    "The Adventure game mode is ideal for maps with tasks.",
    "Wood types differ in color but not in durability.",
    "The Nether has its own biomes like soul sand valleys or bastions.",
    "An anvil can be used to repair and combine items.",
    "Rails and redstone can be used to build automatic transport systems.",
    "Mooshroom is a rare variant of the cow.",
    "Burnt pig or chicken mobs are called Piglins or Hoglins in the Nether.",
    "Cave generation can have different formations like stalactites and stalagmites.",
    "String can be used to craft traps, bows, and fishing rods.",
    "Looting increases the chance of rare drops.",
    "Music discs can be used to play custom sounds in the game."
]

#------
@client.slash_command(description="Test command")
async def testcmd(ctx):
    try:
        embed = discord.Embed(
            title=f"{BOT_NAME} - TestCMD",
            description=f"Hello {ctx.author}",
            colour=0x00b0f4,
            timestamp=datetime.now()
        )
        await ctx.respond(embed=embed, ephemeral=True)
        print(discord.__version__)
        print(ctx.author.roles)
        print([r.id for r in ctx.author.roles])

    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Discord bot help command")
async def help(ctx):
    try:
        embed = discord.Embed(
            title="Command Help List",
            description="Commands:\n\n/help - Shows this view\n/testcmd - TestCommand\n/say - Sends text as a bot message (permission only)\n/dice - Rolls a die\n/coinflip - Flips a coin\n/mcblock - Gives a random block\n/mcmob - Gives a random Minecraft mob\n/mcfact - Gives you a random Minecraft fact\n/bug - Allows you to report a bug\n/webapp - Get access to the web dashboard\n/warn - Warn a user (permission only)\n/roleall - Assign a role to all members (permission only)\n/ticket panel - Create a ticket panel (permission only)\n/ticket close - Close a ticket\n/ticket add - Add a user to the ticket\n/ticket remove - Remove a user from the ticket",
            timestamp=datetime.now()
        )
        embed.set_footer(text=BOT_NAME)
        await ctx.defer(ephemeral=True)
        await ctx.send_followup(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Send text and optionally an image.")
async def say(ctx, text: str, image_url: str = None, image: discord.Attachment = None):
    try:
        if not await require_permission(ctx, "say"):
            return
        await ctx.defer(ephemeral=True)
        await ctx.delete()

        if image_url and image:
            embed = discord.Embed(description=text)
            embed.set_image(url=image_url)
            await ctx.send(embed=embed, file=await image.to_file())
            return

        if image_url:
            embed = discord.Embed(description=text)
            embed.set_image(url=image_url)
            await ctx.send(embed=embed)
            return

        if image:
            await ctx.send(content=text, file=await image.to_file())
            return

        await ctx.send(text)
        
    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Dice command. Roll a die.")
async def dice(ctx):
    try:
        await ctx.defer()
        await ctx.send_followup(f"{ctx.author.mention} rolled a die.")
        await asyncio.sleep(1)
        await ctx.send_followup(f"{ctx.author.mention} rolled {random.randint(1, 6)}!")
    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Coinflip command. Flip a coin.")
async def coinflip(ctx):
    try:
        await ctx.defer()
        await ctx.send_followup(f"{ctx.author.mention} flipped a coin.")
        await asyncio.sleep(1)
        x = random.randint(1, 2)
        if x == 1:
            await ctx.send_followup(f"{ctx.author.mention} got 'Heads'!")
        else:
            await ctx.send_followup(f"{ctx.author.mention} got 'Tails'!")
    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Get a random Minecraft block.")
async def mcblock(ctx):
    try:
        await ctx.respond(f"Here is your random Minecraft block, {ctx.author.mention}. The block is: {random.choice(blocks)}", ephemeral=True)
    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Get a random Minecraft mob.")
async def mcmob(ctx):
    try:
        await ctx.respond(f"Here is your random Minecraft mob, {ctx.author.mention}. The mob is: {random.choice(mobs)}", ephemeral=True)
    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Random facts about Minecraft.")
async def mcfact(ctx):
    try:
        await ctx.defer()
        await ctx.send_followup(f"Here is your random Minecraft fact, {ctx.author.mention}. The fact is: {random.choice(minecraft_facts)}", ephemeral=True)
    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Report a bug using this command.")
async def bug(ctx, your_bug: str):
    try:
        await ctx.defer(ephemeral=True)
        if BUG_CHANNEL_ID is None:
            await ctx.followup.send(
                "BUG_CHANNEL_ID is missing or invalid in the .env file.", ephemeral=True
            )
            return

        channel = client.get_channel(BUG_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title=f"Bug report by {ctx.author}",
                description=f"Bug description:\n\n{your_bug}",
                colour=0xff0000,
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Bug - {BOT_NAME}")

            await channel.send(embed=embed)

            await ctx.followup.send("Bug reported successfully!", ephemeral=True)
        else:
            await ctx.followup.send(
                "The bug channel does not exist or the ID is incorrect.", ephemeral=True
            )
    except Exception as e:
        print(f"An error occurred: {e}")
        await ctx.followup.send(
            "An error occurred while sending the bug report.", ephemeral=True)

@client.slash_command(description="Warn a user")
async def warn(ctx, user: discord.Member, reason: str):
    try:
        if not await require_permission(ctx, "warn"):
            return
        await ctx.defer()
        embed = discord.Embed(
            title="Warning",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )

        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)

        embed.set_footer(text=f"User ID: {user.id}")

        await ctx.send_followup(embed=embed)

        try:
            dm_embed = discord.Embed(
                title="Warning",
                description="You have received a warning.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.set_footer(text=f"User ID: {user.id}")
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Could not send warn DM: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")

@client.slash_command(description="Check your role permissions.")
async def roleperms(ctx, role: discord.Role = None):
    try:
        if _role_config is None:
            _load_role_config()

        roles_cfg = _role_config.get("roles", {})
        commands_cfg = _role_config.get("commands", {})
        prefixes_cfg = _role_config.get("prefixes", {})

        if role:
            target_roles = [role]
        else:
            target_roles = ctx.author.roles

        user_role_ids = {r.id for r in target_roles}
        user_groups = []
        for group_name, group_role_ids in roles_cfg.items():
            if isinstance(group_role_ids, list):
                if any(rid in user_role_ids for rid in group_role_ids):
                    user_groups.append(group_name)
            else:
                if group_role_ids in user_role_ids:
                    user_groups.append(group_name)

        embed = discord.Embed(
            title="Role Permissions",
            colour=0x00b0f4,
            timestamp=datetime.now()
        )

        if role:
            embed.description = f"Permissions for **@{role.name}**"
        else:
            embed.description = f"Your permissions, {ctx.author.mention}"

        if user_groups:
            group_labels = []
            for g in user_groups:
                prefix = prefixes_cfg.get(g, "")
                if prefix:
                    group_labels.append(f"{prefix} **{g}**")
                else:
                    group_labels.append(f"**{g}**")
            embed.add_field(
                name="Role Groups",
                value=", ".join(group_labels),
                inline=False
            )
        else:
            embed.add_field(name="Role Groups", value="None", inline=False)

        accessible_commands = []
        for cmd_name, required_groups in commands_cfg.items():
            if any(g in user_groups for g in required_groups):
                accessible_commands.append(f"`/{cmd_name}`")

        if accessible_commands:
            embed.add_field(
                name="Accessible Commands",
                value=", ".join(accessible_commands),
                inline=False
            )
        else:
            embed.add_field(name="Accessible Commands", value="None", inline=False)

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        await ctx.respond(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"An error occurred in roleperms: {e}")
        await ctx.respond("An error occurred.", ephemeral=True)


@client.slash_command(description="Set DevCoder status (owners only)")
async def devcoderstatus(ctx, status: str):
    try:
        global _devcoder_config
        owner_ids = _devcoder_config.get("owner_ids", [])
        if ctx.author.id not in owner_ids:
            await ctx.respond("You do not have permission to use this command.", ephemeral=True)
            return
        _devcoder_config["current_status"] = status
        _save_devcoder_config(_devcoder_config)
        await ctx.respond(f"DevCoder status set to: **{status}**", ephemeral=True)
    except Exception as e:
        print(f"An error occurred in devcoderstatus: {e}")
        await ctx.respond("An error occurred.", ephemeral=True)


@client.slash_command(description="Add a role to every user with a single command.")
async def roleall(ctx, role: discord.Role):
    try:
        if not await require_permission(ctx, "roleall"):
            return

        count = 0

        for member in ctx.guild.members:
            if role not in member.roles:
                try:
                    await member.add_roles(role)
                    count += 1

                    await asyncio.sleep(0.5)

                except discord.Forbidden:
                    continue

        await ctx.respond(f"Role has been assigned to **{count}** members.")

    except Exception as e:
        print(f"An error occurred: {e}")
        await ctx.respond("An error occurred.")


@client.slash_command(description="Get access to the web dashboard")
async def webapp(ctx):
    await ctx.defer(ephemeral=True)
    try:
        from dashboard.database import init_db
        init_db()
    except Exception:
        pass
    if not ctx.guild:
        await ctx.send_followup("This command can only be used on a server.", ephemeral=True)
        return
    from dashboard.auth import create_login_code
    DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:6062")

    role_config = _load_role_config()
    roles_cfg = role_config.get("roles", {})
    admin_groups = ["owner", "dev", "manager", "sr-admin", "admin"]
    user_role_ids = {r.id for r in ctx.author.roles}
    authorized = False
    for group_name in admin_groups:
        group_ids = roles_cfg.get(group_name, [])
        if isinstance(group_ids, list):
            if any(rid in user_role_ids for rid in group_ids):
                authorized = True
                break
        else:
            if group_ids in user_role_ids:
                authorized = True
                break

    if authorized:
        code = await create_login_code(str(ctx.author.id), str(ctx.author), "en")
        msg = (
            f"Your dashboard login code: **{code}**\n"
            f"Open: {DASHBOARD_URL}/login?code={code}\n"
            f"Code expires in 5 minutes."
        )
        try:
            await ctx.author.send(msg)
            await ctx.send_followup("Check your DMs! Code sent.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send_followup(
                f"Code: **{code}**\n{DASHBOARD_URL}/login?code={code}",
                ephemeral=True,
            )
    else:
        await ctx.send_followup(
            f"Visit the GlazeSMP info page: {DASHBOARD_URL}/guest",
            ephemeral=True,
        )


import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cogs.translate import TranslateCog
from cogs.voice_admin import VoiceAdminCog
client.add_cog(TranslateCog(client))
client.add_cog(VoiceAdminCog(client))

if not TOKEN:
    raise RuntimeError("TOKEN missing in the .env file.")

async def start_dashboard():
    try:
        try:
            import multipart
        except ImportError:
            print("WARNING: python-multipart not installed. Form parsing (login) will fail.")
            print("Install: pip install python-multipart")

        from dashboard.database import init_db
        from dashboard.server import create_app
        init_db()
        app = create_app(client)
        import uvicorn
        config = uvicorn.Config(app, host="0.0.0.0", port=6062, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        print(f"DASHBOARD STARTUP ERROR: {e}")
        import traceback
        traceback.print_exc()


async def main():
    await asyncio.gather(
        client.start(TOKEN),
        start_dashboard(),
    )

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("TOKEN missing in the .env file.")
    asyncio.run(main())
