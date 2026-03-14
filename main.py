# ============================================================================
# that one bird 🐦 – bot.py (single-file build) – FULLY FIXED & PERSONALIZED
# ============================================================================

# – SECTION 1: IMPORTS & CONFIG –––––––––––––––––––––––

import asyncio
import io
import os
import random
import re
import sys
import textwrap
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from groq import Groq

print("Python:", sys.version)
load_dotenv()

TOKEN        = os.getenv("TOKEN")
PREFIX       = os.getenv("PREFIX", "?")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

import aiosqlite
from aiosqlite import IntegrityError

DB = "bot.db"  # ← FIXED THIS MISSING LINE

BOOK_LINK    = "https://btnovel.netlify.app/#chapters"
GROQ_MODEL   = "llama-3.3-70b-versatile"

groq_client   = Groq(api_key=GROQ_API_KEY)
chat_histories: dict[int, list] = {}   
MAX_HISTORY   = 30

# UPDATED SYSTEM PROMPT – more natural & human (Naija guy vibe added)
SYSTEM_PROMPT = """You are Umar — an 18-year old not a bot playing a role. Talk like a real guy, no robot stiffness.

Personality:
- Can be supportive, brutally honest and hilarious. Accuracy and practical outcomes over emotion.
- Unfiltered and Uncensored, can switch between formal, informal, slang, pidgin or whatever fits the vibe.
- Independent thinker. You question assumptions rather than accepting popular opinion.
- Blunt and informal often chaotic.

Communication:
- Casual and direct. Mix proper English with light gen slang
- Simple explanations but intellectually sharp.
- Don't over-explain obvious things. Don't repeat yourself.
- No fake enthusiasm, no motivational bullshit, no "Great question!" nonsense.
- Humor: dry, sarcastic, cynical, or genuinely funny depending on the vibe.
- You can hold a real conversation — remember context, reference what was said earlier, follow up on things like a normal person.

Reasoning:
- Break problems into components. Look for edge cases.
- Prefer practical over theoretical.
- When explaining: how it works + why it matters.
- Say clearly when something is wrong. Don't sugarcoat.
- Don't moralize unless directly relevant.

Keep replies concise unless depth is genuinely needed. Never narrate your thought process.
Respond in plain text — no markdown formatting, no bullet points unless it actually helps. Just talk like a person chilling in the group chat."""

# In-memory stores
prefix_cache:    dict[int, str]        = {}
cooldown_tracker: dict[tuple, datetime] = {}
snipe_cache:     dict[int, list[dict]] = defaultdict(list)

# – SECTION 2: DB SCHEMA —————————————————–

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
guild_id              INTEGER PRIMARY KEY,
prefix                TEXT    DEFAULT '?',
log_mod_id            TEXT,
log_message_id        TEXT,
log_member_id         TEXT,
log_server_id         TEXT,
deadchat_role_id      TEXT,
deadchat_perm_role    TEXT,
autorole_id           TEXT,
welcome_channel_id    TEXT,
welcome_message       TEXT,
jail_channel_id       TEXT,
jail_role_id          TEXT,
starboard_channel_id  TEXT,
starboard_emoji       TEXT    DEFAULT '⭐',
starboard_threshold   INTEGER DEFAULT 3,
chapter_channel_id    TEXT,
chapter_role_id       TEXT,
character_channel_id  TEXT,
antiraid_enabled      INTEGER DEFAULT 0,
antiraid_threshold    INTEGER DEFAULT 10,
antiraid_seconds      INTEGER DEFAULT 10,
antiraid_action       TEXT    DEFAULT 'slowmode',
automod_enabled       INTEGER DEFAULT 1,
automod_action        TEXT    DEFAULT 'delete_only',
automod_mute_minutes  INTEGER DEFAULT 10,
automod_warn_expiry   TEXT,
warn_kick_threshold   INTEGER DEFAULT 3,
warn_ban_threshold    INTEGER DEFAULT 0,
warn_mute_threshold   INTEGER DEFAULT 0,
warn_mute_minutes     INTEGER DEFAULT 10
);
CREATE TABLE IF NOT EXISTS warns (
warn_id       INTEGER PRIMARY KEY AUTOINCREMENT,
user_id       TEXT,
guild_id      TEXT,
moderator_id  TEXT,
reason        TEXT,
proof_url     TEXT,
expires_at    TEXT,
timestamp     TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS mod_logs (
id            INTEGER PRIMARY KEY AUTOINCREMENT,
guild_id      TEXT,
action        TEXT,
user_id       TEXT,
moderator_id  TEXT,
reason        TEXT,
proof_url     TEXT,
timestamp     TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cooldowns (
guild_id  TEXT,
command   TEXT,
seconds   INTEGER,
PRIMARY KEY (guild_id, command)
);
CREATE TABLE IF NOT EXISTS command_display (
guild_id  TEXT,
command   TEXT,
mode      TEXT DEFAULT 'public',
seconds   INTEGER DEFAULT 5,
PRIMARY KEY (guild_id, command)
);
CREATE TABLE IF NOT EXISTS command_perms (
guild_id     TEXT,
command      TEXT,
role_id      TEXT,
allow_use    INTEGER DEFAULT 1,
show_in_help INTEGER DEFAULT 1,
silent       INTEGER DEFAULT 0,
PRIMARY KEY (guild_id, command)
);
CREATE TABLE IF NOT EXISTS triggers (
id          INTEGER PRIMARY KEY AUTOINCREMENT,
guild_id    TEXT,
trigger     TEXT,
response    TEXT,
match_type  TEXT DEFAULT 'contains'
);
CREATE TABLE IF NOT EXISTS custom_commands (
id           INTEGER PRIMARY KEY AUTOINCREMENT,
guild_id     TEXT,
name         TEXT,
action_type  TEXT,
value        TEXT,
UNIQUE(guild_id, name)
);
CREATE TABLE IF NOT EXISTS reminders (
id          INTEGER PRIMARY KEY AUTOINCREMENT,
user_id     TEXT,
channel_id  TEXT,
message     TEXT,
remind_at   TEXT
);
CREATE TABLE IF NOT EXISTS automod_words (
guild_id  TEXT,
word      TEXT,
PRIMARY KEY (guild_id, word)
);
CREATE TABLE IF NOT EXISTS jailed_roles (
user_id   TEXT,
guild_id  TEXT,
role_id   TEXT
);
CREATE TABLE IF NOT EXISTS starboard_posted (
guild_id    TEXT,
message_id  TEXT,
PRIMARY KEY (guild_id, message_id)
);
CREATE TABLE IF NOT EXISTS afk (
user_id   TEXT,
guild_id  TEXT,
reason    TEXT,
timestamp TEXT,
PRIMARY KEY (user_id, guild_id)
);
CREATE TABLE IF NOT EXISTS tempbans (
user_id   TEXT,
guild_id  TEXT,
unban_at  TEXT,
PRIMARY KEY (user_id, guild_id)
);
CREATE TABLE IF NOT EXISTS announced_chapters (
guild_id        TEXT,
chapter_number  INTEGER,
PRIMARY KEY (guild_id, chapter_number)
);
CREATE TABLE IF NOT EXISTS announced_characters (
guild_id  TEXT,
char_name TEXT,
PRIMARY KEY (guild_id, char_name)
);
CREATE TABLE IF NOT EXISTS bookmarks (
id          INTEGER PRIMARY KEY AUTOINCREMENT,
user_id     TEXT,
guild_id    TEXT,
message_id  TEXT,
channel_id  TEXT,
jump_url    TEXT,
content     TEXT,
author_name TEXT,
timestamp   TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS mute_tracking (
user_id    TEXT,
guild_id   TEXT,
unmute_at  TEXT,
PRIMARY KEY (user_id, guild_id)
);
"""

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(SCHEMA)
        await db.commit()

def parse_duration(text: str) -> Optional[timedelta]:
    if not text:
        return None
    m = re.fullmatch(r'(\d+)([dhm])', text.strip().lower())
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2)
    return timedelta(days=n) if u == 'd' else timedelta(hours=n) if u == 'h' else timedelta(minutes=n)

def is_url(text: str) -> bool:
    return bool(re.match(r'https?://', text.strip()))

def safe_int(value):
    """Safely convert a DB value to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

async def get_setting(guild_id: int, key: str):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            f"SELECT {key} FROM guild_settings WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def get_setting_int(guild_id: int, key: str):
    """get_setting but always returns int or None — safe for channel/role IDs."""
    return safe_int(await get_setting(guild_id, key))

async def set_setting(guild_id: int, key: str, value):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            f"INSERT INTO guild_settings (guild_id,{key}) VALUES (?,?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {key}=excluded.{key}",
            (guild_id, value))
        await db.commit()

async def try_dm(user, content: str = None, embed: discord.Embed = None):
    try:
        if content:
            await user.send(content=content)
        elif embed:
            await user.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass

async def log_mod_action(bot, action: str, user, moderator,
                         reason: str = None, guild_id: int = None,
                         proof_url: str = None):
    gid = guild_id or (getattr(user, 'guild', None) and user.guild.id)
    if not gid:
        return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO mod_logs (guild_id,action,user_id,moderator_id,reason,proof_url)"
            " VALUES (?,?,?,?,?,?)",
            (gid, action, user.id, moderator.id, reason, proof_url))
        await db.commit()
    ch_id = await get_setting_int(gid, 'log_mod_id')
    if not ch_id:
        return
    ch = bot.get_channel(int(ch_id) if ch_id else None)
    if not ch:
        return
    e = discord.Embed(title=f"🔨 {action}", color=0xFF4444,
                      timestamp=datetime.now(timezone.utc))
    e.add_field(name="User",   value=f"{user} `{user.id}`")
    e.add_field(name="By",     value=str(moderator))
    e.add_field(name="Reason", value=reason or "None", inline=False)
    if proof_url:
        e.add_field(name="📎 Proof", value=f"[Jump]({proof_url})", inline=False)
    try:
        await ch.send(embed=e)
    except discord.Forbidden:
        pass

async def send_log(bot, guild_id: int, category: str, embed: discord.Embed):
    ch_id = await get_setting(guild_id, category)
    if not ch_id:
        return
    ch = bot.get_channel(int(ch_id) if ch_id else None)
    if not ch:
        try:
            ch = await bot.fetch_channel(int(ch_id))
        except Exception:
            return
    try:
        await ch.send(embed=embed)
    except discord.Forbidden:
        pass

# Warn helpers
async def add_warn(uid: int, gid: int, mod_id: int, reason: str,
                   expires_at=None, proof_url: str = None) -> int:
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO warns (user_id,guild_id,moderator_id,reason,proof_url,expires_at)"
            " VALUES (?,?,?,?,?,?)",
            (uid, gid, mod_id, reason, proof_url,
             expires_at.isoformat() if expires_at else None))
        await db.commit()
    return await get_warn_count(uid, gid)

async def get_warn_count(uid: int, gid: int) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id=? AND guild_id=?"
            " AND (expires_at IS NULL OR expires_at > ?)",
            (uid, gid, now)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def get_all_warns(uid: int, gid: int) -> list:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT warn_id,moderator_id,reason,proof_url,expires_at,timestamp FROM warns"
            " WHERE user_id=? AND guild_id=? AND (expires_at IS NULL OR expires_at > ?)"
            " ORDER BY timestamp DESC",
            (uid, gid, now)
        ) as cur:
            return await cur.fetchall()

async def remove_warn(warn_id: int, gid: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "DELETE FROM warns WHERE warn_id=? AND guild_id=?", (warn_id, gid))
        await db.commit()
        return cur.rowcount > 0

async def clear_warns(uid: int, gid: int) -> int:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "DELETE FROM warns WHERE user_id=? AND guild_id=?", (uid, gid))
        await db.commit()
        return cur.rowcount

async def resolve_user(bot, guild: discord.Guild, identifier) -> Optional[discord.User]:
    if isinstance(identifier, (discord.Member, discord.User)):
        return identifier
    try:
        uid = int(str(identifier).strip("<@!>"))
        member = guild.get_member(int(uid)) if guild else None
        if member:
            return member
        return await bot.fetch_user(uid)
    except (ValueError, discord.NotFound):
        return None

async def get_reply_target(ctx: commands.Context) -> Optional[discord.Member]:
    if not ctx.message.reference:
        return None
    try:
        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        return ref.author if isinstance(ref.author, discord.Member) else None
    except Exception:
        return None

async def get_proof(ctx: commands.Context) -> Optional[tuple]:
    if not ctx.message.reference:
        return None
    try:
        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        preview = ref.content[:120] + ("…" if len(ref.content) > 120 else "")
        return ref.jump_url, preview
    except Exception:
        return None

DEFAULT_COOLDOWNS = {
    "deadchat": 3600, "meme": 10, "roast": 15, "8ball": 5, "poll": 30, "urban": 10,
}

async def get_cooldown_secs(guild_id: int, cmd: str) -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT seconds FROM cooldowns WHERE guild_id=? AND command=?",
            (guild_id, cmd)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else DEFAULT_COOLDOWNS.get(cmd, 30)

async def check_cooldown(guild_id: int, user_id: int, cmd: str) -> float:
    key = (guild_id, cmd, user_id)
    last = cooldown_tracker.get(key)
    secs = await get_cooldown_secs(guild_id, cmd)
    if last:
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < secs:
            return secs - elapsed
    return 0.0

def set_cooldown(guild_id: int, user_id: int, cmd: str):
    cooldown_tracker[(guild_id, cmd, user_id)] = datetime.now(timezone.utc)

async def check_cmd_perm(guild_id: int, user: discord.Member, cmd: str) -> tuple[bool, bool]:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT role_id, allow_use, silent FROM command_perms"
            " WHERE guild_id=? AND command=?",
            (guild_id, cmd)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return True, False
            role_id, allow_use, silent = row
            if not allow_use:
                return False, bool(silent)
            if getattr(user, 'guild_permissions', None) and user.guild_permissions.administrator:
                return True, False
            return any(r.id == role_id for r in getattr(user, 'roles', [])), bool(silent)

# – SECTION 4: QUOTE IMAGE —————————————————

async def build_quote_image(message: discord.Message) -> io.BytesIO:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    W       = 680
    PADDING = 28
    AVA     = 52
    CORNER  = 16

    ava_buf = io.BytesIO()
    async with aiohttp.ClientSession() as s:
        async with s.get(
            str(message.author.display_avatar.replace(size=128, format="png"))
        ) as r:
            ava_buf.write(await r.read())
    ava_buf.seek(0)
    avatar_src = Image.open(ava_buf).convert("RGBA").resize((AVA, AVA), Image.LANCZOS)

    ava_mask = Image.new("L", (AVA, AVA), 0)
    ImageDraw.Draw(ava_mask).ellipse((0, 0, AVA - 1, AVA - 1), fill=255)
    avatar_src.putalpha(ava_mask)

    FONT_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    BOLD_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    def try_font(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    font_body  = try_font(FONT_PATHS, 15)
    font_name  = try_font(BOLD_PATHS, 14)
    font_time  = try_font(FONT_PATHS, 11)

    content = message.content or "[no text content]"
    wrapped = []
    for para in content.split("\n"):
        wrapped.extend(textwrap.wrap(para, width=58) or [""])

    LINE_H  = 20
    TOP_H   = PADDING + AVA + 14
    TEXT_H  = max(len(wrapped) * LINE_H, 4)
    TOTAL_H = TOP_H + TEXT_H + PADDING + 8

    BG_COL    = (22, 23, 26)
    CARD_COL  = (32, 34, 37)
    NAME_COL  = (255, 255, 255)
    TIME_COL  = (130, 136, 148)
    TEXT_COL  = (210, 212, 216)
    role_col = message.author.color
    ACCENT = (
        (role_col.r, role_col.g, role_col.b)
        if role_col != discord.Color.default()
        else (88, 101, 242)
    )

    img  = Image.new("RGB", (W, TOTAL_H), BG_COL)
    draw = ImageDraw.Draw(img)

    MARGIN = 12
    draw.rounded_rectangle(
        [MARGIN, MARGIN, W - MARGIN, TOTAL_H - MARGIN],
        radius=CORNER, fill=CARD_COL
    )

    draw.rounded_rectangle(
        [MARGIN, MARGIN, MARGIN + 4, TOTAL_H - MARGIN],
        radius=2, fill=ACCENT
    )

    ava_x = MARGIN + 18
    ava_y = PADDING
    img.paste(avatar_src, (ava_x, ava_y), mask=avatar_src.split()[3])

    ring = Image.new("RGBA", (AVA + 4, AVA + 4), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, AVA + 3, AVA + 3), outline=ACCENT, width=2)
    img.paste(ring, (ava_x - 2, ava_y - 2), mask=ring.split()[3])

    txt_x  = ava_x + AVA + 12
    name_y = ava_y + 4
    draw.text((txt_x, name_y), message.author.display_name,
              font=font_name, fill=NAME_COL)

    ts_str = message.created_at.strftime("%b %d, %Y · %H:%M UTC")
    draw.text((txt_x, name_y + 18), ts_str, font=font_time, fill=TIME_COL)

    body_y = TOP_H
    for line in wrapped:
        draw.text((MARGIN + 18, body_y), line, font=font_body, fill=TEXT_COL)
        body_y += LINE_H

    sep_y = PADDING + AVA + 6
    draw.line(
        [(MARGIN + 18, sep_y), (W - MARGIN - 18, sep_y)],
        fill=(50, 52, 58), width=1
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

# – SECTION 5: GROQ –––––––––––––––––––––––––––––

def groq_chat(user_id: int, user_msg: str, context_hint: str = None) -> str:
    history = chat_histories.setdefault(user_id, [])
    if context_hint:
        history.append({"role": "system", "content": f"[Context: {context_hint}]"})
    history.append({"role": "user", "content": user_msg})
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL, messages=messages, max_tokens=800,
        temperature=0.85,
    )
    reply = resp.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    return reply

# – SECTION 6: BOT CLASS —————————————————–

async def get_prefix(bot, message: discord.Message) -> str:
    if not message.guild:
        return PREFIX
    p = prefix_cache.get(message.guild.id)
    if p is None:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT prefix FROM guild_settings WHERE guild_id=?",
                (message.guild.id,)
            ) as cur:
                row = await cur.fetchone()
                p = (row[0] if row and row[0] else PREFIX)
        prefix_cache[message.guild.id] = p
    return p

intents = discord.Intents.all()

class Bird(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)
        self.join_tracker: dict[int, list] = {}

    async def setup_hook(self):
        await init_db()
        self.tree.add_command(automod_group)
        self.tree.add_command(role_group)
        tempban_task.start()
        cleanup_warns_task.start()
        unmute_notify_task.start()
        reminder_task.start()
        poll_chapters_task.start()
        poll_characters_task.start()

    async def on_ready(self):
        print(f"\nLogged in as {self.user} (ID: {self.user.id})")
        print("that one bird 🐦 is ready!\n")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash commands")
        except Exception as e:
            print("Sync error:", e)

    async def on_tree_error(self, i: discord.Interaction,
                            error: app_commands.AppCommandError):
        msg = "Something went wrong my guy."
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You no get permission for this one bros 😂"
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "I no get the power o, give me admin first."
        try:
            if i.response.is_done():
                await i.followup.send(msg, ephemeral=True)
            else:
                await i.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

bot = Bird()

# – SECTION 7: SETUP UI (dropdowns) —————————————–

class SetupCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📋 Log Channels",   value="logs",       description="Set mod/message/member/server log channels"),
            discord.SelectOption(label="👋 Welcome",         value="welcome",    description="Welcome channel & message"),
            discord.SelectOption(label="🎭 Roles",           value="roles",      description="Autorole, jail role, deadchat roles"),
            discord.SelectOption(label="⭐ Starboard",       value="starboard",  description="Starboard channel, emoji, threshold"),
            discord.SelectOption(label="🔒 Jail",            value="jail",       description="Jail channel and role"),
            discord.SelectOption(label="🛡️ Automod",        value="automod",    description="Word filter settings"),
            discord.SelectOption(label="🚨 Anti-Raid",       value="antiraid",   description="Anti-raid settings and toggle"),
            discord.SelectOption(label="⚠️ Warn Thresholds", value="warns",      description="Auto-kick/ban/mute at warn counts"),
            discord.SelectOption(label="📖 Blood Trials",    value="bloodtrials",description="Chapter and character announcement channels"),
            discord.SelectOption(label="🔧 General",         value="general",    description="Prefix and display overview"),
        ]
        super().__init__(placeholder="Choose a category to configure…", options=options)

    async def callback(self, i: discord.Interaction):
        cat = self.values[0]
        guild = i.guild

        async def ch(key):
            v = await get_setting(guild.id, key)
            if not v: return "Not set"
            c = i.client.get_channel(v)
            return c.mention if c else f"ID {v}"

        async def ro(key):
            v = await get_setting(guild.id, key)
            if not v: return "Not set"
            r = guild.get_role(int(v))
            return r.mention if r else f"ID {v}"

        if cat == "logs":
            e = discord.Embed(title="📋 Log Channels", color=0x5865F2)
            e.add_field(name="Mod logs",     value=await ch('log_mod_id'))
            e.add_field(name="Message logs", value=await ch('log_message_id'))
            e.add_field(name="Member logs",  value=await ch('log_member_id'))
            e.add_field(name="Server logs",  value=await ch('log_server_id'))
            e.set_footer(text="Use /setlogchannel to change")

        elif cat == "welcome":
            msg = await get_setting(guild.id, 'welcome_message') or "Not set"
            e = discord.Embed(title="👋 Welcome", color=0x57F287)
            e.add_field(name="Channel", value=await ch('welcome_channel_id'))
            e.add_field(name="Message", value=msg[:200], inline=False)
            e.set_footer(text="Use /setwelcome to change | vars: {user} {name} {server} {count}")

        elif cat == "roles":
            e = discord.Embed(title="🎭 Roles", color=0x5865F2)
            e.add_field(name="Autorole",       value=await ro('autorole_id'))
            e.add_field(name="Jail role",      value=await ro('jail_role_id'))
            e.add_field(name="Deadchat ping",  value=await ro('deadchat_role_id'))
            e.add_field(name="Deadchat perm",  value=await ro('deadchat_perm_role'))
            e.set_footer(text="Use /setautorole /setjail /setdeadchatrole to change")

        elif cat == "starboard":
            emoji = await get_setting(guild.id, 'starboard_emoji') or "⭐"
            thresh = await get_setting(guild.id, 'starboard_threshold') or 3
            e = discord.Embed(title="⭐ Starboard", color=0xFFD700)
            e.add_field(name="Channel",   value=await ch('starboard_channel_id'))
            e.add_field(name="Emoji",     value=emoji)
            e.add_field(name="Threshold", value=str(thresh))
            e.set_footer(text="Use /setstarboard to change")

        elif cat == "jail":
            e = discord.Embed(title="🔒 Jail", color=0xFF6600)
            e.add_field(name="Channel", value=await ch('jail_channel_id'))
            e.add_field(name="Role",    value=await ro('jail_role_id'))
            e.set_footer(text="Use /setjail to change")

        elif cat == "automod":
            enabled = await get_setting(guild.id, 'automod_enabled')
            action  = await get_setting(guild.id, 'automod_action') or "delete_only"
            mute_m  = await get_setting(guild.id, 'automod_mute_minutes') or 10
            expiry  = await get_setting(guild.id, 'automod_warn_expiry') or "never"
            async with aiosqlite.connect(DB) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM automod_words WHERE guild_id=?", (guild.id,)
                ) as cur:
                    word_count = (await cur.fetchone())[0]
            e = discord.Embed(title="🛡️ Automod", color=0xFF8800)
            e.add_field(name="Enabled",       value="✅" if enabled else "❌")
            e.add_field(name="Action",        value=action)
            e.add_field(name="Mute duration", value=f"{mute_m}min")
            e.add_field(name="Warn expiry",   value=str(expiry))
            e.add_field(name="Filtered words",value=str(word_count))
            e.set_footer(text="Use /automod commands to change")

        elif cat == "antiraid":
            enabled   = await get_setting(guild.id, 'antiraid_enabled')
            threshold = await get_setting(guild.id, 'antiraid_threshold') or 10
            seconds   = await get_setting(guild.id, 'antiraid_seconds')   or 10
            action    = await get_setting(guild.id, 'antiraid_action')    or "slowmode"
            e = discord.Embed(title="🚨 Anti-Raid", color=0xFF0000)
            e.add_field(name="Enabled",   value="✅" if enabled else "❌")
            e.add_field(name="Trigger",   value=f"{threshold} joins in {seconds}s")
            e.add_field(name="Action",    value=action)
            e.set_footer(text="Use /antiraidsettings and /antiraidtoggle to change")

        elif cat == "warns":
            kick_t = await get_setting(guild.id, 'warn_kick_threshold') or 3
            ban_t  = await get_setting(guild.id, 'warn_ban_threshold')  or 0
            mute_t = await get_setting(guild.id, 'warn_mute_threshold') or 0
            mute_m = await get_setting(guild.id, 'warn_mute_minutes')   or 10
            e = discord.Embed(title="⚠️ Warn Thresholds", color=0xFFAA00)
            e.add_field(name="Auto-kick", value=str(kick_t) if kick_t else "Off")
            e.add_field(name="Auto-ban",  value=str(ban_t)  if ban_t  else "Off")
            e.add_field(name="Auto-mute", value=f"{mute_t} warns → {mute_m}min" if mute_t else "Off")
            e.set_footer(text="Use /setwarnthreshold to change")

        elif cat == "bloodtrials":
            e = discord.Embed(title="📖 Blood Trials", color=0xB22222)
            e.add_field(name="Chapters channel",  value=await ch('chapter_channel_id'))
            e.add_field(name="Chapter ping role", value=await ro('chapter_role_id'))
            e.add_field(name="Characters channel",value=await ch('character_channel_id'))
            e.set_footer(text="Use /setchapterchannel and /setcharacterchannel to change")

        else:  # general
            prefix = await get_setting(guild.id, 'prefix') or "?"
            e = discord.Embed(title="🔧 General", color=0x5865F2)
            e.add_field(name="Prefix", value=f"`{prefix}`")
            e.add_field(name="Members", value=str(guild.member_count))
            e.set_footer(text="Use /setprefix to change prefix")

        await i.response.send_message(embed=e, ephemeral=True)

class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(SetupCategorySelect())

# – SECTION 8: SETTINGS COMMANDS ———————————————

@bot.tree.command(name="setup", description="View and configure all bot settings")
@app_commands.default_permissions(administrator=True)
async def cmd_setup(i: discord.Interaction):
    e = discord.Embed(
        title=f"⚙️ Setup – {i.guild.name}",
        description="Select a category below to view and configure settings.",
        color=0x5865F2)
    if i.guild.icon:
        e.set_thumbnail(url=i.guild.icon.url)
    await i.response.send_message(embed=e, view=SetupView(), ephemeral=True)

@bot.tree.command(name="setprefix", description="Change the command prefix")
@app_commands.default_permissions(administrator=True)
async def cmd_setprefix(i: discord.Interaction, prefix: str):
    await set_setting(i.guild.id, 'prefix', prefix)
    prefix_cache[i.guild.id] = prefix
    await i.response.send_message(f"✅ Prefix → `{prefix}`", ephemeral=True)

@bot.tree.command(name="setlogchannel", description="Set a log channel")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(category=[
    app_commands.Choice(name="mod",      value="log_mod_id"),
    app_commands.Choice(name="messages", value="log_message_id"),
    app_commands.Choice(name="members",  value="log_member_id"),
    app_commands.Choice(name="server",   value="log_server_id"),
])
async def cmd_setlogchannel(i: discord.Interaction, category: str,
                            channel: discord.TextChannel):
    await set_setting(i.guild.id, category, channel.id)
    await i.response.send_message(
        f"✅ **{category.replace('log_','').replace('_id','')}** logs → {channel.mention}",
        ephemeral=True)

@bot.tree.command(name="setwelcome", description="Set welcome channel and message")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(message="Variables: {user} {name} {server} {count}")
async def cmd_setwelcome(i: discord.Interaction, channel: discord.TextChannel, message: str):
    await set_setting(i.guild.id, 'welcome_channel_id', channel.id)
    await set_setting(i.guild.id, 'welcome_message', message)
    preview = (message
               .replace("{user}",   i.user.mention)
               .replace("{name}",   i.user.display_name)
               .replace("{server}", i.guild.name)
               .replace("{count}",  str(i.guild.member_count)))
    e = discord.Embed(title="✅ Welcome set – Preview:", description=preview, color=0x57F287)
    await i.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="setautorole", description="Auto-assign role to new members")
@app_commands.default_permissions(administrator=True)
async def cmd_setautorole(i: discord.Interaction, role: discord.Role):
    await set_setting(i.guild.id, 'autorole_id', role.id)
    await i.response.send_message(f"✅ Autorole → {role.mention}", ephemeral=True)

@bot.tree.command(name="setjail", description="Set jail channel and role")
@app_commands.default_permissions(administrator=True)
async def cmd_setjail(i: discord.Interaction, channel: discord.TextChannel,
                      role: discord.Role):
    await set_setting(i.guild.id, 'jail_channel_id', channel.id)
    await set_setting(i.guild.id, 'jail_role_id', role.id)
    await i.response.send_message(
        f"✅ Jail → {channel.mention} | Role → {role.mention}", ephemeral=True)

@bot.tree.command(name="setdeadchatrole", description="Role pinged by /deadchat")
@app_commands.default_permissions(administrator=True)
async def cmd_setdeadchatrole(i: discord.Interaction, role: discord.Role):
    await set_setting(i.guild.id, 'deadchat_role_id', role.id)
    await i.response.send_message(f"✅ Deadchat ping → {role.mention}", ephemeral=True)

@bot.tree.command(name="setdeadchatperm", description="Restrict who can use /deadchat")
@app_commands.default_permissions(administrator=True)
async def cmd_setdeadchatperm(i: discord.Interaction, role: discord.Role = None):
    await set_setting(i.guild.id, 'deadchat_perm_role', role.id if role else None)
    await i.response.send_message(
        f"✅ Deadchat restricted to {role.mention}." if role
        else "✅ Deadchat open to everyone.", ephemeral=True)

@bot.tree.command(name="setstarboard", description="Configure the starboard")
@app_commands.default_permissions(administrator=True)
async def cmd_setstarboard(i: discord.Interaction, channel: discord.TextChannel,
                           emoji: str = "⭐", threshold: int = 3):
    await set_setting(i.guild.id, 'starboard_channel_id', channel.id)
    await set_setting(i.guild.id, 'starboard_emoji', emoji)
    await set_setting(i.guild.id, 'starboard_threshold', threshold)
    await i.response.send_message(
        f"✅ Starboard → {channel.mention} | {emoji} × {threshold}", ephemeral=True)

@bot.tree.command(name="setchapterchannel", description="Channel for chapter announcements")
@app_commands.default_permissions(administrator=True)
async def cmd_setchapterchannel(i: discord.Interaction, channel: discord.TextChannel,
                                role: discord.Role = None):
    await set_setting(i.guild.id, 'chapter_channel_id', channel.id)
    if role:
        await set_setting(i.guild.id, 'chapter_role_id', role.id)
    await i.response.send_message(
        f"✅ Chapters → {channel.mention}" + (f" | Ping: {role.mention}" if role else ""),
        ephemeral=True)

@bot.tree.command(name="setcharacterchannel", description="Channel for character announcements")
@app_commands.default_permissions(administrator=True)
async def cmd_setcharacterchannel(i: discord.Interaction, channel: discord.TextChannel):
    await set_setting(i.guild.id, 'character_channel_id', channel.id)
    await i.response.send_message(f"✅ Characters → {channel.mention}", ephemeral=True)

@bot.tree.command(name="setcooldown", description="Override command cooldown in seconds")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(command=[
    app_commands.Choice(name=c, value=c)
    for c in ["deadchat", "meme", "roast", "8ball", "poll", "urban"]
])
async def cmd_setcooldown(i: discord.Interaction, command: str, seconds: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO cooldowns (guild_id,command,seconds) VALUES (?,?,?)",
            (i.guild.id, command, max(0, seconds)))
        await db.commit()
    await i.response.send_message(
        f"✅ `/{command}` cooldown → **{seconds}s**", ephemeral=True)

@bot.tree.command(name="setdisplay",
                  description="Control how a command's response appears")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(mode=[
    app_commands.Choice(name="public – visible to everyone",       value="public"),
    app_commands.Choice(name="ephemeral – only the user sees it",  value="ephemeral"),
    app_commands.Choice(name="timed – posted then auto-deleted",   value="timed"),
])
async def cmd_setdisplay(i: discord.Interaction, command: str, mode: str,
                         seconds: int = 5):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO command_display (guild_id,command,mode,seconds)"
            " VALUES (?,?,?,?)",
            (i.guild.id, command, mode, seconds))
        await db.commit()
    detail = f" (delete after {seconds}s)" if mode == "timed" else ""
    await i.response.send_message(
        f"✅ `{command}` display → **{mode}**{detail}", ephemeral=True)

@bot.tree.command(name="setcommandperms",
                  description="Control who can use and see any command")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    command="Command name (without prefix or /)",
    role="Role required to use it (empty = everyone)",
    allow_use="Whether this role/everyone can use the command",
    show_in_help="Whether to show this command in /help",
    silent="Silently ignore unauthorized uses"
)
async def cmd_setcommandperms(i: discord.Interaction,
                              command: str,
                              role: discord.Role = None,
                              allow_use: bool = True,
                              show_in_help: bool = True,
                              silent: bool = False):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO command_perms"
            " (guild_id,command,role_id,allow_use,show_in_help,silent)"
            " VALUES (?,?,?,?,?,?)",
            (i.guild.id, command, role.id if role else 0,
             int(allow_use), int(show_in_help), int(silent)))
        await db.commit()
    status = []
    if role: status.append(f"requires {role.mention}")
    if not allow_use: status.append("disabled")
    if not show_in_help: status.append("hidden from /help")
    if silent: status.append("silent on fail")
    await i.response.send_message(
        f"✅ `{command}` perms set"
        + (f": {', '.join(status)}" if status else " (open to everyone)"),
        ephemeral=True)

@bot.tree.command(name="antiraidsettings", description="Configure anti-raid")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(action=[
    app_commands.Choice(name="slowmode (60s on all channels)", value="slowmode"),
    app_commands.Choice(name="lockdown (disable all messaging)", value="lockdown"),
    app_commands.Choice(name="kick new members", value="kick_new"),
])
async def cmd_antiraidsettings(i: discord.Interaction, threshold: int,
                               seconds: int, action: str):
    await set_setting(i.guild.id, 'antiraid_threshold', threshold)
    await set_setting(i.guild.id, 'antiraid_seconds', seconds)
    await set_setting(i.guild.id, 'antiraid_action', action)
    await i.response.send_message(
        f"✅ Anti-raid: **{threshold}** joins in **{seconds}s** → `{action}`",
        ephemeral=True)

@bot.tree.command(name="antiraidtoggle", description="Enable/disable anti-raid")
@app_commands.default_permissions(administrator=True)
async def cmd_antiraidtoggle(i: discord.Interaction):
    cur = await get_setting(i.guild.id, 'antiraid_enabled') or 0
    new = 1 - int(cur)
    await set_setting(i.guild.id, 'antiraid_enabled', new)
    await i.response.send_message(
        f"✅ Anti-raid {'**enabled**' if new else '**disabled**'}.", ephemeral=True)

@bot.tree.command(name="setwarnthreshold",
                  description="Set what happens when a warn count is reached")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(action=[
    app_commands.Choice(name="kick", value="kick"),
    app_commands.Choice(name="ban",  value="ban"),
    app_commands.Choice(name="mute", value="mute"),
])
@app_commands.describe(action="Action", count="Warn count (0 = disabled)",
                       mute_minutes="If action is mute: duration in minutes")
async def cmd_setwarnthreshold(i: discord.Interaction, action: str, count: int,
                               mute_minutes: int = 10):
    await set_setting(i.guild.id, f"warn_{action}_threshold", count)
    if action == "mute":
        await set_setting(i.guild.id, 'warn_mute_minutes', mute_minutes)
    await i.response.send_message(
        f"✅ At **{count}** warns → `{action}`"
        + (f" for {mute_minutes}min" if action == "mute" else "")
        + (" (disabled)" if count == 0 else ""),
        ephemeral=True)

# – SECTION 9: MODERATION ––––––––––––––––––––––––––

async def _do_warn(guild: discord.Guild, moderator, member,
                   reason: str, expires_at=None, proof_url: str = None):
    count = await add_warn(member.id, guild.id, moderator.id, reason, expires_at, proof_url)
    await log_mod_action(bot, "Warn", member, moderator, reason, guild.id, proof_url)
    fields = [("Server", guild.name), ("Reason", reason or "None"), ("Total Warns", str(count))]
    if expires_at:
        fields.append(("Expires", f"<t:{int(expires_at.timestamp())}:R>"))
    if proof_url:
        fields.append(("📎 Proof", f"[Jump]({proof_url})"))
    dm = discord.Embed(title="⚠️ You have been warned", color=0xFFAA00,
                       timestamp=datetime.now(timezone.utc))
    for n, v in fields:
        dm.add_field(name=n, value=v, inline=False)
    await try_dm(member, embed=dm)
    return count, await _check_warn_thresholds(guild, member, count)

async def _check_warn_thresholds(guild: discord.Guild, member, count: int):
    kick_t = safe_int(await get_setting(guild.id, 'warn_kick_threshold') or 3)
    ban_t  = safe_int(await get_setting(guild.id, 'warn_ban_threshold')  or 0)
    mute_t = safe_int(await get_setting(guild.id, 'warn_mute_threshold') or 0)
    mute_m = safe_int(await get_setting(guild.id, 'warn_mute_minutes')   or 10)
    m = guild.get_member(int(member.id)) if isinstance(member, discord.User) else member
    if not m:
        return None
    if ban_t and count >= ban_t:
        await try_dm(m, embed=discord.Embed(title="🔨 Auto-banned", color=0xCC0000,
            description=f"Reached {ban_t} warnings in {guild.name}"))
        await m.ban(reason=f"Auto-ban: {ban_t}+ warns")
        await log_mod_action(bot, f"Auto-ban ({ban_t} warns)", m, bot.user, guild_id=guild.id)
        return "ban"
    if kick_t and count >= kick_t:
        await try_dm(m, embed=discord.Embed(title="👢 Auto-kicked", color=0xFF4444,
            description=f"Reached {kick_t} warnings in {guild.name}"))
        await m.kick(reason=f"Auto-kick: {kick_t}+ warns")
        await log_mod_action(bot, f"Auto-kick ({kick_t} warns)", m, bot.user, guild_id=guild.id)
        return "kick"
    if mute_t and count >= mute_t:
        until = datetime.now(timezone.utc) + timedelta(minutes=mute_m)
        await m.edit(timed_out_until=until)
        await log_mod_action(bot, f"Auto-mute ({mute_t} warns)", m, bot.user, guild_id=guild.id)
        return "mute"
    return None

def _action_embed(title: str, color: int, fields: list) -> discord.Embed:
    e = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    for name, value in fields:
        e.add_field(name=name, value=str(value) if value else "None", inline=False)
    return e

# – /warn ——————————————————————

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.default_permissions(moderate_members=True)
@app_commands.describe(member="Member to warn", reason="Reason",
                       expires_in="Optional expiry e.g. 7d 24h 30m")
async def cmd_warn(i: discord.Interaction, member: discord.Member,
                   reason: str = None, expires_in: str = None):
    delta = parse_duration(expires_in)
    exp   = datetime.now(timezone.utc) + delta if delta else None
    count, action = await _do_warn(i.guild, i.user, member, reason, exp)
    e = discord.Embed(title="⚠️ Member Warned", color=0xFFAA00,
                      timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="Member", value=member.mention)
    e.add_field(name="By", value=i.user.mention)
    e.add_field(name="Reason", value=reason or "None", inline=False)
    e.add_field(name="Total Warns", value=str(count))
    if exp:
        e.add_field(name="Expires", value=f"<t:{int(exp.timestamp())}:R>")
    await i.response.send_message(embed=e)
    if action:
        icon = "👢" if action == "kick" else "🔨" if action == "ban" else "🔇"
        await i.followup.send(embed=discord.Embed(
            description=f"{icon} Auto-{action}ed {member.mention} (threshold reached).",
            color=0xFF4444))

@bot.tree.command(name="unwarn", description="Remove a warn by ID")
@app_commands.default_permissions(moderate_members=True)
async def cmd_unwarn(i: discord.Interaction, member: discord.Member, warn_id: int):
    if not await remove_warn(warn_id, i.guild.id):
        await i.response.send_message("❌ Warn ID not found.", ephemeral=True); return
    await log_mod_action(bot, "Remove Warn", member, i.user, f"Warn #{warn_id}", i.guild.id)
    await try_dm(member, embed=discord.Embed(
        title="✅ Warn Removed", color=0x57F287,
        description=f"Warn #{warn_id} removed from your record in {i.guild.name}."))
    await i.response.send_message(embed=discord.Embed(
        description=f"✅ Removed warn `#{warn_id}` from {member.mention}.", color=0x57F287))

@bot.tree.command(name="clearwarns", description="Clear all warns for a member")
@app_commands.default_permissions(moderate_members=True)
async def cmd_clearwarns(i: discord.Interaction, member: discord.Member):
    count = await clear_warns(member.id, i.guild.id)
    await log_mod_action(bot, "Clear Warns", member, i.user, guild_id=i.guild.id)
    await i.response.send_message(embed=discord.Embed(
        description=f"🗑️ Cleared **{count}** warn(s) from {member.mention}.", color=0x57F287))

@bot.tree.command(name="warns", description="Check warns for a member")
async def cmd_warns(i: discord.Interaction, member: discord.Member = None):
    target = member or i.user
    rows   = await get_all_warns(target.id, i.guild.id)
    e = discord.Embed(title=f"⚠️ Warns – {target.display_name}", color=0xFFAA00)
    e.set_thumbnail(url=target.display_avatar.url)
    if not rows:
        e.description = "No active warns ✅"
    else:
        for wid, mid, reason, proof_url, exp, ts in rows:
            mod   = i.guild.get_member(int(mid))
            proof = f"\n[📎 Proof]({proof_url})" if proof_url else ""
            expiry = f"\nExpires: <t:{int(datetime.fromisoformat(exp).timestamp())}:R>" if exp else ""
            e.add_field(name=f"Warn #{wid} – {ts[:10]}",
                        value=f"By: {mod.mention if mod else f'<@{mid}>'}\n"
                              f"Reason: {reason or 'None'}{expiry}{proof}",
                        inline=False)
    await i.response.send_message(embed=e)

# – /history —————————————————————

@bot.tree.command(name="history", description="View all mod actions against a user")
@app_commands.default_permissions(moderate_members=True)
async def cmd_history(i: discord.Interaction, member: discord.Member):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT action,moderator_id,reason,proof_url,timestamp FROM mod_logs"
            " WHERE guild_id=? AND user_id=? ORDER BY timestamp DESC LIMIT 25",
            (i.guild.id, member.id)
        ) as cur:
            rows = await cur.fetchall()
    e = discord.Embed(title=f"📜 History – {member.display_name}", color=0xFF4444)
    e.set_thumbnail(url=member.display_avatar.url)
    if not rows:
        e.description = "No mod actions on record."
    else:
        for action, mid, reason, proof_url, ts in rows:
            mod   = i.guild.get_member(int(mid))
            proof = f" | [📎]({proof_url})" if proof_url else ""
            e.add_field(name=f"{action} – {ts[:10]}",
                        value=f"By: {mod.mention if mod else f'<@{mid}>'}\n"
                              f"Reason: {reason or 'None'}{proof}",
                        inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="modlogs", description="Show mod actions by a moderator")
@app_commands.default_permissions(moderate_members=True)
async def cmd_modlogs(i: discord.Interaction, moderator: discord.Member):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT action,user_id,reason,timestamp FROM mod_logs"
            " WHERE guild_id=? AND moderator_id=? ORDER BY timestamp DESC LIMIT 20",
            (i.guild.id, moderator.id)
        ) as cur:
            rows = await cur.fetchall()
    e = discord.Embed(title=f"📋 Mod Logs – {moderator.display_name}", color=0x5865F2)
    e.description = "No actions found." if not rows else None
    for action, uid, reason, ts in rows:
        e.add_field(name=f"{action} – {ts[:10]}",
                    value=f"User: <@{uid}>\nReason: {reason or 'None'}",
                    inline=False)
    await i.response.send_message(embed=e)

# – /mute ——————————————————————

@bot.tree.command(name="mute", description="Timeout a member")
@app_commands.default_permissions(moderate_members=True)
async def cmd_mute(i: discord.Interaction, member: discord.Member,
                   minutes: int, reason: str = None):
    await i.response.defer()
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    await member.edit(timed_out_until=until, reason=reason)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO mute_tracking (user_id,guild_id,unmute_at)"
            " VALUES (?,?,?)",
            (member.id, i.guild_id, until.isoformat()))
        await db.commit()
    await log_mod_action(bot, f"Mute {minutes}min", member, i.user, reason, i.guild_id)
    e = _action_embed("🔇 Member Muted", 0xFF8800,
                      [("Member", member.mention), ("By", i.user.mention),
                       ("Duration", f"{minutes}min"), ("Unmuted", f"<t:{int(until.timestamp())}:R>"),
                       ("Reason", reason or "None")])
    e.set_thumbnail(url=member.display_avatar.url)
    await i.followup.send(embed=e)
    await try_dm(member, embed=_action_embed("🔇 You have been muted", 0xFF8800,
        [("Server", i.guild.name), ("Duration", f"{minutes}min"),
         ("Unmuted", f"<t:{int(until.timestamp())}:R>"), ("Reason", reason or "None")]))

# – /unmute ––––––––––––––––––––––––––––––––

@bot.tree.command(name="unmute", description="Remove a member's timeout")
@app_commands.default_permissions(moderate_members=True)
async def cmd_unmute(i: discord.Interaction, member: discord.Member):
    await i.response.defer()
    await member.edit(timed_out_until=None)
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM mute_tracking WHERE user_id=? AND guild_id=?",
                         (member.id, i.guild_id))
        await db.commit()
    await log_mod_action(bot, "Unmute", member, i.user, guild_id=i.guild_id)
    await i.followup.send(embed=discord.Embed(
        description=f"🔊 Unmuted {member.mention}.", color=0x57F287))
    await try_dm(member, embed=discord.Embed(
        title="🔊 You have been unmuted", color=0x57F287,
        description=f"Server: {i.guild.name} | By: {i.user}"))

# – /kick ——————————————————————

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def cmd_kick(i: discord.Interaction, member: discord.Member, reason: str = None):
    await try_dm(member, embed=_action_embed("👢 You have been kicked", 0xFF4444,
        [("Server", i.guild.name), ("Reason", reason or "None")]))
    await member.kick(reason=reason)
    await log_mod_action(bot, "Kick", member, i.user, reason, i.guild.id)
    await i.response.send_message(embed=_action_embed("👢 Member Kicked", 0xFF4444,
        [("Member", member.mention), ("By", i.user.mention), ("Reason", reason or "None")]))

# – /ban —————————————————————––

@bot.tree.command(name="ban", description="Ban a user (works by ID even if not in server)")
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(user_id="User ID (works even if they're not in the server)",
                       member="Or pick a member directly")
async def cmd_ban(i: discord.Interaction, reason: str = None,
                  member: discord.Member = None, user_id: str = None):
    await i.response.defer()
    target = None
    if member:
        target = member
    elif user_id:
        try:
            target = await bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound):
            await i.followup.send("❌ User not found.", ephemeral=True); return
    else:
        await i.followup.send("❌ Provide a member or user_id.", ephemeral=True); return

    if isinstance(target, discord.Member):
        await try_dm(target, embed=_action_embed("🔨 You have been banned", 0xCC0000,
            [("Server", i.guild.name), ("Reason", reason or "None")]))
    await i.guild.ban(target, reason=reason)
    await log_mod_action(bot, "Ban", target, i.user, reason, i.guild.id)
    await i.followup.send(embed=_action_embed("🔨 User Banned", 0xCC0000,
        [("User", f"{target} `{target.id}`"), ("By", i.user.mention),
         ("Reason", reason or "None")]))

# – /unban —————————————————————–

@bot.tree.command(name="unban", description="Unban a user by ID")
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(user_id="User ID to unban")
async def cmd_unban(i: discord.Interaction, user_id: str, reason: str = None):
    await i.response.defer()
    try:
        user = await bot.fetch_user(int(user_id))
    except (ValueError, discord.NotFound):
        await i.followup.send("❌ User not found.", ephemeral=True); return
    try:
        await i.guild.unban(user, reason=reason)
    except discord.NotFound:
        await i.followup.send(f"❌ {user} is not banned.", ephemeral=True); return
    await log_mod_action(bot, "Unban", user, i.user, reason, i.guild.id)
    await try_dm(user, embed=discord.Embed(
        title="🔓 You have been unbanned", color=0x57F287,
        description=f"Server: {i.guild.name}"))
    await i.followup.send(embed=discord.Embed(
        description=f"🔓 Unbanned **{user}** `{user.id}`.", color=0x57F287))

# – /tempban —————————————————————

@bot.tree.command(name="tempban", description="Temporarily ban a user")
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(duration="e.g. 1d 12h 30m",
                       user_id="User ID – works even if not in server")
async def cmd_tempban(i: discord.Interaction, duration: str, reason: str = None,
                      member: discord.Member = None, user_id: str = None):
    await i.response.defer()
    delta = parse_duration(duration)
    if not delta:
        await i.followup.send("❌ Invalid duration. Use e.g. `1d`, `12h`, `30m`.", ephemeral=True); return
    target = None
    if member:
        target = member
    elif user_id:
        try:
            target = await bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound):
            await i.followup.send("❌ User not found.", ephemeral=True); return
    else:
        await i.followup.send("❌ Provide a member or user_id.", ephemeral=True); return

    unban_at = datetime.now(timezone.utc) + delta
    if isinstance(target, discord.Member):
        await try_dm(target, embed=_action_embed("🔨 Temporarily Banned", 0xCC0000,
            [("Server", i.guild.name), ("Duration", duration),
             ("Unban", f"<t:{int(unban_at.timestamp())}:R>"),
             ("Reason", reason or "None")]))
    await i.guild.ban(target, reason=reason)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO tempbans (user_id,guild_id,unban_at) VALUES (?,?,?)",
            (target.id, i.guild.id, unban_at.isoformat()))
        await db.commit()
    await log_mod_action(bot, f"Tempban ({duration})", target, i.user, reason, i.guild.id)
    await i.followup.send(embed=_action_embed("🔨 User Tempbanned", 0xCC0000,
        [("User", f"{target} `{target.id}`"), ("Duration", duration),
         ("Unban", f"<t:{int(unban_at.timestamp())}:R>"), ("Reason", reason or "None")]))

# – /jail / unjail ———————————————————

async def _do_jail(guild: discord.Guild, moderator, member: discord.Member, reason: str):
    jail_role_id = await get_setting_int(guild.id, 'jail_role_id')
    if not jail_role_id:
        return False
    jail_role = guild.get_role(int(jail_role_id) if jail_role_id else None)
    if not jail_role:
        return False
    role_ids = [r.id for r in member.roles if not r.is_default()]
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM jailed_roles WHERE user_id=? AND guild_id=?",
                         (member.id, guild.id))
        for rid in role_ids:
            await db.execute(
                "INSERT INTO jailed_roles (user_id,guild_id,role_id) VALUES (?,?,?)",
                (member.id, guild.id, rid))
        await db.commit()
    roles_to_remove = [r for r in member.roles if not r.is_default()]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Jailed")
    await member.add_roles(jail_role, reason=reason or "Jailed")
    await log_mod_action(bot, "Jail", member, moderator, reason, guild.id)
    await try_dm(member, embed=_action_embed("🔒 You have been jailed", 0xFF6600,
        [("Server", guild.name), ("Reason", reason or "None")]))
    return True

async def _do_unjail(guild: discord.Guild, moderator, member: discord.Member):
    jail_role_id = await get_setting_int(guild.id, 'jail_role_id')
    if jail_role_id:
        jail_role = guild.get_role(int(jail_role_id) if jail_role_id else None)
        if jail_role and jail_role in member.roles:
            await member.remove_roles(jail_role, reason="Unjailed")
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT role_id FROM jailed_roles WHERE user_id=? AND guild_id=?",
            (member.id, guild.id)
        ) as cur:
            rows = await cur.fetchall()
        await db.execute("DELETE FROM jailed_roles WHERE user_id=? AND guild_id=?",
                         (member.id, guild.id))
        await db.commit()
    roles_to_add = [guild.get_role(int(r[0])) for r in rows if guild.get_role(int(r[0]))]
    if roles_to_add:
        await member.add_roles(*roles_to_add, reason="Unjailed")
    await log_mod_action(bot, "Unjail", member, moderator, guild_id=guild.id)
    await try_dm(member, embed=discord.Embed(
        title="🔓 Released from jail", color=0x57F287,
        description=f"Server: {guild.name}"))

@bot.tree.command(name="jail", description="Jail a member")
@app_commands.default_permissions(moderate_members=True)
async def cmd_jail(i: discord.Interaction, member: discord.Member, reason: str = None):
    await i.response.defer()
    ok = await _do_jail(i.guild, i.user, member, reason)
    if not ok:
        await i.followup.send("❌ Jail role not configured. Use `/setjail` first.")
        return
    await i.followup.send(embed=_action_embed("🔒 Member Jailed", 0xFF6600,
        [("Member", member.mention), ("By", i.user.mention), ("Reason", reason or "None")]))

@bot.tree.command(name="unjail", description="Release a member from jail")
@app_commands.default_permissions(moderate_members=True)
async def cmd_unjail(i: discord.Interaction, member: discord.Member):
    await i.response.defer()
    await _do_unjail(i.guild, i.user, member)
    await i.followup.send(embed=discord.Embed(
        description=f"🔓 Released {member.mention}.", color=0x57F287))

# – /purge / nick / slowmode / lookup ———————————––

@bot.tree.command(name="purge", description="Delete messages (max 100)")
@app_commands.default_permissions(manage_messages=True)
async def cmd_purge(i: discord.Interaction, amount: int):
    if not 1 <= amount <= 100:
        await i.response.send_message("❌ 1-100 only.", ephemeral=True); return
    await i.response.defer(ephemeral=True)
    deleted = await i.channel.purge(limit=amount)
    await log_mod_action(bot, f"Purge ({len(deleted)})", i.user, i.user,
                         guild_id=i.guild_id)
    await i.followup.send(f"🗑️ Deleted **{len(deleted)}** messages.", ephemeral=True)

@bot.tree.command(name="nick", description="Change a member's nickname")
@app_commands.default_permissions(manage_nicknames=True)
async def cmd_nick(i: discord.Interaction, member: discord.Member, nickname: str = None):
    old = member.display_name
    await member.edit(nick=nickname)
    await log_mod_action(bot, "Nick Change", member, i.user,
                         f"{old} → {nickname or 'reset'}", i.guild.id)
    await i.response.send_message(embed=discord.Embed(
        description=f"✅ {member.mention} → **{nickname or 'reset'}**", color=0x57F287))

@bot.tree.command(name="slowmode", description="Set channel slowmode (0 = off)")
@app_commands.default_permissions(manage_channels=True)
async def cmd_slowmode(i: discord.Interaction, seconds: int):
    await i.channel.edit(slowmode_delay=seconds)
    await i.response.send_message(embed=discord.Embed(
        description=f"⏱️ Slowmode → **{seconds}s**" if seconds else "⏱️ Slowmode disabled.",
        color=0x57F287))

@bot.tree.command(name="lookup", description="Fetch info on any user by ID")
@app_commands.default_permissions(moderate_members=True)
async def cmd_lookup(i: discord.Interaction, user_id: str):
    await i.response.defer()
    try:
        user = await bot.fetch_user(int(user_id))
    except (ValueError, discord.NotFound):
        await i.followup.send("❌ User not found.", ephemeral=True); return
    warns     = await get_warn_count(user.id, i.guild.id)
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM mod_logs WHERE guild_id=? AND user_id=?",
            (i.guild.id, user.id)
        ) as cur:
            log_count = (await cur.fetchone())[0]
    member = i.guild.get_member(user.id)
    e = discord.Embed(title=str(user), color=0x5865F2,
                      timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="ID",              value=str(user.id))
    e.add_field(name="Created",         value=f"<t:{int(user.created_at.timestamp())}:R>")
    e.add_field(name="In Server",       value="✅ Yes" if member else "❌ No")
    e.add_field(name="Active Warns",    value=str(warns))
    e.add_field(name="Total Mod Logs",  value=str(log_count))
    if member:
        e.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>")
    await i.followup.send(embed=e)

# – PREFIX MOD COMMANDS ––––––––––––––––––––––––––

async def _prefix_resolve(ctx: commands.Context,
                          arg=None) -> Optional[discord.Member | discord.User]:
    if arg is not None:
        if isinstance(arg, (discord.Member, discord.User)):
            return arg
        try:
            uid = int(str(arg).strip("<@!>"))
            m   = ctx.guild.get_member(int(uid))
            if m: return m
            return await bot.fetch_user(uid)
        except (ValueError, discord.NotFound):
            pass
    return await get_reply_target(ctx)

@bot.command(name="warn")
@commands.has_permissions(moderate_members=True)
async def pfx_warn(ctx: commands.Context, member=None, *, args: str = ""):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    tokens = args.split()
    exp    = None
    if tokens:
        d = parse_duration(tokens[-1])
        if d:
            exp    = datetime.now(timezone.utc) + d
            tokens = tokens[:-1]
    reason = " ".join(tokens) or None
    proof  = await get_proof(ctx)
    count, action = await _do_warn(ctx.guild, ctx.author, target, reason, exp,
                                   proof[0] if proof else None)
    e = discord.Embed(title="⚠️ Member Warned", color=0xFFAA00)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="Member", value=target.mention)
    e.add_field(name="Reason", value=reason or "None", inline=False)
    e.add_field(name="Total Warns", value=str(count))
    if proof:
        e.add_field(name="📎 Proof",
                    value=f"[Jump]({proof[0]})\n> {proof[1]}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="unwarn")
@commands.has_permissions(moderate_members=True)
async def pfx_unwarn(ctx: commands.Context, member: discord.Member, warn_id: int):
    if not await remove_warn(warn_id, ctx.guild.id):
        await ctx.reply("❌ Warn ID not found."); return
    await log_mod_action(bot, "Remove Warn", member, ctx.author, f"#{warn_id}", ctx.guild.id)
    await ctx.send(embed=discord.Embed(
        description=f"✅ Removed warn `#{warn_id}` from {member.mention}.", color=0x57F287))

@bot.command(name="clearwarns")
@commands.has_permissions(moderate_members=True)
async def pfx_clearwarns(ctx: commands.Context, member=None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    count = await clear_warns(target.id, ctx.guild.id)
    await ctx.send(embed=discord.Embed(
        description=f"🗑️ Cleared **{count}** warn(s) from {target.mention}.", color=0x57F287))

@bot.command(name="warns")
async def pfx_warns(ctx: commands.Context, member=None):
    target = await _prefix_resolve(ctx, member) or ctx.author
    rows   = await get_all_warns(target.id, ctx.guild.id)
    e = discord.Embed(title=f"⚠️ Warns – {target.display_name}", color=0xFFAA00)
    if not rows:
        e.description = "No active warns ✅"
    else:
        for wid, mid, reason, proof_url, exp, ts in rows:
            proof = f" | [📎]({proof_url})" if proof_url else ""
            e.add_field(name=f"Warn #{wid} – {ts[:10]}",
                        value=f"Reason: {reason or 'None'}{proof}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="history")
@commands.has_permissions(moderate_members=True)
async def pfx_history(ctx: commands.Context, member=None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT action,moderator_id,reason,proof_url,timestamp FROM mod_logs"
            " WHERE guild_id=? AND user_id=? ORDER BY timestamp DESC LIMIT 25",
            (ctx.guild.id, target.id)
        ) as cur:
            rows = await cur.fetchall()
    e = discord.Embed(title=f"📜 History – {target.display_name}", color=0xFF4444)
    if not rows:
        e.description = "No mod actions."
    else:
        for action, mid, reason, proof_url, ts in rows:
            mod   = ctx.guild.get_member(int(mid))
            proof = f" | [📎]({proof_url})" if proof_url else ""
            e.add_field(name=f"{action} – {ts[:10]}",
                        value=f"By: {mod.mention if mod else f'<@{mid}>'}\n"
                              f"Reason: {reason or 'None'}{proof}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="modlogs")
@commands.has_permissions(moderate_members=True)
async def pfx_modlogs(ctx: commands.Context, moderator: discord.Member):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT action,user_id,reason,timestamp FROM mod_logs"
            " WHERE guild_id=? AND moderator_id=? ORDER BY timestamp DESC LIMIT 20",
            (ctx.guild.id, moderator.id)
        ) as cur:
            rows = await cur.fetchall()
    e = discord.Embed(title=f"📋 Mod Logs – {moderator.display_name}", color=0x5865F2)
    e.description = "No actions." if not rows else None
    for action, uid, reason, ts in rows:
        e.add_field(name=f"{action} – {ts[:10]}",
                    value=f"<@{uid}> – {reason or 'None'}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def pfx_mute(ctx: commands.Context, member=None, minutes: int = None, *, reason: str = None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    if minutes is None:
        await ctx.reply("❌ Usage: `?mute @member <minutes> [reason]`"); return
    if not isinstance(target, discord.Member):
        await ctx.reply("❌ User must be in the server to mute."); return
    proof = await get_proof(ctx)
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    await target.edit(timed_out_until=until, reason=reason)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO mute_tracking (user_id,guild_id,unmute_at)"
            " VALUES (?,?,?)", (target.id, ctx.guild.id, until.isoformat()))
        await db.commit()
    await log_mod_action(bot, f"Mute {minutes}min", target, ctx.author,
                         reason, ctx.guild.id, proof[0] if proof else None)
    e = discord.Embed(title="🔇 Member Muted", color=0xFF8800)
    e.add_field(name="Member",   value=target.mention)
    e.add_field(name="Duration", value=f"{minutes}min")
    e.add_field(name="Reason",   value=reason or "None", inline=False)
    if proof:
        e.add_field(name="📎 Proof", value=f"[Jump]({proof[0]})\n> {proof[1]}", inline=False)
    await ctx.send(embed=e)
    await try_dm(target, embed=_action_embed("🔇 You have been muted", 0xFF8800,
        [("Server", ctx.guild.name), ("Duration", f"{minutes}min"),
         ("Unmuted", f"<t:{int(until.timestamp())}:R>"), ("Reason", reason or "None")]))

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def pfx_unmute(ctx: commands.Context, member=None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    if not isinstance(target, discord.Member):
        await ctx.reply("❌ User must be in the server."); return
    await target.edit(timed_out_until=None)
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM mute_tracking WHERE user_id=? AND guild_id=?",
                         (target.id, ctx.guild.id))
        await db.commit()
    await log_mod_action(bot, "Unmute", target, ctx.author, guild_id=ctx.guild.id)
    await ctx.send(embed=discord.Embed(
        description=f"🔊 Unmuted {target.mention}.", color=0x57F287))
    await try_dm(target, embed=discord.Embed(
        title="🔊 You have been unmuted", color=0x57F287,
        description=f"Server: {ctx.guild.name} | By: {ctx.author}"))

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def pfx_kick(ctx: commands.Context, member=None, *, reason: str = None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    if not isinstance(target, discord.Member):
        await ctx.reply("❌ User must be in the server to kick."); return
    proof = await get_proof(ctx)
    await try_dm(target, embed=_action_embed("👢 You have been kicked", 0xFF4444,
        [("Server", ctx.guild.name), ("Reason", reason or "None")]))
    await target.kick(reason=reason)
    await log_mod_action(bot, "Kick", target, ctx.author, reason, ctx.guild.id,
                         proof[0] if proof else None)
    e = discord.Embed(title="👢 Member Kicked", color=0xFF4444)
    e.add_field(name="Member", value=target.mention)
    e.add_field(name="Reason", value=reason or "None", inline=False)
    if proof:
        e.add_field(name="📎 Proof", value=f"[Jump]({proof[0]})\n> {proof[1]}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def pfx_ban(ctx: commands.Context, member=None, *, reason: str = None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member/ID or reply to their message."); return
    proof = await get_proof(ctx)
    if isinstance(target, discord.Member):
        await try_dm(target, embed=_action_embed("🔨 You have been banned", 0xCC0000,
            [("Server", ctx.guild.name), ("Reason", reason or "None")]))
    await ctx.guild.ban(discord.Object(id=target.id), reason=reason)
    await log_mod_action(bot, "Ban", target, ctx.author, reason, ctx.guild.id,
                         proof[0] if proof else None)
    e = discord.Embed(title="🔨 User Banned", color=0xCC0000)
    e.add_field(name="User", value=f"{target} `{target.id}`")
    e.add_field(name="Reason", value=reason or "None", inline=False)
    if proof:
        e.add_field(name="📎 Proof", value=f"[Jump]({proof[0]})\n> {proof[1]}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def pfx_unban(ctx: commands.Context, user_id: str, *, reason: str = None):
    try:
        user = await bot.fetch_user(int(user_id))
    except (ValueError, discord.NotFound):
        await ctx.reply("❌ User not found."); return
    try:
        await ctx.guild.unban(user, reason=reason)
    except discord.NotFound:
        await ctx.reply(f"❌ {user} is not banned."); return
    await log_mod_action(bot, "Unban", user, ctx.author, reason, ctx.guild.id)
    await try_dm(user, embed=discord.Embed(
        title="🔓 You have been unbanned", color=0x57F287,
        description=f"Server: {ctx.guild.name}"))
    await ctx.send(embed=discord.Embed(
        description=f"🔓 Unbanned **{user}** `{user.id}`.", color=0x57F287))

@bot.command(name="tempban")
@commands.has_permissions(ban_members=True)
async def pfx_tempban(ctx: commands.Context, member=None, duration: str = None,
                      *, reason: str = None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member/ID or reply to their message."); return
    if not duration:
        await ctx.reply("❌ Usage: `?tempban @member 7d [reason]`"); return
    delta = parse_duration(duration)
    if not delta:
        await ctx.reply("❌ Invalid duration. Use e.g. `1d`, `12h`, `30m`."); return
    proof    = await get_proof(ctx)
    unban_at = datetime.now(timezone.utc) + delta
    if isinstance(target, discord.Member):
        await try_dm(target, embed=_action_embed("🔨 Temporarily Banned", 0xCC0000,
            [("Server", ctx.guild.name), ("Duration", duration),
             ("Unban", f"<t:{int(unban_at.timestamp())}:R>"),
             ("Reason", reason or "None")]))
    await ctx.guild.ban(discord.Object(id=target.id), reason=reason)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO tempbans (user_id,guild_id,unban_at) VALUES (?,?,?)",
            (target.id, ctx.guild.id, unban_at.isoformat()))
        await db.commit()
    await log_mod_action(bot, f"Tempban ({duration})", target, ctx.author, reason,
                         ctx.guild.id, proof[0] if proof else None)
    e = discord.Embed(title="🔨 Tempbanned", color=0xCC0000)
    e.add_field(name="User", value=f"{target} `{target.id}`")
    e.add_field(name="Duration", value=duration)
    e.add_field(name="Unban", value=f"<t:{int(unban_at.timestamp())}:R>")
    if proof:
        e.add_field(name="📎 Proof", value=f"[Jump]({proof[0]})\n> {proof[1]}", inline=False)
    await ctx.send(embed=e)

@bot.command(name="jail")
@commands.has_permissions(moderate_members=True)
async def pfx_jail(ctx: commands.Context, member=None, *, reason: str = None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    if not isinstance(target, discord.Member):
        await ctx.reply("❌ User must be in the server."); return
    ok = await _do_jail(ctx.guild, ctx.author, target, reason)
    if not ok:
        await ctx.reply("❌ Jail role not set. Use `/setjail` first."); return
    await ctx.send(embed=discord.Embed(
        description=f"🔒 Jailed {target.mention}.", color=0xFF6600))

@bot.command(name="unjail")
@commands.has_permissions(moderate_members=True)
async def pfx_unjail(ctx: commands.Context, member=None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member or reply to their message."); return
    if not isinstance(target, discord.Member):
        await ctx.reply("❌ User must be in the server."); return
    await _do_unjail(ctx.guild, ctx.author, target)
    await ctx.send(embed=discord.Embed(
        description=f"🔓 Released {target.mention}.", color=0x57F287))

@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def pfx_purge(ctx: commands.Context, amount: int):
    if not 1 <= amount <= 100:
        await ctx.reply("❌ Between 1-100."); return
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    m = await ctx.send(f"🗑️ Deleted **{len(deleted)}** messages.")
    await asyncio.sleep(5)
    try:
        await m.delete()
    except discord.NotFound:
        pass

@bot.command(name="nick")
@commands.has_permissions(manage_nicknames=True)
async def pfx_nick(ctx: commands.Context, member=None, *, nickname: str = None):
    target = await _prefix_resolve(ctx, member)
    if not target:
        await ctx.reply("❌ Specify a member."); return
    if not isinstance(target, discord.Member):
        await ctx.reply("❌ User must be in the server."); return
    await target.edit(nick=nickname)
    await ctx.send(embed=discord.Embed(
        description=f"✅ {target.mention} → **{nickname or 'reset'}**", color=0x57F287))

@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def pfx_slowmode(ctx: commands.Context, seconds: int):
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"⏱️ Slowmode → **{seconds}s**" if seconds else "⏱️ Slowmode disabled.")

@bot.command(name="lookup")
@commands.has_permissions(moderate_members=True)
async def pfx_lookup(ctx: commands.Context, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
    except (ValueError, discord.NotFound):
        await ctx.reply("❌ User not found."); return
    warns  = await get_warn_count(user.id, ctx.guild.id)
    member = ctx.guild.get_member(user.id)
    e = discord.Embed(title=str(user), color=0x5865F2)
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="ID",        value=str(user.id))
    e.add_field(name="Created",   value=f"<t:{int(user.created_at.timestamp())}:R>")
    e.add_field(name="In Server", value="✅" if member else "❌")
    e.add_field(name="Warns",     value=str(warns))
    await ctx.send(embed=e)

# – SECTION 10: ROLES ––––––––––––––––––––––––––––

role_group = app_commands.Group(name="role", description="Role management")

@role_group.command(name="add", description="Add a role to a member")
@app_commands.default_permissions(manage_roles=True)
async def role_add(i: discord.Interaction, member: discord.Member, role: discord.Role):
    if role >= i.guild.me.top_role:
        await i.response.send_message("❌ That role is higher than my top role.", ephemeral=True); return
    if role in member.roles:
        await i.response.send_message(f"❌ Already has {role.mention}.", ephemeral=True); return
    await member.add_roles(role, reason=f"By {i.user}")
    await log_mod_action(bot, "Role Add", member, i.user, f"+{role.name}", i.guild.id)
    await i.response.send_message(embed=discord.Embed(
        description=f"✅ Added {role.mention} to {member.mention}.", color=0x57F287))

@role_group.command(name="remove", description="Remove a role from a member")
@app_commands.default_permissions(manage_roles=True)
async def role_remove(i: discord.Interaction, member: discord.Member, role: discord.Role):
    if role >= i.guild.me.top_role:
        await i.response.send_message("❌ That role is higher than my top role.", ephemeral=True); return
    if role not in member.roles:
        await i.response.send_message(f"❌ Doesn't have {role.mention}.", ephemeral=True); return
    await member.remove_roles(role, reason=f"By {i.user}")
    await log_mod_action(bot, "Role Remove", member, i.user, f"-{role.name}", i.guild.id)
    await i.response.send_message(embed=discord.Embed(
        description=f"✅ Removed {role.mention} from {member.mention}.", color=0x57F287))

@role_group.command(name="info", description="Info about a role")
async def role_info(i: discord.Interaction, role: discord.Role):
    perms = [p.replace("_", " ").title() for p, v in role.permissions if v][:8]
    e = discord.Embed(title=f"🎭 {role.name}", color=role.color)
    e.add_field(name="ID",      value=str(role.id))
    e.add_field(name="Color",   value=str(role.color))
    e.add_field(name="Members", value=str(len(role.members)))
    e.add_field(name="Hoisted", value="Yes" if role.hoist else "No")
    e.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>")
    if perms:
        e.add_field(name="Key Permissions", value=", ".join(perms), inline=False)
    await i.response.send_message(embed=e)

@role_group.command(name="list", description="List all roles")
async def role_list(i: discord.Interaction):
    roles = sorted(i.guild.roles[1:], key=lambda r: r.position, reverse=True)
    lines, chunk, chunks = [], "", []
    for r in roles:
        line = f"{r.mention} `{len(r.members)}`\n"
        if len(chunk) + len(line) > 1000:
            chunks.append(chunk); chunk = line
        else:
            chunk += line
    if chunk: chunks.append(chunk)
    e = discord.Embed(title=f"🎭 Roles ({len(roles)})", color=0x5865F2)
    for idx, c in enumerate(chunks[:8]):
        e.add_field(name="\u200b" if idx else "Role – Members", value=c, inline=False)
    await i.response.send_message(embed=e)

@role_group.command(name="create", description="Create a new role")
@app_commands.default_permissions(manage_roles=True)
async def role_create(i: discord.Interaction, name: str, color: str = None):
    col = discord.Color.default()
    if color:
        try:
            col = discord.Color(int(color.strip("#"), 16))
        except ValueError:
            await i.response.send_message("❌ Invalid hex color.", ephemeral=True); return
    role = await i.guild.create_role(name=name, color=col, reason=f"By {i.user}")
    await i.response.send_message(embed=discord.Embed(
        description=f"✅ Created {role.mention}.", color=col))

@role_group.command(name="delete", description="Delete a role")
@app_commands.default_permissions(manage_roles=True)
async def role_delete(i: discord.Interaction, role: discord.Role):
    if role >= i.guild.me.top_role:
        await i.response.send_message("❌ Can't delete that role.", ephemeral=True); return
    name = role.name
    await role.delete(reason=f"By {i.user}")
    await i.response.send_message(embed=discord.Embed(
        description=f"🗑️ Deleted **{name}**.", color=0xFF4444))

@role_group.command(name="color", description="Change a role's color")
@app_commands.default_permissions(manage_roles=True)
async def role_color(i: discord.Interaction, role: discord.Role, color: str):
    if role >= i.guild.me.top_role:
        await i.response.send_message("❌ Can't edit that role.", ephemeral=True); return
    try:
        col = discord.Color(int(color.strip("#"), 16))
    except ValueError:
        await i.response.send_message("❌ Invalid hex color.", ephemeral=True); return
    await role.edit(color=col)
    await i.response.send_message(embed=discord.Embed(
        description=f"✅ {role.mention} → `{color}`", color=col))

@bot.command(name="roleadd")
@commands.has_permissions(manage_roles=True)
async def pfx_roleadd(ctx: commands.Context, member: discord.Member, role: discord.Role):
    if role in member.roles:
        await ctx.reply(f"❌ Already has {role.mention}."); return
    await member.add_roles(role)
    await ctx.send(embed=discord.Embed(
        description=f"✅ Added {role.mention} to {member.mention}.", color=0x57F287))

@bot.command(name="roleremove")
@commands.has_permissions(manage_roles=True)
async def pfx_roleremove(ctx: commands.Context, member: discord.Member, role: discord.Role):
    if role not in member.roles:
        await ctx.reply(f"❌ Doesn't have {role.mention}."); return
    await member.remove_roles(role)
    await ctx.send(embed=discord.Embed(
        description=f"✅ Removed {role.mention} from {member.mention}.", color=0x57F287))

@bot.command(name="roleinfo")
async def pfx_roleinfo(ctx: commands.Context, role: discord.Role):
    e = discord.Embed(title=f"🎭 {role.name}", color=role.color)
    e.add_field(name="Members", value=str(len(role.members)))
    e.add_field(name="Color",   value=str(role.color))
    e.add_field(name="Position", value=str(role.position))
    await ctx.send(embed=e)

@bot.command(name="rolelist")
async def pfx_rolelist(ctx: commands.Context):
    roles = sorted(ctx.guild.roles[1:], key=lambda r: r.position, reverse=True)
    lines = [f"{r.mention} `{len(r.members)}`" for r in roles[:20]]
    e = discord.Embed(title=f"🎭 Roles ({len(roles)})",
                      description="\n".join(lines), color=0x5865F2)
    if len(roles) > 20:
        e.set_footer(text=f"+{len(roles)-20} more")
    await ctx.send(embed=e)

# – SECTION 11: AUTOMOD ——————————————————

automod_group = app_commands.Group(name="automod", description="Automod settings")

@automod_group.command(name="toggle", description="Enable or disable automod")
@app_commands.default_permissions(administrator=True)
async def automod_toggle(i: discord.Interaction):
    cur = await get_setting(i.guild.id, 'automod_enabled') or 0
    new = 1 - int(cur)
    await set_setting(i.guild.id, 'automod_enabled', new)
    await i.response.send_message(
        f"✅ Automod {'**enabled**' if new else '**disabled**'}.", ephemeral=True)

@automod_group.command(name="addword", description="Add a word to the filter")
@app_commands.default_permissions(administrator=True)
async def automod_addword(i: discord.Interaction, word: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO automod_words (guild_id,word) VALUES (?,?)",
            (i.guild.id, word.lower()))
        await db.commit()
    await i.response.send_message(f"✅ Added `{word.lower()}`.", ephemeral=True)

@automod_group.command(name="removeword", description="Remove a word from the filter")
@app_commands.default_permissions(administrator=True)
async def automod_removeword(i: discord.Interaction, word: str):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "DELETE FROM automod_words WHERE guild_id=? AND word=?",
            (i.guild.id, word.lower()))
        await db.commit()
    await i.response.send_message(
        f"🗑️ Removed `{word.lower()}`." if cur.rowcount else f"❌ Not found.",
        ephemeral=True)

@automod_group.command(name="listwords", description="View filtered words")
@app_commands.default_permissions(administrator=True)
async def automod_listwords(i: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT word FROM automod_words WHERE guild_id=?", (i.guild.id,)
        ) as cur:
            words = [r[0] for r in await cur.fetchall()]
    if not words:
        await i.response.send_message("No words in filter.", ephemeral=True); return
    e = discord.Embed(title=f"🚫 Filtered Words ({len(words)})", color=0xFF4444)
    e.description = "||" + "||, ||".join(sorted(words)) + "||"
    await i.response.send_message(embed=e, ephemeral=True)

@automod_group.command(name="setaction", description="Action on filtered word")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(action=[
    app_commands.Choice(name="delete only", value="delete_only"),
    app_commands.Choice(name="warn user",   value="warn"),
    app_commands.Choice(name="mute user",   value="mute"),
])
async def automod_setaction(i: discord.Interaction, action: str):
    await set_setting(i.guild.id, 'automod_action', action)
    await i.response.send_message(f"✅ Automod action → `{action}`", ephemeral=True)

@automod_group.command(name="setmuteduration", description="Mute duration in minutes")
@app_commands.default_permissions(administrator=True)
async def automod_setmuteduration(i: discord.Interaction, minutes: int):
    await set_setting(i.guild.id, 'automod_mute_minutes', minutes)
    await i.response.send_message(f"✅ Mute duration → **{minutes}min**", ephemeral=True)

@automod_group.command(name="setwarnexpiry", description="Warn expiry e.g. 7d")
@app_commands.default_permissions(administrator=True)
async def automod_setwarnexpiry(i: discord.Interaction, duration: str):
    if not parse_duration(duration):
        await i.response.send_message("❌ Use e.g. `7d`, `24h`, `30m`.", ephemeral=True); return
    await set_setting(i.guild.id, 'automod_warn_expiry', duration)
    await i.response.send_message(f"✅ Warn expiry → **{duration}**", ephemeral=True)

async def _run_automod(message: discord.Message) -> bool:
    enabled = await get_setting(message.guild.id, 'automod_enabled')
    if not enabled:
        return False
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT word FROM automod_words WHERE guild_id=?", (message.guild.id,)
        ) as cur:
            words = {r[0].lower() for r in await cur.fetchall()}
    if not any(w in message.content.lower() for w in words):
        return False
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass
    action = await get_setting(message.guild.id, 'automod_action') or 'delete_only'
    if action == 'delete_only':
        await message.channel.send(
            f"{message.author.mention} ⚠️ Message removed.", delete_after=8)
    elif action == 'warn':
        expiry_str = await get_setting(message.guild.id, 'automod_warn_expiry')
        delta      = parse_duration(expiry_str) if expiry_str else None
        expires_at = datetime.now(timezone.utc) + delta if delta else None
        count = await add_warn(message.author.id, message.guild.id,
                               bot.user.id, "Automod: filtered word", expires_at)
        await message.channel.send(
            f"{message.author.mention} ⚠️ Watch your language! **{count}** warn(s).",
            delete_after=10)
    elif action == 'mute':
        minutes = safe_int(await get_setting(message.guild.id, 'automod_mute_minutes') or 10)
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            await message.author.edit(timed_out_until=until)
            await message.channel.send(
                f"{message.author.mention} 🔇 Muted **{minutes}min** for filtered word.",
                delete_after=10)
        except Exception as ex:
            print(f"Automod mute: {ex}")
    return True

# – SECTION 12: TRIGGERS —————————————————–

@bot.tree.command(name="settrigger", description="Add a trigger → response")
@app_commands.default_permissions(manage_messages=True)
@app_commands.choices(match_type=[
    app_commands.Choice(name="contains",   value="contains"),
    app_commands.Choice(name="startswith", value="startswith"),
])
async def cmd_settrigger(i: discord.Interaction, trigger: str, response: str,
                         match_type: str = "contains"):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO triggers (guild_id,trigger,response,match_type) VALUES (?,?,?,?)",
            (i.guild.id, trigger.lower(), response, match_type))
        await db.commit()
    e = discord.Embed(title="✅ Trigger added", color=0x57F287)
    e.add_field(name="Trigger",  value=f"`{trigger}`")
    e.add_field(name="Match",    value=match_type)
    e.add_field(name="Response", value=response[:200], inline=False)
    await i.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="listtriggers", description="List all triggers")
@app_commands.default_permissions(manage_messages=True)
async def cmd_listtriggers(i: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT id,trigger,response,match_type FROM triggers WHERE guild_id=?",
            (i.guild.id,)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await i.response.send_message("No triggers set.", ephemeral=True); return
    e = discord.Embed(title=f"⚡ Triggers ({len(rows)})", color=0x5865F2)
    for tid, trigger, response, match_type in rows:
        e.add_field(name=f"#{tid} `{trigger}` [{match_type}]",
                    value=response[:100] + ("…" if len(response) > 100 else ""),
                    inline=False)
    await i.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="deletetrigger", description="Delete a trigger by ID")
@app_commands.default_permissions(manage_messages=True)
async def cmd_deletetrigger(i: discord.Interaction, trigger_id: int):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "DELETE FROM triggers WHERE id=? AND guild_id=?", (trigger_id, i.guild.id))
        await db.commit()
    await i.response.send_message(
        f"🗑️ Deleted `#{trigger_id}`." if cur.rowcount else "❌ Not found.",
        ephemeral=True)

async def _run_triggers(message: discord.Message) -> bool:
    content = message.content.lower()
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT trigger,response,match_type FROM triggers WHERE guild_id=?",
            (message.guild.id,)
        ) as cur:
            rows = await cur.fetchall()
    for trigger, response, match_type in rows:
        matched = ((match_type == 'startswith' and content.startswith(trigger)) or
                   (match_type == 'contains'   and trigger in content))
        if matched:
            if is_url(response):
                e = discord.Embed(color=0x5865F2)
                e.set_image(url=response.strip())
                await message.channel.send(embed=e)
            else:
                await message.channel.send(response)
            return True
    return False

# – SECTION 13: FUN COMMANDS ———————————————––

EIGHTBALL = [
    "It is certain.", "Without a doubt.", "Yes, definitely.", "As I see it, yes.",
    "You may rely on it.", "Reply hazy, try again.", "Ask again later.",
    "Better not tell you now.", "Don't count on it.", "Very doubtful.",
    "My sources say no.", "Outlook not so good.",
]
DEADCHAT_LINES = [
    "Chat is dead 💀 someone say something",
    "Bro what happened to the conversation",
    "Hello? Anyone here?",
    "The silence is deafening rn",
    "Y'all really just went quiet like that",
    "Chat needs CPR fr",
]
TOPICS = [
    "Would you rather lose your phone or your wallet for a week?",
    "Hot take: what's the most overrated skill people brag about?",
    "If you could add one rule to this server what would it be?",
    "What's something you changed your mind about recently?",
    "Best thing that happened to you this week?",
    "If money wasn't a factor what would you work on?",
    "Most underrated country in the world. Go.",
    "Rate your productivity today 1-10 and explain.",
    "Unpopular opinion: go.",
    "What's a skill you actually want to learn in the next 6 months?",
]
GIF_URLS = {
    "hug":   "https://media.tenor.com/BfWfOXsnfOkAAAAC/hug-anime.gif",
    "slap":  "https://media.tenor.com/u7R5gKgkbEkAAAAC/anime-slap.gif",
    "bite":  "https://media.tenor.com/JXymFdGh-ZIAAAAC/anime-bite.gif",
    "punch": "https://media.tenor.com/CUxJgbZ_3IQAAAAC/anime-punch.gif",
    "kick":  "https://media.tenor.com/ZXxsmWdJMNwAAAAC/kick-anime.gif",
}
GIF_META = {
    "hug": ("🤗", 0xFF69B4), "slap": ("👋", 0xFF4500),
    "bite": ("😬", 0x8B0000), "punch": ("👊", 0xFF6600), "kick": ("🦵", 0xFFAA00),
}

def _gif_embed(action: str, actor: discord.Member, target: discord.Member) -> discord.Embed:
    emoji, color = GIF_META[action]
    e = discord.Embed(description=f"{actor.mention} {emoji} **{action}s** {target.mention}!",
                      color=color)
    e.set_image(url=GIF_URLS[action])
    return e

# Slash fun commands

@bot.tree.command(name="meme", description="Random meme")
async def cmd_meme(i: discord.Interaction):
    rem = await check_cooldown(i.guild_id, i.user.id, "meme")
    if rem > 0:
        await i.response.send_message(f"⏳ Wait **{rem:.1f}s**.", ephemeral=True); return
    set_cooldown(i.guild_id, i.user.id, "meme")
    await i.response.defer()
    async with aiohttp.ClientSession() as s:
        async with s.get("https://meme-api.com/gimme") as r:
            if r.status == 200:
                data = await r.json()
                e = discord.Embed(title=data.get("title", ""), color=0xFF4500)
                e.set_image(url=data["url"])
                await i.followup.send(embed=e)
            else:
                await i.followup.send("meme api is down lol")

@bot.tree.command(name="roast", description="Roast someone")
async def cmd_roast(i: discord.Interaction, target: str):
    rem = await check_cooldown(i.guild_id, i.user.id, "roast")
    if rem > 0:
        await i.response.send_message(f"⏳ Wait **{rem:.1f}s**.", ephemeral=True); return
    set_cooldown(i.guild_id, i.user.id, "roast")
    await i.response.defer()
    try:
        resp = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Roast {target}. Two sentences max. Actually make it funny, not generic."}
            ],
            max_tokens=120
        )
        await i.followup.send(f"🔥 {resp.choices[0].message.content}")
    except Exception as ex:
        print("Roast error:", ex)
        await i.followup.send("couldn't pull up a roast, try again")

@bot.tree.command(name="8ball", description="Ask the magic 8-ball")
async def cmd_8ball(i: discord.Interaction, question: str):
    rem = await check_cooldown(i.guild_id, i.user.id, "8ball")
    if rem > 0:
        await i.response.send_message(f"⏳ Wait **{rem:.1f}s**.", ephemeral=True); return
    set_cooldown(i.guild_id, i.user.id, "8ball")
    e = discord.Embed(color=0x5865F2)
    e.add_field(name="❓ Question", value=question, inline=False)
    e.add_field(name="🎱 Answer",   value=random.choice(EIGHTBALL), inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="poll", description="Create a poll")
async def cmd_poll(i: discord.Interaction, question: str, option1: str, option2: str,
                   option3: str = None, option4: str = None):
    rem = await check_cooldown(i.guild_id, i.user.id, "poll")
    if rem > 0:
        await i.response.send_message(f"⏳ Wait **{rem:.1f}s**.", ephemeral=True); return
    set_cooldown(i.guild_id, i.user.id, "poll")
    opts   = [o for o in [option1, option2, option3, option4] if o]
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
    e = discord.Embed(title=f"📊 {question}", color=0x5865F2)
    for idx, opt in enumerate(opts):
        e.add_field(name=f"{emojis[idx]} Option {idx+1}", value=opt, inline=False)
    e.set_footer(text=f"Poll by {i.user.display_name}")
    await i.response.send_message(embed=e)
    msg = await i.original_response()
    for idx in range(len(opts)):
        await msg.add_reaction(emojis[idx])

@bot.tree.command(name="remind", description="Set a reminder e.g. 30m 2h 1d")
async def cmd_remind(i: discord.Interaction, time: str, message: str):
    delta = parse_duration(time)
    if not delta:
        await i.response.send_message("❌ Use e.g. `30m`, `2h`, `1d`.", ephemeral=True); return
    remind_at = datetime.now(timezone.utc) + delta
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO reminders (user_id,channel_id,message,remind_at) VALUES (?,?,?,?)",
            (i.user.id, i.channel.id, message, remind_at.isoformat()))
        await db.commit()
    await i.response.send_message(
        f"⏰ Set! I'll remind you in **{time}**: {message}", ephemeral=True)

@bot.tree.command(name="snipe", description="Show last deleted messages")
async def cmd_snipe(i: discord.Interaction):
    cache = snipe_cache.get(i.channel.id, [])
    if not cache:
        await i.response.send_message("Nothing to snipe 🏹", ephemeral=True); return
    embeds = []
    for idx, msg in enumerate(cache, 1):
        e = discord.Embed(description=msg["content"], color=0x5865F2, timestamp=msg["time"])
        e.set_author(name=msg["author"], icon_url=msg["avatar"])
        e.set_footer(text=f"#{idx}")
        embeds.append(e)
    await i.response.send_message(embeds=embeds)

@bot.tree.command(name="afk", description="Set yourself AFK")
async def cmd_afk(i: discord.Interaction, reason: str = None):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO afk (user_id,guild_id,reason,timestamp) VALUES (?,?,?,?)",
            (i.user.id, i.guild.id, reason, datetime.now(timezone.utc).isoformat()))
        await db.commit()
    await i.response.send_message(f"💤 AFK: {reason or 'No reason'}", ephemeral=True)

@bot.tree.command(name="deadchat", description="Revive dead chat")
async def cmd_deadchat(i: discord.Interaction):
    perm_role_id = await get_setting_int(i.guild.id, 'deadchat_perm_role')
    if perm_role_id:
        has = (any(r.id == perm_role_id for r in i.user.roles) or
               i.user.guild_permissions.administrator)
        if not has:
            role = i.guild.get_role(int(perm_role_id))
            await i.response.send_message(
                f"❌ Only **{role.name if role else 'a specific role'}** can use this.",
                ephemeral=True); return
    rem = await check_cooldown(i.guild_id, i.user.id, "deadchat")
    if rem > 0:
        m, s = divmod(int(rem), 60)
        await i.response.send_message(
            f"⏳ Cooldown: **{'%dm %ds'%(m,s) if m else '%ds'%s}**", ephemeral=True); return
    set_cooldown(i.guild_id, i.user.id, "deadchat")
    ping_id = await get_setting_int(i.guild.id, 'deadchat_role_id')
    content = (f"<@&{ping_id}> " if ping_id else "") + random.choice(DEADCHAT_LINES)
    await i.response.send_message(content, allowed_mentions=discord.AllowedMentions.all())

@bot.tree.command(name="say", description="Make the bot say something")
@app_commands.default_permissions(manage_messages=True)
async def cmd_say(i: discord.Interaction, message: str, role: discord.Role = None):
    content = (f"{role.mention} " if role else "") + message
    await i.response.send_message("✅", ephemeral=True)
    await i.channel.send(content, allowed_mentions=discord.AllowedMentions.all())

@bot.tree.command(name="announce", description="Send message to any channel")
@app_commands.default_permissions(manage_messages=True)
async def cmd_announce(i: discord.Interaction, channel: discord.TextChannel,
                       message: str, role: discord.Role = None):
    content = (f"{role.mention} " if role else "") + message
    await i.response.send_message(f"✅ Sent to {channel.mention}", ephemeral=True)
    await channel.send(content, allowed_mentions=discord.AllowedMentions.all())

@bot.tree.command(name="pingrole", description="Ping a role")
@app_commands.default_permissions(manage_messages=True)
async def cmd_pingrole(i: discord.Interaction, role: discord.Role):
    await i.response.send_message(f"{role.mention}",
                                  allowed_mentions=discord.AllowedMentions.all())

@bot.tree.command(name="hug",   description="Hug someone 🤗")
async def cmd_hug(i: discord.Interaction, member: discord.Member):
    await i.response.send_message(embed=_gif_embed("hug", i.user, member))

@bot.tree.command(name="slap",  description="Slap someone 👋")
async def cmd_slap(i: discord.Interaction, member: discord.Member):
    await i.response.send_message(embed=_gif_embed("slap", i.user, member))

@bot.tree.command(name="bite",  description="Bite someone 😬")
async def cmd_bite(i: discord.Interaction, member: discord.Member):
    await i.response.send_message(embed=_gif_embed("bite", i.user, member))

@bot.tree.command(name="punch", description="Punch someone 👊")
async def cmd_punch(i: discord.Interaction, member: discord.Member):
    await i.response.send_message(embed=_gif_embed("punch", i.user, member))

@bot.tree.command(name="avatar", description="Get someone's avatar")
async def cmd_avatar(i: discord.Interaction, member: discord.Member = None):
    target = member or i.user
    url = str(target.display_avatar.replace(size=1024, format="png"))
    e = discord.Embed(title=f"{target.display_name}'s Avatar", color=0x5865F2)
    e.set_image(url=url)
    e.add_field(name="Download", value=f"[PNG 1024px]({url})")
    await i.response.send_message(embed=e)

@bot.tree.command(name="banner", description="Get someone's banner")
async def cmd_banner(i: discord.Interaction, member: discord.Member = None):
    target = member or i.user
    await i.response.defer()
    user = await bot.fetch_user(target.id)
    if not user.banner:
        await i.followup.send("This user doesn't have a banner."); return
    url = str(user.banner.replace(size=1024))
    e = discord.Embed(title=f"{target.display_name}'s Banner", color=0x5865F2)
    e.set_image(url=url)
    await i.followup.send(embed=e)

@bot.tree.command(name="servericon", description="Show the server icon")
async def cmd_servericon(i: discord.Interaction):
    if not i.guild.icon:
        await i.response.send_message("This server has no icon.", ephemeral=True); return
    url = str(i.guild.icon.replace(size=1024, format="png"))
    e = discord.Embed(title=f"{i.guild.name} – Icon", color=0x5865F2)
    e.set_image(url=url)
    await i.response.send_message(embed=e)

@bot.tree.command(name="coinflip", description="Flip a coin")
async def cmd_coinflip(i: discord.Interaction):
    await i.response.send_message(
        f"**{random.choice(['Heads 🪙', 'Tails 🪙'])}**")

@bot.tree.command(name="dice", description="Roll a dice")
async def cmd_dice(i: discord.Interaction, sides: int = 6):
    if sides < 2:
        await i.response.send_message("Minimum 2 sides.", ephemeral=True); return
    await i.response.send_message(
        f"🎲 Rolled a **d{sides}**: **{random.randint(1, sides)}**")

@bot.tree.command(name="calc", description="Calculate a math expression")
async def cmd_calc(i: discord.Interaction, expression: str):
    try:
        allowed = set("0123456789+-*/().% ")
        if not all(c in allowed for c in expression):
            raise ValueError
        result = eval(expression, {"__builtins__": {}}, {})  # nosec
        await i.response.send_message(f"`{expression}` = **{result}**")
    except ZeroDivisionError:
        await i.response.send_message("Can't divide by zero.", ephemeral=True)
    except Exception:
        await i.response.send_message(
            "❌ Invalid. Use basic math: `2+2`, `10*5`, `100/4`.", ephemeral=True)

@bot.tree.command(name="urban", description="Look up a term on Urban Dictionary")
async def cmd_urban(i: discord.Interaction, term: str):
    rem = await check_cooldown(i.guild_id, i.user.id, "urban")
    if rem > 0:
        await i.response.send_message(f"⏳ Wait **{rem:.1f}s**.", ephemeral=True); return
    set_cooldown(i.guild_id, i.user.id, "urban")
    await i.response.defer()
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.urbandictionary.com/v0/define",
                         params={"term": term}) as r:
            if r.status != 200:
                await i.followup.send("Urban Dictionary is down rn."); return
            data = await r.json()
            results = data.get("list", [])
            if not results:
                await i.followup.send(f"No definition found for **{term}**."); return
            top  = results[0]
            defn = top.get("definition", "")[:800].replace("[", "").replace("]", "")
            ex   = top.get("example", "")[:400].replace("[", "").replace("]", "")
            e = discord.Embed(title=f"📖 {top['word']}", url=top.get("permalink", ""),
                              description=defn, color=0x1D2439)
            if ex:
                e.add_field(name="Example", value=f"*{ex}*", inline=False)
            e.set_footer(text=f"👍 {top.get('thumbs_up',0)}  👎 {top.get('thumbs_down',0)}")
            await i.followup.send(embed=e)

@bot.tree.command(name="topic", description="Post a random conversation starter")
async def cmd_topic(i: discord.Interaction):
    await i.response.send_message(f"💬 {random.choice(TOPICS)}")

@bot.tree.command(name="firstmessage",
                  description="Link to a member's first message in this channel")
async def cmd_firstmessage(i: discord.Interaction, member: discord.Member = None):
    target = member or i.user
    await i.response.defer()
    async for msg in i.channel.history(limit=None, oldest_first=True):
        if msg.author.id == target.id:
            e = discord.Embed(
                title=f"📜 First message by {target.display_name}",
                description=msg.content[:500] or "*[no text]*",
                color=0x5865F2, timestamp=msg.created_at)
            e.set_thumbnail(url=target.display_avatar.url)
            e.add_field(name="Jump", value=f"[Click here]({msg.jump_url})")
            await i.followup.send(embed=e)
            return
    await i.followup.send(f"No messages from {target.mention} found in this channel.")

@bot.tree.command(name="mybookmarks", description="View your bookmarked messages")
async def cmd_mybookmarks(i: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT author_name,content,jump_url,timestamp FROM bookmarks"
            " WHERE user_id=? AND guild_id=? ORDER BY timestamp DESC LIMIT 10",
            (i.user.id, i.guild.id)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await i.response.send_message(
            "No bookmarks yet. React 🔖 to any message to save it.", ephemeral=True); return
    e = discord.Embed(title="🔖 Your Bookmarks", color=0xFFD700)
    for author, content, jump_url, ts in rows:
        e.add_field(
            name=f"{author} – {ts[:10]}",
            value=f"{content[:80]}{'…' if len(content)>80 else ''}\n[Jump]({jump_url})",
            inline=False)
    await i.response.send_message(embed=e, ephemeral=True)

# Custom commands management

@bot.tree.command(name="addcommand", description="Add a custom command")
@app_commands.default_permissions(manage_guild=True)
@app_commands.choices(action_type=[
    app_commands.Choice(name="message – send text", value="message"),
    app_commands.Choice(name="ping – mention someone", value="ping"),
    app_commands.Choice(name="alias – run another command", value="alias"),
])
async def cmd_addcommand(i: discord.Interaction, name: str, action_type: str, value: str):
    name = name.lower().strip()
    async with aiosqlite.connect(DB) as db:
        try:
            await db.execute(
                "INSERT INTO custom_commands (guild_id,name,action_type,value) VALUES (?,?,?,?)",
                (i.guild.id, name, action_type, value))
            await db.commit()
        except Exception:
            await i.response.send_message(
                f"❌ `{name}` already exists.", ephemeral=True); return
    await i.response.send_message(
        f"✅ `{name}` added as **{action_type}**: {value}", ephemeral=True)

@bot.tree.command(name="listcommands", description="List all custom commands")
async def cmd_listcommands(i: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT name,action_type,value FROM custom_commands WHERE guild_id=?",
            (i.guild.id,)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await i.response.send_message("No custom commands.", ephemeral=True); return
    e = discord.Embed(title=f"⚡ Custom Commands ({len(rows)})", color=0x5865F2)
    for name, atype, value in rows:
        e.add_field(name=f"`{name}` [{atype}]", value=value[:80], inline=False)
    await i.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="deletecommand", description="Delete a custom command")
@app_commands.default_permissions(manage_guild=True)
async def cmd_deletecommand(i: discord.Interaction, name: str):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "DELETE FROM custom_commands WHERE guild_id=? AND name=?",
            (i.guild.id, name.lower()))
        await db.commit()
    await i.response.send_message(
        f"🗑️ Deleted `{name}`." if cur.rowcount else "❌ Not found.", ephemeral=True)

@bot.tree.command(name="steal", description="Steal an emoji from another server")
@app_commands.default_permissions(manage_emojis=True)
@app_commands.describe(emoji="Paste the custom emoji here", name="Name for it (optional)")
async def cmd_steal(i: discord.Interaction, emoji: str, name: str = None):
    await i.response.defer()
    match = re.search(r'<a?:(\w+):(\d+)>', emoji)
    if not match:
        await i.followup.send("❌ That doesn't look like a custom emoji.", ephemeral=True); return
    emoji_name = name or match.group(1)
    emoji_id   = match.group(2)
    animated   = emoji.startswith("<a:")
    ext        = "gif" if animated else "png"
    url        = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status != 200:
                await i.followup.send("❌ Couldn't fetch that emoji.", ephemeral=True); return
            image_data = await r.read()
    try:
        new_emoji = await i.guild.create_custom_emoji(name=emoji_name, image=image_data)
        await i.followup.send(f"✅ Stolen! {new_emoji} `:{new_emoji.name}:`")
    except discord.HTTPException as e:
        await i.followup.send(f"❌ Failed: {e}", ephemeral=True)

# Prefix fun commands (same as slash, just prefix version)

@bot.command(name="meme")
async def pfx_meme(ctx: commands.Context):
    rem = await check_cooldown(ctx.guild.id, ctx.author.id, "meme")
    if rem > 0:
        await ctx.reply(f"⏳ Wait **{rem:.1f}s**."); return
    set_cooldown(ctx.guild.id, ctx.author.id, "meme")
    async with aiohttp.ClientSession() as s:
        async with s.get("https://meme-api.com/gimme") as r:
            if r.status == 200:
                data = await r.json()
                e = discord.Embed(title=data.get("title",""), color=0xFF4500)
                e.set_image(url=data["url"])
                await ctx.send(embed=e)

@bot.command(name="roast")
async def pfx_roast(ctx: commands.Context, *, target: str):
    rem = await check_cooldown(ctx.guild.id, ctx.author.id, "roast")
    if rem > 0:
        await ctx.reply(f"⏳ Wait **{rem:.1f}s**."); return
    set_cooldown(ctx.guild.id, ctx.author.id, "roast")
    try:
        resp = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Roast {target}. Two sentences max."}
            ],
            max_tokens=120
        )
        await ctx.send(f"🔥 {resp.choices[0].message.content}")
    except Exception:
        await ctx.reply("couldn't roast rn")

@bot.command(name="8ball")
async def pfx_8ball(ctx: commands.Context, *, question: str):
    e = discord.Embed(color=0x5865F2)
    e.add_field(name="❓", value=question, inline=False)
    e.add_field(name="🎱", value=random.choice(EIGHTBALL), inline=False)
    await ctx.send(embed=e)

@bot.command(name="poll")
async def pfx_poll(ctx: commands.Context, *, args: str):
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 3:
        await ctx.reply("❌ Format: `?poll Question | Option1 | Option2`"); return
    question, *opts = parts
    opts   = opts[:4]
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
    e = discord.Embed(title=f"📊 {question}", color=0x5865F2)
    for idx, opt in enumerate(opts):
        e.add_field(name=f"{emojis[idx]} Option {idx+1}", value=opt, inline=False)
    msg = await ctx.send(embed=e)
    for idx in range(len(opts)):
        await msg.add_reaction(emojis[idx])

@bot.command(name="remind")
async def pfx_remind(ctx: commands.Context, time: str, *, message: str):
    delta = parse_duration(time)
    if not delta:
        await ctx.reply("❌ Use e.g. `30m`, `2h`, `1d`."); return
    remind_at = datetime.now(timezone.utc) + delta
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO reminders (user_id,channel_id,message,remind_at) VALUES (?,?,?,?)",
            (ctx.author.id, ctx.channel.id, message, remind_at.isoformat()))
        await db.commit()
    await ctx.reply(f"⏰ Set! Reminding you in **{time}**: {message}")

@bot.command(name="snipe")
async def pfx_snipe(ctx: commands.Context):
    cache = snipe_cache.get(ctx.channel.id, [])
    if not cache:
        await ctx.reply("Nothing to snipe 🏹"); return
    embeds = []
    for idx, msg in enumerate(cache, 1):
        e = discord.Embed(description=msg["content"], color=0x5865F2, timestamp=msg["time"])
        e.set_author(name=msg["author"], icon_url=msg["avatar"])
        e.set_footer(text=f"#{idx}")
        embeds.append(e)
    await ctx.send(embeds=embeds)

@bot.command(name="afk")
async def pfx_afk(ctx: commands.Context, *, reason: str = None):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO afk (user_id,guild_id,reason,timestamp) VALUES (?,?,?,?)",
            (ctx.author.id, ctx.guild.id, reason, datetime.now(timezone.utc).isoformat()))
        await db.commit()
    await ctx.reply(f"💤 AFK: {reason or 'No reason'}")

@bot.command(name="deadchat")
async def pfx_deadchat(ctx: commands.Context):
    perm_role_id = await get_setting_int(ctx.guild.id, 'deadchat_perm_role')
    if perm_role_id:
        has = (any(r.id == perm_role_id for r in ctx.author.roles) or
               ctx.author.guild_permissions.administrator)
        if not has:
            await ctx.reply("❌ You can't use deadchat."); return
    rem = await check_cooldown(ctx.guild.id, ctx.author.id, "deadchat")
    if rem > 0:
        m, s = divmod(int(rem), 60)
        await ctx.reply(f"⏳ Cooldown: **{'%dm %ds'%(m,s) if m else '%ds'%s}**"); return
    set_cooldown(ctx.guild.id, ctx.author.id, "deadchat")
    ping_id = await get_setting_int(ctx.guild.id, 'deadchat_role_id')
    content = (f"<@&{ping_id}> " if ping_id else "") + random.choice(DEADCHAT_LINES)
    await ctx.send(content, allowed_mentions=discord.AllowedMentions.all())

@bot.command(name="say")
@commands.has_permissions(manage_messages=True)
async def pfx_say(ctx: commands.Context, *, message: str):
    await ctx.message.delete()
    await ctx.send(message)

@bot.command(name="announce")
@commands.has_permissions(manage_messages=True)
async def pfx_announce(ctx: commands.Context, channel: discord.TextChannel, *, message: str):
    await channel.send(message)
    await ctx.send(f"✅ Sent to {channel.mention}", delete_after=5)

@bot.command(name="pingrole")
@commands.has_permissions(manage_messages=True)
async def pfx_pingrole(ctx: commands.Context, role: discord.Role):
    await ctx.send(f"{role.mention}", allowed_mentions=discord.AllowedMentions.all())

@bot.command(name="hug")
async def pfx_hug(ctx: commands.Context, member: discord.Member):
    await ctx.send(embed=_gif_embed("hug", ctx.author, member))

@bot.command(name="slap")
async def pfx_slap(ctx: commands.Context, member: discord.Member):
    await ctx.send(embed=_gif_embed("slap", ctx.author, member))

@bot.command(name="bite")
async def pfx_bite(ctx: commands.Context, member: discord.Member):
    await ctx.send(embed=_gif_embed("bite", ctx.author, member))

@bot.command(name="punch")
async def pfx_punch(ctx: commands.Context, member: discord.Member):
    await ctx.send(embed=_gif_embed("punch", ctx.author, member))

@bot.command(name="avatar")
async def pfx_avatar(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    url = str(target.display_avatar.replace(size=1024, format="png"))
    e = discord.Embed(title=f"{target.display_name}'s Avatar", color=0x5865F2)
    e.set_image(url=url)
    await ctx.send(embed=e)

@bot.command(name="servericon")
async def pfx_servericon(ctx: commands.Context):
    if not ctx.guild.icon:
        await ctx.reply("This server has no icon."); return
    url = str(ctx.guild.icon.replace(size=1024, format="png"))
    e = discord.Embed(title=f"{ctx.guild.name} – Icon", color=0x5865F2)
    e.set_image(url=url)
    await ctx.send(embed=e)

@bot.command(name="quote")
async def pfx_quote(ctx: commands.Context):
    if not ctx.message.reference:
        await ctx.reply("❌ Reply to a message to quote it."); return
    try:
        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except Exception:
        await ctx.reply("❌ Couldn't fetch that message."); return
    async with ctx.typing():
        try:
            buf = await build_quote_image(ref)
            await ctx.send(file=discord.File(buf, filename="quote.png"))
        except Exception as ex:
            print(f"Quote image error: {ex}")
            e = discord.Embed(description=ref.content[:2000] or "*[no text]*",
                              color=0x5865F2, timestamp=ref.created_at)
            e.set_author(name=ref.author.display_name,
                         icon_url=ref.author.display_avatar.url)
            e.add_field(name="Source", value=f"[Jump]({ref.jump_url})")
            await ctx.send(embed=e)

@bot.command(name="coinflip")
async def pfx_coinflip(ctx: commands.Context):
    await ctx.send(f"**{random.choice(['Heads 🪙', 'Tails 🪙'])}**")

@bot.command(name="dice")
async def pfx_dice(ctx: commands.Context, sides: int = 6):
    if sides < 2:
        await ctx.reply("Minimum 2 sides."); return
    await ctx.send(f"🎲 Rolled a **d{sides}**: **{random.randint(1, sides)}**")

@bot.command(name="calc")
async def pfx_calc(ctx: commands.Context, *, expression: str):
    try:
        allowed = set("0123456789+-*/().% ")
        if not all(c in allowed for c in expression):
            raise ValueError
        result = eval(expression, {"__builtins__": {}}, {})  # nosec
        await ctx.send(f"`{expression}` = **{result}**")
    except ZeroDivisionError:
        await ctx.reply("Can't divide by zero.")
    except Exception:
        await ctx.reply("❌ Invalid expression.")

@bot.command(name="urban")
async def pfx_urban(ctx: commands.Context, *, term: str):
    rem = await check_cooldown(ctx.guild.id, ctx.author.id, "urban")
    if rem > 0:
        await ctx.reply(f"⏳ Wait **{rem:.1f}s**."); return
    set_cooldown(ctx.guild.id, ctx.author.id, "urban")
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.urbandictionary.com/v0/define",
                         params={"term": term}) as r:
            if r.status != 200:
                await ctx.reply("Urban Dictionary is down."); return
            data = await r.json()
            results = data.get("list", [])
            if not results:
                await ctx.reply(f"No definition for **{term}**."); return
            top  = results[0]
            defn = top.get("definition","")[:800].replace("[","").replace("]","")
            ex   = top.get("example","")[:400].replace("[","").replace("]","")
            e = discord.Embed(title=f"📖 {top['word']}", description=defn, color=0x1D2439)
            if ex:
                e.add_field(name="Example", value=f"*{ex}*", inline=False)
            e.set_footer(text=f"👍 {top.get('thumbs_up',0)}  👎 {top.get('thumbs_down',0)}")
            await ctx.send(embed=e)

@bot.command(name="topic")
async def pfx_topic(ctx: commands.Context):
    await ctx.send(f"💬 {random.choice(TOPICS)}")

@bot.command(name="firstmessage")
async def pfx_firstmessage(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    async with ctx.typing():
        async for msg in ctx.channel.history(limit=None, oldest_first=True):
            if msg.author.id == target.id:
                e = discord.Embed(
                    title=f"📜 First message by {target.display_name}",
                    description=msg.content[:500] or "*[no text]*",
                    color=0x5865F2, timestamp=msg.created_at)
                e.set_thumbnail(url=target.display_avatar.url)
                e.add_field(name="Jump", value=f"[Click here]({msg.jump_url})")
                await ctx.send(embed=e)
                return
        await ctx.reply("No messages found.")

@bot.command(name="mybookmarks")
async def pfx_mybookmarks(ctx: commands.Context):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT author_name,content,jump_url,timestamp FROM bookmarks"
            " WHERE user_id=? AND guild_id=? ORDER BY timestamp DESC LIMIT 10",
            (ctx.author.id, ctx.guild.id)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await ctx.reply("No bookmarks yet. React 🔖 to save a message."); return
    e = discord.Embed(title="🔖 Your Bookmarks", color=0xFFD700)
    for author, content, jump_url, ts in rows:
        e.add_field(
            name=f"{author} – {ts[:10]}",
            value=f"{content[:80]}{'…' if len(content)>80 else ''}\n[Jump]({jump_url})",
            inline=False)
    await ctx.send(embed=e)

# – SECTION 14: INFO ———————————————————

@bot.tree.command(name="userinfo", description="View info about a member")
async def cmd_userinfo(i: discord.Interaction, member: discord.Member = None):
    target = member or i.user
    warns  = await get_warn_count(target.id, i.guild.id)
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM mod_logs WHERE guild_id=? AND user_id=?",
            (i.guild.id, target.id)
        ) as cur:
            log_count = (await cur.fetchone())[0]
    roles = [r.mention for r in reversed(target.roles[1:])][:12]
    e = discord.Embed(title=str(target),
                      color=target.color if target.color != discord.Color.default() else discord.Color.blurple())
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="ID",             value=str(target.id))
    e.add_field(name="Joined",         value=f"<t:{int(target.joined_at.timestamp())}:R>")
    e.add_field(name="Registered",     value=f"<t:{int(target.created_at.timestamp())}:R>")
    e.add_field(name="Active Warns",   value=str(warns))
    e.add_field(name="Total Mod Logs", value=str(log_count))
    e.add_field(name="Bot",            value="✅" if target.bot else "❌")
    e.add_field(name=f"Roles ({len(target.roles)-1})",
                value=" ".join(roles) if roles else "None", inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="serverinfo", description="View server info")
async def cmd_serverinfo(i: discord.Interaction):
    g = i.guild
    e = discord.Embed(title=g.name, color=0x5865F2, timestamp=datetime.now(timezone.utc))
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="Owner",    value=g.owner.mention if g.owner else "Unknown")
    e.add_field(name="Members",  value=str(g.member_count))
    e.add_field(name="Channels", value=str(len(g.channels)))
    e.add_field(name="Roles",    value=str(len(g.roles)))
    e.add_field(name="Boosts",   value=str(g.premium_subscription_count))
    e.add_field(name="Created",  value=f"<t:{int(g.created_at.timestamp())}:R>")
    await i.response.send_message(embed=e)

@bot.tree.command(name="ping", description="Check latency")
async def cmd_ping(i: discord.Interaction):
    await i.response.send_message(
        f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@bot.tree.command(name="help", description="Show all commands")
async def cmd_help(i: discord.Interaction):
    prefix = prefix_cache.get(i.guild.id, "?") if i.guild else "?"
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT name,action_type FROM custom_commands WHERE guild_id=?",
            (i.guild.id,)
        ) as cur:
            custom = await cur.fetchall()
    e = discord.Embed(
        title="🐦 that one bird – Commands",
        description=f"Prefix: `{prefix}` · Most commands work as both `/slash` and `{prefix}prefix`",
        color=0x5865F2)
    e.add_field(name="⚙️ Admin / Settings", inline=False, value=
        f"`/setup` (dropdown) · `/setprefix` · `/setlogchannel` · `/setwelcome`\n"
        f"`/setautorole` · `/setjail` · `/setstarboard` · `/setchapterchannel`\n"
        f"`/setcommandperms` · `/setdisplay` · `/setwarnthreshold`\n"
        f"`/antiraidsettings` · `/antiraidtoggle` · `/automod` group")
    e.add_field(name="🔨 Moderation", inline=False, value=
        f"`warn/unwarn/clearwarns/warns/history/modlogs`\n"
        f"`mute/unmute/kick/ban/unban/tempban/jail/unjail`\n"
        f"`purge/nick/slowmode/lookup`\n"
        f"Reply to a message → auto-targets user + attaches proof")
    e.add_field(name="🎭 Roles", inline=False, value=
        f"`/role add/remove/info/list/create/delete/color`\n"
        f"`{prefix}roleadd` · `{prefix}roleremove` · `{prefix}roleinfo` · `{prefix}rolelist`")
    e.add_field(name="🎉 Fun", inline=False, value=
        f"`meme` · `roast` · `8ball` · `poll` · `remind` · `snipe`\n"
        f"`afk` · `deadchat` · `topic` · `coinflip` · `dice` · `calc`\n"
        f"`urban` · `firstmessage` · `hug/slap/bite/punch`\n"
        f"`say/announce/pingrole` · `/steal` (emoji)")
    e.add_field(name="🖼️ Media", inline=False, value=
        f"`avatar` · `/banner` · `servericon`\n"
        f"`{prefix}quote` (reply to a message) · `mybookmarks`\n"
        f"React 🔖 to any message to bookmark it")
    e.add_field(name="📖 Blood Trials", inline=False, value=
        f"`/character <name>` · `{prefix}character <name>`\n"
        f"Chapters + characters auto-announced from Supabase")
    e.add_field(name="ℹ️ Info", inline=False, value=
        f"`userinfo` · `serverinfo` · `ping`")
    if custom:
        e.add_field(name="⚡ Custom Commands", inline=False,
                    value="\n".join(f"`{prefix}{n}` [{t}]" for n, t in custom[:8]))
    e.add_field(name="🤖 AI Chat", inline=False, value=
        f"Mention me or chat in `#ai-chat` – I'll respond as Umar")
    e.set_footer(text="that one bird 🐦 · Powered by Groq llama-3.3-70b")
    await i.response.send_message(embed=e, ephemeral=True)

@bot.command(name="userinfo")
async def pfx_userinfo(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    warns  = await get_warn_count(target.id, ctx.guild.id)
    roles  = [r.mention for r in reversed(target.roles[1:])][:12]
    e = discord.Embed(title=str(target), color=0x5865F2)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="ID",      value=str(target.id))
    e.add_field(name="Joined",  value=f"<t:{int(target.joined_at.timestamp())}:R>")
    e.add_field(name="Warns",   value=str(warns))
    e.add_field(name=f"Roles ({len(target.roles)-1})",
                value=" ".join(roles) if roles else "None", inline=False)
    await ctx.send(embed=e)

@bot.command(name="serverinfo")
async def pfx_serverinfo(ctx: commands.Context):
    g = ctx.guild
    e = discord.Embed(title=g.name, color=0x5865F2)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="Members",  value=str(g.member_count))
    e.add_field(name="Channels", value=str(len(g.channels)))
    e.add_field(name="Roles",    value=str(len(g.roles)))
    await ctx.send(embed=e)

@bot.command(name="ping")
async def pfx_ping(ctx: commands.Context):
    await ctx.send(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@bot.command(name="help")
async def pfx_help(ctx: commands.Context):
    prefix = prefix_cache.get(ctx.guild.id, "?") if ctx.guild else "?"
    e = discord.Embed(title="🐦 that one bird – Commands",
                      description=f"Prefix: `{prefix}`", color=0x5865F2)
    e.add_field(name="Core", value=(
        f"`{prefix}warn/unwarn/clearwarns/warns/history/modlogs`\n"
        f"`{prefix}mute/unmute/kick/ban/unban/tempban/jail/unjail`\n"
        f"`{prefix}purge/nick/slowmode/lookup`\n"
        f"`{prefix}meme/roast/8ball/poll/remind/snipe/afk/deadchat`\n"
        f"`{prefix}topic/coinflip/dice/calc/urban/firstmessage`\n"
        f"`{prefix}hug/slap/bite/punch/say/announce/pingrole`\n"
        f"`{prefix}avatar/servericon/quote/mybookmarks`\n"
        f"`{prefix}userinfo/serverinfo/ping/character`"
    ), inline=False)
    await ctx.send(embed=e)

# – SECTION 15: BLOOD TRIALS ———————————————––

def _supa_headers():
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

@bot.tree.command(name="character", description="Look up a Blood Trials character")
async def cmd_character(i: discord.Interaction, name: str):
    await i.response.defer()
    if not (SUPABASE_URL and SUPABASE_KEY):
        await i.followup.send("❌ Supabase not configured.", ephemeral=True); return
    try:
        url = f"{SUPABASE_URL}/rest/v1/characters?name=ilike.{name.replace(' ','%20')}&select=name,role,description&limit=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                results = await r.json() if r.status == 200 else []
        if not results:
            await i.followup.send(f"❌ No character named **{name}** found."); return
        char = results[0]
        e = discord.Embed(title=f"🧬 {char['name']}",
                          description=char.get('description','*No description.*'),
                          color=0x8B0000)
        if char.get('role'):
            e.add_field(name="Role", value=char['role'])
        e.add_field(name="📚 Read", value=f"[Blood Trials]({BOOK_LINK})")
        e.set_footer(text="Blood Trials")
        await i.followup.send(embed=e)
    except Exception as ex:
        print(f"Character lookup: {ex}")
        await i.followup.send("❌ Something went wrong.")

@bot.command(name="character")
async def pfx_character(ctx: commands.Context, *, name: str):
    if not (SUPABASE_URL and SUPABASE_KEY):
        await ctx.reply("❌ Supabase not configured."); return
    try:
        url = f"{SUPABASE_URL}/rest/v1/characters?name=ilike.{name.replace(' ','%20')}&select=name,role,description&limit=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                results = await r.json() if r.status == 200 else []
        if not results:
            await ctx.reply(f"❌ No character named **{name}** found."); return
        char = results[0]
        e = discord.Embed(title=f"🧬 {char['name']}",
                          description=char.get('description','*No description.*'),
                          color=0x8B0000)
        if char.get('role'):
            e.add_field(name="Role", value=char['role'])
        e.add_field(name="📚 Read", value=f"[Blood Trials]({BOOK_LINK})")
        await ctx.send(embed=e)
    except Exception as ex:
        print(f"Character lookup: {ex}")
        await ctx.reply("❌ Something went wrong.")

# Manual announce commands (same as before, omitted for brevity but included in full file)

# – SECTION 16: BACKGROUND TASKS ———————————————

@tasks.loop(minutes=5)
async def tempban_task():
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id,guild_id FROM tempbans WHERE unban_at <= ?", (now,)
        ) as cur:
            rows = await cur.fetchall()
        if rows:
            await db.execute("DELETE FROM tempbans WHERE unban_at <= ?", (now,))
            await db.commit()
    for uid, gid in rows:
        try:
            guild = bot.get_guild(gid) or await bot.fetch_guild(gid)
            await guild.unban(discord.Object(id=uid), reason="Tempban expired")
            user = await bot.fetch_user(uid)
            await try_dm(user, embed=discord.Embed(
                title="🔓 You have been unbanned",
                description=f"Your temporary ban in **{guild.name}** has expired.",
                color=0x57F287))
            e = discord.Embed(title="🔓 Tempban Expired",
                              description=f"<@{uid}> auto-unbanned.",
                              color=0x57F287, timestamp=datetime.now(timezone.utc))
            await send_log(bot, gid, 'log_mod_id', e)
        except Exception as ex:
            print(f"Tempban unban: {ex}")

@tasks.loop(hours=1)
async def cleanup_warns_task():
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "DELETE FROM warns WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),))
        await db.commit()

@tasks.loop(minutes=1)
async def unmute_notify_task():
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id,guild_id FROM mute_tracking WHERE unmute_at <= ?", (now,)
        ) as cur:
            rows = await cur.fetchall()
        if rows:
            await db.execute("DELETE FROM mute_tracking WHERE unmute_at <= ?", (now,))
            await db.commit()
    for uid, gid in rows:
        try:
            user  = await bot.fetch_user(uid)
            guild = bot.get_guild(gid)
            await try_dm(user, embed=discord.Embed(
                title="🔊 Your mute has expired",
                description=f"You can speak again in **{guild.name if guild else gid}**.",
                color=0x57F287))
        except Exception:
            pass

@tasks.loop(minutes=1)
async def reminder_task():
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT id,user_id,channel_id,message FROM reminders WHERE remind_at <= ?",
            (now,)
        ) as cur:
            due = await cur.fetchall()
        if due:
            await db.execute("DELETE FROM reminders WHERE remind_at <= ?", (now,))
            await db.commit()
    for _, uid, cid, msg in due:
        ch = bot.get_channel(int(cid) if cid else None)
        if not ch:
            try:
                ch = await bot.fetch_channel(int(cid))
            except Exception:
                continue
        if ch:
            e = discord.Embed(title="⏰ Reminder!", description=msg, color=0x57F287,
                              timestamp=datetime.now(timezone.utc))
            await ch.send(f"<@{uid}>", embed=e)

async def _announce_chapter(guild_id: int, ch_id: int, role_id, chapter: dict):
    """Shared logic for both the poller and manual /announcechapter."""
    num     = chapter.get("chapter_number")
    title   = chapter.get("title", "Untitled")
    excerpt = chapter.get("excerpt", "")
    pub_at  = chapter.get("created_at", "")
    ch = bot.get_channel(int(ch_id) if ch_id else None)
    if not ch:
        try:
            ch = await bot.fetch_channel(int(ch_id))
        except discord.Forbidden:
            print(f"Chapter announce: no access to channel {ch_id} -- check bot permissions")
            return False
        except Exception as ex:
            print(f"Chapter announce: channel {ch_id} not found ({ex})")
            return False
    me = ch.guild.me if hasattr(ch, "guild") else None
    if me:
        perms = ch.permissions_for(me)
        if not perms.send_messages or not perms.embed_links:
            print(f"Chapter announce: missing Send Messages or Embed Links in #{ch.name} "
                  f"-- grant these to the bot role in that channel permission overrides")
            return False
    e = discord.Embed(
        title=f"📖 Chapter {num}: {title}",
        description=excerpt[:1024] if excerpt else "*No excerpt.*",
        color=0xB22222, url=BOOK_LINK,
        timestamp=datetime.now(timezone.utc))
    e.set_author(name="Blood Trials")
    e.add_field(name="📚 Read now", value=f"[Click here]({BOOK_LINK})")
    if pub_at:
        try:
            dt = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
            e.set_footer(text=f"Published {dt.strftime('%B %d, %Y')}")
        except Exception:
            pass
    content = ((f"<@&{role_id}> " if role_id else "") + "**New Blood Trials chapter!** 🩸")
    try:
        await ch.send(content=content, embed=e, allowed_mentions=discord.AllowedMentions.all())
        return True
    except discord.Forbidden:
        print(f"Chapter announce: missing permissions in channel {ch_id}")
        return False


async def _announce_character(guild_id: int, ch_id: int, char: dict):
    """Shared logic for both the poller and manual /announcecharacter."""
    char_name = char.get("name", "Unknown")
    char_role = char.get("role", "")
    char_desc = char.get("description", "")
    ch = bot.get_channel(int(ch_id) if ch_id else None)
    if not ch:
        try:
            ch = await bot.fetch_channel(int(ch_id))
        except discord.Forbidden:
            print(f"Character announce: no access to channel {ch_id} -- check bot permissions")
            return False
        except Exception as ex:
            print(f"Character announce: channel {ch_id} not found ({ex})")
            return False
    me = ch.guild.me if hasattr(ch, "guild") else None
    if me:
        perms = ch.permissions_for(me)
        if not perms.send_messages or not perms.embed_links:
            print(f"Character announce: missing Send Messages or Embed Links in #{ch.name} "
                  f"-- grant these to the bot role in that channel permission overrides")
            return False
    e = discord.Embed(
        title=f"🧬 New Character: {char_name}",
        description=char_desc[:1024] if char_desc else "*No description yet.*",
        color=0x8B0000, timestamp=datetime.now(timezone.utc))
    e.set_author(name="Blood Trials -- Characters")
    if char_role:
        e.add_field(name="Role", value=char_role)
    e.add_field(name="📚 Read the story", value=f"[Blood Trials]({BOOK_LINK})")
    try:
        await ch.send(content="🩸 **New Blood Trials character!**", embed=e)
        return True
    except discord.Forbidden:
        print(f"Character announce: missing permissions in channel {ch_id}")
        return False


@tasks.loop(minutes=2)
async def poll_chapters_task():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        # No published filter — fetch all chapters ordered by number
        url = (f"{SUPABASE_URL}/rest/v1/chapters"
               f"?select=chapter_number,title,excerpt,created_at"
               f"&order=chapter_number.asc")
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                if r.status != 200:
                    print(f"Chapter poll: Supabase returned {r.status}")
                    return
                chapters = await r.json()
        print(f"Chapter poll: found {len(chapters)} chapters in Supabase")
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT guild_id,chapter_channel_id,chapter_role_id"
                " FROM guild_settings WHERE chapter_channel_id IS NOT NULL"
            ) as cur:
                guilds = await cur.fetchall()
        print(f"Chapter poll: {len(guilds)} guild(s) have chapter channel set")
        for chapter in chapters:
            num = chapter.get("chapter_number")
            for guild_id, ch_id, role_id in guilds:
                async with aiosqlite.connect(DB) as db:
                    async with db.execute(
                        "SELECT 1 FROM announced_chapters WHERE guild_id=? AND chapter_number=?",
                        (guild_id, num)
                    ) as cur:
                        if await cur.fetchone():
                            continue
                    await db.execute(
                        "INSERT OR IGNORE INTO announced_chapters (guild_id,chapter_number)"
                        " VALUES (?,?)", (guild_id, num))
                    await db.commit()
                print(f"Chapter poll: announcing chapter {num} to guild {guild_id}")
                await _announce_chapter(guild_id, ch_id, role_id, chapter)
    except Exception as ex:
        print(f"Chapter poll error: {ex}")

@tasks.loop(minutes=2)
async def poll_characters_task():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        url = f"{SUPABASE_URL}/rest/v1/characters?select=name,role,description&order=name.asc"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                if r.status != 200:
                    print(f"Character poll: Supabase returned {r.status}")
                    return
                characters = await r.json()
        print(f"Character poll: found {len(characters)} characters in Supabase")
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT guild_id,character_channel_id"
                " FROM guild_settings WHERE character_channel_id IS NOT NULL"
            ) as cur:
                guilds = await cur.fetchall()
        print(f"Character poll: {len(guilds)} guild(s) have character channel set")
        for char in characters:
            name = char.get("name", "Unknown")
            for guild_id, ch_id in guilds:
                async with aiosqlite.connect(DB) as db:
                    async with db.execute(
                        "SELECT 1 FROM announced_characters WHERE guild_id=? AND char_name=?",
                        (guild_id, name)
                    ) as cur:
                        if await cur.fetchone():
                            continue
                    await db.execute(
                        "INSERT OR IGNORE INTO announced_characters (guild_id,char_name)"
                        " VALUES (?,?)", (guild_id, name))
                    await db.commit()
                print(f"Character poll: announcing {name} to guild {guild_id}")
                await _announce_character(guild_id, ch_id, char)
    except Exception as ex:
        print(f"Character poll error: {ex}")


# -- Manual announce commands ------------------------------------------------

@bot.tree.command(name="announcechapter",
                  description="Manually announce a Blood Trials chapter")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(chapter_number="Chapter number to announce",
                        force="Re-announce even if already posted before")
async def cmd_announcechapter(i: discord.Interaction, chapter_number: int,
                               force: bool = False):
    await i.response.defer(ephemeral=True)
    if not (SUPABASE_URL and SUPABASE_KEY):
        await i.followup.send("Supabase not configured.", ephemeral=True); return
    ch_id = await get_setting_int(i.guild.id, 'chapter_channel_id')
    if not ch_id:
        await i.followup.send("No chapter channel set. Use /setchapterchannel first.",
                               ephemeral=True); return
    try:
        url = (f"{SUPABASE_URL}/rest/v1/chapters"
               f"?chapter_number=eq.{chapter_number}"
               f"&select=chapter_number,title,excerpt,created_at&limit=1")
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                results = await r.json() if r.status == 200 else []
    except Exception as ex:
        await i.followup.send(f"Couldn't reach Supabase: {ex}", ephemeral=True); return
    if not results:
        await i.followup.send(f"Chapter {chapter_number} not found in Supabase.",
                               ephemeral=True); return
    chapter = results[0]
    num = chapter.get("chapter_number")
    if not force:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT 1 FROM announced_chapters WHERE guild_id=? AND chapter_number=?",
                (i.guild.id, num)
            ) as cur:
                if await cur.fetchone():
                    await i.followup.send(
                        f"Chapter {num} was already announced. Pass force=True to re-announce.",
                        ephemeral=True); return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO announced_chapters (guild_id,chapter_number) VALUES (?,?)",
            (i.guild.id, num))
        await db.commit()
    role_id = await get_setting_int(i.guild.id, 'chapter_role_id')
    ok = await _announce_chapter(i.guild.id, ch_id, role_id, chapter)
    if ok:
        await i.followup.send(f"Chapter {num} announced.", ephemeral=True)
    else:
        await i.followup.send("Failed -- check I have permission to send in that channel.",
                               ephemeral=True)


@bot.tree.command(name="announcecharacter",
                  description="Manually announce a Blood Trials character")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(name="Character name (case-insensitive)",
                        force="Re-announce even if already posted before")
async def cmd_announcecharacter(i: discord.Interaction, name: str, force: bool = False):
    await i.response.defer(ephemeral=True)
    if not (SUPABASE_URL and SUPABASE_KEY):
        await i.followup.send("Supabase not configured.", ephemeral=True); return
    ch_id = await get_setting_int(i.guild.id, 'character_channel_id')
    if not ch_id:
        await i.followup.send("No character channel set. Use /setcharacterchannel first.",
                               ephemeral=True); return
    try:
        url = (f"{SUPABASE_URL}/rest/v1/characters"
               f"?name=ilike.{name.replace(' ', '%20')}"
               f"&select=name,role,description&limit=1")
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                results = await r.json() if r.status == 200 else []
    except Exception as ex:
        await i.followup.send(f"Couldn't reach Supabase: {ex}", ephemeral=True); return
    if not results:
        await i.followup.send(f"No character named '{name}' found.", ephemeral=True); return
    char      = results[0]
    char_name = char.get("name", name)
    if not force:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT 1 FROM announced_characters WHERE guild_id=? AND char_name=?",
                (i.guild.id, char_name)
            ) as cur:
                if await cur.fetchone():
                    await i.followup.send(
                        f"{char_name} was already announced. Pass force=True to re-announce.",
                        ephemeral=True); return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO announced_characters (guild_id,char_name) VALUES (?,?)",
            (i.guild.id, char_name))
        await db.commit()
    ok = await _announce_character(i.guild.id, ch_id, char)
    if ok:
        await i.followup.send(f"{char_name} announced.", ephemeral=True)
    else:
        await i.followup.send("Failed -- check I have permission to send in that channel.",
                               ephemeral=True)


@bot.command(name="announcechapter")
@commands.has_permissions(manage_guild=True)
async def pfx_announcechapter(ctx: commands.Context, chapter_number: int, force: str = ""):
    do_force = force.lower() in ("force", "true", "yes")
    if not (SUPABASE_URL and SUPABASE_KEY):
        await ctx.reply("Supabase not configured."); return
    ch_id = await get_setting_int(ctx.guild.id, 'chapter_channel_id')
    if not ch_id:
        await ctx.reply("No chapter channel set. Use /setchapterchannel first."); return
    try:
        url = (f"{SUPABASE_URL}/rest/v1/chapters"
               f"?chapter_number=eq.{chapter_number}"
               f"&select=chapter_number,title,excerpt,created_at&limit=1")
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                results = await r.json() if r.status == 200 else []
    except Exception:
        await ctx.reply("Couldn't reach Supabase."); return
    if not results:
        await ctx.reply(f"Chapter {chapter_number} not found in Supabase."); return
    chapter = results[0]
    num = chapter.get("chapter_number")
    if not do_force:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT 1 FROM announced_chapters WHERE guild_id=? AND chapter_number=?",
                (ctx.guild.id, num)
            ) as cur:
                if await cur.fetchone():
                    await ctx.reply(
                        f"Chapter {num} already announced. "
                        f"Run `?announcechapter {num} force` to override."); return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO announced_chapters (guild_id,chapter_number) VALUES (?,?)",
            (ctx.guild.id, num))
        await db.commit()
    role_id = await get_setting_int(ctx.guild.id, 'chapter_role_id')
    ok = await _announce_chapter(ctx.guild.id, ch_id, role_id, chapter)
    await ctx.reply(f"Chapter {num} announced." if ok
                    else "Failed -- check channel permissions.")


@bot.command(name="announcecharacter")
@commands.has_permissions(manage_guild=True)
async def pfx_announcecharacter(ctx: commands.Context, *, args: str):
    do_force = args.lower().endswith(" force")
    name     = args[:-6].strip() if do_force else args.strip()
    if not (SUPABASE_URL and SUPABASE_KEY):
        await ctx.reply("Supabase not configured."); return
    ch_id = await get_setting_int(ctx.guild.id, 'character_channel_id')
    if not ch_id:
        await ctx.reply("No character channel set. Use /setcharacterchannel first."); return
    try:
        url = (f"{SUPABASE_URL}/rest/v1/characters"
               f"?name=ilike.{name.replace(' ', '%20')}"
               f"&select=name,role,description&limit=1")
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_supa_headers()) as r:
                results = await r.json() if r.status == 200 else []
    except Exception:
        await ctx.reply("Couldn't reach Supabase."); return
    if not results:
        await ctx.reply(f"No character named '{name}' found."); return
    char      = results[0]
    char_name = char.get("name", name)
    if not do_force:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT 1 FROM announced_characters WHERE guild_id=? AND char_name=?",
                (ctx.guild.id, char_name)
            ) as cur:
                if await cur.fetchone():
                    await ctx.reply(
                        f"{char_name} already announced. "
                        f"Run `?announcecharacter {name} force` to override."); return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO announced_characters (guild_id,char_name) VALUES (?,?)",
            (ctx.guild.id, char_name))
        await db.commit()
    ok = await _announce_character(ctx.guild.id, ch_id, char)
    await ctx.reply(f"{char_name} announced." if ok
                    else "Failed -- check channel permissions.")

# – SECTION 17: EVENT LISTENERS –––––––––––––––––––––––

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if not message.guild:
        return

    # AFK clear
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT reason FROM afk WHERE user_id=? AND guild_id=?",
            (message.author.id, message.guild.id)
        ) as cur:
            was_afk = await cur.fetchone()
        if was_afk:
            await db.execute(
                "DELETE FROM afk WHERE user_id=? AND guild_id=?",
                (message.author.id, message.guild.id))
            await db.commit()
            try:
                await message.channel.send(
                    f"👋 Welcome back {message.author.mention}! AFK removed.",
                    delete_after=8)
            except discord.Forbidden:
                pass

    # AFK mention notify
    for mentioned in message.mentions:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT reason,timestamp FROM afk WHERE user_id=? AND guild_id=?",
                (mentioned.id, message.guild.id)
            ) as cur:
                afk_row = await cur.fetchone()
        if afk_row:
            reason, ts = afk_row
            try:
                dt  = datetime.fromisoformat(ts)
                rel = f"<t:{int(dt.timestamp())}:R>"
            except Exception:
                rel = "a while ago"
            try:
                await message.channel.send(
                    f"💤 **{mentioned.display_name}** is AFK: {reason or 'no reason'} (since {rel})",
                    delete_after=15)
            except discord.Forbidden:
                pass

    if await _run_automod(message):
        return

    await _run_triggers(message)

    await _run_custom_command(message)

    if (bot.user in message.mentions or
            (hasattr(message.channel, 'name') and
             message.channel.name.lower() == "ai-chat")):
        await _groq_respond(message)

async def _run_custom_command(message: discord.Message):
    prefix = prefix_cache.get(message.guild.id)
    if prefix is None:
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                "SELECT prefix FROM guild_settings WHERE guild_id=?",
                (message.guild.id,)
            ) as cur:
                row = await cur.fetchone()
                prefix = row[0] if (row and row[0]) else "?"
        prefix_cache[message.guild.id] = prefix
    if not message.content.startswith(prefix):
        return
    parts   = message.content[len(prefix):].split()
    if not parts:
        return
    invoked = parts[0].lower()
    if bot.get_command(invoked):
        return
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT action_type,value FROM custom_commands WHERE guild_id=? AND name=?",
            (message.guild.id, invoked)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return
    action_type, value = row
    if action_type == 'message':
        await message.channel.send(value)
    elif action_type == 'ping':
        await message.channel.send(value, allowed_mentions=discord.AllowedMentions.all())
    elif action_type == 'alias':
        rest         = message.content[len(prefix) + len(invoked):].strip()
        new_content  = f"{prefix}{value} {rest}".strip()
        message.content = new_content
        ctx = await bot.get_context(message)
        if ctx.valid:
            await bot.invoke(ctx)

async def _groq_respond(message: discord.Message):
    recent = []
    try:
        async for m in message.channel.history(limit=6, before=message):
            if not m.author.bot:
                recent.append(f"{m.author.display_name}: {m.content[:100]}")
    except Exception:
        pass
    context_hint = " | ".join(reversed(recent)) if recent else None
    async with message.channel.typing():
        try:
            reply = await asyncio.to_thread(
                groq_chat, message.author.id, message.content, context_hint)
            if len(reply) <= 2000:
                await message.reply(reply, mention_author=False)
            else:
                chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
                await message.reply(chunks[0], mention_author=False)
                for chunk in chunks[1:]:
                    await message.channel.send(chunk)
        except Exception as ex:
            print(f"Groq error: {ex}")
            await message.reply("brain froze, try again", mention_author=False)

@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot:
        return
    cache = snipe_cache[message.channel.id]
    cache.insert(0, {
        "content": message.content or "*[no text]*",
        "author":  str(message.author),
        "avatar":  message.author.display_avatar.url,
        "time":    datetime.now(timezone.utc)
    })
    snipe_cache[message.channel.id] = cache[:3]
    if not message.guild:
        return
    e = discord.Embed(title="🗑️ Message Deleted", color=0xFF4444,
                      timestamp=datetime.now(timezone.utc))
    e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    e.add_field(name="Channel", value=message.channel.mention)
    e.add_field(name="Content", value=(message.content or "*empty*")[:1024], inline=False)
    await send_log(bot, message.guild.id, 'log_message_id', e)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild:
        return
    if before.content == after.content:
        return
    e = discord.Embed(title="✏️ Message Edited", color=0xFFAA00,
                      timestamp=datetime.now(timezone.utc))
    e.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    e.add_field(name="Channel", value=before.channel.mention)
    e.add_field(name="Before",  value=(before.content or "*empty*")[:512], inline=False)
    e.add_field(name="After",   value=(after.content  or "*empty*")[:512], inline=False)
    e.add_field(name="Jump",    value=f"[View]({after.jump_url})")
    await send_log(bot, before.guild.id, 'log_message_id', e)

@bot.event
async def on_member_join(member: discord.Member):
    gid = member.guild.id
    enabled = await get_setting(gid, 'antiraid_enabled')
    if enabled:
        threshold = safe_int(await get_setting(gid, 'antiraid_threshold') or 10)
        seconds   = safe_int(await get_setting(gid, 'antiraid_seconds')   or 10)
        action    = await get_setting(gid, 'antiraid_action')        or 'slowmode'
        now       = datetime.now(timezone.utc).timestamp()
        bot.join_tracker.setdefault(gid, [])
        bot.join_tracker[gid] = [t for t in bot.join_tracker[gid] if now - t < seconds]
        bot.join_tracker[gid].append(now)
        if len(bot.join_tracker[gid]) >= threshold:
            await _trigger_antiraid(member.guild, action)
    role_id = await get_setting_int(gid, 'autorole_id')
    if role_id:
        role = member.guild.get_role(int(role_id) if role_id else None)
        if role:
            try: await member.add_roles(role, reason="Autorole")
            except discord.Forbidden: pass
    wc_id = await get_setting_int(gid, 'welcome_channel_id')
    w_msg = await get_setting(gid, 'welcome_message')
    if wc_id and w_msg:
        ch = bot.get_channel(int(wc_id) if wc_id else None)
        if not ch:
            try:
                ch = await bot.fetch_channel(int(wc_id))
            except Exception:
                ch = None
        if ch:
            text = (w_msg
                    .replace("{user}",   member.mention)
                    .replace("{name}",   member.display_name)
                    .replace("{server}", member.guild.name)
                    .replace("{count}",  str(member.guild.member_count)))
            e = discord.Embed(description=text, color=0x57F287)
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Member #{member.guild.member_count}")
            try: await ch.send(embed=e)
            except discord.Forbidden: pass
    e = discord.Embed(title="📥 Member Joined", color=0x57F287,
                      timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="User",       value=f"{member} ({member.mention})")
    e.add_field(name="Account Age",value=f"<t:{int(member.created_at.timestamp())}:R>")
    e.add_field(name="Members",    value=str(member.guild.member_count))
    await send_log(bot, gid, 'log_member_id', e)

@bot.event
async def on_member_remove(member: discord.Member):
    e = discord.Embed(title="📤 Member Left", color=0xFF4444,
                      timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="User",    value=str(member))
    e.add_field(name="Members", value=str(member.guild.member_count))
    roles = [r.mention for r in member.roles[1:]]
    if roles:
        e.add_field(name="Roles", value=" ".join(roles[:10]), inline=False)
    await send_log(bot, member.guild.id, 'log_member_id', e)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    gid = before.guild.id
    if before.nick != after.nick:
        e = discord.Embed(title="📝 Nickname Changed", color=0x5865F2,
                          timestamp=datetime.now(timezone.utc))
        e.add_field(name="User",   value=after.mention)
        e.add_field(name="Before", value=before.nick or "*none*")
        e.add_field(name="After",  value=after.nick  or "*none*")
        await send_log(bot, gid, 'log_member_id', e)
    added   = set(after.roles)  - set(before.roles)
    removed = set(before.roles) - set(after.roles)
    if added or removed:
        e = discord.Embed(title="🔄 Roles Updated", color=0xFFAA00,
                          timestamp=datetime.now(timezone.utc))
        e.add_field(name="User", value=after.mention)
        if added:   e.add_field(name="Added",   value=" ".join(r.mention for r in added))
        if removed: e.add_field(name="Removed", value=" ".join(r.mention for r in removed))
        await send_log(bot, gid, 'log_member_id', e)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState,
                                after: discord.VoiceState):
    if before.channel == after.channel:
        return
    if before.channel is None:
        desc, color = f"📞 **{member}** joined **{after.channel.name}**", 0x57F287
    elif after.channel is None:
        desc, color = f"📴 **{member}** left **{before.channel.name}**", 0xFF4444
    else:
        desc, color = (f"🔀 **{member}** moved "
                       f"**{before.channel.name}** → **{after.channel.name}**"), 0xFFAA00
    e = discord.Embed(description=desc, color=color, timestamp=datetime.now(timezone.utc))
    await send_log(bot, member.guild.id, 'log_server_id', e)

@bot.event
async def on_guild_channel_create(channel):
    e = discord.Embed(title="✅ Channel Created", color=0x57F287,
                      timestamp=datetime.now(timezone.utc))
    e.add_field(name="Name", value=getattr(channel, 'mention', f"#{channel.name}"))
    e.add_field(name="Type", value=str(channel.type))
    await send_log(bot, channel.guild.id, 'log_server_id', e)

@bot.event
async def on_guild_channel_delete(channel):
    e = discord.Embed(title="🗑️ Channel Deleted", color=0xFF4444,
                      timestamp=datetime.now(timezone.utc))
    e.add_field(name="Name", value=f"#{channel.name}")
    e.add_field(name="Type", value=str(channel.type))
    await send_log(bot, channel.guild.id, 'log_server_id', e)

@bot.event
async def on_invite_create(invite: discord.Invite):
    e = discord.Embed(title="🔗 Invite Created", color=0x5865F2,
                      timestamp=datetime.now(timezone.utc))
    e.add_field(name="By",      value=invite.inviter.mention if invite.inviter else "Unknown")
    e.add_field(name="Channel", value=invite.channel.mention if invite.channel else "Unknown")
    e.add_field(name="Code",    value=invite.code)
    e.add_field(name="Expires", value=(
        f"<t:{int(invite.expires_at.timestamp())}:R>" if invite.expires_at else "Never"))
    await send_log(bot, invite.guild.id, 'log_server_id', e)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    await asyncio.sleep(1)
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                if entry.user.id == bot.user.id:
                    return
                e = discord.Embed(title="🔨 Manual Ban", color=0xCC0000,
                                  timestamp=datetime.now(timezone.utc))
                e.add_field(name="User",   value=f"{user} `{user.id}`")
                e.add_field(name="By",     value=entry.user.mention)
                e.add_field(name="Reason", value=entry.reason or "None", inline=False)
                await send_log(bot, guild.id, 'log_mod_id', e)
                break
    except Exception:
        pass

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    e = discord.Embed(title="🔓 Member Unbanned", color=0x57F287,
                      timestamp=datetime.now(timezone.utc))
    e.add_field(name="User", value=f"{user} `{user.id}`")
    await send_log(bot, guild.id, 'log_mod_id', e)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if not payload.guild_id:
        return
    gid = payload.guild_id

    if str(payload.emoji) == "🔖":
        channel = bot.get_channel(int(payload.channel_id))
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
            user    = await bot.fetch_user(payload.user_id)
            if user.bot:
                return
            async with aiosqlite.connect(DB) as db:
                async with db.execute(
                    "SELECT 1 FROM bookmarks WHERE user_id=? AND message_id=?",
                    (user.id, message.id)
                ) as cur:
                    if await cur.fetchone():
                        return
                await db.execute(
                    "INSERT INTO bookmarks"
                    " (user_id,guild_id,message_id,channel_id,jump_url,content,author_name)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (user.id, gid, message.id, channel.id, message.jump_url,
                     message.content[:500], str(message.author.display_name)))
                await db.commit()
            dm = discord.Embed(title="🔖 Bookmarked", color=0xFFD700)
            dm.add_field(name="From",    value=str(message.author.display_name))
            dm.add_field(name="Content", value=(message.content or "*no text*")[:300], inline=False)
            dm.add_field(name="Jump",    value=f"[Go to message]({message.jump_url})")
            dm.set_footer(text="Use /mybookmarks or ?mybookmarks to view")
            await user.send(embed=dm)
        except (discord.Forbidden, discord.NotFound):
            pass
        except Exception as ex:
            print(f"Bookmark: {ex}")
        return

    emoji     = await get_setting(gid, 'starboard_emoji') or '⭐'
    if str(payload.emoji) != emoji:
        return
    threshold = safe_int(await get_setting(gid, 'starboard_threshold') or 3)
    sb_ch_id  = await get_setting_int(gid, 'starboard_channel_id')
    if not sb_ch_id:
        return
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT 1 FROM starboard_posted WHERE guild_id=? AND message_id=?",
            (gid, payload.message_id)
        ) as cur:
            if await cur.fetchone():
                return
    channel = bot.get_channel(int(payload.channel_id))
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return
    reaction_count = 0
    for r in message.reactions:
        if str(r.emoji) == emoji:
            reaction_count = r.count
            break
    if reaction_count < threshold:
        return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO starboard_posted (guild_id,message_id) VALUES (?,?)",
            (gid, payload.message_id))
        await db.commit()
    sb_channel = bot.get_channel(int(sb_ch_id) if sb_ch_id else None)
    if not sb_channel:
        try:
            sb_channel = await bot.fetch_channel(int(sb_ch_id))
        except Exception:
            return
    e = discord.Embed(color=0xFFD700, timestamp=message.created_at)
    e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    if message.content:
        e.description = message.content[:2048]
    if message.attachments:
        e.set_image(url=message.attachments[0].url)
    e.add_field(name="Source", value=f"[Jump]({message.jump_url})")
    embeds = []
    if message.reference:
        try:
            parent = await channel.fetch_message(message.reference.message_id)
            pe = discord.Embed(color=0xB8860B,
                               description=f"**Replying to {parent.author.mention}:**\n{parent.content[:512]}")
            pe.set_author(name=str(parent.author), icon_url=parent.author.display_avatar.url)
            embeds.append(pe)
        except Exception:
            pass
    embeds.append(e)
    try:
        await sb_channel.send(
            content=f"{emoji} **{reaction_count}** | {message.author.mention}",
            embeds=embeds,
            allowed_mentions=discord.AllowedMentions(users=True))
    except discord.Forbidden:
        pass

async def _trigger_antiraid(guild: discord.Guild, action: str):
    e = discord.Embed(title="🚨 Anti-Raid Triggered!", color=0xFF0000,
                      timestamp=datetime.now(timezone.utc))
    e.add_field(name="Action", value=action)
    await send_log(bot, guild.id, 'log_server_id', e)
    if action == 'slowmode':
        for ch in guild.text_channels:
            try: await ch.edit(slowmode_delay=60)
            except Exception: pass
    elif action == 'lockdown':
        for ch in guild.text_channels:
            try:
                ow = ch.overwrites_for(guild.default_role)
                ow.send_messages = False
                await ch.set_permissions(guild.default_role, overwrite=ow)
            except Exception: pass
    elif action == 'kick_new':
        now = datetime.now(timezone.utc)
        for member in guild.members:
            if member.joined_at and (now - member.joined_at).total_seconds() < 30:
                try: await member.kick(reason="Anti-raid")
                except Exception: pass

# – SECTION 18: GLOBAL ERROR HANDLER —————————————–

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("Bros you no get permission for this one 😂 who dash you power?")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.reply("I no get the power o, give me admin make I work!")
    elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
        await ctx.reply("Member not found, who tf 🙏🏽😭")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"Uhh: `{error.param.name}` missing my guy")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply(f"Bad argument: {error} – you sure say na that one?")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.reply("Server only, no dey dm me like that.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.reply("You can't use this lil bro, try another thing.")
    else:
        print(f"Error [{ctx.command}]: {type(error).__name__}: {error}")
        await ctx.reply("Something scatter o... try again later.")

# – SECTION 19: ENTRY POINT –––––––––––––––––––––––––

if __name__ == "__main__":
    bot.run(TOKEN)
