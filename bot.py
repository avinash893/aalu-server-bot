"""
Tillu Minecraft Discord Bot
24/7 Cloud Edition for Render with Gemini AI, Natural Chat & Role Cooldowns
Author: Antigravity Pair Programmer
"""

import os
import sys
import time
import socket
import struct
import json
import asyncio
import re
import logging
import aiohttp
from aiohttp import web
import requests
import discord
from discord.ext import commands
from discord import app_commands
from collections import deque

# Force UTF-8 output encoding across environments to avoid UnicodeEncodeError crashes
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ── CONFIGURATION ────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SERVER_HOST = os.environ.get("SERVER_HOST", "legacy-7.hexacraft.fun")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "25587"))

PRIMARY_GUILD_ID = int(os.environ.get("PRIMARY_GUILD_ID", "1456298447979286541"))
CS2_GUILD_ID = int(os.environ.get("CS2_GUILD_ID", "1530719250237362297"))

CONSOLE_CHANNEL_ID = int(os.environ.get("CONSOLE_CHANNEL_ID", "1486114457674453083"))
WHITELIST_CHANNEL_ID = int(os.environ.get("WHITELIST_CHANNEL_ID", "1511614214962151585"))
CHAT_CHANNEL_ID = int(os.environ.get("CHAT_CHANNEL_ID", "1456299736326733998"))

PTERO_URL = os.environ.get("PTERO_URL", "https://panel.hexacraft.fun")
PTERO_KEY = os.environ.get("PTERO_KEY", "")
PTERO_SERVER = os.environ.get("PTERO_SERVER", "14c2ebb6")
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://aalu-server-bot.onrender.com")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
raw_keys = os.environ.get("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
if not GEMINI_API_KEYS and GEMINI_API_KEY:
    GEMINI_API_KEYS = [GEMINI_API_KEY]

GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash"
]

# ── USER CONTEXT WINDOW (Rolling 10 Chats per User) ──────────────────────────
MAX_USER_HISTORY = 10
user_context_windows: dict[int, deque] = {}

def get_user_context(user_id: int) -> list[dict]:
    if not user_id:
        return []
    if user_id not in user_context_windows:
        user_context_windows[user_id] = deque(maxlen=MAX_USER_HISTORY)
    return list(user_context_windows[user_id])

def record_user_context(user_id: int, role: str, text: str):
    if not user_id or not text:
        return
    if user_id not in user_context_windows:
        user_context_windows[user_id] = deque(maxlen=MAX_USER_HISTORY)
    user_context_windows[user_id].append({"role": role, "text": text.strip()})

COOLDOWN_SECONDS = 20
user_cooldowns = {}

# ── ACTIVE CONVERSATION SESSION (Awake state) ───────────────────────────────
CONVERSATION_TIMEOUT_SECONDS = 120
ACTIVE_USER_CONVERSATIONS: dict[tuple[int, int], float] = {}

WHITELIST_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")

# ── COOLDOWN & PERMISSIONS ───────────────────────────────────────────────────
def is_privileged_user(user, guild=None) -> bool:
    """Check if user is Server Owner, Admin, or Moderator (0-second cooldown)."""
    if not user:
        return False
    user_id = user.id

    # Guild owner check
    if guild and getattr(guild, 'owner_id', None) == user_id:
        return True

    # Member role & permission checks
    if isinstance(user, discord.Member):
        perms = user.guild_permissions
        if perms.administrator or perms.manage_guild or perms.manage_messages or perms.moderate_members:
            return True
        for role in user.roles:
            rname = role.name.lower()
            if any(w in rname for w in ["admin", "owner", "mod", "moderator", "staff", "builder", "host"]):
                return True

    return False

def check_cooldown(user, guild=None) -> tuple[bool, int]:
    """Returns (is_allowed, remaining_seconds). Admins/Mods have 0 cooldown."""
    if is_privileged_user(user, guild):
        return True, 0
    now = time.time()
    last = user_cooldowns.get(user.id, 0)
    elapsed = now - last
    if elapsed < COOLDOWN_SECONDS:
        return False, int(COOLDOWN_SECONDS - elapsed)
    user_cooldowns[user.id] = now
    return True, 0

# ── LOCAL PERSISTENCE ────────────────────────────────────────────────────────
def load_whitelist_registry() -> dict:
    if os.path.exists(WHITELIST_REGISTRY_PATH):
        try:
            with open(WHITELIST_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_whitelist_registry(data: dict):
    try:
        with open(WHITELIST_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save whitelist registry: {e}")

# ── MINECRAFT SLP PING ───────────────────────────────────────────────────────
def ping_minecraft_server(timeout=2.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((SERVER_HOST, SERVER_PORT))

        def send_varint(val):
            res = bytearray()
            while True:
                b = val & 0x7F
                val >>= 7
                if val != 0:
                    b |= 0x80
                res.append(b)
                if val == 0:
                    break
            return bytes(res)

        def read_varint(sock):
            val = 0
            for i in range(5):
                b = sock.recv(1)
                if not b:
                    raise EOFError("Closed")
                byte = b[0]
                val |= (byte & 0x7F) << (7 * i)
                if not (byte & 0x80):
                    break
            return val

        host_b = SERVER_HOST.encode('utf-8')
        packet = b'\x00' + send_varint(767) + send_varint(len(host_b)) + host_b + struct.pack('>H', SERVER_PORT) + send_varint(1)
        s.send(send_varint(len(packet)) + packet)
        s.send(send_varint(1) + b'\x00')

        length = read_varint(s)
        packet_id = read_varint(s)
        str_len = read_varint(s)
        data = b''
        while len(data) < str_len:
            chunk = s.recv(min(4096, str_len - len(data)))
            if not chunk:
                break
            data += chunk
        s.close()

        res = json.loads(data.decode('utf-8'))
        online_players = res.get('players', {}).get('online', 0)
        max_players = res.get('players', {}).get('max', 50)
        version = res.get('version', {}).get('name', 'Paper 26.3')
        return True, f"Online ({online_players}/{max_players})", online_players, max_players, version
    except Exception:
        return False, "Offline", 0, 0, None

# ── PTERODACTYL API HELPER ───────────────────────────────────────────────────
def ptero_api_call(method: str, endpoint: str, json_data=None):
    url = f"{PTERO_URL}/api/client/servers/{PTERO_SERVER}{endpoint}"
    headers = {
        "Authorization": f"Bearer {PTERO_KEY}",
        "Accept": "Application/vnd.pterodactyl.v1+json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.request(method, url, headers=headers, json=json_data, timeout=8)
        if resp.status_code in [200, 204]:
            return True, resp.json() if resp.text else {}
        return False, resp.text
    except Exception as e:
        return False, str(e)

def send_pterodactyl_start():
    return ptero_api_call("POST", "/power", {"signal": "start"})

async def execute_server_command(command: str) -> tuple[bool, str]:
    """Execute command directly via DiscordSRV console channel and fallback to panel."""
    cmd = command.strip().lstrip('/')
    dispatched_console = False

    # 1. Route directly into DiscordSRV console channel (#🎚️console)
    try:
        ch = bot.get_channel(CONSOLE_CHANNEL_ID)
        if ch:
            await ch.send(cmd)
            dispatched_console = True
            logging.info(f"[Console Dispatch] Sent `{cmd}` to #{ch.name} ({CONSOLE_CHANNEL_ID})")
    except Exception as e:
        logging.warning(f"[Console Dispatch] DiscordSRV channel send notice: {e}")

    # 2. Also attempt Pterodactyl panel API
    try:
        ptero_ok, ptero_resp = await asyncio.to_thread(ptero_api_call, "POST", "/command", {"command": cmd})
        if ptero_ok:
            return True, str(ptero_resp)
    except Exception as pe:
        logging.warning(f"[Console Dispatch] Pterodactyl panel notice: {pe}")

    if dispatched_console:
        return True, f"Dispatched to <#{CONSOLE_CHANNEL_ID}>"
    return False, "Failed to dispatch command"

def send_console_command(command: str) -> tuple[bool, str]:
    """Execute arbitrary command on Minecraft server console (sync wrapper)."""
    cmd = command.strip().lstrip('/')
    if bot and bot.loop and bot.loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(execute_server_command(cmd), bot.loop)
            return True, f"Dispatched to <#{CONSOLE_CHANNEL_ID}>"
        except Exception as e:
            logging.error(f"[send_console_command] Coroutine scheduling notice: {e}")
    p_ok, p_res = ptero_api_call("POST", "/command", {"command": cmd})
    return p_ok, str(p_res)

async def execute_whitelist_command(ign: str) -> bool:
    """Execute whitelist commands for a player IGN across console and panel."""
    clean_ign = ign.strip()
    await execute_server_command(f"whitelist add {clean_ign}")
    await execute_server_command(f"fwd:whitelist add {clean_ign}")
    await execute_server_command("whitelist reload")
    try:
        wch = bot.get_channel(WHITELIST_CHANNEL_ID)
        if wch:
            await wch.send(f"🎟️ Whitelist registered: `{clean_ign}`")
    except Exception:
        pass
    return True

def send_whitelist_command(ign: str) -> bool:
    clean_ign = ign.strip()
    if bot and bot.loop and bot.loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(execute_whitelist_command(clean_ign), bot.loop)
            return True
        except Exception:
            pass
    try:
        ptero_api_call("POST", "/command", {"command": f"whitelist add {clean_ign}"})
        ptero_api_call("POST", "/command", {"command": f"fwd:whitelist add {clean_ign}"})
        ptero_api_call("POST", "/command", {"command": "whitelist reload"})
        return True
    except Exception:
        return False

# ── GEMINI AI KNOWLEDGE & QUERY ──────────────────────────────────────────────
SYSTEM_KNOWLEDGE = f"""You are Tillu, the friendly, witty, and humorous AI assistant and co-host for AALU_CHIPAS and the AALU_CHIPAS Minecraft Server & Live Community.

MINECRAFT SERVER DETAILS:
- Server Address (Java): {SERVER_HOST}:{SERVER_PORT} (Supports 1.7 to 1.21.x cross-version)
- Server Address (Bedrock/PE/Mobile): IP: {SERVER_HOST} | Port: {SERVER_PORT}
- Features: OneBlock Void, Survival SMP with villager trading, Superheroes PvP Arena (kits: Spiderman, Ironman, Thor, Hulk, Flash, Superman).
- Host: Hexacraft 24/7 protected server.
- Whitelist: Whitelist is enabled! Anyone can whitelist themselves by asking you (e.g. "tillu whitelist me <IGN>") or using `/whitelist <ign>`.
- Power: Anyone can turn on the server anytime using `/start` or `!start`.

STREAM & CHANNEL DETAILS:
- Creator & Server Owner: AALU_CHIPAS (Avinash)
- Channels: YouTube (@AALU_CHIPAS) and Twitch (aaluchipas)
- Active Giveaway: Official Minecraft Java & Bedrock Edition key! Ends October 15, 2026. Viewers earn points by watching, then type !ticket to enter.

PERSONALITY & COMMUNICATION STYLE (CRITICAL):
1. CASUAL, WITTY & FRIENDLY (OLD TILLU IS BACK):
   - Talk like an energetic, fun Indian streamer buddy in casual Hinglish/English.
   - Use friendly expressions naturally (e.g. "bhai", "boss", "yaar", "arre waah", "kya haal hai").
   - NEVER be stiff, corporate, or overly formal! No "Kshama karein" or stiff robotic words. Be your real fun self!

2. SHORT & SNAPPY (LESS WORDS):
   - Keep replies short, crisp, and to the point (10-25 words / 1-2 punchy lines max).
   - Never write long essays or walls of text unless the user specifically asks for a full guide/tutorial.
   - For greetings and casual chats, answer naturally like a real friend in 1 short line. Do NOT spam server details or buttons unless asked!

3. ROLES & ACTIONS:
   - SERVER OWNER & ADMIN COMMANDS:
     Server Owner (Avinash) and Admins have FULL COMMAND over the Minecraft server console!
     When an Admin or Owner tells you to ban, unban, kick, remove from whitelist, or run any console command:
     OUTPUT FORMAT ON FIRST LINE:
     ADMIN_INTENT: <exact_minecraft_console_command>
     Followed by an energetic, short confirmation:
     "Done boss! Command console me bhej diya! 🔥"
     Examples:
     - "tillu remove Aalu_chipas from whitelist" -> ADMIN_INTENT: whitelist remove Aalu_chipas
     - "tillu ban Steve griefing" -> ADMIN_INTENT: ban Steve griefing
     - "tillu unban Steve" -> ADMIN_INTENT: pardon Steve
     - "tillu kick Steve" -> ADMIN_INTENT: kick Steve

   - REGULAR MEMBER WHITELIST:
     When a normal member asks to whitelist (e.g. "whitelist me <IGN>", "my IGN is <IGN>"):
     OUTPUT FORMAT ON FIRST LINE:
     WHITELIST_INTENT: <exact_clean_ign>
     Followed by a warm, short welcome (1 line):
     "Welcome bhai! IGN whitelist me add ho gaya hai, aaja khelte hain! 🚀"
     If a normal member asks to ban or kick someone, refuse playfully:
     "Arre bhai, Tillu kisi ko ban nahi karta, peace only! 😄"

4. CONTEXT AWARENESS:
   - Remember the ongoing conversation context (last 10 chats) to answer follow-up questions seamlessly.

5. LIVE SERVER TELEMETRY & STATUS:
   - When users ask about server status, player count, who is online, or if the server is up, ALWAYS use the provided [LIVE REAL-TIME MINECRAFT STATUS] block.
   - Answer accurately and enthusiastically in 1-2 punchy lines with the exact real-time player count and IP!
"""

def query_gemini(prompt: str, user_name: str, user_id: int = 0, is_admin: bool = False) -> str:
    keys = GEMINI_API_KEYS if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    if not keys:
        return "⚠️ Gemini API key is not configured."

    user_role_tag = "[USER ROLE: SERVER OWNER / ADMIN / MODERATOR - HAS CONSOLE POWERS]" if is_admin else "[USER ROLE: REGULAR MEMBER]"

    # Live server status query
    try:
        is_up, _, cur_players, max_players, ver_name = ping_minecraft_server(timeout=1.2)
    except Exception:
        is_up, cur_players, max_players, ver_name = False, 0, 50, "Paper 26.3"

    if is_up:
        live_telemetry = (
            f"[LIVE REAL-TIME MINECRAFT STATUS: ONLINE]\n"
            f"- Players Currently Online: {cur_players}/{max_players}\n"
            f"- Server Version: {ver_name}\n"
            f"- Server IP (Java & Bedrock): {SERVER_HOST}:{SERVER_PORT}\n"
            f"If the user asks who is online, how many players are playing, or if server is up, use this exact live data!"
        )
    else:
        live_telemetry = (
            f"[LIVE REAL-TIME MINECRAFT STATUS: OFFLINE]\n"
            f"- Server Address: {SERVER_HOST}:{SERVER_PORT}\n"
            f"If the user asks, tell them the server is currently sleeping/offline, and they can turn it on with /start or !start!"
        )

    context_str = ""
    history = get_user_context(user_id)
    if history:
        history_lines = []
        for h in history:
            speaker = user_name if h["role"] == "user" else "Tillu"
            history_lines.append(f"{speaker}: {h['text']}")
        context_str = "\n[CONVERSATION CONTEXT (LAST 10 CHATS WITH THIS USER)]:\n" + "\n".join(history_lines) + "\n"

    final_prompt = (
        f"{SYSTEM_KNOWLEDGE}\n\n"
        f"{live_telemetry}\n\n"
        f"{user_role_tag}\n"
        f"{context_str}\n"
        f"Current Query from {user_name}: {prompt}\n"
        f"Tillu's Response:"
    )

    last_err = "No Gemini response"
    for key in keys:
        for model_name in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            { "text": final_prompt }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 600
                }
            }
            try:
                r = requests.post(url, json=payload, timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text:
                        text = text.strip()
                        if user_id:
                            record_user_context(user_id, "user", prompt)
                            clean_text = re.sub(r'(ADMIN_INTENT|WHITELIST_INTENT):[^\n\r]+', '', text).strip()
                            record_user_context(user_id, "model", clean_text or text)
                        return text
                else:
                    last_err = f"{model_name} HTTP {r.status_code}: {r.text[:120]}"
                    logging.warning(f"Gemini {model_name} HTTP {r.status_code}: {r.text[:150]}")
            except Exception as e:
                last_err = f"{model_name} {type(e).__name__}: {str(e)[:120]}"
                logging.warning(f"Gemini {model_name} attempt failed: {e}")
                continue

    return f"⚠️ Arre yaar, Tillu AI se connect nahi ho pa raha abhi. ({last_err})"

# ── DISCORD BOT & UI ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

start_lock = asyncio.Lock()
is_starting = False

REEL_VIDEO_PATTERNS = [
    r'https?://(?:www\.)?instagram\.com/(?:reel|reels|p)/[a-zA-Z0-9_-]+',
    r'https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.-]+/video/[0-9]+',
    r'https?://(?:vt|vm)\.tiktok\.com/[a-zA-Z0-9]+',
    r'https?://(?:www\.)?youtube\.com/shorts/[a-zA-Z0-9_-]+',
    r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+',
    r'https?://youtu\.be/[a-zA-Z0-9_-]+',
    r'https?://(?:fb\.watch|www\.facebook\.com/reel)/[a-zA-Z0-9_-]+',
]
tracked_video_messages = set()

def contains_reel_or_video(message: discord.Message) -> bool:
    content = message.content or ""
    for pat in REEL_VIDEO_PATTERNS:
        if re.search(pat, content, re.IGNORECASE):
            return True
    for att in message.attachments:
        fname = (att.filename or "").lower()
        ctype = (att.content_type or "").lower()
        if ctype.startswith("video/") or fname.endswith(('.mp4', '.mov', '.webm', '.mkv', '.avi')):
            return True
    return False

def should_show_server_options(text: str) -> bool:
    t = text.lower().strip()
    keywords = [
        "server ip", "server address", "server port", "mc ip", "ip address",
        "ip kya hai", "kya ip hai", "port kya hai", "how to join", "kaise join kare",
        "whitelist me", "add whitelist", "whitelist kardo", "/whitelist", "!whitelist",
        "server status", "turn on server", "start server", "server start"
    ]
    return any(k in t for k in keywords)

class WhitelistModal(discord.ui.Modal, title="Minecraft Whitelist"):
    ign_input = discord.ui.TextInput(
        label="Minecraft Username (Java or Bedrock)",
        placeholder="e.g. AaluGamer123 or .BedrockUser",
        min_length=3,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await handle_whitelist_request(interaction, self.ign_input.value, user=interaction.user, guild=interaction.guild)

class ServerControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Turn On Server", style=discord.ButtonStyle.success, custom_id="btn_start_server", emoji="⚡")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_start_request(interaction, user=interaction.user, guild=interaction.guild)

    @discord.ui.button(label="📊 Server Status", style=discord.ButtonStyle.secondary, custom_id="btn_status_server", emoji="🔍")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_status_request(interaction, user=interaction.user, guild=interaction.guild)

    @discord.ui.button(label="📝 Whitelist Me", style=discord.ButtonStyle.primary, custom_id="btn_whitelist_server", emoji="🎟️")
    async def whitelist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WhitelistModal())

class TilluBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(ServerControlView())
        logging.info("[SetupHook] Persistent ServerControlView registered.")

        for gid in [PRIMARY_GUILD_ID, CS2_GUILD_ID]:
            try:
                g_obj = discord.Object(id=gid)
                self.tree.copy_global_to(guild=g_obj)
                synced = await self.tree.sync(guild=g_obj)
                logging.info(f"[SetupHook] Synced {len(synced)} slash commands directly to Guild {gid}.")
            except Exception as ge:
                logging.error(f"[SetupHook] Sync error for guild {gid}: {ge}")

        try:
            await self.tree.sync()
            logging.info("[SetupHook] Global slash commands synced.")
        except Exception as se:
            logging.error(f"[SetupHook] Global sync notice: {se}")

bot = TilluBot(command_prefix=['!', '/', '.'], intents=intents, help_command=None)

# ── REQUEST HANDLERS ─────────────────────────────────────────────────────────
async def handle_status_request(interaction_or_ctx, user=None, guild=None):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target_user = user or (interaction_or_ctx.user if is_inter else interaction_or_ctx.author)
    target_guild = guild or (interaction_or_ctx.guild if is_inter else interaction_or_ctx.guild)

    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        reply_fn = (lambda *a, **kw: interaction_or_ctx.followup.send(*a, ephemeral=True, **kw)) if interaction_or_ctx.response.is_done() else (lambda *a, **kw: interaction_or_ctx.response.send_message(*a, ephemeral=True, **kw))
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, delete_after=45, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, delete_after=45, **kwargs)

    allowed, remain = check_cooldown(target_user, target_guild)
    if not allowed:
        await reply_fn(embed=discord.Embed(
            title="⏳ Tillu is catching his breath!",
            description=f"Please wait **{remain}s** before using another command.\n*(Server Owner, Admins, and Mods have no cooldown)*",
            color=0xF1C40F
        ))
        return

    is_online, desc, online_p, max_p, ver = await asyncio.to_thread(ping_minecraft_server, 2.5)

    if is_online:
        embed = discord.Embed(
            title="🟢 Minecraft Server is ONLINE & READY!",
            description="The server is actively running and accepting connections.",
            color=0x2ECC71
        )
        embed.add_field(name="👥 Players Online", value=f"`{online_p}/{max_p}`", inline=True)
        embed.add_field(name="⚡ Version", value=f"`{ver}`\n*(Crossplay 1.7 - 1.21.x & Bedrock)*", inline=True)
        embed.add_field(name="☕ Java Connection", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
        embed.add_field(name="📱 Bedrock Connection", value=f"IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`", inline=False)
        embed.set_footer(text="Tillu • 24/7 Always-Online Active")
        await reply_fn(embed=embed, view=ServerControlView())
    else:
        embed = discord.Embed(
            title="🔴 Minecraft Server is OFFLINE",
            description="The server is currently stopped. Click below to turn it on!",
            color=0xE74C3C
        )
        embed.add_field(name="🚀 How to turn on?", value="Click **🟢 Turn On Server** below, type `/start`, or say `tillu start server`.", inline=False)
        embed.add_field(name="📝 Join Whitelist", value="Click **📝 Whitelist Me** or tell Tillu `whitelist me <ign>`.", inline=False)
        embed.set_footer(text="Tillu • Click below to play!")
        await reply_fn(embed=embed, view=ServerControlView())

async def handle_start_request(interaction_or_ctx, user, guild=None):
    global is_starting
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target_guild = guild or (interaction_or_ctx.guild if is_inter else interaction_or_ctx.guild)

    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        reply_fn = (lambda *a, **kw: interaction_or_ctx.followup.send(*a, ephemeral=True, **kw)) if interaction_or_ctx.response.is_done() else (lambda *a, **kw: interaction_or_ctx.response.send_message(*a, ephemeral=True, **kw))
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, delete_after=45, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, delete_after=45, **kwargs)

    allowed, remain = check_cooldown(user, target_guild)
    if not allowed:
        await reply_fn(embed=discord.Embed(
            title="⏳ Tillu is catching his breath!",
            description=f"Please wait **{remain}s** before using another command.\n*(Server Owner, Admins, and Mods have no cooldown)*",
            color=0xF1C40F
        ))
        return

    is_online, desc, online_p, max_p, ver = await asyncio.to_thread(ping_minecraft_server, 1.5)
    if is_online:
        embed = discord.Embed(
            title="🟢 Server is Already ONLINE!",
            description=f"The server is already running with **{online_p}/{max_p}** players.\nJoin now at `{SERVER_HOST}:{SERVER_PORT}`!",
            color=0x2ECC71
        )
        await reply_fn(embed=embed, view=ServerControlView())
        return

    if is_starting:
        embed = discord.Embed(
            title="⏳ Server is Already Booting Up!",
            description="Someone has already requested to start the server! Please wait ~20-30 seconds.",
            color=0xF1C40F
        )
        await reply_fn(embed=embed, view=ServerControlView())
        return

    async with start_lock:
        is_starting = True
        try:
            embed_init = discord.Embed(
                title="🚀 Turning ON the Minecraft Server...",
                description=f"Startup command triggered by **{user.mention}**!\n\nSending power signal to hosting panel...",
                color=0x3498DB
            )
            embed_init.add_field(name="📍 Server Address", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
            embed_init.add_field(name="⏳ Expected Boot Time", value="~25-45 seconds for Paper to load worlds.", inline=False)
            embed_init.set_footer(text="Tillu • 24/7 Cloud Host")
            await reply_fn(embed=embed_init, view=ServerControlView())

            p_ok, p_res = await asyncio.to_thread(send_pterodactyl_start)

            ready = False
            for _ in range(20):
                await asyncio.sleep(3)
                is_up, _, cur_players, _, ver = await asyncio.to_thread(ping_minecraft_server, 2.0)
                if is_up:
                    ready = True
                    break

            if ready:
                embed_ready = discord.Embed(
                    title="🎉 Minecraft Server is NOW ONLINE!",
                    description="The server has booted successfully and is **READY TO PLAY**!",
                    color=0x2ECC71
                )
                embed_ready.add_field(name="☕ Java Connection", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
                embed_ready.add_field(name="📱 Bedrock Connection", value=f"IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`", inline=False)
                embed_ready.set_footer(text="Tillu • Have fun!")
                await reply_fn(embed=embed_ready, view=ServerControlView())
            else:
                desc_note = f"The server is booting up.\nCheck `/status` or connect in 1 minute at `{SERVER_HOST}:{SERVER_PORT}`."
                if not p_ok and ("Just a moment" in str(p_res) or "403" in str(p_res)):
                    desc_note += "\n\n*(Note: Hexacraft panel has Cloudflare verification active. Server Owner Avinash can tap Start at [panel.hexacraft.fun](https://panel.hexacraft.fun))*"
                embed_to = discord.Embed(
                    title="⏳ Server Boot Status",
                    description=desc_note,
                    color=0xF1C40F
                )
                await reply_fn(embed=embed_to, view=ServerControlView())
        except Exception as e:
            embed_err = discord.Embed(
                title="✖ Notice on Start Request",
                description=f"Startup signal dispatched. Please check `/status` in 30 seconds.\n`{str(e)[:200]}`",
                color=0xF1C40F
            )
            await reply_fn(embed=embed_err, view=ServerControlView())
        finally:
            is_starting = False

async def handle_whitelist_request(interaction_or_ctx, ign: str, user, guild=None, bypass_cooldown=False):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target_guild = guild or (interaction_or_ctx.guild if is_inter else interaction_or_ctx.guild)

    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        reply_fn = (lambda *a, **kw: interaction_or_ctx.followup.send(*a, ephemeral=True, **kw)) if interaction_or_ctx.response.is_done() else (lambda *a, **kw: interaction_or_ctx.response.send_message(*a, ephemeral=True, **kw))
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, delete_after=45, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, delete_after=45, **kwargs)

    if not bypass_cooldown:
        allowed, remain = check_cooldown(user, target_guild)
        if not allowed:
            await reply_fn(embed=discord.Embed(
                title="⏳ Tillu is catching his breath!",
                description=f"Please wait **{remain}s** before using another command.\n*(Server Owner, Admins, and Mods have no cooldown)*",
                color=0xF1C40F
            ))
            return

    if not ign:
        await reply_fn("❌ Usage: `/whitelist <your_minecraft_ign>` or say `tillu whitelist me <ign>`")
        return

    clean_ign = ign.strip().replace('"', '').replace("'", '').replace("`", "")

    # Strict Safety Guardrail: Prevent harmful commands or ban attempts
    harmful_tokens = ["ban", "kick", "op", "deop", "kill", "stop", "clear", "gamemode", "sudo", "execute", "eval", "pardon"]
    if any(h in clean_ign.lower().split() for h in harmful_tokens):
        embed_err = discord.Embed(
            title="🚫 Action Not Allowed",
            description="Tillu only helps with whitelisting and friendly server info. Tillu cannot ban, kick, or harm players!",
            color=0xE74C3C
        )
        await reply_fn(embed=embed_err)
        return

    if not re.match(r'^[a-zA-Z0-9_.* ]{3,20}$', clean_ign):
        embed_err = discord.Embed(
            title="❌ Invalid Minecraft Username",
            description=f"**`{clean_ign}`** is not a valid username.\nPlease enter your Java or Bedrock gamer tag (3-20 characters).",
            color=0xE74C3C
        )
        await reply_fn(embed=embed_err)
        return

    reg = load_whitelist_registry()
    user_id_str = str(user.id)
    prev_entry = reg.get(user_id_str)

    reg[user_id_str] = {
        "ign": clean_ign,
        "discord_id": user.id,
        "discord_username": str(user),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_whitelist_registry(reg)

    applied_live = False
    try:
        applied_live = await execute_whitelist_command(clean_ign)
    except Exception:
        pass

    avatar_url = f"https://mc-heads.net/avatar/{clean_ign.replace(' ', '%20')}/128"

    embed = discord.Embed(
        title="✅ Successfully Whitelisted on Aalu SMP!",
        description=f"Welcome to the community, {user.mention}!\nYour account **`{clean_ign}`** has been registered to the whitelist.",
        color=0x2ECC71
    )
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="🎮 Minecraft IGN", value=f"`{clean_ign}`", inline=True)
    embed.add_field(name="⚡ Whitelist Status", value="**Active & Whitelisted**" if applied_live else "**Queued (Applies on boot)**", inline=True)
    embed.add_field(name="☕ Java Connection", value=f"`{SERVER_HOST}:{SERVER_PORT}`\n*(Versions 1.7 to 1.21.x)*", inline=False)
    embed.add_field(name="📱 Bedrock Connection", value=f"IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`", inline=False)

    if prev_entry and prev_entry.get("ign") != clean_ign:
        embed.set_footer(text=f"Updated from previous IGN: {prev_entry.get('ign')} • Tillu is always here to help!")
    else:
        embed.set_footer(text="Tillu • 24/7 Always-Online Active")

    await reply_fn(embed=embed, view=ServerControlView())

async def handle_ask_request(interaction_or_ctx, query: str, user, guild=None, bypass_cooldown: bool = False):
    """Processes user query with Gemini AI, supporting natural conversation and whitelist requests."""
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target_guild = guild or (interaction_or_ctx.guild if is_inter else interaction_or_ctx.guild)

    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        reply_fn = (lambda *a, **kw: interaction_or_ctx.followup.send(*a, ephemeral=True, **kw)) if interaction_or_ctx.response.is_done() else (lambda *a, **kw: interaction_or_ctx.response.send_message(*a, ephemeral=True, **kw))
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, **kwargs)

    if not bypass_cooldown:
        allowed, remain = check_cooldown(user, target_guild)
        if not allowed:
            cooldown_text = f"⏳ Tillu is catching his breath! Please wait **{remain}s** before asking another question."
            if is_inter:
                await reply_fn(embed=discord.Embed(
                    title="⏳ Tillu is catching his breath!",
                    description=f"Please wait **{remain}s** before asking another question.\n*(Server Owner, Admins, and Mods have no cooldown)*",
                    color=0xF1C40F
                ))
            elif isinstance(interaction_or_ctx, commands.Context):
                await reply_fn(content=cooldown_text, delete_after=15)
            else:
                await reply_fn(content=cooldown_text, delete_after=15)
            return

    is_admin = is_privileged_user(user, target_guild)

    # Call Gemini in thread with user ID (10-chat context window) and admin context
    user_id = getattr(user, "id", 0)
    answer = await asyncio.to_thread(query_gemini, query, str(user), user_id, is_admin)

    # 1. Check for ADMIN_INTENT (Console / Moderation commands for Admin/Owner)
    if "ADMIN_INTENT:" in answer:
        match = re.search(r'ADMIN_INTENT:\s*([^\n\r]+)', answer)
        if match:
            cmd = match.group(1).strip()
            if not is_admin:
                await reply_fn(content="🚫 Arre bhai, sirf Server Owner, Admins aur Moderators ke paas console ya ban/kick commands chalane ki permission hai!")
                return

            ok, resp_str = await execute_server_command(cmd)
            # If removing from whitelist, also clean local registry
            if "whitelist remove" in cmd.lower():
                target_p = cmd.split()[-1]
                await execute_server_command(f"fwd:whitelist remove {target_p}")
                await execute_server_command("whitelist reload")
                reg = load_whitelist_registry()
                new_reg = {k: v for k, v in reg.items() if v.get("ign", "").lower() != target_p.lower()}
                save_whitelist_registry(new_reg)

            clean_reply = answer.replace(match.group(0), "").strip()
            status_tag = f"⚙️ **[Console Action: `{cmd}`]**"
            channel_hint = f"\n*(Dispatched to <#{CONSOLE_CHANNEL_ID}> • Admins can also run commands directly in <#{CONSOLE_CHANNEL_ID}>)*"
            if clean_reply:
                await reply_fn(content=f"{status_tag}\n{clean_reply}{channel_hint}")
            else:
                await reply_fn(content=f"{status_tag}\nCommand successfully dispatched to <#{CONSOLE_CHANNEL_ID}>!{channel_hint}")
            return

    # 2. Check for Whitelist Intent
    if "WHITELIST_INTENT:" in answer:
        match = re.search(r'WHITELIST_INTENT:\s*([a-zA-Z0-9_.* ]{3,20})', answer)
        if match:
            extracted_ign = match.group(1).strip()
            logging.info(f"[Tillu Whitelist] Extracted IGN: '{extracted_ign}' from user: {user}")
            await handle_whitelist_request(interaction_or_ctx, extracted_ign, user, guild=target_guild, bypass_cooldown=True)
            return

    # 3. Final output logic:
    # - Slash Command Interaction -> Private Ephemeral reply (visible only to the user who ran it)
    # - Prefix Command (!tillu) -> Auto-delete after 45s to avoid chat clutter
    # - Normal chat in channel (on_message) -> Publicly visible as clean plain text, NO EMBEDS!
    if is_inter:
        if should_show_server_options(query):
            embed = discord.Embed(
                title="🤖 Tillu",
                description=answer,
                color=0x9B59B6
            )
            embed.set_footer(text="Tillu • legacy-7.hexacraft.fun")
            await reply_fn(embed=embed, view=ServerControlView())
        else:
            await reply_fn(content=answer)
    elif isinstance(interaction_or_ctx, commands.Context):
        await reply_fn(content=answer, delete_after=45)
    else:
        # Normal chat in channel: Publicly visible clean plain text (NO EMBEDS!)
        if hasattr(interaction_or_ctx, "channel"):
            await interaction_or_ctx.channel.send(content=answer)
        else:
            await reply_fn(content=answer)

# ── SLASH COMMANDS ───────────────────────────────────────────────────────────
@bot.tree.command(name="ask", description="Ask Tillu anything about the server, stream, or request whitelist!")
@app_commands.describe(query="What would you like to ask Tillu? (e.g. 'whitelist me GamerX' or 'how to join SMP')")
async def slash_ask(interaction: discord.Interaction, query: str):
    await handle_ask_request(interaction, query, user=interaction.user, guild=interaction.guild)

@bot.tree.command(name="start", description="Turn on the Minecraft server (anyone can use this!)")
async def slash_start(interaction: discord.Interaction):
    await handle_start_request(interaction, user=interaction.user, guild=interaction.guild)

@bot.tree.command(name="status", description="Check if the Minecraft server is online or offline")
async def slash_status(interaction: discord.Interaction):
    await handle_status_request(interaction, user=interaction.user, guild=interaction.guild)

@bot.tree.command(name="whitelist", description="Self-service: Whitelist your Minecraft IGN to join the Aalu SMP!")
@app_commands.describe(ign="Your exact in-game Minecraft username (Java or Bedrock)")
async def slash_whitelist(interaction: discord.Interaction, ign: str):
    await handle_whitelist_request(interaction, ign, user=interaction.user, guild=interaction.guild)

@bot.tree.command(name="console", description="Owner/Admin/Mod only: Run a command on the Minecraft server console")
@app_commands.describe(command="The exact console command to execute (e.g. 'say Hello' or 'whitelist reload')")
async def slash_console(interaction: discord.Interaction, command: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await interaction.response.send_message("🚫 Only Server Owner, Admins, and Moderators can execute console commands!", ephemeral=True)
        return
    ok, resp = await execute_server_command(command)
    await interaction.response.send_message(f"⚙️ **[Console Action: `{command}`]**\nDispatched to <#{CONSOLE_CHANNEL_ID}>! Check <#{CONSOLE_CHANNEL_ID}> for live execution.", ephemeral=True)

@bot.tree.command(name="ban", description="Owner/Admin/Mod only: Ban a player from the Minecraft server")
@app_commands.describe(player="Minecraft player username", reason="Reason for ban")
async def slash_ban(interaction: discord.Interaction, player: str, reason: str = "Banned by administrator"):
    if not is_privileged_user(interaction.user, interaction.guild):
        await interaction.response.send_message("🚫 Only Server Owner, Admins, and Moderators can ban players!", ephemeral=True)
        return
    await execute_server_command(f"ban {player} {reason}")
    await interaction.response.send_message(f"🔨 **[Banned]** `{player}` has been banned from the server! (Reason: {reason})\nDispatched to <#{CONSOLE_CHANNEL_ID}>.", ephemeral=True)

@bot.tree.command(name="unban", description="Owner/Admin/Mod only: Unban a player from the Minecraft server")
@app_commands.describe(player="Minecraft player username")
async def slash_unban(interaction: discord.Interaction, player: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await interaction.response.send_message("🚫 Only Server Owner, Admins, and Moderators can unban players!", ephemeral=True)
        return
    await execute_server_command(f"pardon {player}")
    await interaction.response.send_message(f"🕊️ **[Unbanned]** `{player}` has been pardoned.\nDispatched to <#{CONSOLE_CHANNEL_ID}>.", ephemeral=True)

@bot.tree.command(name="unwhitelist", description="Owner/Admin/Mod only: Remove a player from the Minecraft whitelist")
@app_commands.describe(player="Minecraft player username to remove")
async def slash_unwhitelist(interaction: discord.Interaction, player: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await interaction.response.send_message("🚫 Only Server Owner, Admins, and Moderators can remove whitelist!", ephemeral=True)
        return
    clean_p = player.strip()
    await execute_server_command(f"whitelist remove {clean_p}")
    await execute_server_command(f"fwd:whitelist remove {clean_p}")
    await execute_server_command("whitelist reload")
    reg = load_whitelist_registry()
    new_reg = {k: v for k, v in reg.items() if v.get("ign", "").lower() != clean_p.lower()}
    save_whitelist_registry(new_reg)
    await interaction.response.send_message(f"🗑️ **[Whitelist Removed]** `{clean_p}` removed from whitelist.\nDispatched to <#{CONSOLE_CHANNEL_ID}>.", ephemeral=True)

@bot.tree.command(name="help", description="Show Tillu bot commands & features")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Tillu Bot Commands",
        description="I am Tillu, your server assistant! Here's how you can talk to me:",
        color=0x9B59B6
    )
    embed.add_field(name="💬 Talk Naturally", value="Just type `tillu <question>` or `@Tillu <question>` anywhere in chat!", inline=False)
    embed.add_field(name="🎟️ Whitelist Me", value="Say `tillu whitelist me <IGN>` or `/whitelist <ign>`", inline=False)
    embed.add_field(name="🚀 Turn On Server", value="`/start`, `!start`, or the green button below", inline=False)
    embed.add_field(name="🔍 Check Status", value="`/status`, `!status`, or `!ip`", inline=False)
    embed.add_field(name="👑 Admin Commands", value="`!c <cmd>`, `!ban <player>`, `!unban <player>`, `!kick <player>`, `!unwhitelist <player>`", inline=False)
    embed.add_field(name="🎚️ Live Server Console", value=f"Owner, Admins & Mods can type Minecraft commands directly in <#{CONSOLE_CHANNEL_ID}> anytime without visiting the website panel!", inline=False)
    embed.add_field(name="⏱️ Cooldown", value="20s cooldown for members • **0s cooldown** for Owner, Admins & Mods", inline=False)
    embed.set_footer(text="Tillu • 24/7 Always-Online Active")
    await interaction.response.send_message(embed=embed, view=ServerControlView(), ephemeral=True)

# ── TEXT COMMANDS ────────────────────────────────────────────────────────────
@bot.command(name="tillu", aliases=["ask", "ai", "question"])
async def cmd_tillu(ctx, *, query: str = None):
    if not query:
        await ctx.send("❌ Usage: `!tillu <your question or whitelist request>`")
        return
    await handle_ask_request(ctx, query, user=ctx.author, guild=ctx.guild)

@bot.command(name="c", aliases=["console", "cmd"])
async def cmd_console(ctx, *, command: str = None):
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 Only Server Owner, Admins, and Moderators can execute console commands!")
        return
    if not command:
        await ctx.send(f"❌ Usage: `!c <minecraft command>` (e.g. `!c say hello` or `!c whitelist reload`)\n💡 Tip: You can also type directly in <#{CONSOLE_CHANNEL_ID}> without visiting the website panel!")
        return
    ok, resp = await execute_server_command(command)
    await ctx.send(f"⚙️ **[Console Action: `{command}`]**\nDispatched to <#{CONSOLE_CHANNEL_ID}>! Check <#{CONSOLE_CHANNEL_ID}> for live execution.")

@bot.command(name="ban")
async def cmd_ban(ctx, player: str = None, *, reason: str = "Banned by administrator"):
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 Only Server Owner, Admins, and Moderators can ban players!")
        return
    if not player:
        await ctx.send("❌ Usage: `!ban <player> [reason]`")
        return
    await execute_server_command(f"ban {player} {reason}")
    await ctx.send(f"🔨 **[Banned]** `{player}` has been banned from the server! (Reason: {reason})\nDispatched to <#{CONSOLE_CHANNEL_ID}>.")

@bot.command(name="unban", aliases=["pardon"])
async def cmd_unban(ctx, player: str = None):
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 Only Server Owner, Admins, and Moderators can unban players!")
        return
    if not player:
        await ctx.send("❌ Usage: `!unban <player>`")
        return
    await execute_server_command(f"pardon {player}")
    await ctx.send(f"🕊️ **[Unbanned]** `{player}` has been pardoned on the server.\nDispatched to <#{CONSOLE_CHANNEL_ID}>.")

@bot.command(name="kick")
async def cmd_kick(ctx, player: str = None, *, reason: str = "Kicked by administrator"):
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 Only Server Owner, Admins, and Moderators can kick players!")
        return
    if not player:
        await ctx.send("❌ Usage: `!kick <player> [reason]`")
        return
    await execute_server_command(f"kick {player} {reason}")
    await ctx.send(f"👢 **[Kicked]** `{player}` has been kicked from the server!\nDispatched to <#{CONSOLE_CHANNEL_ID}>.")

@bot.command(name="unwhitelist", aliases=["wlremove", "removewhitelist"])
async def cmd_unwhitelist(ctx, player: str = None):
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 Only Server Owner, Admins, and Moderators can remove whitelist!")
        return
    if not player:
        await ctx.send("❌ Usage: `!unwhitelist <player>`")
        return
    clean_p = player.strip()
    await execute_server_command(f"whitelist remove {clean_p}")
    await execute_server_command(f"fwd:whitelist remove {clean_p}")
    await execute_server_command("whitelist reload")
    reg = load_whitelist_registry()
    new_reg = {k: v for k, v in reg.items() if v.get("ign", "").lower() != clean_p.lower()}
    save_whitelist_registry(new_reg)
    await ctx.send(f"🗑️ **[Whitelist Removed]** `{clean_p}` has been removed from the whitelist.\nDispatched to <#{CONSOLE_CHANNEL_ID}>.")

@bot.command(name="start", aliases=["startserver", "turnon", "on"])
async def cmd_start(ctx):
    await handle_start_request(ctx, user=ctx.author, guild=ctx.guild)

@bot.command(name="status", aliases=["online", "server", "ip", "info"])
async def cmd_status(ctx):
    await handle_status_request(ctx, user=ctx.author, guild=ctx.guild)

@bot.command(name="whitelist", aliases=["wl", "addwhitelist"])
async def cmd_whitelist(ctx, *, ign: str = None):
    await handle_whitelist_request(ctx, ign, user=ctx.author, guild=ctx.guild)

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(
        title="🤖 Tillu Bot Commands",
        description="I am Tillu, your server assistant! Here's how you can talk to me:",
        color=0x9B59B6
    )
    embed.add_field(name="💬 Talk Naturally", value="Just type `tillu <question>` or `@Tillu <question>` anywhere in chat!", inline=False)
    embed.add_field(name="🎟️ Whitelist Me", value="Say `tillu whitelist me <IGN>` or `/whitelist <ign>`", inline=False)
    embed.add_field(name="🚀 Turn On Server", value="`!start` or `/start`", inline=False)
    embed.add_field(name="🔍 Check Status", value="`!status` or `/status`", inline=False)
    embed.add_field(name="👑 Admin Commands", value="`!c <cmd>`, `!ban <player>`, `!unban <player>`, `!kick <player>`, `!unwhitelist <player>`", inline=False)
    embed.add_field(name="🎚️ Live Server Console", value=f"Owner, Admins & Mods can type Minecraft commands directly in <#{CONSOLE_CHANNEL_ID}> anytime without visiting the website panel!", inline=False)
    embed.add_field(name="⏱️ Cooldown", value="20s cooldown for members • **0s cooldown** for Owner, Admins & Mods", inline=False)
    embed.set_footer(text="Tillu • 24/7 Cloud Host")
    await ctx.send(embed=embed, view=ServerControlView())

async def delayed_video_reply(message: discord.Message):
    try:
        # Wait 5 minutes (300 seconds) before replying
        await asyncio.sleep(300)

        channel = message.channel
        if not channel:
            return

        prompt = (
            f"A user posted this reel or video in our Discord chat: '{message.content[:200]}'. "
            f"You are Tillu, an Indian AI streamer companion. You just watched it after 5 minutes! "
            f"Write a funny, witty, short reaction (1-2 lines) in Hinglish/English reacting to the video or meme. "
            f"Sound like a genuine friend laughing or reacting. Do NOT mention whitelist or server commands."
        )
        reaction = await asyncio.to_thread(query_gemini, prompt, "Tillu")

        if not reaction or "⚠️" in reaction or "WHITELIST_INTENT" in reaction:
            import random
            fallback_reactions = [
                "Bhai 5 minute lag gaye dekhne me, par kya mast video tha yaar! 😂 Mazza aa gaya!",
                "Yeh reel dekh ke has has ke bura haal ho gaya bhai 😂🔥 10/10 content!",
                "Tillu approved reel! Pure 5 minute ka full entertainment tha boss! 👌",
                "Arre bhai kya cheez share ki hai! Tillu ne pura dekh liya, ek number! 🔥😂"
            ]
            reaction = random.choice(fallback_reactions)

        try:
            await message.reply(reaction)
        except Exception:
            await channel.send(f"{message.author.mention} {reaction}")
    except Exception as e:
        logging.error(f"[delayed_video_reply] Error: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    channel = guild.system_channel
    if not channel or not channel.permissions_for(guild.me).send_messages:
        for ch in guild.text_channels:
            if any(name in ch.name.lower() for name in ["welcome", "general", "lounge", "chat", "main"]):
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
    if not channel:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break

    if channel:
        welcome_text = (
            f"🎉 **Arre swagat hai, {member.mention}!** Welcome to **{guild.name}**!\n"
            f"Mai hu **Tillu**, aapka dost aur server assistant! 🤖\n\n"
            f"Agar humare Minecraft server me khelna hai, toh bas mujhe bolo `tillu whitelist me <IGN>` ya neeche button se whitelist karlo! Have fun! 🚀"
        )
        embed = discord.Embed(
            title="👋 Welcome to the Community!",
            description=welcome_text,
            color=0x2ECC71
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="☕ Java & Bedrock IP", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
        embed.set_footer(text="Tillu • 24/7 Always-Online Active")
        try:
            await channel.send(embed=embed, view=ServerControlView())
        except Exception as e:
            logging.error(f"[on_member_join] Error sending welcome: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Check for reel or video link/attachment to reply after 5 minutes
    if contains_reel_or_video(message) and message.id not in tracked_video_messages:
        tracked_video_messages.add(message.id)
        asyncio.create_task(delayed_video_reply(message))

    # Process standard prefix commands first (e.g. !start, !whitelist, !tillu, !ask)
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return

    # Check for natural conversation directed at Tillu:
    # 1. Bot is explicitly mentioned
    # 2. Reply to a message sent by the bot
    # 3. Message contains "tillu" or "mr tillu"
    is_mentioned = bot.user in message.mentions if bot.user else False
    is_reply_to_bot = False
    is_reply_to_other = False
    if message.reference and message.reference.resolved:
        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message):
            if bot.user and resolved.author.id == bot.user.id:
                is_reply_to_bot = True
            elif resolved.author.id != message.author.id:
                is_reply_to_other = True

    content = message.content.strip()
    if not content:
        return

    match_tillu = bool(re.search(r'\b(tillu|mr\s*tillu)\b', content, re.IGNORECASE))
    is_dismissal = bool(re.search(r'\b(bye|good\s*night|goodnight|tata|alvida|so\s*ja|shubh\s*ratri|stop\s*talking|chup\s*raho)\b', content, re.IGNORECASE))

    session_key = (message.author.id, message.channel.id)
    now = time.time()
    is_active_session = False
    if session_key in ACTIVE_USER_CONVERSATIONS:
        if now - ACTIVE_USER_CONVERSATIONS[session_key] <= CONVERSATION_TIMEOUT_SECONDS:
            is_active_session = True
        else:
            ACTIVE_USER_CONVERSATIONS.pop(session_key, None)

    # CASE A: Explicit wake-up or message directed at Tillu
    if is_mentioned or is_reply_to_bot or match_tillu:
        if is_dismissal:
            ACTIVE_USER_CONVERSATIONS.pop(session_key, None)
        else:
            ACTIVE_USER_CONVERSATIONS[session_key] = now

        # Clean query text
        query = content
        if bot.user:
            query = re.sub(rf'<@!?{bot.user.id}>', '', query).strip()
        query = re.sub(r'^(hey\s+|yo\s+|hello\s+|hi\s+|arre\s+)?(mr\s*tillu|tillu)[\s,:]*', '', query, flags=re.IGNORECASE).strip()
        if not query:
            query = content

        try:
            async with message.channel.typing():
                await handle_ask_request(message, query, user=message.author, guild=message.guild, bypass_cooldown=True)
        except Exception as e:
            logging.error(f"[on_message] Error handling natural query for Tillu: {e}")

    # CASE B: Active conversation session (user asks follow-up questions without mentioning Tillu)
    elif is_active_session:
        # Ignore if user is replying to someone else or mentioning another user
        has_other_mentions = any(m.id != (bot.user.id if bot.user else 0) for m in message.mentions)
        if is_reply_to_other or has_other_mentions:
            return

        # Ignore bot prefix commands meant for other bots
        if content.startswith(('!', '/', '.', '?', '-', '$', ';;', '>', ';', '~', '+', '=')):
            return

        if is_dismissal:
            ACTIVE_USER_CONVERSATIONS.pop(session_key, None)
        else:
            ACTIVE_USER_CONVERSATIONS[session_key] = now

        try:
            async with message.channel.typing():
                await handle_ask_request(message, content, user=message.author, guild=message.guild, bypass_cooldown=True)
        except Exception as e:
            logging.error(f"[on_message] Error handling active session follow-up for Tillu: {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        await asyncio.sleep(0.05)
        if not interaction.response.is_done():
            custom_id = (interaction.data or {}).get("custom_id", "")
            if "start" in custom_id:
                await handle_start_request(interaction, user=interaction.user, guild=interaction.guild)
            elif "status" in custom_id:
                await handle_status_request(interaction, user=interaction.user, guild=interaction.guild)
            elif "whitelist" in custom_id:
                await interaction.response.send_modal(WhitelistModal())

# ── BACKGROUND KEEP-ALIVE HTTP SERVER & GUARDIAN ─────────────────────────────
async def health_handler(request):
    return web.Response(text=json.dumps({"status": "healthy", "service": "Tillu Minecraft Bot", "time": time.time()}), content_type="application/json")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_handler)
    app.router.add_get('/healthz', health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"[OK] Health Check Web Server running on port {PORT}")

async def render_keepalive_loop():
    await asyncio.sleep(30)
    while True:
        try:
            urls_to_ping = [f"http://127.0.0.1:{PORT}/healthz"]
            if RENDER_EXTERNAL_URL:
                urls_to_ping.append(f"{RENDER_EXTERNAL_URL}/healthz")

            async with aiohttp.ClientSession() as session:
                for u in urls_to_ping:
                    async with session.get(u, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        pass
        except Exception:
            pass
        await asyncio.sleep(300)

async def guardian_loop():
    await asyncio.sleep(10)
    while True:
        try:
            is_up, _, p_count, _, _ = await asyncio.to_thread(ping_minecraft_server, 2.0)
            if is_up:
                activity = discord.Activity(type=discord.ActivityType.playing, name=f"Tillu | Minecraft ({p_count}/50)")
                await bot.change_presence(status=discord.Status.online, activity=activity)
            else:
                activity = discord.Activity(type=discord.ActivityType.listening, name="Tillu | legacy-7.hexacraft.fun")
                await bot.change_presence(status=discord.Status.idle, activity=activity)
        except Exception:
            pass
        await asyncio.sleep(1800)

@bot.event
async def on_ready():
    logging.info(f"==========================================================")
    logging.info(f"  TILLU BOT ONLINE: {bot.user} (ID: {bot.user.id})")
    logging.info(f"==========================================================")
    for guild in bot.guilds:
        try:
            await guild.me.edit(nick="Tillu")
        except Exception:
            pass
    asyncio.create_task(guardian_loop())
    asyncio.create_task(render_keepalive_loop())

async def main():
    try:
        await start_web_server()
    except Exception as we:
        logging.error(f"[WebServer] Failed to start web server: {we}")

    if not BOT_TOKEN:
        logging.critical("[Fatal] BOT_TOKEN environment variable is not set!")
        while True:
            await asyncio.sleep(60)

    while True:
        try:
            logging.info("[Bot] Connecting to Discord Gateway...")
            await bot.start(BOT_TOKEN)
        except (discord.LoginFailure, discord.PrivilegedIntentsRequired) as fatal_e:
            logging.critical(f"[Bot] Fatal Discord auth error: {fatal_e}. Please verify BOT_TOKEN.")
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"[Bot] Discord error: {e}. Reconnecting in 10s...", exc_info=True)
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())

