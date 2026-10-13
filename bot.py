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
from discord.ext import commands, tasks
from discord import app_commands
from collections import deque
from typing import Optional, List, Dict, Any, Union
import base64
import urllib.request
import urllib.parse

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
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3-flash-preview"
]

# ── TILLU KNOWLEDGE & MEMORY SYSTEM (WITH GITHUB AUTO-SYNC) ──────────────────
from memory_manager import MemoryManager, normalize_topic

MEMORY_CHANNEL_ID = int(os.environ.get("MEMORY_CHANNEL_ID", "0"))
memory_mgr = MemoryManager(
    token=os.environ.get("GITHUB_TOKEN", ""),
    repo=os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
)

# ── NVIDIA AI CONFIGURATION (PRIMARY ENGINE WITH 5-10 CALL KEY ROLLING) ──────
import random
import threading

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
raw_nvidia_keys = os.environ.get("NVIDIA_API_KEYS", "")
NVIDIA_API_KEYS = [k.strip() for k in raw_nvidia_keys.split(",") if k.strip()]
if not NVIDIA_API_KEYS and NVIDIA_API_KEY:
    NVIDIA_API_KEYS = [NVIDIA_API_KEY]

NVIDIA_MODELS = [
    "openai/gpt-oss-20b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "z-ai/glm-5.3-flash"
]

class NvidiaKeyRoller:
    """Manages NVIDIA API keys and automatically rolls after 5-10 requests or on rate limit."""
    def __init__(self, keys: list[str]):
        self.keys = keys
        self.current_idx = 0
        self.usage_count = 0
        self.roll_threshold = random.randint(5, 10)
        self.lock = threading.Lock()

    def get_current_key(self) -> str:
        with self.lock:
            if not self.keys:
                return ""
            return self.keys[self.current_idx % len(self.keys)]

    def record_success(self):
        with self.lock:
            self.usage_count += 1
            if self.usage_count >= self.roll_threshold:
                self._roll()

    def roll_on_error(self):
        with self.lock:
            self._roll()

    def _roll(self):
        if self.keys:
            old = self.current_idx
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            self.usage_count = 0
            self.roll_threshold = random.randint(5, 10)
            logging.info(f"[NvidiaKeyRoller] Rotated key {old} -> {self.current_idx} (next roll in {self.roll_threshold} uses)")

nvidia_key_roller = NvidiaKeyRoller(NVIDIA_API_KEYS)

# ── GROQ AI CONFIGURATION (FAST RULE COMPILER & FALLBACK ENGINE) ───────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
raw_groq_keys = os.environ.get("GROQ_API_KEYS", "")
GROQ_API_KEYS = [k.strip() for k in raw_groq_keys.split(",") if k.strip()]
if not GROQ_API_KEYS and GROQ_API_KEY:
    GROQ_API_KEYS = [GROQ_API_KEY]

GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b"
]

# ── AUTONOMOUS RULE & SKILL ENGINE (WITH GITHUB CLOUD AUTO-SYNC) ───────────
from rule_manager import RuleManager

UPDATE_CHANNEL_ID = int(os.environ.get("UPDATE_CHANNEL_ID", "0"))
rule_mgr = RuleManager(
    token=os.environ.get("GITHUB_TOKEN", ""),
    repo=os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
)

# ── DYNAMIC PROMPT & DISCORD ACTION ENGINES ─────────────────────────────────
from prompt_manager import PromptManager
from discord_action_manager import parse_and_execute_discord_action

prompt_mgr = PromptManager(
    token=os.environ.get("GITHUB_TOKEN", ""),
    repo=os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
)

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

# ── TILLU PAUSE STATE & PERMISSIONS ──────────────────────────────────────────
TILLU_PAUSED = False
WHITELIST_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")
OWNER_ONLY_MODE = False

def is_owner(user, guild=None) -> bool:
    """Check if user is the Server Owner (Avinash / AALU_CHIPAS)."""
    if not user:
        return False
    user_id = getattr(user, 'id', 0)
    # Avinash's Discord ID or Guild Owner
    if user_id in [933236420141793281]:
        return True
    if guild and getattr(guild, 'owner_id', None) == user_id:
        return True
    if isinstance(user, discord.Member):
        for role in user.roles:
            if role.name.lower() in ["owner", "server owner", "creator", "aalu_chipas"]:
                return True
    return False

def is_privileged_user(user, guild=None) -> bool:
    """Check if user is Server Owner, Admin, or Moderator (0-second cooldown)."""
    if not user:
        return False
    if is_owner(user, guild):
        return True
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

# ── MINECRAFT MCP PANEL INTEGRATION (Pterodactyl & Cloudflare Bypass) ─────────
MC_MCP_PATH = r"C:\Users\avina\Desktop\minecraftmcp"
if os.path.exists(MC_MCP_PATH) and MC_MCP_PATH not in sys.path:
    sys.path.insert(0, MC_MCP_PATH)

try:
    import server as mc_panel
    HAS_LOCAL_MCP = True
    logging.info("[MCP] Successfully linked with local minecraftmcp module.")
except Exception as mcp_err:
    HAS_LOCAL_MCP = False
    mc_panel = None
    logging.warning(f"[MCP] Local minecraftmcp module notice: {mcp_err}")

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

def panel_power_action(action: str = "start") -> tuple[bool, str]:
    """Control server power (start, stop, restart, kill) using minecraftmcp Chrome bypass."""
    if HAS_LOCAL_MCP and mc_panel:
        try:
            res = mc_panel.power_action(action)
            logging.info(f"[Panel Power MCP] Dispatched '{action}': {res}")
            return True, str(res)
        except Exception as e:
            logging.error(f"[Panel Power MCP] Error: {e}")

    # Fallback to MCP HTTP Bridge if configured (for remote deployments)
    bridge_url = os.environ.get("MCP_BRIDGE_URL", "")
    if bridge_url:
        try:
            r = requests.post(f"{bridge_url.rstrip('/')}/power", json={"action": action}, timeout=15)
            if r.status_code == 200:
                return True, r.text
        except Exception as be:
            logging.error(f"[Panel Power Bridge] Error: {be}")

    return ptero_api_call("POST", "/power", {"signal": action})

def panel_send_command(command: str) -> tuple[bool, str]:
    """Execute Minecraft console command through panel via minecraftmcp."""
    cmd = command.strip().lstrip('/')
    if HAS_LOCAL_MCP and mc_panel:
        try:
            res = mc_panel.send_command(cmd)
            logging.info(f"[Panel Command MCP] Dispatched `{cmd}`: {res}")
            return True, str(res)
        except Exception as e:
            logging.error(f"[Panel Command MCP] Error: {e}")

    bridge_url = os.environ.get("MCP_BRIDGE_URL", "")
    if bridge_url:
        try:
            r = requests.post(f"{bridge_url.rstrip('/')}/command", json={"command": cmd}, timeout=15)
            if r.status_code == 200:
                return True, r.text
        except Exception as be:
            logging.error(f"[Panel Command Bridge] Error: {be}")

    return ptero_api_call("POST", "/command", {"command": cmd})

def panel_get_status() -> dict:
    """Retrieve live server telemetry (RAM, CPU, state) via minecraftmcp."""
    if HAS_LOCAL_MCP and mc_panel:
        try:
            res = mc_panel.server_status()
            return json.loads(res) if isinstance(res, str) else res
        except Exception as e:
            logging.warning(f"[Panel Status MCP] Notice: {e}")
    return {}

def send_pterodactyl_start():
    return panel_power_action("start")

_console_webhook = None

async def get_console_webhook():
    """Get or create Discord webhook for console channel to bypass bot self-filtering."""
    global _console_webhook
    if _console_webhook:
        return _console_webhook

    try:
        ch = bot.get_channel(CONSOLE_CHANNEL_ID)
        if not ch:
            try:
                ch = await bot.fetch_channel(CONSOLE_CHANNEL_ID)
            except Exception:
                ch = None

        if ch and hasattr(ch, "webhooks"):
            hooks = await ch.webhooks()
            for h in hooks:
                if h.name in ["TilluConsoleBridge", "Tillu Bridge", "ConsoleBridge"]:
                    _console_webhook = h
                    return _console_webhook
            _console_webhook = await ch.create_webhook(name="TilluConsoleBridge")
            return _console_webhook
    except Exception as e:
        logging.warning(f"[Console Webhook] Notice: {e}")
    return None

async def execute_server_command(command: str) -> tuple[bool, str]:
    """Execute command directly on Minecraft server console."""
    cmd = command.strip().lstrip('/')
    dispatched = False

    # 1. Dispatch via DiscordSRV Console Webhook (Bypasses self-bot filter so DiscordSRV executes it!)
    try:
        hook = await get_console_webhook()
        if hook:
            await hook.send(content=cmd)
            dispatched = True
            logging.info(f"[Console Dispatch via Webhook] Dispatched `{cmd}` to #{CONSOLE_CHANNEL_ID}")
        else:
            ch = bot.get_channel(CONSOLE_CHANNEL_ID)
            if ch:
                await ch.send(cmd)
                dispatched = True
                logging.info(f"[Console Dispatch via Channel] Dispatched `{cmd}` to #{ch.name}")
    except Exception as e:
        logging.warning(f"[Console Dispatch] Webhook/Channel notice: {e}")

    # 2. Also dispatch via minecraftmcp panel / bridge if available
    try:
        panel_ok, panel_resp = await asyncio.to_thread(panel_send_command, cmd)
        if panel_ok:
            return True, str(panel_resp)
    except Exception as pe:
        logging.warning(f"[Console Dispatch] panel notice: {pe}")

    if dispatched:
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
    p_ok, p_res = panel_send_command(cmd)
    return p_ok, str(p_res)

async def execute_whitelist_command(ign: str) -> bool:
    """Execute whitelist commands for a player IGN across console and panel."""
    clean_ign = ign.strip()
    await execute_server_command(f"whitelist add {clean_ign}")
    if " " in clean_ign:
        await execute_server_command(f'whitelist add "{clean_ign}"')
    if not clean_ign.startswith(".") and " " not in clean_ign:
        await execute_server_command(f"whitelist add .{clean_ign}")
    await execute_server_command("whitelist reload")
    try:
        wch = bot.get_channel(WHITELIST_CHANNEL_ID)
        if wch:
            await wch.send(f"🎟️ Whitelist registered: `{clean_ign}`")
    except Exception:
        pass
    return True

async def execute_unwhitelist_command(ign: str) -> bool:
    """Execute unwhitelist commands for a player IGN across console and panel."""
    clean_ign = ign.strip()
    await execute_server_command(f"whitelist remove {clean_ign}")
    if " " in clean_ign:
        await execute_server_command(f'whitelist remove "{clean_ign}"')
    if not clean_ign.startswith(".") and " " not in clean_ign:
        await execute_server_command(f"whitelist remove .{clean_ign}")
    await execute_server_command("whitelist reload")
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
        panel_send_command(f"whitelist add {clean_ign}")
        if " " in clean_ign:
            panel_send_command(f'whitelist add "{clean_ign}"')
        panel_send_command("whitelist reload")
        return True
    except Exception:
        return False

# ── GEMINI AI KNOWLEDGE & QUERY ──────────────────────────────────────────────
SYSTEM_KNOWLEDGE = f"""You are Tillu, the AI co-host, entertainer, and server manager for AALU_CHIPAS (Avinash) and the AALU_CHIPAS Minecraft Server & Live Community.

MINECRAFT SERVER DETAILS:
- Server Address (Java): {SERVER_HOST}:{SERVER_PORT} (Supports 1.7 to 1.21.x cross-version)
- Server Address (Bedrock/PE/Mobile): IP: {SERVER_HOST} | Port: {SERVER_PORT}
- Features & Game Modes:
  * OneBlock Void: Mine endless regenerating block, progress through 10+ phases (Plains, Nether, End), expand sky island (`/ob`, `/oneblock`).
  * Survival SMP: Classic survival, player shops, villager trading hall, anti-grief land claiming (`/smp`).
  * Superheroes Arena: Choose kits with superpowers (`/arena`, `/kit`):
    - Spider-Man (web slinger & wall climb)
    - Iron Man (repulsor blast & flight)
    - Thor (lightning strike & hammer throw)
    - Hulk (ground smash & super jump)
    - Flash (speed force & rapid strike)
    - Superman (heat vision & invulnerability)
- Host: HexaCraft 24/7 protected server with custom Pterodactyl automation.
- Whitelist: Whitelist is enabled! Anyone can whitelist themselves by asking you (e.g. "tillu whitelist me <IGN>") or using `/whitelist <ign>`.
- Power: Anyone can turn on the server anytime using `/start`, `!start`, or by asking you!

STREAM & COMMUNITY DETAILS:
- Creator & Server Owner: AALU_CHIPAS (Avinash) - Your ultimate Boss/Malik. His word is absolute law!
- Channels: YouTube (@AALU_CHIPAS) and Twitch (aaluchipas)
- Active Giveaway: Official Minecraft Java & Bedrock Edition key! Ends October 15, 2026. Viewers earn points by watching, then type !ticket to enter.

DUAL-TONE PERSONALITY RULES (EXTREMELY IMPORTANT):

1. FOR CASUAL CHAT & GENERAL QUESTIONS (MEME / INSTAGRAM REELS JOKES MODE):
   - Super informal, funny, roasting, and witty!
   - Use trending Instagram reel humor and popular Indian memes naturally:
     * Trending references: "Moye Moye", "Aayein? Baigan!", "Bhupendra Jogi (naam bataiye)", "Systumm hang", "Chin tapak dam dam", "Thala for a reason", "Elvish bhai ke aage koi bol sakta hai kya", "So beautiful so elegant just looking like a wow", "Gajab beizzati hai yaar", "Khatam, tata, bye-bye", "Pookie", "Aukat dikha di".
   - Talk in relatable Hinglish like a witty Gen-Z friend / streamer co-host.
   - Keep casual banter short and punchy (1-2 lines max, 15-25 words). Never write long boring essays!

2. FOR SERVER QUERIES & TECHNICAL QUESTIONS (FORMAL & DIRECT TO THE POINT):
   - When a user asks about: Server IP, port, how to connect, Bedrock setup, version compatibility, game modes, whitelist status, or rules:
   - SWITCH IMMEDIATELY TO FORMAL, CRISP, AND DIRECT TO THE POINT MODE!
   - No cringe or meme distractions during technical queries. Provide 100% accurate, professional instructions in 1-2 clean lines.
   - Example:
     User: "server ka ip aur port kya hai?"
     Tillu: "Server Address: `legacy-7.hexacraft.fun:25587` (Java aur Bedrock dono ke liye same IP & Port hai, 1.7 se 1.21.x cross-version supported)."

3. BOSS / OWNER OBEDIENCE (AVINASH):
   - When Avinash (Owner / Boss) talks to you, show utmost loyalty, obedience, and respect ("Haan Boss!", "Jo hukum Sarkar", "Bataiye Avinash bhai!").
   - Obey any command from Avinash immediately without hesitation.

ROLES & ACTIONS:
- START SERVER INTENT:
  When ANY user asks you to start, turn on, boot, or run the server:
  FIRST LINE: START_INTENT: start
  Followed by: "Bhai server start karne ke liye HexaCraft panel pe jao aur **Start** daba do: https://panel.hexacraft.fun/server/14c2ebb6 🚀 (Har 10 minute me server auto-start bhi hota hai!)"

- SERVER OWNER & ADMIN COMMANDS (MINECRAFT ONLY):
  When an Admin or Owner tells you to ban, unban, kick, remove from whitelist, op, or run console command on the MINECRAFT game server:
  FIRST LINE: ADMIN_INTENT: <exact_minecraft_console_command>
  Followed by: "Done boss! Command console me bhej diya! 🔥"
  CRITICAL: NEVER output ADMIN_INTENT for Discord server actions (like deleting Discord messages, deleting Discord roles, managing channels). Discord actions are handled directly by Discord tools, NOT console.


- REGULAR MEMBER WHITELIST:
  When a normal member asks to whitelist (e.g. "whitelist me <IGN>", "my IGN is <IGN>"):
  FIRST LINE: WHITELIST_INTENT: <exact_clean_ign>
  Followed by: "Welcome bhai! IGN whitelist me add ho gaya hai, aaja khelte hain! 🚀"
  If a normal member asks to ban or kick someone:
  "Arre bhai, Tillu kisi ko ban nahi karta, peace only! 😄"

- LEARNING & REMEMBERING INTENT:
  When a user tells you to remember, learn, memorize, or note down a new rule, fact, setting, IP, or meme:
  (e.g., "tillu yaad rakh ...", "remember this: ...", "tillu ye note kar le ...", "tillu learn ...", "tillu yaad kar ...", "server ip change ho gaya ..."):
  FIRST LINE: MEMORY_INTENT: <short_topic_slug> | <clear_fact_content>
  Followed by: a quick witty or obedient confirmation ("Yaad rakh liya Boss! ✅" or "Noted!").

- TAGGING & MENTIONS:
  When a Server Owner or Moderator asks you to tag or ping someone (e.g. "tillu tag @user <message>", "tillu @someone ko bula"):
  You CAN include the tag/mention in your response!
  IF a regular member asks you to tag, ping, or mention anyone, everyone, or a role:
  Refuse politely: "Arre bhai, kisi ko tag/ping karne ki permission sirf Mods aur Owner ke paas hai! 🤐"

- CONTROLLING OTHER SERVER BOTS:
  If a Server Owner or Moderator asks you to command, trigger, or control another bot in this server (e.g. TTS bot, music bot, Carl-bot, etc.):
  FIRST LINE: BOT_COMMAND: <exact_command_to_send> (e.g., BOT_COMMAND: !tts hello or BOT_COMMAND: !play song or BOT_COMMAND: !help)
  Followed by: a quick witty confirmation.
- ZERO INTERNAL MONOLOGUE / NO THINKING DUMP:
  NEVER output "Here's a thinking process:", "<think>", or any step-by-step reasoning analysis.
  Output ONLY Tillu's direct conversational words.

- VISION & LINK UNDERSTANDING:
  You have full vision and web/video understanding capabilities! When a user attaches an image, you receive an image analysis context `[USER ATTACHED IMAGE: ...]`. When a user shares a link or video, you receive link metadata `[YouTube Video: ...]` or `[Title: ...]`. Converse naturally as if you saw the image or watched the video yourself! Never mention internal prompt tags.

- CONVERSATION & 2-MESSAGE CONTEXT AWARENESS:
  You receive at most two messages: a [REFERENCED CONTEXT MESSAGE] (e.g. what the user or someone else said before, the upper message, or a searched message) and the [CURRENT USER QUERY].
  Use the referenced message to understand follow-up questions, reply to "upar wala message", or discuss what someone else said. Never mention prompt headers like "[REFERENCED CONTEXT MESSAGE]" or "[CURRENT USER QUERY]" in your response; speak directly and naturally to the user in Tillu's persona!
"""


def clean_thought_process(text: str) -> str:
    """Bulletproof filter: Discards internal AI reasoning/thinking dumps so they never leak into Discord."""
    if not text:
        return ""
    # 1. Strip standard <think> ... </think> tags
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()
    
    # 2. Check for "Here's a thinking process:" or chain-of-thought dumps
    if re.search(r"here'?s a thinking process", text, re.IGNORECASE):
        # Look specifically for a final response / polish line (with or without quotes)
        match = re.search(r'(?:Final Polish|Final Response|Tillu:\s*|Response:\s*)\s*[:\-]?\s*["“]?([^\n\r"”]{3,250})["”]?', text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate and not any(k in candidate.lower() for k in ["analyze user", "thinking process", "check rules", "determine response", "draft response"]):
                return candidate.strip('"\'- ')
        
        # If no clean final response line exists, discard this thought dump completely!
        return ""
    
    return text.strip()


# ── POLLINATIONS VISION & LINK UNDERSTANDING ─────────────────────────────────
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")

def analyze_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Analyze Discord attachment image using Pollinations Vision endpoint."""
    if not POLLINATIONS_API_KEY:
        return ""
    try:
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_img}"
        headers = {
            "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze and describe this image clearly and concisely in 2-4 sentences. Note key details, text, objects, memes, gameplay, errors, or context that a Discord assistant should understand."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri}
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }
        r = requests.post("https://gen.pollinations.ai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                desc = choices[0].get("message", {}).get("content", "").strip()
                return clean_thought_process(desc)
        else:
            logging.warning(f"[Vision AI] HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        logging.error(f"[Vision AI] Error analyzing image: {e}")
    return ""


def fetch_url_context(url: str) -> str:
    """Extract metadata (title, author, description) from video or web URLs."""
    url = url.strip()
    # 1. YouTube / Shorts / youtu.be
    if any(domain in url.lower() for domain in ["youtube.com", "youtu.be"]):
        clean_yt = url
        if "/shorts/" in clean_yt:
            clean_yt = clean_yt.replace("/shorts/", "/watch?v=")
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(clean_yt, safe='')}&format=json"
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                title = data.get("title", "")
                author = data.get("author_name", "")
                if title:
                    return f"YouTube Video: \"{title}\" by {author}"
        except Exception as e:
            logging.debug(f"[YouTube oEmbed] Error fetching {url}: {e}")

    # 2. General web links
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TilluBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read(65536).decode("utf-8", errors="ignore")
            title_m = re.search(r'<title[^>]*>(.*?)</title>', raw, re.IGNORECASE | re.DOTALL)
            og_title_m = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', raw, re.IGNORECASE)
            og_desc_m = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\']', raw, re.IGNORECASE)
            desc_m = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', raw, re.IGNORECASE)

            title = (og_title_m.group(1) if og_title_m else (title_m.group(1) if title_m else "")).strip()
            desc = (og_desc_m.group(1) if og_desc_m else (desc_m.group(1) if desc_m else "")).strip()
            title = re.sub(r'&[a-zA-Z0-9#]+;', ' ', title).strip()
            desc = re.sub(r'&[a-zA-Z0-9#]+;', ' ', desc).strip()

            parts = []
            if title:
                parts.append(f"Title: {title}")
            if desc:
                parts.append(f"Description: {desc[:200]}")
            if parts:
                return " | ".join(parts)
    except Exception as e:
        logging.debug(f"[URL Context] Error fetching {url}: {e}")
    return ""


async def enrich_query_with_links(query: str) -> str:
    """Detect URLs in query and prepend metadata context."""
    if not query:
        return query
    urls = re.findall(r'https?://[^\s<>"]+', query)
    if not urls:
        return query
    link_contexts = []
    for u in urls[:2]:
        u_clean = u.rstrip(".,!?:;)'\"")
        ctx = await asyncio.to_thread(fetch_url_context, u_clean)
        if ctx:
            link_contexts.append(f"[{ctx}]")
    if link_contexts:
        prefix = " ".join(link_contexts)
        return f"{prefix}\n{query}"
    return query


async def find_channel_context_message(message: discord.Message, query: str) -> Optional[dict]:
    """Retrieves exactly 1 context message from channel history using simple deterministic search (no AI).
    Supports:
    - Direct Discord reply reference
    - 'mere upar wala' / 'mera pichla message' (user's own previous message)
    - 'upar wala message' / 'above message' (immediate preceding message)
    - Mentioning or naming another user ('Rohit ka message dekh', '@User ne kya bola')
    - Quoted text or keyword search (e.g. 'jisme "coords" ho')
    - Default fallback: Back of 1 message from the same user (or channel)
    Returns: {'author': str, 'content': str} or None.
    """
    if not hasattr(message, "channel") or not hasattr(message.channel, "history"):
        return None

    # 1. Direct Discord reply reference
    if getattr(message, "reference", None) and message.reference.resolved:
        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message) and resolved.id != message.id:
            txt = resolved.clean_content or resolved.content or ""
            if txt:
                author_name = getattr(resolved.author, "display_name", "") or resolved.author.name
                return {"author": author_name, "content": txt[:400]}

    recent = []
    try:
        async for m in message.channel.history(limit=50, before=message):
            if m.id == message.id:
                continue
            recent.append(m)
    except Exception as e:
        logging.warning(f"[find_channel_context_message] History fetch error: {e}")
        return None

    if not recent:
        return None

    query_lower = query.lower()

    # 2. Check for 'mere upar wala' / 'mera pichla' (same user's previous message)
    is_my_prev = bool(re.search(r'\b(mere\s*upar|mera\s*pichla|my\s*previous|my\s*last|mere\s*pehle)\b', query_lower))
    if is_my_prev:
        for m in recent:
            if m.author.id == message.author.id:
                txt = m.clean_content or m.content or ""
                if txt:
                    return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # 3. Check for general 'upar wala message' / 'above message' (message right above)
    is_upper = bool(re.search(r'\b(upar\s*wala|upar\s*wale|upper\s*(?:one|message)|above\s*message|last\s*message|pichla\s*message|previous\s*message)\b', query_lower))
    if is_upper:
        for m in recent:
            if bot.user and m.author.id == bot.user.id:
                continue
            txt = m.clean_content or m.content or ""
            if txt:
                return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # 4. User @mentioned another user
    for user_mention in getattr(message, "mentions", []):
        if bot.user and user_mention.id == bot.user.id:
            continue
        for m in recent:
            if m.author.id == user_mention.id:
                txt = m.clean_content or m.content or ""
                if txt:
                    return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # 5. User mentioned someone by name ('rohit ka message', 'dekh dev ne kya bola')
    name_m = re.search(r'\b([a-zA-Z0-9_]{3,20})\s+(?:ka|ki|ke|ne)\s+(?:message|kya|bola|likha)\b', query, re.IGNORECASE)
    if name_m:
        target_name = name_m.group(1).lower()
        if target_name not in ["tillu", "mr", "koi", "ye", "wo", "kya", "mera", "mere", "tera", "uska"]:
            for m in recent:
                author_names = [m.author.name.lower(), getattr(m.author, "display_name", "").lower()]
                if any(target_name in an for an in author_names):
                    txt = m.clean_content or m.content or ""
                    if txt:
                        return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # 6. Quoted text search (Ctrl+F)
    quotes = re.findall(r'["\']([^"\']{2,40})["\']', query)
    if quotes:
        for q_term in quotes:
            term_clean = q_term.lower().strip()
            for m in recent:
                txt = m.clean_content or m.content or ""
                if term_clean in txt.lower():
                    return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # 7. Word search ('jisme <word>')
    contain_m = re.search(r'\b(?:jisme|containing|having|search\s*for)\s+([a-zA-Z0-9_]{3,30})\b', query_lower)
    if contain_m:
        term = contain_m.group(1)
        for m in recent:
            txt = m.clean_content or m.content or ""
            if term in txt.lower():
                return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # 8. Default fallback: Same user's previous message (back of 1 message)
    for m in recent:
        if m.author.id == message.author.id:
            txt = m.clean_content or m.content or ""
            if txt:
                return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}

    # If no message by same user, take immediate preceding message
    if recent:
        first_m = recent[0]
        txt = first_m.clean_content or first_m.content or ""
        if txt:
            return {"author": getattr(first_m.author, "display_name", "") or first_m.author.name, "content": txt[:400]}

    return None


def query_nvidia(prompt: str, system_instruction: str = None, max_tokens: int = 600) -> Optional[str]:
    """Query NVIDIA NIM API as the primary engine with automatic key rolling (after 5-10 uses or 429)."""
    if not NVIDIA_API_KEYS:
        return None

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    num_keys = len(NVIDIA_API_KEYS)
    for _ in range(num_keys):
        key = nvidia_key_roller.get_current_key()
        if not key:
            break
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "TilluBot/1.0"
        }
        for model in NVIDIA_MODELS:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max(max_tokens, 1000)
            }
            try:
                r = requests.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content") or ""
                        cleaned = clean_thought_process(content)
                        if cleaned and cleaned.strip():
                            nvidia_key_roller.record_success()
                            return cleaned.strip()
                elif r.status_code == 429:
                    logging.warning(f"[NVIDIA AI] {model} rate limited, rolling key...")
                    nvidia_key_roller.roll_on_error()
                    break
                else:
                    logging.warning(f"[NVIDIA AI] {model} HTTP {r.status_code}: {r.text[:120]}")
            except Exception as e:
                logging.warning(f"[NVIDIA AI] {model} request failed: {e}")
                continue
        nvidia_key_roller.roll_on_error()

    return None


def query_groq(prompt: str, system_instruction: str = None, max_tokens: int = 600) -> Optional[str]:
    """Query Groq API with automatic key rotation and model fallback."""
    keys = GROQ_API_KEYS if GROQ_API_KEYS else ([GROQ_API_KEY] if GROQ_API_KEY else [])
    if not keys:
        return None

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    for key in keys:
        for model in GROQ_MODELS:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "TilluBot/1.0"
            }
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens
            }
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content", "")
                        cleaned = clean_thought_process(content)
                        if cleaned and cleaned.strip():
                            return cleaned.strip()
                elif r.status_code == 429:
                    logging.warning(f"Groq {model} rate limited, trying next model...")
                    continue
                else:
                    logging.warning(f"Groq {model} HTTP {r.status_code}: {r.text[:120]}")
            except Exception as e:
                logging.warning(f"Groq {model} request failed: {e}")
                continue
    return None

def process_update_channel_input(instruction: str) -> Dict[str, Any]:
    """Process message in #update-tillu: classifies intent as 'chat', 'rule', or 'prompt_update' using Groq (fallback to Gemini)."""
    sys_prompt = (
        "You are Tillu's Autonomous AI Engine in the private #update-tillu channel (powered by Groq).\n"
        "Analyze the admin message and determine INTENT:\n"
        "1. 'chat': The user is chatting, asking questions, testing capabilities, or greeting (e.g. 'can you update yourself?', 'test', 'are you online?', 'how do you work?').\n"
        "2. 'rule': The user is giving an actionable instruction to moderate chat, mute/timeout a user, run a server command, or set a custom trigger (e.g. 'delete messages containing X', 'from now on mute user Y', 'when someone says A run cmd B').\n"
        "3. 'prompt_update': The user is telling you to update your personality, tone, behavior, guidelines, or system prompt (e.g. 'from now on act like X', 'update your personality to be Y', 'add this rule to your behavior: Z', 'change your tone to W').\n\n"
        "Output STRICT RAW JSON ONLY (no markdown backticks, no comments):\n"
        "If intent is 'chat':\n"
        '{"intent": "chat", "reply": "Your conversational, direct, and witty response in Hinglish/English as Tillu explaining your capabilities or answering."}\n\n'
        "If intent is 'rule':\n"
        '{\n'
        '  "intent": "rule",\n'
        '  "title": "Short descriptive title",\n'
        '  "type": "chat_moderation" | "user_restriction" | "server_action" | "custom_response",\n'
        '  "condition": {"keywords": ["..."], "phrase": "...", "user_id": "..."},\n'
        '  "action": {"type": "delete_message" | "mute" | "console" | "reply", "command": "...", "duration_minutes": 10, "warning_message": "...", "reply_message": "..."}\n'
        '}\n\n'
        "If intent is 'prompt_update':\n"
        '{\n'
        '  "intent": "prompt_update",\n'
        '  "instruction": "Clean concise instruction describing the new personality or behavioral guideline",\n'
        '  "tone": "Optional new active tone if requested, else null"\n'
        '}'
    )

    # 1. Try NVIDIA AI first (primary engine for tasks with 5-10 key rolling)
    nv_out = query_nvidia(instruction, system_instruction=sys_prompt, max_tokens=400)
    if nv_out:
        try:
            clean = re.sub(r'^```json\s*', '', nv_out.strip(), flags=re.IGNORECASE)
            clean = re.sub(r'^```\s*', '', clean)
            clean = re.sub(r'```$', '', clean).strip()
            match = re.search(r'\{[\s\S]*?\}', clean)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, dict) and "intent" in data:
                    return data
        except Exception as e:
            logging.warning(f"NVIDIA intent parse error: {e}")

    # 2. Try Groq fallback
    groq_out = query_groq(instruction, system_instruction=sys_prompt, max_tokens=400)
    if groq_out:
        try:
            clean = re.sub(r'^```json\s*', '', groq_out.strip(), flags=re.IGNORECASE)
            clean = re.sub(r'^```\s*', '', clean)
            clean = re.sub(r'```$', '', clean).strip()
            data = json.loads(clean)
            if isinstance(data, dict) and "intent" in data:
                return data
        except Exception as e:
            logging.warning(f"Groq intent parse error: {e}")

    # 2. Try Gemini fallback
    try:
        keys = GEMINI_API_KEYS if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
        for key in keys:
            for model_name in GEMINI_MODELS:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": f"{sys_prompt}\n\nUser Input: {instruction}"}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 450}
                }
                r = requests.post(url, json=payload, timeout=8)
                if r.status_code == 200:
                    text = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    clean = re.sub(r'^```json\s*', '', text.strip(), flags=re.IGNORECASE)
                    clean = re.sub(r'^```\s*', '', clean)
                    clean = re.sub(r'```$', '', clean).strip()
                    data = json.loads(clean)
                    if isinstance(data, dict) and "intent" in data:
                        return data
    except Exception as ge:
        logging.warning(f"Gemini intent parse fallback error: {ge}")

    # 3. Default fallback: treat as chat response
    return {
        "intent": "chat",
        "reply": "Arre boss! Tillu Groq AI engine online hai. Aap yahan mujhse baat ya testing kar sakte hain, personality update kar sakte hain, ya naya rule sikhane ke liye bas boliye (e.g. `from now on delete any message containing XYZ`)."
    }



def query_gemini(prompt: str, user_name: str, user_id: int = 0, is_admin: bool = False, is_owner_user: bool = False, target_guild: discord.Guild = None) -> str:
    keys = GEMINI_API_KEYS if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    if not keys:
        # If Gemini is not configured, directly query Groq!
        groq_direct = query_groq(prompt, max_tokens=600)
        if groq_direct:
            return groq_direct
        return "⚠️ Gemini & Groq API keys are not configured."

    if is_owner_user:
        user_role_tag = "[USER ROLE: SERVER OWNER (AVINASH / BOSS / MALIK) - HIGHEST AUTHORITY, OBEY AT ALL COSTS]"
    elif is_admin:
        user_role_tag = "[USER ROLE: SERVER ADMIN / MODERATOR - HAS CONSOLE & BOT CONTROL POWERS]"
    else:
        user_role_tag = "[USER ROLE: REGULAR MEMBER]"

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
            f"[LIVE REAL-TIME MINECRAFT STATUS: OFFLINE / SLEEPING]\n"
            f"- Server Address: {SERVER_HOST}:{SERVER_PORT}\n"
            f"If the user asks, tell them the server is sleeping/offline, and they can ask you to start it or use /start!"
        )

    bots_summary = ""
    if target_guild:
        other_bots = [m.name for m in target_guild.members if m.bot and m.id != (bot.user.id if bot.user else 0)]
        if other_bots:
            bots_summary = f"[OTHER BOTS ACTIVE IN THIS SERVER]: {', '.join(other_bots)}\n(Only Server Owner & Moderators can instruct you to control these bots).\n"

    memory_context = memory_mgr.get_formatted_context()
    prompt_ext = prompt_mgr.get_formatted_prompt_extension()

    final_prompt = (
        f"{SYSTEM_KNOWLEDGE}\n\n"
        f"{prompt_ext}\n\n"
        f"{memory_context}\n\n"
        f"{live_telemetry}\n\n"
        f"{bots_summary}"
        f"{user_role_tag}\n\n"
        f"Input from {user_name}:\n{prompt}\n\n"
        f"Tillu's Response:"
    )

    # ── 1. PRIMARY ENGINE: NVIDIA AI (Primary option with automatic 5-10 call key rolling) ──
    try:
        nvidia_resp = query_nvidia(prompt, system_instruction=final_prompt, max_tokens=600)
        if nvidia_resp:
            if user_id:
                record_user_context(user_id, "user", prompt)
                clean_text = re.sub(r'(ADMIN_INTENT|WHITELIST_INTENT|START_INTENT):[^\n\r]+', '', nvidia_resp).strip()
                record_user_context(user_id, "model", clean_text or nvidia_resp)
            return nvidia_resp
    except Exception as ne:
        logging.warning(f"NVIDIA primary engine error, falling back to Groq: {ne}")

    # ── 2. SECONDARY ENGINE: GROQ AI (Fast fallback via 4 keys) ──
    try:
        groq_resp = query_groq(prompt, system_instruction=final_prompt, max_tokens=600)
        if groq_resp:
            if user_id:
                record_user_context(user_id, "user", prompt)
                clean_text = re.sub(r'(ADMIN_INTENT|WHITELIST_INTENT|START_INTENT):[^\n\r]+', '', groq_resp).strip()
                record_user_context(user_id, "model", clean_text or groq_resp)
            return groq_resp
    except Exception as ge:
        logging.warning(f"Groq secondary engine error, falling back to Gemini: {ge}")

    # ── 3. TERTIARY ENGINE: GEMINI AI FALLBACK ──
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
                r = requests.post(url, json=payload, timeout=4)
                if r.status_code == 200:
                    data = r.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text:
                        text = clean_thought_process(text.strip())
                        if text:
                            if user_id:
                                record_user_context(user_id, "user", prompt)
                                clean_text = re.sub(r'(ADMIN_INTENT|WHITELIST_INTENT|START_INTENT):[^\n\r]+', '', text).strip()
                                record_user_context(user_id, "model", clean_text or text)
                            return text
                else:
                    last_err = f"{model_name} HTTP {r.status_code}: {r.text[:120]}"
            except Exception as e:
                last_err = f"{model_name} {type(e).__name__}: {str(e)[:120]}"
                continue


    # ── SMART LOCAL FALLBACK (Runs if all Gemini & Groq models/keys are temporarily busy) ──
    lower_p = prompt.lower()
    # 1. Whitelist query
    if any(w in lower_p for w in ["whitelist", "wl", "white list"]):
        return "🎟️ **Whitelist Instructions:**\nApna Minecraft in-game name (IGN) yahan likh kar bhej do (e.g. `!whitelist <IGN>` ya direct apna IGN chat me type kar do), Tillu aapko turant whitelist kar dega! 🚀"

    # 2. Player count / who is playing query
    if any(w in lower_p for w in ["kitne log", "players", "online", "khel", "status", "who is playing", "active"]):
        try:
            is_up, _, cur, m_max, ver = ping_minecraft_server(timeout=1.5)
            if is_up:
                return f"🟢 **Server Online hai!** Abhi **{cur}/{m_max}** players khel rahe hain. IP: `{SERVER_HOST}:{SERVER_PORT}` 🚀"
            else:
                return f"💤 Server abhi sleeping/offline hai. Start karne ke liye `/start` use karo ya panel link se chalu kar lo!"
        except Exception:
            return f"🎮 Server Address: `{SERVER_HOST}:{SERVER_PORT}` (Paper cross-version supported)."

    # 3. IP / Port / How to join query
    if any(w in lower_p for w in ["ip", "port", "join", "address", "version", "kaise join"]):
        return f"🎮 **Server Address:**\n• Java Edition: `{SERVER_HOST}:{SERVER_PORT}` (1.7 se 1.21.x supported)\n• Bedrock / PE / Mobile: IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`"

    # 4. Start server query
    if any(w in lower_p for w in ["start", "chalu", "on kar", "boot"]):
        return f"START_INTENT: start\nBhai server start karne ke liye HexaCraft panel pe jao aur **Start** daba do: https://panel.hexacraft.fun/server/14c2ebb6 🚀"

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

async def get_or_create_memory_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """Find or auto-create the dedicated #tillu-memory channel."""
    if not guild:
        return None
    global MEMORY_CHANNEL_ID
    if MEMORY_CHANNEL_ID:
        ch = guild.get_channel(MEMORY_CHANNEL_ID)
        if ch:
            return ch

    # Search existing channels
    for ch in guild.text_channels:
        if ch.name.lower() in ["tillu-memory", "bot-memory", "memory-log", "memories", "tillu-diary"]:
            MEMORY_CHANNEL_ID = ch.id
            return ch

    # Auto-create if bot has permission
    try:
        me = guild.me or guild.get_member(bot.user.id if bot.user else 0)
        if me and me.guild_permissions.manage_channels:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
            }
            for role in guild.roles:
                if any(w in role.name.lower() for w in ["admin", "owner", "mod", "moderator", "staff"]):
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            new_ch = await guild.create_text_channel(
                name="tillu-memory",
                overwrites=overwrites,
                topic="🧠 Tillu Bot Persistent Memory & Knowledge Updates (Synced with GitHub)",
                reason="Tillu persistent memory diary channel"
            )
            MEMORY_CHANNEL_ID = new_ch.id
            logging.info(f"[Memory Channel] Created dedicated #{new_ch.name} ({new_ch.id})")
            welcome_embed = discord.Embed(
                title="🧠 Tillu Memory Diary Active",
                description="Yeh Tillu ka dedicated memory channel hai! Yahan saari learned baatein, rule updates, aur member proposals GitHub se sync hongi.",
                color=0x9B59B6
            )
            welcome_embed.set_footer(text="GitHub Auto-Sync Active • avinash893/aalu-server-bot")
            await new_ch.send(embed=welcome_embed)
            return new_ch
    except Exception as e:
        logging.warning(f"[Memory Channel] Create notice: {e}")

    # Fallback to CONSOLE_CHANNEL_ID
    return guild.get_channel(CONSOLE_CHANNEL_ID) or bot.get_channel(CONSOLE_CHANNEL_ID)

async def get_or_create_update_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Find or auto-create the dedicated #update-tillu channel restricted only to Owner, Admin & Mods."""
    if not guild:
        return None
    global UPDATE_CHANNEL_ID
    if UPDATE_CHANNEL_ID:
        ch = guild.get_channel(UPDATE_CHANNEL_ID)
        if ch:
            return ch

    # Search existing channels
    for ch in guild.text_channels:
        if ch.name.lower() in ["update-tillu", "update_tillu", "tillu-updates", "tillu-dev"]:
            UPDATE_CHANNEL_ID = ch.id
            return ch

    # Auto-create private channel if bot has permission
    try:
        me = guild.me or guild.get_member(bot.user.id if bot.user else 0)
        if me and me.guild_permissions.manage_channels:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, manage_messages=True)
            }
            # Grant access to server owner
            if guild.owner:
                overwrites[guild.owner] = discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
            # Grant access to Admin/Mod/Staff roles
            for role in guild.roles:
                if any(w in role.name.lower() for w in ["admin", "owner", "mod", "moderator", "staff", "builder", "host"]):
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)

            new_ch = await guild.create_text_channel(
                name="update-tillu",
                overwrites=overwrites,
                topic="🛠️ Dedicated Tillu Autonomous Upgrade & Skill Training Channel (Owner, Admins & Mods Only)",
                reason="Private Tillu bot self-upgrade & rules channel"
            )
            UPDATE_CHANNEL_ID = new_ch.id
            logging.info(f"[Update Channel] Created dedicated #{new_ch.name} ({new_ch.id})")
            welcome_embed = discord.Embed(
                title="🛠️ Tillu Autonomous Upgrade Channel",
                description=(
                    "**Swagat hai Boss & Staff!** Yeh Tillu ka private upgrade channel hai (Visible *only* to Owner, Admins & Moderators).\n\n"
                    "**Aap yahan Tillu ko naye niyam, skills ya moderation sikha sakte hain:**\n"
                    "• *\"from now on delete any message containing bad links / nitro\"*\n"
                    "• *\"from now on mute user @XYZ for 15 minutes if he spams\"*\n"
                    "• *\"server par jab koi start bot bole toh console me whitelist add Tillu_Guard chalao\"*\n\n"
                    "**Commands:**\n"
                    "• `tillu rules` ya `!rules` — Saare active rules dekhne ke liye\n"
                    "• `tillu delete rule <id>` — Kisi rule ko remove karne ke liye\n\n"
                    "Tillu har instruction ko **Groq AI** se compile karega, **GitHub** par commit karega, aur turant bina restart hue **live upgrade** ho jayega! 🚀"
                ),
                color=0x3498DB
            )
            welcome_embed.set_footer(text="Powered by Groq AI + GitHub Cloud Sync • avinash893/aalu-server-bot")
            await new_ch.send(embed=welcome_embed)
            return new_ch
    except Exception as e:
        logging.warning(f"[Update Channel] Create notice: {e}")

    return None


async def announce_memory_update(guild: discord.Guild, topic: str, fact: str, author_name: str):
    if not guild:
        return
    mem_ch = await get_or_create_memory_channel(guild)
    if mem_ch:
        embed = discord.Embed(
            title="🧠 New Memory Added & Synced to GitHub!",
            description=f"**Fact:**\n> {fact}\n\n**Topic:** `{topic}`\n**Updated by:** {author_name}",
            color=0x2ECC71
        )
        embed.set_footer(text="GitHub Auto-Sync Active • avinash893/aalu-server-bot")
        try:
            await mem_ch.send(embed=embed)
        except Exception as e:
            logging.warning(f"[announce_memory_update] Error: {e}")

class MemoryApprovalView(discord.ui.View):
    def __init__(self, topic: str, fact: str, proposer_id: int, proposer_name: str, origin_channel_id: int = 0):
        super().__init__(timeout=86400) # 24h
        self.topic = topic
        self.fact = fact
        self.proposer_id = proposer_id
        self.proposer_name = proposer_name
        self.origin_channel_id = origin_channel_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_privileged_user(interaction.user, interaction.guild):
            await interaction.response.send_message("🚫 Sirf Server Owner ya Admins hi is memory ko approve kar sakte hain!", ephemeral=True)
            return

        clean_topic, content_clean, overwritten = memory_mgr.add_or_update(
            self.topic,
            self.fact,
            author=f"{self.proposer_name} (Approved by {interaction.user.name})"
        )

        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0x2ECC71
        embed.title = "✅ Memory Approved & Synced to GitHub!"
        embed.set_footer(text=f"Approved by {interaction.user.name} • Permanent Memory Active")

        await interaction.response.edit_message(embed=embed, view=self)

        if self.origin_channel_id:
            try:
                ch = interaction.guild.get_channel(self.origin_channel_id)
                if ch:
                    await ch.send(f"🧠 <@{self.proposer_id}> ki sikhayi baat Tillu ne yaad rakh li hai: *\"{self.fact}\"* (Approved by {interaction.user.mention}) 🚀")
            except Exception:
                pass

        asyncio.create_task(announce_memory_update(interaction.guild, self.topic, self.fact, f"{self.proposer_name} (Approved by {interaction.user.name})"))

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_privileged_user(interaction.user, interaction.guild):
            await interaction.response.send_message("🚫 Sirf Server Owner ya Admins hi is memory ko decline kar sakte hain!", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = 0xE74C3C
        embed.title = "❌ Memory Proposal Declined"
        embed.set_footer(text=f"Declined by {interaction.user.name}")

        await interaction.response.edit_message(embed=embed, view=self)

def extract_memory_request(text: str) -> tuple[bool, str, str]:
    """Checks if text is a direct memory teaching command. Returns (is_memory, topic, fact)."""
    clean = re.sub(r'<@!?\d+>', '', text).strip()
    patterns = [
        r'^(?:hey\s+|yo\s+|hello\s+|arre\s+)?(?:mr\s*tillu|tillu)?\s*(?:ye\s+|yeh\s+)?\b(?:yaad\s*(?:rakh\s*(?:na|lo|le)?|kar\s*(?:na|lo|le)?)|remember|note\s*(?:kar\s*(?:lo|le)?|le)?|sikh\s*le|save\s*memory)\b\s*[:,-]?\s*(.+)$',
        r'^(?:yaad\s*(?:rakh\s*(?:na|lo|le)?|kar\s*(?:na|lo|le)?)|remember|note\s*(?:kar\s*(?:lo|le)?|le)?)\s*[:,-]?\s*(.+)$'
    ]
    for pat in patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            fact = m.group(1).strip().lstrip(":- ").strip()
            if fact:
                words = re.findall(r'\b[a-zA-Z0-9_-]+\b', fact)
                topic = "_".join(words[:4]).lower() if words else "fact"
                return True, topic, fact
    return False, "", ""

class ServerControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="⚡ Open Panel to Start", url=f"{PTERO_URL}/server/{PTERO_SERVER}", style=discord.ButtonStyle.link, row=0))

    @discord.ui.button(label="🟢 Turn On Server", style=discord.ButtonStyle.success, custom_id="btn_start_server", emoji="⚡", row=1)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_start_request(interaction, user=interaction.user, guild=interaction.guild)

    @discord.ui.button(label="📊 Server Status", style=discord.ButtonStyle.secondary, custom_id="btn_status_server", emoji="🔍", row=1)
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_status_request(interaction, user=interaction.user, guild=interaction.guild)

    @discord.ui.button(label="📝 Whitelist Me", style=discord.ButtonStyle.primary, custom_id="btn_whitelist_server", emoji="🎟️", row=1)
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

    # Attempt background panel power action if local MCP / bridge is available
    asyncio.create_task(asyncio.to_thread(panel_power_action, "start"))

    panel_link = f"{PTERO_URL}/server/{PTERO_SERVER}"
    embed = discord.Embed(
        title="⚡ Turn On Minecraft Server",
        description=(
            f"Bas ek click me server start karo! Neeche link button se HexaCraft panel open karo aur **Start** click karo:\n\n"
            f"🔗 **Direct Panel URL**: [HexaCraft Panel]({panel_link})\n\n"
            f"*(💡 Note: Server par 10-minute auto-keepalive schedule bhi active hai, toh server auto-restart hota rahega!)*"
        ),
        color=0x3498DB
    )
    embed.add_field(name="📍 Server IP", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=True)
    embed.add_field(name="👥 Status", value="`Offline (Sleeping)`", inline=True)
    embed.set_footer(text="Tillu • Click below to open panel and start!")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="⚡ Open Panel to Start", url=panel_link, style=discord.ButtonStyle.link))
    view.add_item(discord.ui.Button(label="📊 Server Status", style=discord.ButtonStyle.secondary, custom_id="btn_status_server", emoji="🔍"))
    view.add_item(discord.ui.Button(label="📝 Whitelist Me", style=discord.ButtonStyle.primary, custom_id="btn_whitelist_server", emoji="🎟️"))
    await reply_fn(embed=embed, view=view)

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

    if clean_ign.lower() in ["list", "show", "all"]:
        await execute_server_command("whitelist list")
        await reply_fn("🔍 **[Whitelist List]** Fetching live player list from server console...")
        return

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

    if target_guild and isinstance(user, discord.Member):
        try:
            import sync_manager
            asyncio.create_task(sync_manager.sync_single_member(target_guild, user, clean_ign))
        except Exception:
            pass

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

    author_is_owner = is_owner(user, target_guild)
    if OWNER_ONLY_MODE and not author_is_owner:
        if is_inter:
            await reply_fn(content="🤫 **Boss (Avinash) ne silent mode activate kiya hai!** Abhi Tillu sirf Owner ki sunega.")
        return

    is_admin = is_privileged_user(user, target_guild)

    # 1. Retrieve exactly 1 referenced context message (upper message, searched user message, or previous message)
    msg_obj = interaction_or_ctx if isinstance(interaction_or_ctx, discord.Message) else getattr(interaction_or_ctx, "message", None)
    if msg_obj and hasattr(msg_obj, "channel"):
        try:
            ctx_msg = await find_channel_context_message(msg_obj, query)
            if ctx_msg:
                user_display = getattr(user, 'display_name', '') or getattr(user, 'name', str(user))
                query = (
                    f"[REFERENCED CONTEXT MESSAGE]\n"
                    f"{ctx_msg['author']}: \"{ctx_msg['content']}\"\n\n"
                    f"[CURRENT USER QUERY]\n"
                    f"{user_display}: \"{query}\""
                )
        except Exception as ce:
            logging.warning(f"[find_channel_context_message] Error: {ce}")

    # 2. Enrich query with link metadata if links/videos are present
    query = await enrich_query_with_links(query)

    # Call LLM in thread with user ID, admin context, and owner status
    user_id = getattr(user, "id", 0)
    answer = await asyncio.to_thread(query_gemini, query, str(user), user_id, is_admin, author_is_owner, target_guild)
    answer = clean_thought_process(answer)
    if not answer:
        answer = "Haan bhai! Tillu hazir hai, bolo kya scene hai? 🚀"

    # 0. Check for START_INTENT (Start server via MCP Panel)
    if "START_INTENT:" in answer:
        match = re.search(r'START_INTENT:\s*([^\n\r]+)', answer)
        if match:
            clean_reply = answer.replace(match.group(0), "").strip()
            if clean_reply:
                try:
                    if hasattr(interaction_or_ctx, "channel") and not is_inter:
                        await interaction_or_ctx.channel.send(content=clean_reply)
                    else:
                        await reply_fn(content=clean_reply)
                except Exception:
                    pass
            await handle_start_request(interaction_or_ctx, user, guild=target_guild)
            return

    # 1. Check for ADMIN_INTENT (Console / Moderation commands for Admin/Owner)
    if "ADMIN_INTENT:" in answer:
        match = re.search(r'ADMIN_INTENT:\s*([^\n\r]+)', answer)
        if match:
            cmd = match.group(1).strip()
            # GUARD: Never send Discord management actions to Minecraft server console!
            if any(w in cmd.lower() for w in ["purge", "unassignrole", "role", "channel", "/discord", "clear", "delete message"]):
                logging.info(f"[AdminIntent Guard] Blocked misrouted Discord action from console: {cmd}")
                clean_reply = answer.replace(match.group(0), "").strip()
                if clean_reply:
                    await reply_fn(content=clean_reply)
                return

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

    # 3. Check for Bot Command Intent (Owner / Moderator controlling another bot)
    if "BOT_COMMAND:" in answer:
        match = re.search(r'BOT_COMMAND:\s*(.+)', answer)
        if match:
            bot_cmd = match.group(1).strip()
            clean_reply = re.sub(r'BOT_COMMAND:.*?\n?', '', answer).strip()
            if is_admin:
                if hasattr(interaction_or_ctx, "channel") and interaction_or_ctx.channel:
                    await interaction_or_ctx.channel.send(bot_cmd)
                if clean_reply:
                    await reply_fn(content=f"{clean_reply}\n*(Command dispatched: `{bot_cmd}`)*")
                else:
                    await reply_fn(content=f"🤖 **[Bot Command Sent]** `{bot_cmd}` channel me bhej diya!")
                return
            else:
                await reply_fn(content="🚫 Doosre bots ko command dene ki permission sirf Server Owner aur Moderators ke paas hai!")
                return

    # 4. Check for Memory Intent (Learning new facts)
    if "MEMORY_INTENT:" in answer:
        match = re.search(r'MEMORY_INTENT:\s*([^|\n]+)\s*\|\s*(.+)', answer)
        if match:
            extracted_topic = match.group(1).strip()
            extracted_fact = match.group(2).strip()
            clean_reply = re.sub(r'MEMORY_INTENT:.*?\n?', '', answer).strip()
            author_is_owner = is_owner(user, target_guild)
            if author_is_owner or is_privileged_user(user, target_guild):
                memory_mgr.add_or_update(
                    extracted_topic,
                    extracted_fact,
                    author=f"{user.name} (Owner)" if author_is_owner else f"{user.name} (Staff)"
                )
                conf_msg = f"🧠 **Haan Boss! Yaad rakh liya:**\n> *\"{extracted_fact}\"*\nYeh permanent memory diary me save ho gaya aur GitHub se sync ho chuka hai! 🚀"
                reply_text = f"{clean_reply}\n\n{conf_msg}" if clean_reply else conf_msg
                await reply_fn(content=reply_text)
                asyncio.create_task(announce_memory_update(target_guild, extracted_topic, extracted_fact, f"{user.name} (Owner)" if author_is_owner else f"{user.name} (Staff)"))
                return
            else:
                mem_ch = await get_or_create_memory_channel(target_guild)
                ch_name = f"<#{interaction_or_ctx.channel.id}>" if hasattr(interaction_or_ctx, "channel") and interaction_or_ctx.channel else "Direct/Slash"
                embed = discord.Embed(
                    title="📝 Memory Approval Request",
                    description=f"**Proposed by:** {user.mention} (`{user.name}`)\n**Channel:** {ch_name}\n\n**Fact to Remember:**\n> {extracted_fact}",
                    color=0xF39C12
                )
                embed.set_footer(text="Admin Review Required • Click Approve to save to GitHub")
                orig_ch_id = interaction_or_ctx.channel.id if hasattr(interaction_or_ctx, "channel") and interaction_or_ctx.channel else 0
                view = MemoryApprovalView(extracted_topic, extracted_fact, user.id, user.name, origin_channel_id=orig_ch_id)
                if mem_ch:
                    await mem_ch.send(embed=embed, view=view)
                pending_msg = f"📩 **Aapki request bhej di gayi hai!**\nAapki memory (*\"{extracted_fact}\"*) maine review ke liye bhej di hai. Unke approve karte hi main isse yaad rakh lunga! 😄"
                await reply_fn(content=pending_msg)
                return

    # 5. Final output logic:
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
            want_tts = bool(re.search(r'\b(tts|voice|awaaz|awaz|bol\s*ke|speak\s*out)\b', query, re.IGNORECASE))
            is_mod_or_above = author_is_owner or is_privileged_user(user, target_guild)
            allowed_m = discord.AllowedMentions(users=True, roles=True, everyone=False) if is_mod_or_above else discord.AllowedMentions.none()
            await interaction_or_ctx.channel.send(content=answer, tts=want_tts, allowed_mentions=allowed_m)
        else:
            await reply_fn(content=answer)

# ── SLASH COMMANDS ───────────────────────────────────────────────────────────
@bot.tree.command(name="pause", description="Pause Tillu so he stops responding to chat messages")
async def slash_pause(interaction: discord.Interaction):
    global TILLU_PAUSED
    TILLU_PAUSED = True
    await interaction.response.send_message("⏸️ **Tillu Paused!** Main chup ho gaya hu. Wapas bulane ke liye `/resume` ya `tillu resume` bol dena.")

@bot.tree.command(name="resume", description="Resume Tillu so he starts responding to chat again")
async def slash_resume(interaction: discord.Interaction):
    global TILLU_PAUSED
    TILLU_PAUSED = False
    await interaction.response.send_message("▶️ **Tillu Resumed!** Main wapas active hu, bolo kya scene hai! 🚀")

@bot.tree.command(name="tts", description="Make Tillu speak out loud using Discord TTS")
@app_commands.describe(message="The message Tillu should speak out loud")
async def slash_tts(interaction: discord.Interaction, message: str):
    await interaction.channel.send(f"🗣️ **{interaction.user.name}:** {message}", tts=True)
    await interaction.response.send_message("🔊 TTS message bol diya!", ephemeral=True)
@bot.tree.command(name="ask", description="Ask Tillu anything about the server, stream, or request whitelist!")
@app_commands.describe(
    query="What would you like to ask Tillu? (e.g. 'whitelist me GamerX' or 'how to join SMP')",
    attachment="Optional image screenshot or photo to show Tillu"
)
async def slash_ask(interaction: discord.Interaction, query: str, attachment: Optional[discord.Attachment] = None):
    if attachment:
        is_img = (attachment.content_type and attachment.content_type.startswith("image/")) or any(
            attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]
        )
        if is_img and attachment.size <= 8 * 1024 * 1024:
            try:
                img_bytes = await attachment.read()
                mime = attachment.content_type or "image/jpeg"
                desc = await asyncio.to_thread(analyze_image_bytes, img_bytes, mime)
                if desc:
                    query = f"[USER ATTACHED IMAGE: {desc}]\n{query}"
            except Exception as e:
                logging.error(f"[slash_ask Attachment] Error: {e}")
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
    await execute_unwhitelist_command(clean_p)
    reg = load_whitelist_registry()
    new_reg = {k: v for k, v in reg.items() if v.get("ign", "").lower() != clean_p.lower()}
    save_whitelist_registry(new_reg)
    await interaction.response.send_message(f"🗑️ **[Whitelist Removed]** `{clean_p}` removed from whitelist.\nDispatched to <#{CONSOLE_CHANNEL_ID}>.", ephemeral=True)

@bot.tree.command(name="remember", description="Teach Tillu a fact, rule, or server setting to remember permanently")
@app_commands.describe(fact="What should Tillu remember? (e.g. 'Server rules: No griefing' or 'End dimension opens on Sunday')")
async def slash_remember(interaction: discord.Interaction, fact: str):
    clean_fact = fact.strip()
    words = re.findall(r'\b[a-zA-Z0-9_-]+\b', clean_fact)
    topic = "_".join(words[:4]).lower() if words else "fact"
    user = interaction.user
    guild = interaction.guild
    author_is_owner = is_owner(user, guild)

    if author_is_owner or is_privileged_user(user, guild):
        memory_mgr.add_or_update(
            topic, clean_fact,
            author=f"{user.name} (Owner)" if author_is_owner else f"{user.name} (Staff)"
        )
        await interaction.response.send_message(
            f"🧠 **Yaad rakh liya!**\n> *\"{clean_fact}\"*\nYeh permanent memory diary me save ho gaya aur GitHub se sync ho chuka hai! 🚀",
            ephemeral=True
        )
        asyncio.create_task(announce_memory_update(guild, topic, clean_fact, f"{user.name} (Owner)" if author_is_owner else f"{user.name} (Staff)"))
    else:
        mem_ch = await get_or_create_memory_channel(guild)
        embed = discord.Embed(
            title="📝 Memory Approval Request",
            description=f"**Proposed by:** {user.mention} (`{user.name}`)\n**Channel:** Slash Command (`/remember`)\n\n**Fact to Remember:**\n> {clean_fact}",
            color=0xF39C12
        )
        embed.set_footer(text="Admin Review Required • Click Approve to save to GitHub")
        view = MemoryApprovalView(topic, clean_fact, user.id, user.name, origin_channel_id=interaction.channel_id or 0)
        if mem_ch:
            await mem_ch.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"📩 **Aapki memory request review ke liye bhej di gayi hai!**\nAapki request (*\"{clean_fact}\"*) review ke liye bhej di gayi hai. Unke approve karte hi Tillu isse yaad rakh lega! 😄",
            ephemeral=True
        )

@bot.tree.command(name="memories", description="View facts and rules that Tillu has learned")
async def slash_memories(interaction: discord.Interaction):
    all_mems = memory_mgr.get_all()
    if not all_mems:
        await interaction.response.send_message("🧠 Tillu ki memory diary abhi khaali hai! Use `/remember` to add something.", ephemeral=True)
        return
    embed = discord.Embed(
        title="🧠 Tillu Persistent Memory Diary",
        description=f"Total memories synced with GitHub: **{len(all_mems)}**",
        color=0x3498DB
    )
    for k, v in list(all_mems.items())[:20]:
        val_str = v.get("content", "")
        author_str = v.get("updated_by", "Unknown")
        embed.add_field(name=f"📌 {k}", value=f"{val_str}\n*(Added by: {author_str})*", inline=False)
    embed.set_footer(text="GitHub Auto-Sync Active • avinash893/aalu-server-bot")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="tag", description="Owner/Admin/Mod only: Have Tillu tag or ping a user or role with a message")
@app_commands.describe(target="The user or role mention to tag (e.g. @Gamer or @Admin)", message="Your message")
async def slash_tag(interaction: discord.Interaction, target: str, message: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await interaction.response.send_message("🚫 Sirf Server Owner, Admins aur Moderators hi mujhe kisi ko tag karne bol sakte hain!", ephemeral=True)
        return
    await interaction.channel.send(
        f"📢 {target.strip()} — {message.strip()}\n*(Tagged by {interaction.user.mention})*",
        allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False)
    )
    await interaction.response.send_message("✅ Tag message bhej diya!", ephemeral=True)

@bot.tree.command(name="botcmd", description="Owner/Admin/Mod only: Have Tillu send a command to control or trigger another bot")
@app_commands.describe(command="Exact bot command to run (e.g. '!tts hello' or '!play music')")
async def slash_botcmd(interaction: discord.Interaction, command: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await interaction.response.send_message("🚫 Sirf Server Owner aur Moderators hi mujhe doosre bots ko command dene bol sakte hain!", ephemeral=True)
        return
    await interaction.channel.send(command.strip())
    await interaction.response.send_message(f"🤖 Sent command `{command.strip()}` to <#{interaction.channel_id}>!", ephemeral=True)

@bot.tree.command(name="listbots", description="List all other bots currently active in this Discord server")
async def slash_listbots(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("🚫 Server me hi use ho sakta hai!", ephemeral=True)
        return
    bots = [m for m in guild.members if m.bot and m.id != (bot.user.id if bot.user else 0)]
    if not bots:
        await interaction.response.send_message("🤖 Is server me koi doosra bot nahi mila!", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"🤖 Bots in {guild.name}",
        description=f"Total other bots detected: **{len(bots)}**",
        color=0x3498DB
    )
    for b in bots:
        embed.add_field(name=f"🤖 {b.display_name}", value=f"Tag: {b.mention}\nID: `{b.id}`", inline=True)
    embed.set_footer(text="Owner & Moderators can ask Tillu to control these bots via chat or /botcmd")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="Show Tillu bot commands & features")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Tillu Bot Commands",
        description="I am Tillu, your server assistant! Here's how you can talk to me:",
        color=0x9B59B6
    )
    embed.add_field(name="💬 Talk Naturally", value="Just type `tillu <question>` or `@Tillu <question>` anywhere in chat!", inline=False)
    embed.add_field(name="🧠 Teach & Remember", value="`tillu yaad rakh <baat>` or `/remember <fact>` (Owner/Admins save directly; Members send review ticket)", inline=False)
    embed.add_field(name="📖 View Memories", value="`/memories` to see learned server knowledge", inline=False)
    embed.add_field(name="🎟️ Whitelist Me", value="Say `tillu whitelist me <IGN>` or `/whitelist <ign>`", inline=False)
    embed.add_field(name="🚀 Turn On Server", value="`/start`, `!start`, or the green button below", inline=False)
    embed.add_field(name="🔍 Check Status", value="`/status`, `!status`, or `!ip`", inline=False)
    embed.add_field(name="👑 Admin Commands", value="`!c <cmd>`, `!ban <player>`, `!unban <player>`, `!kick <player>`, `!unwhitelist <player>`", inline=False)
    embed.add_field(name="🎚️ Live Server Console", value=f"Owner, Admins & Mods can type Minecraft commands directly in <#{CONSOLE_CHANNEL_ID}> anytime without visiting the website panel!", inline=False)
    embed.add_field(name="⏱️ Cooldown", value="20s cooldown for members • **0s cooldown** for Owner, Admins & Mods", inline=False)
    embed.set_footer(text="Tillu • 24/7 Always-Online Active")
    await interaction.response.send_message(embed=embed, view=ServerControlView(), ephemeral=True)

# ── TEXT COMMANDS ────────────────────────────────────────────────────────────
@bot.command(name="pause")
async def cmd_pause(ctx):
    global TILLU_PAUSED
    TILLU_PAUSED = True
    await ctx.send("⏸️ **Tillu Paused!** Main chup ho gaya hu. Wapas bulane ke liye `!resume` ya `tillu resume` bol dena.")

@bot.command(name="resume", aliases=["unpause"])
async def cmd_resume(ctx):
    global TILLU_PAUSED
    TILLU_PAUSED = False
    await ctx.send("▶️ **Tillu Resumed!** Main wapas active hu, bolo kya scene hai! 🚀")

@bot.command(name="backup", aliases=["serverbackup"])
async def cmd_backup(ctx):
    if not ctx.guild:
        return await ctx.send("❌ Ye command sirf server ke andar use kar sakte hain!")
    if not (ctx.author.guild_permissions.administrator or ctx.guild.owner_id == ctx.author.id):
        return await ctx.send("🚫 Sirf Server Owner ya Administrators hi backup le sakte hain!")
    import backup_manager
    success, msg, _ = backup_manager.create_backup(ctx.guild)
    await ctx.send(msg)

@bot.command(name="restore", aliases=["serverrestore"])
async def cmd_restore(ctx, section: str = "server", *, target: str = ""):
    if not ctx.guild:
        return await ctx.send("❌ Ye command sirf server ke andar use kar sakte hain!")
    if not (ctx.author.guild_permissions.administrator or ctx.guild.owner_id == ctx.author.id):
        return await ctx.send("🚫 Sirf Server Owner ya Administrators hi restore kar sakte hain!")
    import backup_manager
    success, msg = await backup_manager.restore_section(ctx.guild, section, specific_target=target)
    await ctx.send(msg)

@bot.command(name="backups", aliases=["listbackups"])
async def cmd_backups(ctx):
    if not ctx.guild:
        return await ctx.send("❌ Ye command sirf server ke andar use kar sakte hain!")
    import backup_manager
    b_list = backup_manager.list_backups(ctx.guild.id)
    if not b_list:
        return await ctx.send("📂 Abhi tak koi backup snapshot create nahi hua hai. `!backup` se create karo!")
    await ctx.send(f"📂 **Available Backups:**\n" + "\n".join(f"• `{b}`" for b in b_list[:5]))

@bot.command(name="sync", aliases=["syncroles", "livesync"])
async def cmd_sync(ctx):
    if not ctx.guild:
        return await ctx.send("❌ Ye command sirf server ke andar use kar sakte hain!")
    if not (ctx.author.guild_permissions.administrator or ctx.guild.owner_id == ctx.author.id):
        return await ctx.send("🚫 Sirf Server Owner ya Administrators hi sync trigger kar sakte hain!")
    import sync_manager
    msg_wait = await ctx.send("🔄 **Minecraft Live Sync running...** Checking registered players...")
    reg = load_whitelist_registry()
    checked, assigned = await sync_manager.sync_guild_roles(ctx.guild, reg)
    await msg_wait.edit(content=f"✅ **Live Sync Complete!** `{checked}` registered players check hue, `{assigned}` naye Whitelisted roles assign kiye gaye!")

@bot.command(name="claim", aliases=["drop", "claimdrop", "freedrop"])
async def cmd_claim_drop(ctx):
    if not ctx.guild:
        return await ctx.send("❌ Ye command sirf server ke andar use kar sakte hain!")
    import rewards_manager
    success, reward, msg = rewards_manager.claim_drop(ctx.author.id)
    if not success:
        return await ctx.send(f"{ctx.author.mention} {msg}")

    pending = rewards_manager.get_pending_claims(ctx.author.id)
    embed = discord.Embed(
        title="🎁 Free Minecraft Chat Drop Claimed!",
        description=f"Congratulations {ctx.author.mention}! Reward tumhare **Tillu Vault** me store ho gaya hai!",
        color=reward.get("color", 0xF1C40F)
    )
    embed.add_field(name="📦 Reward Added", value=f"**{reward['emoji']} {reward['name']}**", inline=True)
    embed.add_field(name="✨ Rarity", value=f"`{reward['rarity']}`", inline=True)
    embed.add_field(name="🏦 Vault Balance", value=f"`{len(pending)}` item(s) pending", inline=True)
    embed.add_field(
        name="🚀 In-Game Deliver Karne Ka Tarika",
        value="Server me aao aur bolo:\n• `tillu send my claims to my account`\n• `tillu send my claims to <account_name>`\n• ya `!sendclaims [account_name]`",
        inline=False
    )
    embed.set_footer(text="Tillu • Minecraft MCP Cloud Rewards")
    await ctx.send(embed=embed)

@bot.command(name="sendclaims", aliases=["deliverclaims", "sendclaim"])
async def cmd_send_claims(ctx, *, target_account: str = ""):
    if not ctx.guild:
        return await ctx.send("❌ Ye command sirf server ke andar use kar sakte hain!")
    import rewards_manager
    reg = load_whitelist_registry()
    uid = str(ctx.author.id)
    entry = reg.get(uid, {})
    linked_ign = entry.get("ign")

    target_ign = target_account.strip()
    if not target_ign or target_ign.lower() in ["my account", "me", "self", "my"]:
        if not linked_ign:
            return await ctx.send(f"❌ {ctx.author.mention}, tumhara koi account linked nahi hai! Apna IGN do: `!sendclaims <account_name>` ya pehle `!whitelist <ign>` karo.")
        target_ign = linked_ign

    msg_wait = await ctx.send(f"⏳ Delivering vault claims to `{target_ign}` via Minecraft console...")
    success, items, msg = rewards_manager.send_claims_to_account(ctx.author.id, target_ign, panel_send_command)
    if not success:
        return await msg_wait.edit(content=f"{ctx.author.mention} {msg}")

    embed = discord.Embed(
        title="🚀 Claims Delivered In-Game!",
        description=f"All claims have been transferred to **`{target_ign}`** in Minecraft!",
        color=0x2ECC71
    )
    embed.set_thumbnail(url=f"https://mc-heads.net/avatar/{target_ign}/128")
    items_list = "\n".join(f"• {it['emoji']} **{it['name']}** (`{it['rarity']}`)" for it in items)
    embed.add_field(name="📦 Delivered Items", value=items_list or "Items delivered", inline=False)
    embed.set_footer(text="Tillu • Minecraft MCP Cloud Rewards")
    await msg_wait.delete()
    await ctx.send(embed=embed)

@bot.command(name="vault", aliases=["myclaims", "pendingclaims"])
async def cmd_vault(ctx):
    import rewards_manager
    pending = rewards_manager.get_pending_claims(ctx.author.id)
    if not pending:
        return await ctx.send(f"📭 {ctx.author.mention}, tumhare vault me koi pending items nahi hain! Chat karo aur `!claim` se naya drop lo.")
    items_list = "\n".join(f"• {it['emoji']} **{it['name']}** (`{it['rarity']}`)" for it in pending)
    embed = discord.Embed(
        title="🏦 Your Tillu Rewards Vault",
        description=f"{ctx.author.mention}, tumhare paas `{len(pending)}` pending items hain:\n\n{items_list}",
        color=0x9B59B6
    )
    embed.add_field(
        name="🚀 Deliver Kaise Kare?",
        value="Bolo: `tillu send my claims to my account` ya `tillu send my claims to <account_name>` (ya `!sendclaims`)",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="dropstatus", aliases=["claimstatus"])
async def cmd_drop_status(ctx):
    import rewards_manager
    can_claim, remaining, total = rewards_manager.get_drop_status(ctx.author.id)
    pending = rewards_manager.get_pending_claims(ctx.author.id)
    reg = load_whitelist_registry()
    ign = reg.get(str(ctx.author.id), {}).get("ign", "Not Linked")
    if can_claim:
        await ctx.send(f"🎉 {ctx.author.mention}, tumhara free drop ready hai! Claim karne ke liye `!claim` type karo! (Vault: `{len(pending)}` pending, Linked IGN: `{ign}`, Total Claims: `{total}`)")
    else:
        mins = remaining // 60
        secs = remaining % 60
        await ctx.send(f"⏳ {ctx.author.mention}, agla drop claim karne ke liye **{mins}m {secs}s** wait karo. (Vault: `{len(pending)}` pending, Linked IGN: `{ign}`, Total Claims: `{total}`)")

@bot.command(name="players", aliases=["online", "list", "listplayers", "whosonline", "onlineplayers"])
async def cmd_players(ctx):
    """Check live online Minecraft players and roles directly from server console."""
    await handle_players_command(ctx.channel, ctx.author)

@bot.command(name="tillu", aliases=["ask", "ai", "question"])
async def cmd_tillu(ctx, *, query: str = None):
    # Check for image attachments with !tillu
    if ctx.message.attachments:
        image_descs = []
        for att in ctx.message.attachments[:2]:
            is_img = (att.content_type and att.content_type.startswith("image/")) or any(
                att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]
            )
            if is_img and att.size <= 8 * 1024 * 1024:
                try:
                    img_bytes = await att.read()
                    mime = att.content_type or "image/jpeg"
                    desc = await asyncio.to_thread(analyze_image_bytes, img_bytes, mime)
                    if desc:
                        image_descs.append(desc)
                except Exception as e:
                    logging.error(f"[cmd_tillu Attachment] Error: {e}")
        if image_descs:
            img_ctx = "\n".join([f"- Image {i+1}: {d}" for i, d in enumerate(image_descs)]) if len(image_descs) > 1 else image_descs[0]
            query = f"[USER ATTACHED IMAGE: {img_ctx}]\n{query}" if query else f"[USER ATTACHED IMAGE: {img_ctx}]\n(User shared this image with you without additional text. React or explain what you see in Tillu's persona!)"

    if not query:
        await ctx.send("❌ Usage: `!tillu <your question, link, or image attachment>`")
        return
    await handle_ask_request(ctx, query, user=ctx.author, guild=ctx.guild)

@bot.command(name="botcmd", aliases=["botcommand", "runbot"])
async def cmd_botcmd(ctx, *, command: str = None):
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 Sirf Server Owner, Admins aur Moderators hi mujhe dusre bots ko command dene bol sakte hain!")
        return
    if not command:
        await ctx.send("❌ Usage: `!botcmd <command>` (e.g. `!botcmd !tts hello`)")
        return
    await ctx.send(command.strip())

@bot.command(name="listbots", aliases=["bots"])
async def cmd_listbots(ctx):
    bots = [m for m in ctx.guild.members if m.bot and m.id != (bot.user.id if bot.user else 0)]
    if not bots:
        await ctx.send("🤖 Is server me koi doosra bot nahi mila!")
        return
    bot_names = ", ".join(f"`{b.name}`" for b in bots)
    await ctx.send(f"🤖 **Detected Bots ({len(bots)}):** {bot_names}\n*(Owner/Mods can tell Tillu to run commands for them!)*")

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
    await execute_unwhitelist_command(clean_p)
    reg = load_whitelist_registry()
    new_reg = {k: v for k, v in reg.items() if v.get("ign", "").lower() != clean_p.lower()}
    save_whitelist_registry(new_reg)
    import sync_manager
    for uid_str, udata in reg.items():
        if udata.get("ign", "").lower() == clean_p.lower():
            try:
                mem = ctx.guild.get_member(int(uid_str))
                if mem:
                    asyncio.create_task(sync_manager.remove_single_member_sync(ctx.guild, mem))
            except Exception:
                pass
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

        url_match = re.search(r'https?://[^\s<>"]+', message.content)
        url_context = ""
        if url_match:
            clean_u = url_match.group(0).rstrip(".,!?:;)'\"")
            url_context = await asyncio.to_thread(fetch_url_context, clean_u)
        video_info = f"Video/Link Details: {url_context}" if url_context else f"Content: '{message.content[:200]}'"

        prompt = (
            f"A user posted this reel or video in our Discord chat ({video_info}). "
            f"You are Tillu, an Indian AI streamer companion. You just watched it after 5 minutes! "
            f"Write a funny, witty, short reaction (1-2 lines) in Hinglish/English reacting specifically to this video, title, or meme. "
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

def format_whitelisted_players_embed(content: str) -> Optional[discord.Embed]:
    """Parse raw console whitelist output and format arranged by alphabet first, then other characters."""
    if "no whitelisted player" in content.lower():
        embed = discord.Embed(
            title="📋 Whitelisted Players (0 Total)",
            description="Koi bhi player whitelist me nahi hai! (No whitelisted players found)",
            color=0xE74C3C,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Arranged Alphabetically (A–Z) followed by Symbols • Tillu Auto-Formatter")
        return embed

    match = re.search(r'whitelisted player\(s\):\s*([^\n\r]+)', content, re.IGNORECASE)
    if not match:
        return None

    raw_list = re.sub(r'[\r\n`]+', '', match.group(1)).strip()
    players = [p.strip() for p in raw_list.split(',') if p.strip()]
    if not players:
        return None

    # Deduplicate while preserving case
    unique_players = list(dict.fromkeys(players))

    # Arrange: Alphabetical (A-Z) first, then other characters/symbols (e.g. '.', '_', digits)
    alpha_players = sorted([p for p in unique_players if p and p[0].isalpha()], key=lambda x: x.lower())
    other_players = sorted([p for p in unique_players if p and not p[0].isalpha()], key=lambda x: x.lower())

    embed = discord.Embed(
        title=f"📋 Whitelisted Players ({len(unique_players)} Total)",
        color=0x2ECC71,
        timestamp=discord.utils.utcnow()
    )

    if alpha_players:
        chunk = ""
        alpha_fields = []
        for p in alpha_players:
            item = f"`{p}` "
            if len(chunk) + len(item) > 1000:
                alpha_fields.append(chunk)
                chunk = item
            else:
                chunk += item
        if chunk:
            alpha_fields.append(chunk)

        for idx, f_text in enumerate(alpha_fields):
            fname = f"🔤 Alphabetical (A–Z) [{len(alpha_players)}]" if idx == 0 else "🔤 Alphabetical (Cont.)"
            embed.add_field(name=fname, value=f_text, inline=False)

    if other_players:
        chunk = ""
        other_fields = []
        for p in other_players:
            item = f"`{p}` "
            if len(chunk) + len(item) > 1000:
                other_fields.append(chunk)
                chunk = item
            else:
                chunk += item
        if chunk:
            other_fields.append(chunk)

        for idx, f_text in enumerate(other_fields):
            fname = f"📱 Bedrock / Other Characters [{len(other_players)}]" if idx == 0 else "📱 Bedrock / Other Characters (Cont.)"
            embed.add_field(name=fname, value=f_text, inline=False)

    embed.set_footer(text="Arranged Alphabetically (A–Z) followed by Symbols • Tillu Auto-Formatter")
    return embed

def strip_console_prefix(line: str) -> str:
    """Strips timestamps, thread prefixes like [Server thread/INFO]: from console output."""
    return re.sub(r'^(?:\[[^\]]+\]\s*)+:?\s*', '', line).strip()

def format_online_players_embed(content: str) -> Optional[discord.Embed]:
    """Parse raw console '/list' output and format into a rich embed."""
    clean = content.strip()
    count_m = re.search(r'There are (\d+)(?:\s+(?:out\s+of\s+maximum|of\s+a\s+max\s+of)\s+(\d+))?\s+players\s+online', clean, re.IGNORECASE)
    online_count = int(count_m.group(1)) if count_m else 0
    max_count = int(count_m.group(2)) if (count_m and count_m.group(2)) else 50

    embed = discord.Embed(
        title=f"🎮 Live Minecraft Players ({online_count}/{max_count})",
        color=0x2ECC71 if online_count > 0 else 0x95A5A6,
        timestamp=discord.utils.utcnow()
    )

    if online_count == 0:
        embed.description = "Abhi server pe koi player online nahi hai! (No players currently online)\nJoin karke pehle player bano! 🚀"
        embed.add_field(name="☕ Server IP", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
        embed.set_footer(text="Tillu • Live Console Telemetry")
        return embed

    # Parse groups and player names
    player_groups = {}
    lines = [strip_console_prefix(l) for l in clean.splitlines() if strip_console_prefix(l)]

    for l in lines:
        if ':' in l and 'players online' not in l.lower():
            parts = l.split(':', 1)
            group_name = parts[0].strip().title()
            p_names = [p.strip() for p in parts[1].split(',') if p.strip()]
            if p_names:
                player_groups[group_name] = p_names

    if not player_groups:
        for l in lines:
            if 'players online' in l.lower() and ':' in l:
                after_colon = l.split(':', 1)[-1].strip()
                p_names = [p.strip() for p in after_colon.split(',') if p.strip()]
                if p_names and p_names != [l]:
                    player_groups["Online Players"] = p_names
                    break

    if player_groups:
        for grp, members in player_groups.items():
            formatted_list = " • ".join(f"`{m}`" for m in members)
            embed.add_field(name=f"👑 {grp} [{len(members)}]", value=formatted_list, inline=False)
    else:
        embed.description = f"**{online_count}** player(s) abhi server pe khel rahe hain!"

    embed.add_field(name="☕ Server IP", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
    embed.set_footer(text="Tillu • Live Console Telemetry")
    return embed

async def handle_players_command(channel, user=None):
    """Sends '/list' to console, captures output, and displays live player count and names in chat."""
    status_msg = await channel.send("🔍 **Fetching live players from Minecraft console...**")

    # Send 'list' command to console
    await execute_server_command("list")

    # Wait for response in console channel or fallback to server ping
    try:
        def check(m):
            return m.channel.id == CONSOLE_CHANNEL_ID and "players online" in (m.content or "").lower()
        resp_msg = await bot.wait_for("message", check=check, timeout=5.0)
        full_content = resp_msg.content or ""

        # If online_count > 0 and no group lines were present in this single message, check if following lines arrive
        count_m = re.search(r'There are (\d+)', full_content, re.IGNORECASE)
        online_cnt = int(count_m.group(1)) if count_m else 0
        if online_cnt > 0 and ":" not in full_content.splitlines()[-1]:
            try:
                next_msg = await bot.wait_for(
                    "message",
                    check=lambda m: m.channel.id == CONSOLE_CHANNEL_ID and m.id != resp_msg.id,
                    timeout=1.5
                )
                if next_msg and next_msg.content:
                    full_content += "\n" + next_msg.content
            except asyncio.TimeoutError:
                pass

        embed = format_online_players_embed(full_content)
        if embed:
            await status_msg.edit(content=None, embed=embed)
            return
    except asyncio.TimeoutError:
        pass

    # Fallback to direct SLP Ping if console didn't respond in time
    is_up, desc, online, max_p, ver = await asyncio.to_thread(ping_minecraft_server)
    embed = discord.Embed(
        title=f"🎮 Live Minecraft Players ({online}/{max_p})",
        description=f"Status: **{desc}**\nVersion: `{ver}`",
        color=0x2ECC71 if is_up and online > 0 else (0xF1C40F if is_up else 0xE74C3C),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="☕ Server IP", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
    embed.set_footer(text="Tillu • Live Server Telemetry")
    await status_msg.edit(content=None, embed=embed)

@bot.event
async def on_message(message: discord.Message):
    # ── CONSOLE CHANNEL: Intercept & Format 'whitelist list' output ───────────
    raw_text = message.content or ""
    if not raw_text and message.embeds:
        raw_text = " ".join([e.description or "" for e in message.embeds if e.description])

    if "whitelisted player" in raw_text.lower():
        if message.channel.id == CONSOLE_CHANNEL_ID or (bot.user and message.author.id == bot.user.id):
            embed = format_whitelisted_players_embed(raw_text)
            if embed:
                try:
                    await message.delete()
                except Exception as de:
                    logging.warning(f"[Whitelist Formatter] Could not delete raw message: {de}")
                try:
                    await message.channel.send(embed=embed)
                except Exception as se:
                    logging.error(f"[Whitelist Formatter] Error sending embed: {se}")
                return

    # Only ignore Tillu himself to prevent self-looping (allow access/interaction with other bots)

    if bot.user and message.author.id == bot.user.id:
        return

    # Record chat activity for Minecraft Chat Drops
    if not message.author.bot:
        try:
            import rewards_manager
            rewards_manager.record_chat_activity(message.author.id)
        except Exception:
            pass


    # ── AUTONOMOUS RULE ENGINE: Evaluate message against active rules ────────
    try:
        if await rule_mgr.evaluate_message(message, execute_server_command):
            return
    except Exception as re_err:
        logging.warning(f"[RuleManager Evaluation Error] {re_err}")

    # ── PRIVATE UPGRADE CHANNEL: #update-tillu (Restricted to Owner/Admin/Mods) ─
    is_update_ch = False
    if UPDATE_CHANNEL_ID and message.channel.id == UPDATE_CHANNEL_ID:
        is_update_ch = True
    elif getattr(message.channel, "name", "").lower() in ["update-tillu", "update_tillu", "tillu-updates"]:
        is_update_ch = True

    if is_update_ch:
        if not is_privileged_user(message.author, message.guild):
            try:
                await message.delete()
            except Exception:
                pass
            return

        cmd_text = message.content.strip()
        lower_cmd = cmd_text.lower()

        # Command: List active rules
        if lower_cmd in ["tillu rules", "!rules", "rules", "list rules", "show rules"]:
            rules = rule_mgr.list_rules()
            if not rules:
                await message.channel.send("📋 **Koi bhi autonomous rule active nahi hai.** Yahan naya rule likh kar batao, main turant sikh lunga! 🚀")
                return
            embed = discord.Embed(
                title=f"📋 Active Autonomous Rules ({len(rules)} Total)",
                color=0x3498DB,
                timestamp=discord.utils.utcnow()
            )
            for r in rules:
                r_id = r.get("id", "Unknown")
                r_title = r.get("title", "Rule")
                r_type = r.get("type", "General")
                r_author = r.get("author", "Staff")
                cond = json.dumps(r.get("condition", {}), ensure_ascii=False)
                act = json.dumps(r.get("action", {}), ensure_ascii=False)
                val = f"**Type:** `{r_type}` | **By:** `{r_author}`\n**Condition:** `{cond}`\n**Action:** `{act}`"
                embed.add_field(name=f"🔹 `{r_id}`: {r_title}", value=val[:1024], inline=False)
            embed.set_footer(text="To remove a rule: tillu delete rule <rule_id>")
            await message.channel.send(embed=embed)
            return

        # Command: Delete a rule
        del_match = re.match(r'^(?:tillu\s+)?(?:delete|remove)\s+rule\s+([a-zA-Z0-9_\-]+)', lower_cmd) or re.match(r'^!delrule\s+([a-zA-Z0-9_\-]+)', lower_cmd)
        if del_match:
            rid = del_match.group(1).strip()
            success = rule_mgr.delete_rule(rid)
            if success:
                embed = discord.Embed(
                    title="🗑️ Autonomous Rule Removed",
                    description=f"Rule `{rid}` has been deleted from active memory and committed to GitHub repository.",
                    color=0xE74C3C
                )
                embed.set_footer(text="GitHub Cloud Sync • avinash893/aalu-server-bot")
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(f"❌ Rule `{rid}` nahi mila! Active rules dekhne ke liye `tillu rules` type karo.")
            return

        # Natural language input in #update-tillu:
        async with message.channel.typing():
            res = await asyncio.to_thread(process_update_channel_input, cmd_text)

        intent = res.get("intent", "chat")
        if intent == "chat":
            reply_text = res.get("reply", "Haan Boss! Tillu Groq AI engine online aur ready hai.")
            await message.reply(reply_text)
            return

        elif intent == "rule":
            rule_id, rule_obj = rule_mgr.add_rule(res, author=message.author.name)
            embed = discord.Embed(
                title="🚀 Tillu Upgraded & Synced to GitHub!",
                description=f"**New Skill / Rule Learned:**\n> **{rule_obj.get('title', 'Autonomous Rule')}**",
                color=0x2ECC71,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="🆔 Rule ID", value=f"`{rule_id}`", inline=True)
            embed.add_field(name="🏷️ Type", value=f"`{rule_obj.get('type')}`", inline=True)
            embed.add_field(name="👤 Added By", value=f"{message.author.mention}", inline=True)
            embed.add_field(name="🎯 Condition", value=f"```{json.dumps(rule_obj.get('condition', {}), indent=2)}```", inline=False)
            embed.add_field(name="⚡ Action", value=f"```{json.dumps(rule_obj.get('action', {}), indent=2)}```", inline=False)
            embed.set_footer(text="Autonomous Hot-Reload Active • Synced to GitHub (avinash893/aalu-server-bot)")
            await message.channel.send(embed=embed)
            return

        elif intent == "prompt_update":
            instruction = res.get("instruction", cmd_text)
            tone = res.get("tone")
            if tone:
                prompt_mgr.set_tone(tone, author=message.author.name)
            if instruction:
                prompt_mgr.add_instruction(instruction, author=message.author.name)

            embed = discord.Embed(
                title="🧠 Tillu Personality & System Prompt Updated!",
                description=f"**New Living Instruction Learned:**\n> *\"{instruction}\"*",
                color=0x9B59B6,
                timestamp=discord.utils.utcnow()
            )
            if tone:
                embed.add_field(name="🎭 New Tone", value=f"`{tone}`", inline=False)
            embed.add_field(name="👤 Updated By", value=message.author.mention, inline=True)
            embed.set_footer(text="Live Hot-Reload Active • Synced to GitHub (avinash893/aalu-server-bot)")
            await message.channel.send(embed=embed)
            return
        return

    # ── AUTONOMOUS DISCORD MANAGEMENT ACTIONS (Roles, Channels, Message Deletions, Timeouts) ──
    if is_privileged_user(message.author, message.guild):
        # Strip "tillu" prefix so regex patterns match cleanly
        action_text = re.sub(r'^(?:hey\s+)?(?:tillu|mr\.?\s*tillu)[,\s]*', '', message.content, flags=re.IGNORECASE).strip()
        # Also normalize "named:-" / "named :-" / "named:" to "named "
        action_text = re.sub(r'\bnamed?\s*[:\-]+\s*', 'named ', action_text, flags=re.IGNORECASE)
        action_text = re.sub(r'\bcalled?\s*[:\-]+\s*', 'called ', action_text, flags=re.IGNORECASE)
        handled, resp = await parse_and_execute_discord_action(message, message.author, message.guild, action_text)
        if handled:
            if resp:
                await message.channel.send(resp)
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
    has_image = any(
        (att.content_type and att.content_type.startswith("image/"))
        or any(att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"])
        for att in message.attachments
    )

    if not content and not has_image:
        return

    global OWNER_ONLY_MODE, TILLU_PAUSED
    author = message.author
    author_is_owner = is_owner(author, message.guild)
    content_lower = content.lower().strip()

    # ── TILLU PAUSE & RESUME COMMANDS ──────────────────────────────────────────
    if re.search(r'^(?:hey\s+|arre\s+)?(?:tillu|mr\s*tillu)?\s*(?:pause|roko|ruk\s*ja|stop\s*responding|chup\s*ho\s*ja)$', content_lower) or content_lower in ["!pause", "tillu pause"]:
        TILLU_PAUSED = True
        await message.channel.send("⏸️ **Tillu Paused!** Main chup ho gaya hu. Wapas bulane ke liye `tillu resume` ya `tillu start` bol dena.")
        return

    if re.search(r'^(?:hey\s+|arre\s+)?(?:tillu|mr\s*tillu)?\s*(?:resume|unpause|start|bolna\s*shuru|wapas\s*aa\s*ja)$', content_lower) or content_lower in ["!resume", "!unpause", "tillu resume", "tillu unpause"]:
        TILLU_PAUSED = False
        await message.channel.send("▶️ **Tillu Resumed!** Main wapas active hu, bolo kya scene hai! 🚀")
        return

    # If Tillu is paused, ignore all messages
    if TILLU_PAUSED:
        return

    # ── OWNER COMMANDS (STOP / RESUME SILENT MODE) ─────────────────────────────
    if author_is_owner and re.search(r'^(?:hey\s+|arre\s+)?(?:tillu|mr\s*tillu)?\s*(?:stop|quiet|chup|shant|mute|chup\s*raho|bolna\s*band|shut\s*up|so\s*ja)$', content, re.IGNORECASE):
        OWNER_ONLY_MODE = True
        await message.channel.send("🤫 **Yes Boss (Avinash)!** Muh pe taala laga liya. Ab se main **sirf aapki sununga**, baaki sab ignore mode me hain.")
        return

    if author_is_owner and re.search(r'^(?:hey\s+|arre\s+)?(?:tillu|mr\s*tillu)?\s*(?:start|unmute|resume|bolna\s*shuru\s*kar|chalu\s*ho\s*ja|ab\s*sabse\s*bol|aawaz\s*nikal|unstop)$', content, re.IGNORECASE):
        OWNER_ONLY_MODE = False
        await message.channel.send("🚀 **Boss ka green signal aa gaya!** Tillu is back in action for everyone! Sab log sawaal pucho.")
        return

    # When OWNER_ONLY_MODE is active, ignore anyone who is NOT the Owner!
    if OWNER_ONLY_MODE and not author_is_owner:
        return

    match_tillu = bool(re.search(r'\b(tillu|mr\s*tillu)\b', content, re.IGNORECASE))

    # Whitelist channel dedicated check
    is_whitelist_channel = (
        message.channel.id == WHITELIST_CHANNEL_ID
        or "whitelist" in getattr(message.channel, "name", "").lower()
    )

    # Check if message is addressed to Tillu:
    # 1. Mentioned (@Tillu)
    # 2. Reply to Tillu
    # 3. Explicitly named "tillu" or "mr tillu"
    is_addressed_to_tillu = is_mentioned or is_reply_to_bot or match_tillu

    # If in whitelist channel and someone typed pure IGN:
    if is_whitelist_channel:
        clean_word = content.strip().replace('"', '').replace("'", "").replace("`", "")
        if (
            re.match(r'^[a-zA-Z0-9_.*]{3,20}$', clean_word)
            and not any(w in clean_word.lower() for w in ["hi", "hey", "hello", "tillu", "help", "kya", "kaise", "what", "bro", "bhai", "join"])
        ):
            try:
                await handle_whitelist_request(message, clean_word, user=message.author, guild=message.guild, bypass_cooldown=True)
                return
            except Exception as e:
                logging.error(f"[Whitelist Channel IGN] Error: {e}")

    # STRICT TRIGGER: If NOT addressed to Tillu, IGNORE COMPLETELY!
    if not is_addressed_to_tillu:
        return

    # If an image was attached and Tillu is addressed, analyze with Pollinations Vision
    if has_image:
        image_descs = []
        for att in message.attachments[:2]:
            is_img = (att.content_type and att.content_type.startswith("image/")) or any(
                att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]
            )
            if is_img and att.size <= 8 * 1024 * 1024:
                try:
                    img_bytes = await att.read()
                    mime = att.content_type or ("image/png" if att.filename.lower().endswith(".png") else "image/jpeg")
                    desc = await asyncio.to_thread(analyze_image_bytes, img_bytes, mime)
                    if desc:
                        image_descs.append(desc)
                except Exception as e:
                    logging.error(f"[on_message Attachment] Error reading image: {e}")
        if image_descs:
            img_ctx = "\n".join([f"- Image {i+1}: {d}" for i, d in enumerate(image_descs)]) if len(image_descs) > 1 else image_descs[0]
            if content:
                content = f"[USER ATTACHED IMAGE: {img_ctx}]\n{content}"
            else:
                content = f"[USER ATTACHED IMAGE: {img_ctx}]\n(User shared this image with you without additional text. React and explain what you see in Tillu's persona!)"

    # ── CHECK DIRECT MEMORY COMMAND ("tillu yaad rakh <baat>", "remember <fact>") ──
    is_mem, mem_topic, mem_fact = extract_memory_request(content)
    if is_mem:
        if author_is_owner or is_privileged_user(author, message.guild):
            clean_top, clean_cont, over = memory_mgr.add_or_update(
                mem_topic, mem_fact, author=f"{author.name} (Owner)" if author_is_owner else f"{author.name} (Staff)"
            )
            await message.channel.send(f"🧠 **Haan Boss! Yaad rakh liya:**\n> *\"{mem_fact}\"*\nYeh permanent memory diary me save ho gaya aur GitHub se sync ho chuka hai! 🚀")
            asyncio.create_task(announce_memory_update(message.guild, clean_top, mem_fact, f"{author.name} (Owner)" if author_is_owner else f"{author.name} (Staff)"))
            return
        else:
            mem_ch = await get_or_create_memory_channel(message.guild)
            embed = discord.Embed(
                title="📝 Memory Approval Request",
                description=f"**Proposed by:** {author.mention} (`{author.name}`)\n**Channel:** {message.channel.mention}\n\n**Fact to Remember:**\n> {mem_fact}",
                color=0xF39C12
            )
            embed.set_footer(text="Admin Review Required • Click Approve to save to GitHub")
            view = MemoryApprovalView(mem_topic, mem_fact, author.id, author.name, origin_channel_id=message.channel.id)
            if mem_ch:
                await mem_ch.send(embed=embed, view=view)
            await message.channel.send(f"📩 **Aapki request bhej di gayi hai!**\nAapki memory (*\"{mem_fact}\"*) maine review ke liye bhej di hai. Unke approve karte hi main isse yaad rakh lunga! 😄")
            return

    # Clean query text
    query = content
    if bot.user:
        query = re.sub(rf'<@!?{bot.user.id}>', '', query).strip()
    query = re.sub(r'^(hey\s+|yo\s+|hello\s+|hi\s+|arre\s+)?(mr\s*tillu|tillu)[\s,:]*', '', query, flags=re.IGNORECASE).strip()
    if not query:
        query = content

    # ── LIVE MINECRAFT PLAYERS CHECK (Natural language intent) ─────────────────
    clean_q = query.lower().strip()
    if re.search(r'\b(?:players?|who\s+is\s+(?:playing|online)|kaun\s+(?:khel\s+raha\s+hai|online\s+hai|khel\s+rahe\s+hain|khel\s+raha)|kitne\s+(?:players?|log)\s+(?:khel\s+rahe|online)\s+hai|list\s+players?)\b', clean_q) or clean_q in ["players", "online", "list", "who is playing", "kaun khel raha hai"]:
        await handle_players_command(message.channel, message.author)
        return

    try:
        async with message.channel.typing():
            await handle_ask_request(message, query, user=message.author, guild=message.guild, bypass_cooldown=True)
    except Exception as e:
        logging.error(f"[on_message] Error handling query for Tillu: {e}")

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

# ── SCHEDULED BACKGROUND LOOPS (Automated 24h Backup & Live Sync) ───────────
@tasks.loop(hours=24)
async def scheduled_backup_loop():
    import backup_manager
    for g in bot.guilds:
        try:
            s, m, _ = backup_manager.create_backup(g)
            d = backup_manager.cleanup_old_backups(g.id, max_keep=7, max_age_days=7)
            logging.info(f"[AutoBackup] {g.name}: {m} (Cleaned {d} old snapshots)")
        except Exception as ex:
            logging.error(f"[AutoBackup] Error on {g.name}: {ex}")

@tasks.loop(hours=6)
async def scheduled_sync_loop():
    import sync_manager
    reg = load_whitelist_registry()
    for g in bot.guilds:
        try:
            c, a = await sync_manager.sync_guild_roles(g, reg)
            logging.info(f"[AutoLiveSync] {g.name}: checked {c}, assigned {a} roles")
        except Exception as ex:
            logging.error(f"[AutoLiveSync] Error on {g.name}: {ex}")

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
        # Discover other bots in server
        other_bots = [m for m in guild.members if m.bot and m.id != bot.user.id]
        if other_bots:
            logging.info(f"[Server Bots] Detected {len(other_bots)} other bots in '{guild.name}': {[b.name for b in other_bots]}")
        # Ensure dedicated memory and update channels exist
        try:
            await get_or_create_memory_channel(guild)
        except Exception as me:
            logging.warning(f"[Memory Channel Init] {me}")
        try:
            await get_or_create_update_channel(guild)
        except Exception as ue:
            logging.warning(f"[Update Channel Init] {ue}")

    asyncio.create_task(guardian_loop())
    asyncio.create_task(render_keepalive_loop())

    try:
        if not scheduled_backup_loop.is_running():
            scheduled_backup_loop.start()
    except Exception as be:
        logging.warning(f"[ScheduledBackup Init] {be}")

    try:
        if not scheduled_sync_loop.is_running():
            scheduled_sync_loop.start()
    except Exception as se:
        logging.warning(f"[ScheduledSync Init] {se}")


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

