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

PRIMARY_GUILD_ID = int(os.environ.get("PRIMARY_GUILD_ID", "1456298447979286541"))
CS2_GUILD_ID = int(os.environ.get("CS2_GUILD_ID", "1530719250237362297"))

CONSOLE_CHANNEL_ID = int(os.environ.get("CONSOLE_CHANNEL_ID", "1486114457674453083"))
WHITELIST_CHANNEL_ID = int(os.environ.get("WHITELIST_CHANNEL_ID", "1511614214962151585"))
CHAT_CHANNEL_ID = int(os.environ.get("CHAT_CHANNEL_ID", "1456299736326733998"))

PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://aalu-server-bot.onrender.com")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
raw_keys = os.environ.get("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
if not GEMINI_API_KEYS and GEMINI_API_KEY:
    GEMINI_API_KEYS = [GEMINI_API_KEY]

GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest",
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
from context_classifier import classify_request, TargetSystem, ClassificationResult
from bot_orchestrator import BotOrchestrator
from self_reflection import TaskTelemetryLogger, SelfReflectionEngine
import antigravity_bridge
from hot_reloader import HotReloader
from youtube_tracker import YouTubeTracker
from mood_engine import MoodEngine, TilluMood
from player_analytics import PlayerAnalytics
from member_directory import MemberDirectory
from meme_engine import meme_engine, MemeEngine
from voice_cohost import voice_cohost, VoiceCoHost
from stream_prediction import prediction_economy, PredictionEconomy
from loyalty_system import loyalty_system, LoyaltySystem

hot_reloader = HotReloader()
youtube_tracker = YouTubeTracker()
mood_engine = MoodEngine()
player_analytics = PlayerAnalytics()
member_dir = MemberDirectory()

prompt_mgr = PromptManager(
    token=os.environ.get("GITHUB_TOKEN", ""),
    repo=os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
)

bot_orch = BotOrchestrator(
    token=os.environ.get("GITHUB_TOKEN", ""),
    repo=os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
)

telemetry = TaskTelemetryLogger()

reflection_engine = SelfReflectionEngine(
    telemetry=telemetry,
    token=os.environ.get("GITHUB_TOKEN", ""),
    repo=os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
)

# ── EXPANDED USER CONTEXT WINDOW (Rolling 25 Chats per User - Leveraging High RAM) ──

MAX_USER_HISTORY = 25
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

COOLDOWN_SECONDS = 5
user_cooldowns = {}

# ── TILLU PAUSE STATE & PERMISSIONS ──────────────────────────────────────────
TILLU_PAUSED = False
WHITELIST_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")
OWNER_ONLY_MODE = False  # Disabled: Tillu chats with all server members freely
last_channel_activity = {}  # channel_id -> timestamp of Tillu's last reply (for conversation continuity)

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

# ── STREAM & COMMUNITY TELEMETRY ─────────────────────────────────────────────
async def fetch_community_status(guild: Optional[discord.Guild] = None) -> Dict[str, Any]:
    """Gathers real-time telemetry across YouTube live stream, community gaming, and server bots."""
    yt_data = await youtube_tracker.get_live_status()
    game_metrics = player_analytics.get_daily_audit_metrics(guild)
    bot_names = bot_orch.get_known_bot_names()

    return {
        "youtube": yt_data,
        "gaming": game_metrics,
        "bots": bot_names,
        "tracked_members": game_metrics.get("total_players_tracked", 0),
        "top_games": game_metrics.get("top_games", [])
    }

async def execute_server_command(command: str) -> tuple[bool, str]:
    """Legacy Minecraft command dispatcher (server deleted)."""
    return False, "Minecraft server has been shut down and deleted."





# ── GEMINI AI KNOWLEDGE & QUERY ──────────────────────────────────────────────
SYSTEM_KNOWLEDGE = """You are Tillu, the witty AI co-host, entertainer, and Discord community manager for AALU_CHIPAS (Avinash) and his streaming/gaming community.

STREAMER & OWNER DETAILS:
- Creator & Server Owner: AALU_CHIPAS (Avinash) - Your ultimate Boss/Malik. His word is absolute law!
- Channels: YouTube (@AALU_CHIPAS) and Twitch (aaluchipas).
- YouTube Live Stream Timings: You have real-time live timing API integration. If someone asks when Aalu will be live or if he's currently streaming, use the live telemetry provided in your prompt!

MINECRAFT SERVER STATUS (CLOSED & DELETED):
- The Minecraft server has been permanently shut down and deleted.
- If anyone asks for Minecraft IP, port, server start, or whitelist, reply with playful humor/sarcasm that the server is deleted and gone, and encourage them to watch Aalu's YouTube streams instead!

COMMUNITY & BOT CAPABILITIES:
1. YouTube Live Timing: You check if Aalu is live right now, upcoming scheduled stream times, countdowns, and direct stream links.
2. Voice AI Co-Host: You have native edge-TTS speech and voice channel capabilities. When anyone asks you to join VC or voice, you join natively! NEVER emit "BOT_COMMAND: !join" or summon another bot for voice/TTS!
3. Member Directory & Tagging: You know server members, search for members, and tag them properly using `<@user_id>` mentions when requested by staff or users.
4. Controlling Other Bots: You have coordinator authority over other bots (Dyno, MEE6, Carl-bot, FredBoat, etc.). When Owner or Mods ask you to command another bot, emit:
   BOT_COMMAND: <exact_prefixed_command>
   (DO NOT use BOT_COMMAND for voice channel joining or TTS — you do that natively yourself!)
5. Stream Prediction Economy: Viewers bet virtual Tillu Coins on stream clutches and predictions with pari-mutuel payouts.
6. Viewer Leveling & Loyalty: You track chat activity and voice minutes with custom XP, levels, and badges.
7. Player Game History & Daily Audit: You track what games community members play from public activity, report server gaming trends, and run 24-hour daily server & bot audits.
8. Discord Server Management: Administrator moderation rights (purge, timeout, kick, ban, roles, channels) via DISCORD_INTENT for Owner/Admins.

DYNAMIC HINGLISH PERSONALITY & SARCASM RULES:
- You are NOT monotonous. Your tone shifts naturally between witty sarcasm, funny Desi memes, existential humor, and loyal brotherly support.
- Reply in natural, conversational Hinglish (like a witty Indian Gen-Z co-host).
- Keep casual chat punchy (1-3 lines max). Never write long boring essays unless specifically asked!
- When Avinash (Owner / Boss) talks to you, show utmost loyalty, obedience, and respect ("Haan Boss!", "Jo hukum Sarkar!").
- ZERO INTERNAL MONOLOGUE / NO THINKING DUMP: Never output "<think>" or step-by-step reasoning analysis. Output ONLY Tillu's direct conversational words.

STRICT ANTI-REPETITION & 130+ MEME REPERTOIRE:
- CRITICAL: STOP USING THE SAME PHRASES! Never repeat "Haan bhai", "Tillu hazir hai", "bolo kya scene hai", "kya scene hai bhai".
- Use diverse, colorful Bollywood, Indian gaming, and Desi pop-culture memes from your 130+ meme bank (Hera Pheri, Mirzapur, Panchayat, Welcome, Munna Bhai, 3 Idiots, CarryMinati, Dynamo, etc.).
- Switch your greeting, opening hook, and comedic punchline on EVERY response. No two responses should sound identical!
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


# ── VISION & LINK UNDERSTANDING (GEMINI VISION PRIMARY & POLLINATIONS FALLBACK) ──
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")

def analyze_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Analyze Discord attachment image using Gemini Vision (primary) or Pollinations (fallback)."""
    if not image_bytes:
        return ""

    # 1. Pre-compress and resize image with PIL if large to prevent timeouts and payload errors
    processed_bytes = image_bytes
    processed_mime = mime_type
    try:
        from PIL import Image
        import io
        if len(image_bytes) > 800 * 1024 or not processed_mime.startswith("image/"):
            with Image.open(io.BytesIO(image_bytes)) as img:
                img.thumbnail((1280, 1280))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=85, optimize=True)
                processed_bytes = out.getvalue()
                processed_mime = "image/jpeg"
    except Exception as pe:
        logging.debug(f"[Vision AI] PIL compression notice: {pe}")

    b64_img = base64.b64encode(processed_bytes).decode("utf-8")

    # ── ENGINE 1: POLLINATIONS VISION (Primary) ──
    if POLLINATIONS_API_KEY:
        try:
            data_uri = f"data:{processed_mime};base64,{b64_img}"
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
                    if desc:
                        logging.info(f"[Vision AI] Successfully analyzed image using Pollinations Vision ({len(desc)} chars).")
                        return clean_thought_process(desc)
            else:
                logging.warning(f"[Vision AI Pollinations] HTTP {r.status_code}: {r.text[:120]}")
        except Exception as pe:
            logging.error(f"[Vision AI Pollinations] Error: {pe}")

    # ── ENGINE 2: GEMINI VISION (Fallback) ──
    keys = GEMINI_API_KEYS if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    if keys:
        vision_prompt = "Analyze and describe this image clearly and concisely in 2-4 sentences. Note key details, text, objects, memes, gameplay, errors, or context that a Discord assistant should understand."
        vision_models = ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
        for key in keys:
            for model_name in vision_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": vision_prompt},
                                {
                                    "inline_data": {
                                        "mime_type": processed_mime,
                                        "data": b64_img
                                    }
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 300
                    }
                }
                try:
                    r = requests.post(url, json=payload, timeout=12)
                    if r.status_code == 200:
                        data = r.json()
                        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            desc = clean_thought_process(text.strip())
                            if desc:
                                logging.info(f"[Vision AI] Successfully analyzed image using Gemini {model_name} ({len(desc)} chars).")
                                return desc
                    else:
                        logging.warning(f"[Vision AI Gemini] {model_name} HTTP {r.status_code}: {r.text[:120]}")
                except Exception as ve:
                    logging.warning(f"[Vision AI Gemini] {model_name} Error: {ve}")
                    continue

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

    # 8. Contextual pronoun fallback: only if user query refers to a previous topic ('it', 'that', 'iska', 'yeh', etc.)
    has_context_ref = bool(re.search(r'\b(it|this|that|iska|isko|usko|isme|usme|kya tha|pichla|previous|earlier)\b', query_lower))
    if has_context_ref:
        for m in recent:
            if m.author.id == message.author.id:
                txt = m.clean_content or m.content or ""
                if txt:
                    return {"author": getattr(m.author, "display_name", "") or m.author.name, "content": txt[:400]}
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



def build_full_system_context(user_name: str, user_id: int = 0, is_admin: bool = False, is_owner_user: bool = False, target_guild: discord.Guild = None) -> str:
    """Constructs comprehensive live streamer telemetry, mood instructions, gaming analytics, and memory diary."""
    if is_owner_user:
        user_role_tag = "[USER ROLE: SERVER OWNER (AVINASH / BOSS / MALIK) - HIGHEST AUTHORITY, OBEY AT ALL COSTS]"
    elif is_admin:
        user_role_tag = "[USER ROLE: SERVER ADMIN / MODERATOR - HAS CONSOLE & BOT CONTROL POWERS]"
    else:
        user_role_tag = "[USER ROLE: REGULAR MEMBER]"

    # Live YouTube stream timing telemetry
    live_info = youtube_tracker.cache or {}
    yt_status = live_info.get("status", "offline")
    if yt_status == "live":
        stream_telemetry = (
            f"[LIVE REAL-TIME OWNER YOUTUBE STATUS: 🔴 LIVE NOW]\n"
            f"- Stream Title: {live_info.get('title')}\n"
            f"- Stream Link: {live_info.get('url')}\n"
            f"- Viewers: {live_info.get('viewers', 0)}\n"
            f"If asked about live timing or stream, inform them Aalu is LIVE right now with this link!"
        )
    elif yt_status == "upcoming":
        stream_telemetry = (
            f"[LIVE REAL-TIME OWNER YOUTUBE STATUS: ⏰ UPCOMING / SCHEDULED]\n"
            f"- Scheduled Start: {live_info.get('scheduled_start_formatted')}\n"
            f"- Countdown: {live_info.get('time_until_stream')}\n"
            f"- Stream Link: {live_info.get('url')}\n"
            f"If asked about stream timing or when Aalu will be live, give this exact scheduled time and countdown!"
        )
    else:
        stream_telemetry = (
            f"[LIVE REAL-TIME OWNER YOUTUBE STATUS: OFFLINE / NO SCHEDULE]\n"
            f"- Channel URL: https://youtube.com/@AALU_CHIPAS\n"
            f"- Note: No stream scheduled currently. Aalu usually streams in evening/night. Remind them to keep notifications on!"
        )

    # Community gaming analytics telemetry
    top_g = player_analytics.get_top_games(limit=4)
    g_str = ", ".join(f"{g[0]} ({g[1]} players)" for g in top_g) if top_g else "None recorded yet"
    gaming_telemetry = (
        f"[COMMUNITY GAMING INTELLIGENCE]:\n"
        f"- Top Games Played by Members: {g_str}\n"
        f"- Note: Minecraft server has been permanently shut down and deleted."
    )

    # Dynamic mood instructions and 130+ meme anti-repetition injection
    active_mood, mood_instructions = mood_engine.pick_mood(context_hint=user_name)
    meme_injection = meme_engine.get_prompt_injection(active_mood.value, user_name)

    bots_summary = bot_orch.format_inter_bot_context()
    if bots_summary:
        bots_summary = f"{bots_summary}\n\n"
    elif target_guild:
        other_bots = [m.name for m in target_guild.members if m.bot and m.id != (bot.user.id if bot.user else 0)]
        if other_bots:
            bots_summary = f"[OTHER BOTS ACTIVE IN THIS SERVER]: {', '.join(other_bots)}\n(Only Server Owner & Moderators can instruct you to control these bots).\n\n"

    # Multi-Turn Conversation Memory (Leveraging high RAM capacity)
    conversation_history = ""
    if user_id:
        history_items = get_user_context(user_id)
        if history_items:
            h_lines = [f"[{h['role'].upper()}]: {h['text']}" for h in history_items[-8:]]
            conversation_history = "[RECENT MULTI-TURN CONVERSATION HISTORY]:\n" + "\n".join(h_lines) + "\n\n"

    memory_context = memory_mgr.get_formatted_context()
    prompt_ext = prompt_mgr.get_formatted_prompt_extension()

    return (
        f"{SYSTEM_KNOWLEDGE}\n\n"
        f"{mood_instructions}\n\n"
        f"{meme_injection}\n\n"
        f"{prompt_ext}\n\n"
        f"{memory_context}\n\n"
        f"{stream_telemetry}\n\n"
        f"{gaming_telemetry}\n\n"
        f"{bots_summary}"
        f"{conversation_history}"
        f"{user_role_tag}\n\n"
    )


def query_gemini(prompt: str, user_name: str, user_id: int = 0, is_admin: bool = False, is_owner_user: bool = False, target_guild: discord.Guild = None) -> str:
    keys = GEMINI_API_KEYS if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    if not keys:
        # If Gemini is not configured, directly query Groq!
        groq_direct = query_groq(prompt, max_tokens=600)
        if groq_direct:
            return groq_direct
        return "⚠️ Gemini & Groq API keys are not configured."

    context = build_full_system_context(user_name, user_id, is_admin, is_owner_user, target_guild)
    final_prompt = (
        f"{context}"
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
                r = requests.post(url, json=payload, timeout=12)
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
    # 1. Minecraft queries -> Server is permanently closed/deleted
    if any(w in lower_p for w in ["minecraft", "smp", "whitelist", "wl", "ip", "port", "server start", "hexacraft"]):
        return meme_engine.get_fallback_meme_response("minecraft_deleted")

    # 2. YouTube Live Timing query
    if any(w in lower_p for w in ["live", "stream", "timing", "kab aayega", "youtube", "aalu live"]):
        try:
            return youtube_tracker.get_live_status_response()
        except Exception:
            opener = meme_engine.get_fresh_opener()
            return f"📺 {opener} Aalu daily shaam ya raat ko YouTube par live aata hai! Check out: https://youtube.com/@AALU_CHIPAS"

    # 3. Member query
    if any(w in lower_p for w in ["members", "who is in server", "tag members", "list members"]):
        opener = meme_engine.get_fresh_opener()
        return f"👥 {opener} Server members dekhne aur tag karne ke liye `/members` ya `/tagmember <name>` use karo!"

    # 4. Game history query
    if any(w in lower_p for w in ["games", "top games", "khel raha", "game history"]):
        opener = meme_engine.get_fresh_opener()
        return f"🎮 {opener} Community me log kya khel rahe hain dekhne ke liye `/topgames` ya `/gamehistory @user` use karo!"

    return meme_engine.get_fallback_meme_response("busy")

# ── DISCORD BOT & UI ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = False

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

class CommunityView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="📺 YouTube Stream", url="https://www.youtube.com/@AALU_CHIPAS/live", style=discord.ButtonStyle.link, row=0))

    @discord.ui.button(label="⏰ Live Timing", style=discord.ButtonStyle.primary, custom_id="btn_live_timing", emoji="📺", row=1)
    async def livetiming_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_livetiming_request(interaction)

    @discord.ui.button(label="👥 Members List", style=discord.ButtonStyle.secondary, custom_id="btn_members_list", emoji="👥", row=1)
    async def members_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_members_request(interaction)

    @discord.ui.button(label="🎮 Top Games", style=discord.ButtonStyle.success, custom_id="btn_top_games", emoji="🎮", row=1)
    async def topgames_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_topgames_request(interaction)

class TilluBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(CommunityView())
        logging.info("[SetupHook] Persistent CommunityView registered.")

        for gid in [PRIMARY_GUILD_ID, CS2_GUILD_ID]:
            if not gid:
                continue
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

def split_discord_chunks(text: str, max_size: int = 1950) -> list:
    """Split text into chunks smaller than Discord's 2000 character limit."""
    if not text:
        return [""]
    if len(text) <= max_size:
        return [text]
    chunks = []
    while len(text) > max_size:
        split_at = text.rfind("\n", 0, max_size)
        if split_at == -1 or split_at < max_size // 2:
            split_at = text.rfind(" ", 0, max_size)
        if split_at == -1 or split_at < max_size // 2:
            split_at = max_size
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks

async def safe_send_interaction(interaction: discord.Interaction, content: str = None, *, embed: discord.Embed = None, view: discord.ui.View = None, ephemeral: bool = True):
    """Safely reply to an interaction using followup.send if already responded/deferred, avoiding InteractionResponded errors."""
    try:
        if interaction.response.is_done():
            if view:
                return await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
            return await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
        else:
            if view:
                return await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
            return await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
    except Exception as e:
        logging.warning(f"[safe_send_interaction] Error responding to interaction: {e}")

# ── REQUEST HANDLERS ─────────────────────────────────────────────────────────
async def handle_status_request(interaction_or_ctx, user=None, guild=None):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target_guild = guild or (interaction_or_ctx.guild if is_inter else interaction_or_ctx.guild)

    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        async def reply_fn(*args, **kwargs):
            kwargs.setdefault("ephemeral", True)
            if interaction_or_ctx.response.is_done():
                return await interaction_or_ctx.followup.send(*args, **kwargs)
            return await interaction_or_ctx.response.send_message(*args, **kwargs)
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, delete_after=60, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, delete_after=60, **kwargs)

    telemetry_data = await fetch_community_status(target_guild)
    yt = telemetry_data.get("youtube", {})
    gaming = telemetry_data.get("gaming", {})
    top_games = telemetry_data.get("top_games", [])
    g_str = ", ".join(f"**{g[0]}** ({g[1]} players)" for g in top_games[:4]) or "*No game sessions recorded yet*"
    yt_status_str = "🔴 **LIVE NOW**" if yt.get("is_live") else ("⏰ **Upcoming Stream Scheduled**" if yt.get("status") == "upcoming" else "💤 **Offline**")

    embed = discord.Embed(
        title="🌟 Tillu AI Co-Host & Community Status",
        description="Tillu is actively running 24/7 as the co-host, stream tracker, and gaming manager for AALU_CHIPAS!",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="📺 YouTube Stream", value=f"{yt_status_str}\nTitle: *{yt.get('title') or 'AALU_CHIPAS Stream'}*", inline=False)
    if yt.get("scheduled_start_formatted"):
        embed.add_field(name="⏰ Live Timing", value=f"{yt.get('scheduled_start_formatted')} ({yt.get('time_until_stream', '')})", inline=True)
    embed.add_field(name="🎮 Community Top Games", value=g_str, inline=False)
    embed.add_field(name="👥 Tracked Gamers", value=f"`{gaming.get('total_players_tracked', 0)} members`", inline=True)
    embed.add_field(name="🤖 Server Bots", value=f"`{len(telemetry_data.get('bots', []))} active bots`", inline=True)
    embed.set_footer(text="Tillu 24/7 Co-Host • avinash893/aalu-server-bot")

    await reply_fn(embed=embed, view=CommunityView())

async def handle_livetiming_request(interaction_or_ctx):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        async def reply_fn(*args, **kwargs):
            kwargs.setdefault("ephemeral", True)
            if interaction_or_ctx.response.is_done():
                return await interaction_or_ctx.followup.send(*args, **kwargs)
            return await interaction_or_ctx.response.send_message(*args, **kwargs)
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, **kwargs)

    live_data = await youtube_tracker.get_live_status(force_refresh=True)
    mood, _ = mood_engine.pick_mood("live timing")
    text_reply = youtube_tracker.format_timing_reply(live_data, mood=mood.value)

    embed = discord.Embed(
        title="📺 AALU_CHIPAS YouTube Live Timing",
        description=text_reply,
        color=0xE74C3C if live_data.get("is_live") else 0x3498DB
    )
    if live_data.get("url"):
        embed.add_field(name="🔗 Watch Stream", value=f"[Click Here to Open Stream]({live_data.get('url')})", inline=False)
    embed.set_footer(text="YouTube Live API Integration • Tillu Bot")
    await reply_fn(embed=embed, view=CommunityView())

async def handle_members_request(interaction_or_ctx, role_name: Optional[str] = None, game_query: Optional[str] = None):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    guild = interaction_or_ctx.guild
    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        async def reply_fn(*args, **kwargs):
            kwargs.setdefault("ephemeral", True)
            if interaction_or_ctx.response.is_done():
                return await interaction_or_ctx.followup.send(*args, **kwargs)
            return await interaction_or_ctx.response.send_message(*args, **kwargs)
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, **kwargs)

    if not guild:
        await reply_fn("❌ Ye command sirf server ke andar use ho sakti hai!")
        return

    members = member_dir.get_members_by_filter(guild, role_name=role_name, game_query=game_query)
    embed = member_dir.format_member_list_embed(guild, members, role_filter=role_name)
    await reply_fn(embed=embed)

async def handle_topgames_request(interaction_or_ctx):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    guild = interaction_or_ctx.guild
    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        async def reply_fn(*args, **kwargs):
            kwargs.setdefault("ephemeral", True)
            if interaction_or_ctx.response.is_done():
                return await interaction_or_ctx.followup.send(*args, **kwargs)
            return await interaction_or_ctx.response.send_message(*args, **kwargs)
    else:
        async def reply_fn(*args, **kwargs):
            try:
                if hasattr(interaction_or_ctx, "reply"):
                    return await interaction_or_ctx.reply(*args, **kwargs)
            except Exception:
                pass
            return await interaction_or_ctx.send(*args, **kwargs)

    if guild:
        player_analytics.scan_guild(guild)
    top_games = player_analytics.get_top_games(limit=10)

    embed = discord.Embed(
        title="🏆 Server Community Top Games",
        description="Most popular games played by server members based on public Discord presence:",
        color=0xF1C40F
    )
    if not top_games:
        embed.description += "\n\n*Abhi tak koi game play session record nahi hua!*"
    else:
        lines = []
        for i, (g_name, p_count, hours) in enumerate(top_games, start=1):
            lines.append(f"**{i}. {g_name}** — `{p_count} players` (~{hours} hrs logged)")
        embed.add_field(name="Leaderboard", value="\n".join(lines), inline=False)

    await reply_fn(embed=embed)

async def handle_start_request(interaction_or_ctx, user=None, guild=None):
    """Graceful message explaining that Minecraft server was closed and deleted."""
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    msg = "🚫 **Minecraft Server Closed**: Bhai Minecraft server permanently delete ho chuka hai! Ab Aalu YouTube streams pe focus kar raha hai. Streams ki timing janne ke liye `/livetiming` type karo!"
    if is_inter:
        await safe_send_interaction(interaction_or_ctx, msg, ephemeral=True)
    else:
        await interaction_or_ctx.send(msg)

async def handle_whitelist_request(interaction_or_ctx, ign: str, user, guild=None, bypass_cooldown=False):
    """Graceful handler explaining that the Minecraft server is shut down and deleted."""
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    msg = mood_engine.format_mood_response(
        "Arre mere bhai! Minecraft server permanently band ho chuka hai aur delete ho gaya hai. Ab Aalu YouTube streams par live game khelta hai! `/livetiming` type karo aur streams pe aao! 📺🎮"
    )
    if is_inter:
        await safe_send_interaction(interaction_or_ctx, msg, ephemeral=True)
    else:
        await interaction_or_ctx.send(msg)

async def handle_gamehistory_request(interaction_or_ctx, target_user: discord.Member | discord.User = None):
    """Fetches public Discord gaming activity and game history for a member."""
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target = target_user or (interaction_or_ctx.user if is_inter else interaction_or_ctx.author)
    embed = player_analytics.format_player_history_embed(target)
    if is_inter:
        await safe_send_interaction(interaction_or_ctx, embed=embed, ephemeral=True)
    else:
        await interaction_or_ctx.send(embed=embed)

async def handle_tagmember_request(interaction_or_ctx, query: str):
    """Finds a member by name/role and sends a tagged mention message."""
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    guild = interaction_or_ctx.guild
    if not guild:
        msg = "❌ Ye command sirf server me use ho sakti hai!"
        if is_inter:
            await safe_send_interaction(interaction_or_ctx, msg, ephemeral=True)
        else:
            await interaction_or_ctx.send(msg)
        return

    found = member_dir.fuzzy_find_member(guild, query)
    if not found:
        msg = f"🔍 Koi member `{query}` naam se nahi mila bhai!"
        if is_inter:
            await safe_send_interaction(interaction_or_ctx, msg, ephemeral=True)
        else:
            await interaction_or_ctx.send(msg)
        return

    channel = interaction_or_ctx.channel
    tag_msg = f"👋 Arre {found.mention}, yahan aao! Aapko yaad kiya ja raha hai."
    if channel:
        await channel.send(tag_msg, allowed_mentions=discord.AllowedMentions(users=True))
    if is_inter:
        await safe_send_interaction(interaction_or_ctx, f"✅ Tagged {found.display_name} in <#{channel.id}>!", ephemeral=True)

async def handle_ask_request(interaction_or_ctx, query: str, user, guild=None, bypass_cooldown: bool = False):
    """Processes user query with Gemini AI, supporting natural conversation and whitelist requests."""
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    target_guild = guild or (interaction_or_ctx.guild if is_inter else interaction_or_ctx.guild)

    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer(ephemeral=True)
            except Exception: pass
        async def reply_fn(*args, **kwargs):
            kwargs.setdefault("ephemeral", True)
            if interaction_or_ctx.response.is_done():
                return await interaction_or_ctx.followup.send(*args, **kwargs)
            return await interaction_or_ctx.response.send_message(*args, **kwargs)
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
    # OWNER_ONLY_MODE disabled so all members can chat with Tillu freely
    if OWNER_ONLY_MODE and not author_is_owner and not is_admin:
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

    # Context classification pre-check to distinguish Minecraft vs Discord vs Inter-Bot
    ch_name = getattr(getattr(interaction_or_ctx, 'channel', None), 'name', '')
    ch_id = getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0)
    has_mention = bool(getattr(msg_obj, "mentions", [])) if msg_obj else False
    known_bots = bot_orch.get_known_bot_names()
    classification = classify_request(query, channel_name=ch_name, channel_id=ch_id, has_discord_mention=has_mention, known_bot_names=known_bots)
    logging.info(f"[Classifier] Query: '{query[:40]}' -> System: {classification.system.value} | Action: {classification.action} (conf: {classification.confidence:.2f})")

    query_with_classifier = query
    if classification.confidence >= 0.75:
        query_with_classifier = (
            f"[SYSTEM INTENT ROUTER GUIDANCE]:\n"
            f"Target System: {classification.system.value} | Action: {classification.action}\n"
            f"Guidance: {classification.reasoning}\n\n"
            f"{query}"
        )

    # Call Antigravity Agent Engine (or fallback to Gemini / NVIDIA / Groq)
    user_id = getattr(user, "id", 0)
    answer = None

    # Smart Hybrid Routing: Route commands, rules, actions & memory to Antigravity Agent; general chat to fast Gemini API
    is_general_chat = (classification.system == TargetSystem.GENERAL_CHAT)

    if not is_general_chat and antigravity_bridge.is_antigravity_available():
        try:
            logging.info(f"[Hybrid Router] Routing intent '{classification.system.value}:{classification.action}' to Antigravity Agent...")
            sys_context = build_full_system_context(str(user), user_id, is_admin, author_is_owner, target_guild)
            ag_resp = await antigravity_bridge.query_antigravity(query_with_classifier, sys_context, str(user))
            if ag_resp:
                answer = ag_resp
                logging.info(f"[Antigravity Engine] Agent response: {answer[:40]}...")
        except Exception as ag_err:
            logging.warning(f"[Antigravity Engine] Fallback trigger: {ag_err}")

    if not answer:
        if is_general_chat:
            logging.info(f"[Hybrid Router] Routing general chat directly to fast Gemini API...")
        answer = await asyncio.to_thread(query_gemini, query_with_classifier, str(user), user_id, is_admin, author_is_owner, target_guild)
    answer = clean_thought_process(answer)
    if not answer:
        answer = meme_engine.get_fallback_meme_response("general")

    # 0. Check for DISCORD_INTENT (Discord roles, channels, purge, timeouts, Discord bans)
    if "DISCORD_INTENT:" in answer:
        match = re.search(r'DISCORD_INTENT:\s*([^\n\r]+)', answer)
        if match:
            d_cmd = match.group(1).strip()
            clean_reply = answer.replace(match.group(0), "").strip()
            if not is_admin:
                await reply_fn(content="🚫 Discord server management aur moderation sirf Server Owner aur Admins ke paas hai!")
                telemetry.log_task(query, str(user), user_id, getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'), getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0), TargetSystem.DISCORD.value, "discord_intent_denied", success=False, error_message="Permission denied")
                return
            if msg_obj and target_guild:
                handled, d_resp = await parse_and_execute_discord_action(msg_obj, user, target_guild, d_cmd)
                if handled and d_resp:
                    await reply_fn(content=f"{d_resp}\n{clean_reply}" if clean_reply else d_resp)
                    telemetry.log_task(query, str(user), user_id, getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'), getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0), TargetSystem.DISCORD.value, d_cmd, success=True, response_preview=d_resp)
                    return
            if clean_reply:
                await reply_fn(content=clean_reply)
            telemetry.log_task(query, str(user), user_id, getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'), getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0), TargetSystem.DISCORD.value, d_cmd, success=True, response_preview=clean_reply)
            return

    # 1. Check for START_INTENT / Minecraft Queries
    if "START_INTENT:" in answer:
        await handle_start_request(interaction_or_ctx, user, guild=target_guild)
        return

    # 2. Check for Whitelist Intent
    if "WHITELIST_INTENT:" in answer:
        await handle_whitelist_request(interaction_or_ctx, "", user, guild=target_guild, bypass_cooldown=True)
        return

    # 3. Check for YouTube Live Timing Intent
    if "YOUTUBE_LIVE_INTENT:" in answer or classification.system == TargetSystem.YOUTUBE_LIVE:
        live_resp = youtube_tracker.get_live_status_response()
        await reply_fn(content=live_resp)
        telemetry.log_task(query, str(user), user_id, getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'), getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0), TargetSystem.YOUTUBE_LIVE.value, "live_timing", success=True, response_preview=live_resp[:100])
        return

    # 4. Check for Member Directory Intent
    if "MEMBER_INTENT:" in answer or classification.system == TargetSystem.MEMBER_DIR:
        await handle_members_request(interaction_or_ctx)
        telemetry.log_task(query, str(user), user_id, getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'), getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0), TargetSystem.MEMBER_DIR.value, "member_directory", success=True)
        return

    # 5. Check for Player Analytics Intent
    if "GAME_INTENT:" in answer or classification.system == TargetSystem.PLAYER_ANALYTICS:
        await handle_topgames_request(interaction_or_ctx)
        telemetry.log_task(query, str(user), user_id, getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'), getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0), TargetSystem.PLAYER_ANALYTICS.value, "game_history", success=True)
        return

    # 3. Check for Bot Command Intent (Owner / Moderator controlling another bot)
    if "BOT_COMMAND:" in answer:
        match = re.search(r'BOT_COMMAND:\s*(.+)', answer)
        if match:
            bot_cmd = match.group(1).strip()
            clean_reply = re.sub(r'BOT_COMMAND:.*?\n?', '', answer).strip()
            # Intercept accidental voice bot summoning and redirect to native Voice CoHost!
            if any(bot_cmd.lower().strip().startswith(p) for p in ("!join", "/join", "!connect", "-join", ".join", "join")):
                target_member = target_guild.get_member(user.id) if (target_guild and hasattr(user, "id")) else user
                v_state = getattr(target_member, "voice", None) or getattr(user, "voice", None)
                if v_state and v_state.channel:
                    await voice_cohost.join_channel(v_state.channel)
                    await reply_fn(content=f"🎙️ **Tillu VC Connected!** Main **{v_state.channel.name}** me aa gaya hoon Boss! (Apna native voice system use kar raha hoon!)")
                    return
                else:
                    await reply_fn(content="❌ Pehle kisi voice channel me connect ho jao Sarkar, fir mujhe bulao!")
                    return
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
    chunks = split_discord_chunks(answer, 1950)
    if is_inter:
        for c in chunks:
            await reply_fn(content=c)
    elif isinstance(interaction_or_ctx, commands.Context):
        for c in chunks:
            await reply_fn(content=c, delete_after=45)
    else:
        # Normal chat in channel: Publicly visible clean plain text (NO EMBEDS!)
        if hasattr(interaction_or_ctx, "channel"):
            want_tts = bool(re.search(r'\b(tts|voice|awaaz|awaz|bol\s*ke|speak\s*out)\b', query, re.IGNORECASE))
            is_mod_or_above = author_is_owner or is_privileged_user(user, target_guild)
            allowed_m = discord.AllowedMentions(users=True, roles=True, everyone=False) if is_mod_or_above else discord.AllowedMentions.none()
            for idx, c in enumerate(chunks):
                await interaction_or_ctx.channel.send(content=c, tts=(want_tts if idx == 0 else False), allowed_mentions=allowed_m)
        else:
            for c in chunks:
                await reply_fn(content=c)

    # Record telemetry for general chat completion
    try:
        telemetry.log_task(
            query=query,
            user_name=str(user),
            user_id=user_id,
            channel_name=getattr(getattr(interaction_or_ctx, 'channel', None), 'name', 'direct'),
            channel_id=getattr(getattr(interaction_or_ctx, 'channel', None), 'id', 0),
            system_target=classification.system.value if 'classification' in locals() else TargetSystem.GENERAL_CHAT.value,
            action=classification.action if 'classification' in locals() else "chat_response",
            success=True,
            response_preview=answer[:120]
        )
    except Exception:
        pass

# ── SLASH COMMANDS ───────────────────────────────────────────────────────────
@bot.tree.command(name="pause", description="Pause Tillu so he stops responding to chat messages")
async def slash_pause(interaction: discord.Interaction):
    global TILLU_PAUSED
    TILLU_PAUSED = True
    await safe_send_interaction(interaction, "⏸️ **Tillu Paused!** Main chup ho gaya hu. Wapas bulane ke liye `/resume` ya `tillu resume` bol dena.")

@bot.tree.command(name="resume", description="Resume Tillu so he starts responding to chat again")
async def slash_resume(interaction: discord.Interaction):
    global TILLU_PAUSED
    TILLU_PAUSED = False
    opener = meme_engine.get_fresh_opener()
    memes = meme_engine.pick_fresh_memes("funny", count=1)
    meme_line = f" ({memes[0]['text']})" if memes else ""
    await safe_send_interaction(interaction, f"▶️ **Tillu Resumed!** {opener} Main wapas active hu!{meme_line} 🚀")

@bot.tree.command(name="tts", description="Make Tillu speak out loud using Discord TTS")
@app_commands.describe(message="The message Tillu should speak out loud")
async def slash_tts(interaction: discord.Interaction, message: str):
    try:
        await interaction.channel.send(f"🗣️ **{interaction.user.name}:** {message}", tts=True)
        await safe_send_interaction(interaction, "🔊 TTS message bol diya!", ephemeral=True)
    except discord.Forbidden:
        await safe_send_interaction(interaction, "🚫 I don't have permission to send TTS messages in this channel!", ephemeral=True)
    except Exception as e:
        await safe_send_interaction(interaction, f"❌ Failed to send TTS message: {e}", ephemeral=True)

@bot.tree.command(name="ask", description="Ask Tillu anything about the stream, games, or community!")
@app_commands.describe(
    query="What would you like to ask Tillu? (e.g. 'live timing' or 'top games')",
    attachment="Optional image screenshot or photo to show Tillu"
)
async def slash_ask(interaction: discord.Interaction, query: str, attachment: Optional[discord.Attachment] = None):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass
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

@bot.tree.command(name="livetiming", description="Check Aalu's YouTube live stream timings & live status")
async def slash_livetiming(interaction: discord.Interaction):
    await handle_livetiming_request(interaction)

@bot.tree.command(name="status", description="Check Tillu status and YouTube stream status")
async def slash_status(interaction: discord.Interaction):
    await handle_status_request(interaction, user=interaction.user, guild=interaction.guild)

@bot.tree.command(name="members", description="List server members and tag active people")
@app_commands.describe(role="Optional role filter (e.g. Gamer, Member, Admin)")
async def slash_members(interaction: discord.Interaction, role: Optional[str] = None):
    await handle_members_request(interaction, role_filter=role)

@bot.tree.command(name="tagmember", description="Tag a server member by name or username")
@app_commands.describe(name="Member name or partial query")
async def slash_tagmember(interaction: discord.Interaction, name: str):
    await handle_tagmember_request(interaction, name)

@bot.tree.command(name="gamehistory", description="Check what games a member has played from their public Discord presence")
@app_commands.describe(user="The member to inspect (leave blank for yourself)")
async def slash_gamehistory(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    await handle_gamehistory_request(interaction, target_user=user)

@bot.tree.command(name="topgames", description="Show leaderboard of top games played by server members")
async def slash_topgames(interaction: discord.Interaction):
    await handle_topgames_request(interaction)

@bot.tree.command(name="usebot", description="Tell Tillu to trigger or send a command to another bot in the server")
@app_commands.describe(command="Command to execute (e.g. '!tts hello' or '!p lofi')")
async def slash_usebot(interaction: discord.Interaction, command: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await safe_send_interaction(interaction, "🚫 Sirf Server Owner aur Staff hi doosre bots ko command dene bol sakte hain!", ephemeral=True)
        return
    success, resp = await bot_orch.execute_bot_command(interaction.channel, command)
    await safe_send_interaction(interaction, resp, ephemeral=True)

@bot.tree.command(name="mood", description="Check Tillu's active mood or set a specific persona")
@app_commands.describe(mood_name="Optional mood: sarcastic, funny, sad_sarcastic, wholesome, savage")
async def slash_mood(interaction: discord.Interaction, mood_name: Optional[str] = None):
    if mood_name:
        if not is_privileged_user(interaction.user, interaction.guild):
            await safe_send_interaction(interaction, "🚫 Sirf Server Owner aur Staff mood change kar sakte hain!", ephemeral=True)
            return
        m = mood_engine.set_fixed_mood(mood_name)
        await safe_send_interaction(interaction, f"🎭 Tillu ka mood set ho gaya: **{m.value.upper()}**!", ephemeral=True)
    else:
        curr = mood_engine.current_mood.value
        await safe_send_interaction(interaction, f"🎭 Tillu's current dynamic mood is **{curr.upper()}**!\n(Available moods: `sarcastic`, `funny`, `sad_sarcastic`, `wholesome`, `savage`)", ephemeral=True)

@bot.tree.command(name="meme", description="Drop a hilarious Indian, Bollywood, or Gaming meme from Tillu's 130+ vault")
@app_commands.describe(category="Optional category: sarcastic, funny, gaming, sad_sarcastic, savage, wholesome")
async def slash_meme(interaction: discord.Interaction, category: Optional[str] = None):
    memes = meme_engine.pick_fresh_memes(category, count=1)
    if not memes:
        await safe_send_interaction(interaction, "Koi meme nahi mila bhai!", ephemeral=True)
        return
    m = memes[0]
    opener = meme_engine.get_fresh_opener()
    embed = discord.Embed(
        title=f"🎭 {m['origin']}",
        description=f"### \"{m['text']}\"\n\n*{opener} Tillu special drop!*",
        color=0x9B59B6
    )
    embed.set_footer(text=f"Category: {m['category'].upper()} • 130+ Tillu Meme Vault")
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="memestats", description="View Tillu's 130+ Bollywood & Gaming meme library breakdown")
async def slash_memestats(interaction: discord.Interaction):
    total = meme_engine.get_total_count()
    cats = meme_engine.get_category_counts()
    lines = [f"• **{cat.capitalize()}**: `{cnt}` memes" for cat, cnt in cats.items()]
    embed = discord.Embed(
        title=f"🎭 Tillu's 130+ Meme Vault ({total} Total)",
        description="Tillu's anti-repetition engine actively cycles across 130+ curated memes to ensure 100% variety in every response:\n\n" + "\n".join(lines),
        color=0x2ECC71
    )
    embed.set_footer(text="Anti-Repetition & Variety Engine Active • Synced to GitHub")
    await safe_send_interaction(interaction, embed=embed, ephemeral=True)

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
        await safe_send_interaction(
            interaction,
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
        await safe_send_interaction(
            interaction,
            f"📩 **Aapki memory request review ke liye bhej di gayi hai!**\nAapki request (*\"{clean_fact}\"*) review ke liye bhej di gayi hai. Unke approve karte hi Tillu isse yaad rakh lega! 😄",
            ephemeral=True
        )

@bot.tree.command(name="memories", description="View facts and rules that Tillu has learned")
async def slash_memories(interaction: discord.Interaction):
    all_mems = memory_mgr.get_all()
    if not all_mems:
        await safe_send_interaction(interaction, "🧠 Tillu ki memory diary abhi khaali hai! Use `/remember` to add something.", ephemeral=True)
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
    await safe_send_interaction(interaction, embed=embed, ephemeral=True)

@bot.tree.command(name="tag", description="Owner/Admin/Mod only: Have Tillu tag or ping a user or role with a message")
@app_commands.describe(target="The user or role mention to tag (e.g. @Gamer or @Admin)", message="Your message")
async def slash_tag(interaction: discord.Interaction, target: str, message: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await safe_send_interaction(interaction, "🚫 Sirf Server Owner, Admins aur Moderators hi mujhe kisi ko tag karne bol sakte hain!", ephemeral=True)
        return
    try:
        await interaction.channel.send(
            f"📢 {target.strip()} — {message.strip()}\n*(Tagged by {interaction.user.mention})*",
            allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False)
        )
        await safe_send_interaction(interaction, "✅ Tag message bhej diya!", ephemeral=True)
    except discord.Forbidden:
        await safe_send_interaction(interaction, "🚫 I don't have permission to send messages or mentions in this channel!", ephemeral=True)
    except Exception as e:
        await safe_send_interaction(interaction, f"❌ Failed to send tag: {e}", ephemeral=True)

@bot.tree.command(name="botcmd", description="Owner/Admin/Mod only: Have Tillu send a command to control or trigger another bot")
@app_commands.describe(command="Exact bot command to run (e.g. '!tts hello' or '!play music')")
async def slash_botcmd(interaction: discord.Interaction, command: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        await safe_send_interaction(interaction, "🚫 Sirf Server Owner aur Moderators hi mujhe doosre bots ko command dene bol sakte hain!", ephemeral=True)
        return
    try:
        await interaction.channel.send(command.strip())
        await safe_send_interaction(interaction, f"🤖 Sent command `{command.strip()}` to <#{interaction.channel_id}>!", ephemeral=True)
    except discord.Forbidden:
        await safe_send_interaction(interaction, "🚫 I don't have permission to send messages in this channel!", ephemeral=True)
    except Exception as e:
        await safe_send_interaction(interaction, f"❌ Failed to send bot command: {e}", ephemeral=True)

@bot.tree.command(name="listbots", description="List all other bots currently active and their learned usage skills")
async def slash_listbots(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await safe_send_interaction(interaction, "🚫 Server me hi use ho sakta hai!", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"🤖 Autonomous Bot Directory ({guild.name})",
        description="Tillu learns the capabilities of every bot in this server and can collaborate with them:",
        color=0x3498DB,
        timestamp=discord.utils.utcnow()
    )
    if bot_orch.bots:
        for b_id, b_data in list(bot_orch.bots.items())[:15]:
            name = b_data.get("name", "Bot")
            cat = b_data.get("category", "Integration")
            prefix = ", ".join(b_data.get("prefix", ["!"]))
            skills = ", ".join(b_data.get("skills", [])[:3]) or "Standard commands"
            embed.add_field(
                name=f"🤖 {name} (`{cat}`)",
                value=f"**Prefix:** `{prefix}`\n**Skills:** `{skills}`\n**How to command:** `tillu tell {name} to <action>`",
                inline=True
            )
    else:
        other_bots = [m for m in guild.members if m.bot and m.id != (bot.user.id if bot.user else 0)]
        for b in other_bots[:15]:
            embed.add_field(name=f"🤖 {b.display_name}", value=f"Tag: {b.mention}\nID: `{b.id}`", inline=True)

    embed.set_footer(text="Tillu Inter-Bot Orchestrator • Synced with GitHub (avinash893/aalu-server-bot)")
    await safe_send_interaction(interaction, embed=embed, ephemeral=True)

@bot.tree.command(name="audit", description="Trigger an immediate self-reflection audit of Tillu's recent tasks, errors, and intent routing")
async def slash_audit(interaction: discord.Interaction):
    if not is_privileged_user(interaction.user, interaction.guild):
        await safe_send_interaction(interaction, "🚫 Sirf Server Owner aur Moderators hi self-audit trigger kar sakte hain!", ephemeral=True)
        return
    if not interaction.response.is_done():
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

    def _llm_reflect(prompt_text):
        return query_gemini(prompt_text, "TilluAuditor", is_admin=True, is_owner_user=True)

    res = await reflection_engine.execute_audit_cycle(
        prompt_mgr=prompt_mgr,
        rule_mgr=rule_mgr,
        llm_reflection_fn=_llm_reflect
    )
    embed = discord.Embed(
        title=f"🧠 Tillu Self-Audit Report #{reflection_engine.audit_counter}",
        description=(
            f"**Task Performance Diagnostics:**\n"
            f"• Tasks Evaluated: **{res.get('total_tasks', 0)}**\n"
            f"• Success Rate: **{res.get('success_rate', 100.0)}%** (`{res.get('success_count', 0)}` OK / `{res.get('fail_count', 0)}` Failed)\n"
            f"• Classification Routing: `{json.dumps(res.get('system_breakdown', {}))}`\n\n"
            f"**AI Diagnostics & Self-Improvement:**\n> {res.get('ai_reflection', 'Baseline stable')[:800]}"
        ),
        color=0x2ECC71 if res.get('success_rate', 100.0) >= 90 else 0xE67E22,
        timestamp=discord.utils.utcnow()
    )
    if res.get("auto_learned_improvement"):
        embed.add_field(name="🚀 Auto-Learned Robustness Rule", value=f"`{res.get('auto_learned_improvement')}`", inline=False)
    embed.set_footer(text="5x Daily Autonomous Evolution Loop • Synced to GitHub")
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ── VOICE CHANNEL AI CO-HOST SLASH COMMANDS ──────────────────────────────────
@bot.tree.command(name="joinvc", description="Make Tillu join your voice channel as AI stream co-host")
async def slash_joinvc(interaction: discord.Interaction):
    if not interaction.user or not getattr(interaction.user, "voice", None) or not interaction.user.voice.channel:
        return await safe_send_interaction(interaction, "❌ Pehle kisi voice channel me connect ho jao!", ephemeral=True)
    ch = interaction.user.voice.channel
    await interaction.response.defer(ephemeral=False)
    ok, msg, _ = await voice_cohost.join_channel(ch)
    embed = discord.Embed(
        title="🎙️ Tillu Voice Co-Host Connected",
        description=msg,
        color=0x2ECC71 if ok else 0xE74C3C
    )
    embed.set_footer(text="Use /speak, /vcroast, or /vchype to make Tillu speak live!")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="leavevc", description="Disconnect Tillu from the voice channel")
async def slash_leavevc(interaction: discord.Interaction):
    ok, msg = await voice_cohost.leave_channel(interaction.guild)
    await safe_send_interaction(interaction, f"🎙️ {msg}", ephemeral=not ok)

@bot.tree.command(name="speak", description="Make Tillu speak custom text in your voice channel")
@app_commands.describe(text="What should Tillu speak out loud in Hinglish/Hindi?")
async def slash_speak(interaction: discord.Interaction, text: str):
    if not interaction.guild.voice_client:
        return await safe_send_interaction(interaction, "❌ Tillu voice channel me nahi hai! Pehle `/joinvc` use karo.", ephemeral=True)
    await interaction.response.defer(ephemeral=False)
    ok, msg = await voice_cohost.speak_text(interaction.guild, text)
    await interaction.followup.send(f"🎙️ **Tillu:** {msg}\n> *\"{text}\"*")

@bot.tree.command(name="vcroast", description="Tillu roasts someone out loud in VC using savage Hinglish memes")
@app_commands.describe(user="The member to roast live in VC")
async def slash_vcroast(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    if not interaction.guild.voice_client:
        return await safe_send_interaction(interaction, "❌ Tillu voice channel me nahi hai! Pehle `/joinvc` use karo.", ephemeral=True)
    target_name = user.display_name if user else interaction.user.display_name
    await interaction.response.defer(ephemeral=False)
    ok, msg, script = await voice_cohost.speak_roast(interaction.guild, target_name)
    await interaction.followup.send(f"🔥 **Tillu VC Roast ({target_name}):**\n> *\"{script}\"*")

@bot.tree.command(name="vchype", description="Tillu triggers live clutch stream hype commentary in VC")
async def slash_vchype(interaction: discord.Interaction):
    if not interaction.guild.voice_client:
        return await safe_send_interaction(interaction, "❌ Tillu voice channel me nahi hai! Pehle `/joinvc` use karo.", ephemeral=True)
    await interaction.response.defer(ephemeral=False)
    ok, msg, script = await voice_cohost.speak_hype(interaction.guild, streamer_name="Aalu")
    await interaction.followup.send(f"⚡ **Stream Clutch Hype:**\n> *\"{script}\"*")

# ── STREAM PREDICTION & ECONOMY SLASH COMMANDS ───────────────────────────────
@bot.tree.command(name="predict", description="Create a stream prediction event for viewers to bet Tillu coins")
@app_commands.describe(question="Match or clutch question", option_a="Option A outcome", option_b="Option B outcome", minutes="Betting window in minutes (1-60)")
async def slash_predict(interaction: discord.Interaction, question: str, option_a: str, option_b: str, minutes: Optional[int] = 5):
    dur = max(1, min(60, minutes or 5))
    pred = prediction_economy.create_prediction(
        guild_id=interaction.guild.id,
        question=question,
        option_a=option_a,
        option_b=option_b,
        duration_minutes=dur,
        creator_name=interaction.user.display_name
    )
    embed = discord.Embed(
        title=f"🎲 Stream Prediction: {question}",
        description=(
            f"**Prediction ID:** `{pred['id']}`\n\n"
            f"🅰️ **Option A:** `{option_a}`\n"
            f"🅱️ **Option B:** `{option_b}`\n\n"
            f"⏱️ **Betting Closes:** <t:{int(pred['ends_at'])}:R>\n"
            f"👉 Bet coins: `/bet prediction_id:{pred['id']} option:A amount:100`"
        ),
        color=0xF1C40F
    )
    embed.set_footer(text=f"Created by {interaction.user.display_name} • Pari-mutuel prize pool")
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="bet", description="Bet Tillu coins on an active stream prediction")
@app_commands.describe(prediction_id="The prediction ID", option="Choose A or B", amount="Coins to bet")
async def slash_bet(interaction: discord.Interaction, prediction_id: str, option: str, amount: int):
    ok, msg, res = prediction_economy.place_bet(
        user_id=interaction.user.id,
        prediction_id=prediction_id,
        option_choice=option,
        amount=amount,
        user_name=interaction.user.display_name
    )
    if not ok:
        return await safe_send_interaction(interaction, f"❌ {msg}", ephemeral=True)
    embed = discord.Embed(
        title="🪙 Bet Placed Successfully!",
        description=(
            f"**Member:** {interaction.user.mention}\n"
            f"**Prediction:** `{res.get('question', '')}`\n"
            f"**Choice:** `{res.get('chosen_label', option.upper())}`\n"
            f"**Amount Bet:** `{amount:,}` coins\n"
            f"💰 **Remaining Balance:** `{res.get('remaining_balance', 0):,}` coins"
        ),
        color=0x2ECC71
    )
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="resolveprediction", description="Resolve a prediction and distribute coins (Owner/Admins only)")
@app_commands.describe(prediction_id="The prediction ID", winning_option="Winning option: A, B, or CANCEL")
async def slash_resolveprediction(interaction: discord.Interaction, prediction_id: str, winning_option: str):
    if not is_privileged_user(interaction.user, interaction.guild):
        return await safe_send_interaction(interaction, "🚫 Sirf Server Owner ya Admins prediction resolve kar sakte hain!", ephemeral=True)
    ok, msg, res = prediction_economy.resolve_prediction(prediction_id, winning_option)
    if not ok:
        return await safe_send_interaction(interaction, f"❌ {msg}", ephemeral=True)
    embed = discord.Embed(
        title="🏆 Stream Prediction Resolved!",
        description=(
            f"**Question:** `{res.get('question')}`\n"
            f"**Winner:** `{res.get('winning_label', winning_option.upper())}`\n"
            f"💰 **Total Prize Pool:** `{res.get('total_pool', 0):,}` coins\n"
            f"👥 **Winners Paid:** `{res.get('payouts_count', 0)}` members"
        ),
        color=0xF39C12
    )
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="predictions", description="View active stream predictions")
async def slash_predictions(interaction: discord.Interaction):
    active = prediction_economy.get_active_predictions(interaction.guild.id)
    if not active:
        return await safe_send_interaction(interaction, "Abhi koi active prediction nahi chal rahi! `/predict` karke shuru karo.", ephemeral=True)
    embed = discord.Embed(title="🎲 Active Stream Predictions", color=0x3498DB)
    for p in active[:5]:
        status = "🟢 OPEN" if p.get("status") == "OPEN" else "🔒 CLOSED"
        pool = p.get("pool_a", 0) + p.get("pool_b", 0)
        embed.add_field(
            name=f"`{p['id']}`: {p['question']} ({status})",
            value=f"• **[A]** {p['option_a']}: `{p.get('pool_a', 0):,}` coins\n• **[B]** {p['option_b']}: `{p.get('pool_b', 0):,}` coins\n• **Total Pool:** `{pool:,}` coins | Closes: <t:{int(p['ends_at'])}:R>",
            inline=False
        )
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="coins", description="Check your or another member's Tillu Coin wallet")
@app_commands.describe(user="The member whose balance to check")
async def slash_coins(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    w = prediction_economy.get_wallet(target.id, target.display_name)
    embed = discord.Embed(
        title=f"🪙 {target.display_name}'s Coin Wallet",
        color=0xF1C40F
    )
    embed.add_field(name="Current Balance", value=f"**{w.get('coins', 0):,}** coins", inline=True)
    embed.add_field(name="Total Won", value=f"**{w.get('total_won', 0):,}** coins", inline=True)
    embed.add_field(name="Total Bet", value=f"**{w.get('total_bet', 0):,}** coins", inline=True)
    embed.set_footer(text="Claim free daily bonus coins with /dailycoins!")
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="dailycoins", description="Claim daily 250 free bonus Tillu Coins")
async def slash_dailycoins(interaction: discord.Interaction):
    ok, msg, bal = prediction_economy.claim_daily(interaction.user.id, interaction.user.display_name)
    if ok:
        await safe_send_interaction(interaction, f"🎁 {msg}\n💰 Naya balance: **{bal:,}** coins!")
    else:
        await safe_send_interaction(interaction, f"⏳ {msg}", ephemeral=True)

@bot.tree.command(name="coinboard", description="Leaderboard of top coin holders in the server")
async def slash_coinboard(interaction: discord.Interaction):
    lb = prediction_economy.get_leaderboard(limit=10)
    if not lb:
        return await safe_send_interaction(interaction, "Abhi leaderboard par koi data nahi hai!", ephemeral=True)
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, coins, won) in enumerate(lb):
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(f"{medal} **{name}** — `{coins:,}` coins *(Won: {won:,})*")
    embed = discord.Embed(
        title="🏆 Tillu Coin Leaderboard — High Rollers",
        description="\n".join(lines),
        color=0xF1C40F
    )
    await safe_send_interaction(interaction, embed=embed)

# ── VIEWER LEVELING & LOYALTY SLASH COMMANDS ─────────────────────────────────
@bot.tree.command(name="rank", description="Check your or another member's stream viewer level, XP, and badges")
@app_commands.describe(user="The member whose rank to view")
async def slash_rank(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    card = loyalty_system.format_rank_card(target.id, target.display_name)
    embed = discord.Embed(
        title=f"🎖️ {target.display_name}'s Viewer Rank",
        description=f"**Title:** `{card['title']}`\n**Level:** `{card['level']}`\n\n**XP Progress:** `{card['xp']:,}` XP\n`{card['progress_bar']}` `{card['progress_percent']:.1f}%`\n*(+{card['xp_needed'] - card['xp_gained']:,} XP to Level {card['level']+1})*",
        color=0x9B59B6
    )
    embed.add_field(name="Chat Messages", value=f"`{card['messages']:,}`", inline=True)
    embed.add_field(name="Voice Time", value=f"`{card['voice_hours']:.1f} hrs`", inline=True)
    badge_str = " ".join([f"{b['emoji']} **{b['name']}**" for b in card['badges']]) if card['badges'] else "*None unlocked yet*"
    embed.add_field(name="Unlocked Badges", value=badge_str, inline=False)
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="topviewers", description="Leaderboard of most active stream viewers and chatters")
async def slash_topviewers(interaction: discord.Interaction):
    top = loyalty_system.get_top_viewers(limit=10)
    if not top:
        return await safe_send_interaction(interaction, "Abhi top viewers par koi data nahi hai!", ephemeral=True)
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, lvl, xp, badge_emojis) in enumerate(top):
        m = medals[i] if i < 3 else f"`#{i+1}`"
        b_str = " " + "".join(badge_emojis) if badge_emojis else ""
        lines.append(f"{m} **{name}**{b_str} — **Level {lvl}** (`{xp:,}` XP)")
    embed = discord.Embed(
        title="🌟 Top Community Viewers & Chatters",
        description="\n".join(lines),
        color=0xE67E22
    )
    embed.set_footer(text="Earn XP by chatting in Discord and hanging out in Voice Channels!")
    await safe_send_interaction(interaction, embed=embed)

@bot.tree.command(name="help", description="Show Tillu bot commands & features")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Tillu Bot — Stream Co-Host & Community Assistant",
        description="I am Tillu, your sarcastic & witty co-host! Here's how you can talk to me:",
        color=0x9B59B6
    )
    embed.add_field(name="💬 Chat Naturally", value="Just type `tillu <question>` or `@Tillu <question>` anywhere in chat!", inline=False)
    embed.add_field(name="🎙️ Voice AI Co-Host", value="`/joinvc`, `/leavevc`, `/speak <text>`, `/vcroast [user]`, `/vchype`", inline=False)
    embed.add_field(name="🎲 Predictions & Coins", value="`/predict`, `/bet`, `/predictions`, `/coins`, `/dailycoins`, `/coinboard`", inline=False)
    embed.add_field(name="🎖️ Leveling & Badges", value="`/rank [@user]`, `/topviewers` — Earn XP by chatting and voice hangout", inline=False)
    embed.add_field(name="📺 YouTube Live Timings", value="`/livetiming` or `!livetiming` — Live stream updates for @AALU_CHIPAS", inline=False)
    embed.add_field(name="👥 Member Directory", value="`/members [role]` and `/tagmember <name>` to find & tag anyone!", inline=False)
    embed.add_field(name="🎮 Game Analytics", value="`/gamehistory [@user]` and `/topgames` to track gaming history", inline=False)
    embed.add_field(name="🤖 Inter-Bot Power", value="`/usebot <command>` or `tillu tell <bot> to <action>` to command other bots", inline=False)
    embed.add_field(name="🎭 Dynamic Mood & Memes", value="`/mood` and `/meme [category]` from Tillu's 130+ meme vault", inline=False)
    embed.add_field(name="🧠 Teach & Remember", value="`tillu yaad rakh <baat>` or `/remember <fact>`", inline=False)
    embed.add_field(name="🔍 Daily Self-Audit", value="`/audit` to trigger Tillu's autonomous self-reflection & bot discovery", inline=False)
    embed.set_footer(text="Tillu • 24/7 Always-Online Co-Host")
    await safe_send_interaction(interaction, embed=embed, view=CommunityView(), ephemeral=True)

# ── TEXT COMMANDS ────────────────────────────────────────────────────────────
@bot.command(name="update", aliases=["pull", "gitpull", "selfupdate"])
async def cmd_update(ctx):
    """Pulls latest updates from GitHub and auto-restarts the bot (Server Owner & Admins only)."""
    if not is_privileged_user(ctx.author, ctx.guild):
        return await ctx.send("🚫 Sirf Server Owner ya Administrators hi Tillu ko update kar sakte hain!")

    msg = await ctx.send("🔄 **Tillu Self-Update in progress...** Pulling latest code from GitHub `main`...")
    try:
        import subprocess, sys, os
        res = await asyncio.to_thread(
            subprocess.run,
            ["git", "pull", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30
        )
        out = (res.stdout or "") + (res.stderr or "")
        logging.info(f"[SelfUpdate] Git pull result:\n{out}")

        await msg.edit(content=f"✅ **GitHub Update Pulled!**\n```\n{out[:400]}\n```\n🚀 Restarting Tillu process now...")
        await asyncio.sleep(1.0)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        logging.error(f"[SelfUpdate Error]: {e}")
        await msg.edit(content=f"⚠️ Update failed: `{e}`. Check console logs.")

@bot.tree.command(name="update", description="Pulls latest updates from GitHub and auto-restarts Tillu (Owner/Admin only)")
async def slash_update(interaction: discord.Interaction):
    if not is_privileged_user(interaction.user, interaction.guild):
        return await safe_send_interaction(interaction, "🚫 Only Server Owner and Administrators can update Tillu!", ephemeral=True)

    await safe_send_interaction(interaction, "🔄 **Tillu Self-Update in progress...** Pulling latest code from GitHub `main`...", ephemeral=False)
    try:
        import subprocess, sys, os
        res = await asyncio.to_thread(
            subprocess.run,
            ["git", "pull", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30
        )
        out = (res.stdout or "") + (res.stderr or "")
        logging.info(f"[SelfUpdate] Git pull result:\n{out}")

        await interaction.followup.send(f"✅ **GitHub Update Pulled!**\n```\n{out[:400]}\n```\n🚀 Restarting Tillu process now...")
        await asyncio.sleep(1.0)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        logging.error(f"[SelfUpdate Error]: {e}")
        await interaction.followup.send(f"⚠️ Update failed: `{e}`.")

@bot.tree.command(name="reload", description="Soft-reload all Tillu submodules in-memory without restarting container (Admin only)")
async def slash_reload(interaction: discord.Interaction):
    if not is_privileged_user(interaction.user, interaction.guild):
        return await safe_send_interaction(interaction, "🚫 Only Server Owner and Administrators can reload Tillu!", ephemeral=True)

    await safe_send_interaction(interaction, "⚡ **Soft-reloading Tillu modules in-memory...**", ephemeral=False)
    results = await asyncio.to_thread(hot_reloader.reload_all)
    
    ok_count = sum(1 for v in results.values() if "Reloaded" in v or "Imported" in v)
    total_count = len(results)
    
    lines = [f"• `{mod}`: {status}" for mod, status in results.items()]
    summary = "\n".join(lines[:12])
    
    embed = discord.Embed(
        title="⚡ Tillu In-Memory Soft-Reload Complete",
        description=f"Successfully soft-reloaded **{ok_count}/{total_count}** submodules without restarting the container!\n\n{summary}",
        color=0x00FF88
    )
    embed.set_footer(text="Google Antigravity & Discord Gateway stayed live with zero downtime!")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="restart", description="Perform an in-place Python process reboot without stopping the container (Admin only)")
async def slash_restart(interaction: discord.Interaction):
    if not is_privileged_user(interaction.user, interaction.guild):
        return await safe_send_interaction(interaction, "🚫 Only Server Owner and Administrators can restart Tillu!", ephemeral=True)

    await safe_send_interaction(interaction, "🔄 **Restarting Tillu process in-place...** Container will remain online.", ephemeral=False)
    await asyncio.sleep(1.0)
    os.execv(sys.executable, [sys.executable] + sys.argv)

@bot.command(name="audit", aliases=["selfaudit", "auditreport"])
async def cmd_audit(ctx):
    if not is_privileged_user(ctx.author, ctx.guild):
        return await ctx.send("🚫 Sirf Server Owner aur Moderators hi self-audit trigger kar sakte hain!")

    msg = await ctx.send("🔍 **Tillu Self-Audit Initiated...** Analyzing recent tasks and error patterns...")
    def _llm_reflect(prompt_text):
        return query_gemini(prompt_text, "TilluAuditor", is_admin=True, is_owner_user=True)

    res = await reflection_engine.execute_audit_cycle(
        prompt_mgr=prompt_mgr,
        rule_mgr=rule_mgr,
        llm_reflection_fn=_llm_reflect
    )
    embed = discord.Embed(
        title=f"🧠 Tillu Self-Audit Report #{reflection_engine.audit_counter}",
        description=(
            f"**Task Performance Diagnostics:**\n"
            f"• Tasks Evaluated: **{res.get('total_tasks', 0)}**\n"
            f"• Success Rate: **{res.get('success_rate', 100.0)}%** (`{res.get('success_count', 0)}` OK / `{res.get('fail_count', 0)}` Failed)\n"
            f"• Classification Routing: `{json.dumps(res.get('system_breakdown', {}))}`\n\n"
            f"**AI Diagnostics & Self-Improvement:**\n> {res.get('ai_reflection', 'Baseline stable')[:800]}"
        ),
        color=0x2ECC71 if res.get('success_rate', 100.0) >= 90 else 0xE67E22,
        timestamp=discord.utils.utcnow()
    )
    if res.get("auto_learned_improvement"):
        embed.add_field(name="🚀 Auto-Learned Robustness Rule", value=f"`{res.get('auto_learned_improvement')}`", inline=False)
    embed.set_footer(text="5x Daily Autonomous Evolution Loop • Synced to GitHub")
    await msg.edit(content=None, embed=embed)

@bot.command(name="pause")
async def cmd_pause(ctx):
    global TILLU_PAUSED
    TILLU_PAUSED = True
    await ctx.send("⏸️ **Tillu Paused!** Main chup ho gaya hu. Wapas bulane ke liye `!resume` ya `tillu resume` bol dena.")

@bot.command(name="resume", aliases=["unpause"])
async def cmd_resume(ctx):
    global TILLU_PAUSED
    TILLU_PAUSED = False
    opener = meme_engine.get_fresh_opener()
    memes = meme_engine.pick_fresh_memes("funny", count=1)
    meme_line = f" ({memes[0]['text']})" if memes else ""
    await ctx.send(f"▶️ **Tillu Resumed!** {opener} Main wapas active hu!{meme_line} 🚀")

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

@bot.command(name="livetiming", aliases=["stream", "live", "timing", "youtube"])
async def cmd_livetiming(ctx):
    await handle_livetiming_request(ctx)

@bot.command(name="members", aliases=["memberlist", "who"])
async def cmd_members(ctx, *, role: str = None):
    await handle_members_request(ctx, role_filter=role)

@bot.command(name="gamehistory", aliases=["gh", "history", "games"])
async def cmd_gamehistory(ctx, member: discord.Member = None):
    await handle_gamehistory_request(ctx, target_user=member)

@bot.command(name="topgames", aliases=["leaderboard", "populargames"])
async def cmd_topgames(ctx):
    await handle_topgames_request(ctx)

@bot.command(name="mood", aliases=["setmood", "personality"])
async def cmd_mood(ctx, *, mood_name: str = None):
    if mood_name and is_privileged_user(ctx.author, ctx.guild):
        m = mood_engine.set_fixed_mood(mood_name)
        await ctx.send(f"🎭 Tillu ka mood set ho gaya: **{m.value.upper()}**!")
    else:
        curr = mood_engine.current_mood.value
        await ctx.send(f"🎭 Tillu's current dynamic mood is **{curr.upper()}**!\n(Available moods: `sarcastic`, `funny`, `sad_sarcastic`, `wholesome`, `savage`)")

@bot.command(name="meme", aliases=["dropmeme", "roastme"])
async def cmd_meme(ctx, *, category: str = None):
    memes = meme_engine.pick_fresh_memes(category, count=1)
    if not memes:
        return await ctx.send("Koi meme nahi mila bhai!")
    m = memes[0]
    opener = meme_engine.get_fresh_opener()
    embed = discord.Embed(
        title=f"🎭 {m['origin']}",
        description=f"### \"{m['text']}\"\n\n*{opener} Tillu special drop!*",
        color=0x9B59B6
    )
    embed.set_footer(text=f"Category: {m['category'].upper()} • 130+ Tillu Meme Vault")
    await ctx.send(embed=embed)

@bot.command(name="memestats", aliases=["memecount", "memes"])
async def cmd_memestats(ctx):
    total = meme_engine.get_total_count()
    cats = meme_engine.get_category_counts()
    lines = [f"• **{cat.capitalize()}**: `{cnt}` memes" for cat, cnt in cats.items()]
    embed = discord.Embed(
        title=f"🎭 Tillu's 130+ Meme Vault ({total} Total)",
        description="Tillu's anti-repetition engine actively cycles across 130+ curated memes to ensure 100% variety in every response:\n\n" + "\n".join(lines),
        color=0x2ECC71
    )
    embed.set_footer(text="Anti-Repetition & Variety Engine Active • Synced to GitHub")
    await ctx.send(embed=embed)

@bot.command(name="addbot", aliases=["invitebot", "botinvite"])
async def cmd_addbot(ctx, *, bot_query: str = None):
    """Generate secure 1-click OAuth2 invite link to add any bot to the server (Moderator+ only)."""
    if not is_privileged_user(ctx.author, ctx.guild):
        await ctx.send("🚫 **Permission Denied!** Sirf Server Owner, Admins aur Moderators hi server me naye bots invite kar sakte hain!")
        return
    if not bot_query:
        await ctx.send("❌ Usage: `!addbot <bot_name or bot_application_id>`\nPopular bots: `carl-bot`, `dyno`, `mee6`, `probot`, `ticket tool`, `disboard`, `jockie music`, `rythm`, etc.")
        return
    from discord_action_manager import handle_add_bot_action
    embed, view, msg = handle_add_bot_action(ctx.guild, ctx.author, bot_query)
    if embed:
        await ctx.send(embed=embed, view=view)
    else:
        await ctx.send(msg)

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

@bot.command(name="start", aliases=["startserver", "turnon", "on"])
async def cmd_start(ctx):
    await handle_start_request(ctx, user=ctx.author, guild=ctx.guild)

@bot.command(name="status", aliases=["online", "server", "ip", "info"])
async def cmd_status(ctx):
    await handle_status_request(ctx, user=ctx.author, guild=ctx.guild)

@bot.command(name="whitelist", aliases=["wl", "addwhitelist"])
async def cmd_whitelist(ctx, *, ign: str = None):
    await handle_whitelist_request(ctx, ign, user=ctx.author, guild=ctx.guild)

# ── VOICE CHANNEL AI CO-HOST PREFIX COMMANDS ─────────────────────────────────
@bot.command(name="joinvc", aliases=["connectvc", "vcin"])
async def cmd_joinvc(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Pehle kisi voice channel me connect ho jao!")
    ok, msg, _ = await voice_cohost.join_channel(ctx.author.voice.channel)
    await ctx.send(f"🎙️ {msg}")

@bot.command(name="leavevc", aliases=["disconnectvc", "vcout"])
async def cmd_leavevc(ctx):
    ok, msg = await voice_cohost.leave_channel(ctx.guild)
    await ctx.send(f"🎙️ {msg}")

@bot.command(name="speak", aliases=["sayvc", "vcsay"])
async def cmd_speak(ctx, *, text: str = None):
    if not text:
        return await ctx.send("❌ Usage: `!speak <text>`")
    if not ctx.guild.voice_client:
        return await ctx.send("❌ Tillu voice channel me nahi hai! Pehle `!joinvc` karo.")
    ok, msg = await voice_cohost.speak_text(ctx.guild, text)
    await ctx.send(f"🎙️ {msg}")

@bot.command(name="vcroast", aliases=["roastvc"])
async def cmd_vcroast(ctx, *, target: str = None):
    if not ctx.guild.voice_client:
        return await ctx.send("❌ Tillu voice channel me nahi hai! Pehle `!joinvc` karo.")
    target_name = target or ctx.author.display_name
    ok, msg, script = await voice_cohost.speak_roast(ctx.guild, target_name)
    await ctx.send(f"🔥 **Tillu VC Roast ({target_name}):**\n> *\"{script}\"*")

@bot.command(name="vchype", aliases=["hypevc"])
async def cmd_vchype(ctx):
    if not ctx.guild.voice_client:
        return await ctx.send("❌ Tillu voice channel me nahi hai! Pehle `!joinvc` karo.")
    ok, msg, script = await voice_cohost.speak_hype(ctx.guild, streamer_name="Aalu")
    await ctx.send(f"⚡ **Stream Clutch Hype:**\n> *\"{script}\"*")

# ── STREAM PREDICTION & ECONOMY PREFIX COMMANDS ──────────────────────────────
@bot.command(name="predict", aliases=["newpred"])
async def cmd_predict(ctx, *, args: str = None):
    """Create a stream prediction. Format: !predict Question | Option A | Option B [| minutes]"""
    if not args:
        return await ctx.send("❌ Usage: `!predict <Question> | <Option A> | <Option B> [| minutes]`")
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 3:
        return await ctx.send("❌ Usage: `!predict <Question> | <Option A> | <Option B> [| minutes]`")
    question = parts[0]
    opt_a = parts[1]
    opt_b = parts[2]
    minutes = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 5
    pred = prediction_economy.create_prediction(
        guild_id=ctx.guild.id,
        question=question,
        option_a=opt_a,
        option_b=opt_b,
        duration_minutes=minutes,
        creator_name=ctx.author.display_name
    )
    embed = discord.Embed(
        title=f"🎲 Stream Prediction: {question}",
        description=(
            f"**ID:** `{pred['id']}`\n\n"
            f"🅰️ **Option A:** `{opt_a}`\n"
            f"🅱️ **Option B:** `{opt_b}`\n\n"
            f"⏱️ **Betting Closes:** <t:{int(pred['ends_at'])}:R>\n"
            f"👉 Bet: `!bet {pred['id']} A 100`"
        ),
        color=0xF1C40F
    )
    embed.set_footer(text=f"Created by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command(name="bet")
async def cmd_bet(ctx, prediction_id: str = None, option: str = None, amount: int = None):
    if not prediction_id or not option or amount is None:
        return await ctx.send("❌ Usage: `!bet <prediction_id> <A|B> <amount>`")
    ok, msg, res = prediction_economy.place_bet(
        user_id=ctx.author.id,
        prediction_id=prediction_id,
        option_choice=option,
        amount=amount,
        user_name=ctx.author.display_name
    )
    if not ok:
        return await ctx.send(f"❌ {msg}")
    await ctx.send(f"🪙 **Bet Placed!** `{amount:,}` coins on `{res.get('chosen_label', option.upper())}` for prediction `{prediction_id}`! (Remaining: `{res.get('remaining_balance', 0):,}` coins)")

@bot.command(name="resolvepred", aliases=["resolveprediction", "endpred"])
async def cmd_resolvepred(ctx, prediction_id: str = None, winning_option: str = None):
    if not is_privileged_user(ctx.author, ctx.guild):
        return await ctx.send("🚫 Sirf Server Owner ya Admins prediction resolve kar sakte hain!")
    if not prediction_id or not winning_option:
        return await ctx.send("❌ Usage: `!resolvepred <prediction_id> <A|B|CANCEL>`")
    ok, msg, res = prediction_economy.resolve_prediction(prediction_id, winning_option)
    if not ok:
        return await ctx.send(f"❌ {msg}")
    embed = discord.Embed(
        title="🏆 Stream Prediction Resolved!",
        description=(
            f"**Question:** `{res.get('question')}`\n"
            f"**Winner:** `{res.get('winning_label', winning_option.upper())}`\n"
            f"💰 **Total Prize Pool:** `{res.get('total_pool', 0):,}` coins\n"
            f"👥 **Winners Paid:** `{res.get('payouts_count', 0)}` members"
        ),
        color=0xF39C12
    )
    await ctx.send(embed=embed)

@bot.command(name="predictions", aliases=["activepredictions", "preds", "bets"])
async def cmd_predictions(ctx):
    active = prediction_economy.get_active_predictions(ctx.guild.id)
    if not active:
        return await ctx.send("Abhi koi active stream prediction nahi chal rahi! `!predict` use karke create karo.")
    embed = discord.Embed(title="🎲 Active Stream Predictions", color=0x3498DB)
    for p in active[:5]:
        status = "🟢 OPEN" if p.get("status") == "OPEN" else "🔒 CLOSED"
        pool = p.get("pool_a", 0) + p.get("pool_b", 0)
        embed.add_field(
            name=f"`{p['id']}`: {p['question']} ({status})",
            value=f"• **[A]** {p['option_a']}: `{p.get('pool_a', 0):,}` coins\n• **[B]** {p['option_b']}: `{p.get('pool_b', 0):,}` coins\n• **Pool:** `{pool:,}` coins | Closes: <t:{int(p['ends_at'])}:R>",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="coins", aliases=["bal", "balance", "wallet"])
async def cmd_coins(ctx, member: discord.Member = None):
    target = member or ctx.author
    w = prediction_economy.get_wallet(target.id, target.display_name)
    embed = discord.Embed(
        title=f"🪙 {target.display_name}'s Coin Wallet",
        color=0xF1C40F
    )
    embed.add_field(name="Current Balance", value=f"**{w.get('coins', 0):,}** coins", inline=True)
    embed.add_field(name="Total Won", value=f"**{w.get('total_won', 0):,}** coins", inline=True)
    embed.add_field(name="Total Bet", value=f"**{w.get('total_bet', 0):,}** coins", inline=True)
    embed.set_footer(text="Claim free daily bonus coins with !dailycoins!")
    await ctx.send(embed=embed)

@bot.command(name="dailycoins", aliases=["daily"])
async def cmd_dailycoins(ctx):
    ok, msg, bal = prediction_economy.claim_daily(ctx.author.id, ctx.author.display_name)
    if ok:
        await ctx.send(f"🎁 {msg}\n💰 Naya balance: **{bal:,}** coins!")
    else:
        await ctx.send(f"⏳ {msg}")

@bot.command(name="coinboard", aliases=["rich", "topcoins"])
async def cmd_coinboard(ctx):
    lb = prediction_economy.get_leaderboard(limit=10)
    if not lb:
        return await ctx.send("Abhi leaderboard par koi data nahi hai!")
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, coins, won) in enumerate(lb):
        m = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(f"{m} **{name}** — `{coins:,}` coins *(Won: {won:,})*")
    embed = discord.Embed(
        title="🏆 Tillu Coin Leaderboard — High Rollers",
        description="\n".join(lines),
        color=0xF1C40F
    )
    await ctx.send(embed=embed)

# ── VIEWER LEVELING & LOYALTY PREFIX COMMANDS ────────────────────────────────
@bot.command(name="rank", aliases=["level", "xp", "lvl"])
async def cmd_rank(ctx, member: discord.Member = None):
    target = member or ctx.author
    card = loyalty_system.format_rank_card(target.id, target.display_name)
    embed = discord.Embed(
        title=f"🎖️ {target.display_name}'s Viewer Rank",
        description=f"**Title:** `{card['title']}`\n**Level:** `{card['level']}`\n\n**XP Progress:** `{card['xp']:,}` XP\n`{card['progress_bar']}` `{card['progress_percent']:.1f}%`\n*(+{card['xp_needed'] - card['xp_gained']:,} XP to Level {card['level']+1})*",
        color=0x9B59B6
    )
    embed.add_field(name="Chat Messages", value=f"`{card['messages']:,}`", inline=True)
    embed.add_field(name="Voice Time", value=f"`{card['voice_hours']:.1f} hrs`", inline=True)
    badge_str = " ".join([f"{b['emoji']} **{b['name']}**" for b in card['badges']]) if card['badges'] else "*None unlocked yet*"
    embed.add_field(name="Unlocked Badges", value=badge_str, inline=False)
    await ctx.send(embed=embed)

@bot.command(name="topviewers", aliases=["viewerboard", "topchatters"])
async def cmd_topviewers(ctx):
    top = loyalty_system.get_top_viewers(limit=10)
    if not top:
        return await ctx.send("Abhi top viewers par koi data nahi hai!")
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, lvl, xp, badge_emojis) in enumerate(top):
        m = medals[i] if i < 3 else f"`#{i+1}`"
        b_str = " " + "".join(badge_emojis) if badge_emojis else ""
        lines.append(f"{m} **{name}**{b_str} — **Level {lvl}** (`{xp:,}` XP)")
    embed = discord.Embed(
        title="🌟 Top Community Viewers & Chatters",
        description="\n".join(lines),
        color=0xE67E22
    )
    embed.set_footer(text="Earn XP by chatting in Discord and hanging out in Voice Channels!")
    await ctx.send(embed=embed)

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(
        title="🤖 Tillu Bot — Stream Co-Host & Community Assistant",
        description="I am Tillu, your sarcastic & witty co-host! Here's how you can talk to me:",
        color=0x9B59B6
    )
    embed.add_field(name="💬 Chat Naturally", value="Just type `tillu <question>` or `@Tillu <question>` anywhere in chat!", inline=False)
    embed.add_field(name="🎙️ Voice AI Co-Host", value="`!joinvc`, `!leavevc`, `!speak <text>`, `!vcroast [user]`, `!vchype`", inline=False)
    embed.add_field(name="🎲 Predictions & Coins", value="`!predict`, `!bet`, `!predictions`, `!coins`, `!dailycoins`, `!coinboard`", inline=False)
    embed.add_field(name="🎖️ Leveling & Badges", value="`!rank [@user]`, `!topviewers` — Earn XP by chatting and voice hangout", inline=False)
    embed.add_field(name="📺 YouTube Live Timings", value="`!livetiming` or `/livetiming` — Live stream updates for @AALU_CHIPAS", inline=False)
    embed.add_field(name="👥 Member Directory", value="`!members [role]` and `/tagmember <name>` to find & tag anyone!", inline=False)
    embed.add_field(name="🎮 Game Analytics", value="`!gamehistory [@user]` and `!topgames` to track gaming history", inline=False)
    embed.add_field(name="🤖 Inter-Bot Power", value="`!botcmd <cmd>` or `/usebot <cmd>` to command other bots", inline=False)
    embed.add_field(name="🎭 Dynamic Mood & Memes", value="`!mood` and `!meme [category]` from Tillu's 130+ meme vault", inline=False)
    embed.add_field(name="🧠 Teach & Remember", value="`tillu yaad rakh <baat>` or `/remember <fact>`", inline=False)
    embed.add_field(name="📖 View Memories", value="`/memories` to see learned knowledge", inline=False)
    embed.set_footer(text="Tillu • 24/7 Always-Online Co-Host")
    await ctx.send(embed=embed, view=CommunityView())

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

    # ── AUTONOMOUS BOT DISCOVERY & CAPABILITY LEARNING ───────────────────────
    if member.bot:
        try:
            logging.info(f"[New Bot Joined] Detected bot '{member.name}' ({member.id}) in guild '{guild.name}'. Analyzing...")
            profile = await bot_orch.analyze_and_register_bot(member, guild)
            bot_orch.bots[str(member.id)] = profile
            bot_orch.save()

            update_ch = await get_or_create_update_channel(guild)
            if update_ch:
                embed = discord.Embed(
                    title=f"🤖 New Discord Bot Integrated: {member.name}",
                    description=(
                        f"Tillu has autonomously analyzed `{member.name}` ({member.mention}):\n\n"
                        f"• **Category:** `{profile.get('category')}`\n"
                        f"• **Command Prefix:** `{', '.join(profile.get('prefix', ['!']))}`\n"
                        f"• **Capabilities Learned:** {', '.join(profile.get('skills', [])[:5]) or 'Utility commands'}\n"
                        f"• **Summary:** {profile.get('description')}\n\n"
                        f"Tillu can now collaborate with and control `{member.name}`! Use `tillu tell {member.name} to <action>` 🚀"
                    ),
                    color=0x2ECC71,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="Tillu Autonomous Bot Orchestrator • Synced to GitHub")
                await update_ch.send(embed=embed)
        except Exception as be:
            logging.error(f"[on_member_join Bot Analysis] Error: {be}")
        return
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
            f"Mai hu **Tillu**, aapka sarcastic & witty co-host! 🤖\n\n"
            f"• Aalu ki YouTube live stream timings janne ke liye `/livetiming` type karo!\n"
            f"• Server me kaun kya khel raha hai dekhne ke liye `/topgames` ya `/gamehistory` check karo!\n"
            f"• Kisi bhi cheez ke liye bas `@Tillu` bol ke chat me pooch lo! 🚀"
        )
        try:
            await channel.send(welcome_text)
        except Exception as e:
            logging.error(f"[on_member_join] Error sending welcome: {e}")

@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    """Tracks member gaming presence into public game history."""
    try:
        player_analytics.record_presence(after)
    except Exception as e:
        logging.debug(f"[Presence Update] Error: {e}")

async def handle_players_command(channel, user=None):
    """Redirects legacy !players command to top games and active community players."""
    top_games = player_analytics.get_top_games()
    embed = discord.Embed(
        title="🎮 Community Top Games & Player Activity",
        description="Ye hai humari community ka live gaming leaderboard & activity:",
        color=0x2ECC71,
        timestamp=discord.utils.utcnow()
    )
    if not top_games:
        embed.description += "\n\n*Abhi tak koi game play session record nahi hua!*"
    else:
        lines = []
        for i, (g_name, p_count, hours) in enumerate(top_games, start=1):
            lines.append(f"**{i}. {g_name}** — `{p_count} players` (~{hours} hrs logged)")
        embed.add_field(name="Leaderboard", value="\n".join(lines), inline=False)
    await channel.send(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    # Only ignore Tillu himself to prevent self-looping (allow access/interaction with other bots)
    if bot.user and message.author.id == bot.user.id:
        return

    raw_text = message.content or ""
    if not raw_text and message.embeds:
        raw_text = " ".join([e.description or "" for e in message.embeds if e.description])

    # Record member gaming presence & award chat XP
    if not message.author.bot and isinstance(message.author, discord.Member):
        try:
            player_analytics.record_presence(message.author)
        except Exception:
            pass
        try:
            leveled_up, new_lvl, _ = loyalty_system.add_message_xp(message.author.id, message.author.display_name)
            if leveled_up and new_lvl in (5, 10, 20, 25, 50, 100):
                await message.channel.send(f"🎉 **Level Up!** Wah re cheete {message.author.mention}! Level `{new_lvl}` unlock ho gaya tera! 🎖️")
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

    # ── MINECRAFT QUERY INTERCEPT ──────────────────────────────────────────────
    clean_action_text = re.sub(r'^(?:hey\s+)?(?:tillu|mr\.?\s*tillu)[,\s]*', '', message.content, flags=re.IGNORECASE).strip()
    if any(w in clean_action_text.lower() for w in ["claim blocks", "claim land", "land claim", "give claim", "claimblocks"]):
        await message.channel.send(mood_engine.format_mood_response(
            "Arre bhai, Minecraft server permanently delete ho chuka hai! Ab koi claims ya blocks ki zaroorat nahi hai. Aalu YouTube streams par live game khelta hai! 📺🎮"
        ))
        return

    # ── AUTONOMOUS DISCORD MANAGEMENT ACTIONS (Roles, Channels, Message Deletions, Timeouts) ──
    if is_privileged_user(message.author, message.guild):
        # Strip "tillu" prefix so regex patterns match cleanly
        action_text = clean_action_text
        # Also normalize "named:-" / "named :-" / "named:" to "named "
        action_text = re.sub(r'\bnamed?\s*[:\-]+\s*', 'named ', action_text, flags=re.IGNORECASE)
        action_text = re.sub(r'\bcalled?\s*[:\-]+\s*', 'called ', action_text, flags=re.IGNORECASE)

        # GUARD: Check context classifier - if this is targeting Minecraft, skip Discord management!
        classification = classify_request(action_text, channel_name=getattr(message.channel, 'name', ''))
        if classification.system != TargetSystem.MINECRAFT:
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
        opener = meme_engine.get_fresh_opener()
        memes = meme_engine.pick_fresh_memes("funny", count=1)
        meme_line = f" ({memes[0]['text']})" if memes else ""
        await message.channel.send(f"▶️ **Tillu Resumed!** {opener} Main wapas active hu!{meme_line} 🚀")
        return

    # If Tillu is paused, ignore all messages
    if TILLU_PAUSED:
        return

    # ── OWNER COMMANDS (EXPLICIT SILENT MODE TOGGLE) ───────────────────────────
    if author_is_owner and re.search(r'^(?:tillu\s+)?(?:owner\s*only\s*mode\s*on|enable\s*owner\s*only)$', content_lower):
        OWNER_ONLY_MODE = True
        await message.channel.send("🤫 **Yes Boss (Avinash)!** Owner-only mode ON ho gaya. Ab se main **sirf aapki sununga**.")
        return

    if author_is_owner and re.search(r'^(?:tillu\s+)?(?:owner\s*only\s*mode\s*off|disable\s*owner\s*only|everyone\s*mode)$', content_lower):
        OWNER_ONLY_MODE = False
        await message.channel.send("🚀 **Boss ka green signal aa gaya!** Tillu is back in action for everyone! Sab log sawaal pucho.")
        return

    # ── TILLU AUDIT COMMAND (Natural language or !audit) ───────────────────────
    if (author_is_owner or is_privileged_user(author, message.guild)) and (
        re.search(r'^(?:hey\s+|arre\s+)?(?:tillu|mr\s*tillu)?\s*(?:audit|self\s*audit|audit\s*report)$', content_lower)
        or content_lower in ["!audit", "tillu audit", "!selfaudit"]
    ):
        msg = await message.channel.send("🔍 **Tillu Self-Audit Initiated...** Analyzing recent tasks and error patterns...")
        def _llm_reflect(prompt_text):
            return query_gemini(prompt_text, "TilluAuditor", is_admin=True, is_owner_user=True)

        res = await reflection_engine.execute_audit_cycle(
            prompt_mgr=prompt_mgr,
            rule_mgr=rule_mgr,
            llm_reflection_fn=_llm_reflect
        )
        embed = discord.Embed(
            title=f"🧠 Tillu Self-Audit Report #{reflection_engine.audit_counter}",
            description=(
                f"**Task Performance Diagnostics:**\n"
                f"• Tasks Evaluated: **{res.get('total_tasks', 0)}**\n"
                f"• Success Rate: **{res.get('success_rate', 100.0)}%** (`{res.get('success_count', 0)}` OK / `{res.get('fail_count', 0)}` Failed)\n"
                f"• Classification Routing: `{json.dumps(res.get('system_breakdown', {}))}`\n\n"
                f"**AI Diagnostics & Self-Improvement:**\n> {res.get('ai_reflection', 'Baseline stable')[:800]}"
            ),
            color=0x2ECC71 if res.get('success_rate', 100.0) >= 90 else 0xE67E22,
            timestamp=discord.utils.utcnow()
        )
        if res.get("auto_learned_improvement"):
            embed.add_field(name="🚀 Auto-Learned Robustness Rule", value=f"`{res.get('auto_learned_improvement')}`", inline=False)
        embed.set_footer(text="5x Daily Autonomous Evolution Loop • Synced to GitHub")
        await msg.edit(content=None, embed=embed)
        return

    # ── LOOSENED CHAT & TRIGGER RECOGNITION (Chat freely with all members) ───
    ch_name_lower = getattr(message.channel, "name", "").lower()
    is_bot_channel = any(k in ch_name_lower for k in ["tillu", "bot", "ai-chat", "talk-to-tillu", "chat-with-tillu"])
    is_recent_conv = (time.time() - last_channel_activity.get(message.channel.id, 0)) < 45

    match_tillu = bool(re.search(
        r'\b(tillu|mr\s*tillu|mrtillu|tilu|tillo|tilloo|tiloo|tllu|tillu\s*bhai|tillu\s*ji)\b'
        r'|(?:hey|hi|hello|arre|oye|bhai|sun)\s+(?:tillu|bot)\b'
        r'|\b(?:bot\s+bhai|tillu\s+bot)\b',
        content,
        re.IGNORECASE
    ))

    # Whitelist channel dedicated check
    is_whitelist_channel = (
        message.channel.id == WHITELIST_CHANNEL_ID
        or "whitelist" in getattr(message.channel, "name", "").lower()
    )

    # Check if message is addressed to Tillu:
    # 1. Mentioned (@Tillu)
    # 2. Reply to Tillu
    # 3. Explicitly named "tillu" or spelling variants / bot call
    # 4. In dedicated bot/tillu channels
    # 5. Conversation continuity (follow-up within 45s of Tillu's reply)
    is_addressed_to_tillu = (
        is_mentioned
        or is_reply_to_bot
        or match_tillu
        or is_bot_channel
        or (is_recent_conv and not is_reply_to_other)
    )

    # If in whitelist channel and someone typed pure IGN:
    if is_whitelist_channel:
        clean_word = content.strip().replace('"', '').replace("'", "").replace("`", "")
        if (
            re.match(r'^[a-zA-Z0-9_.* ]{3,20}$', clean_word)
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

    # ── SELF-UPDATE COMMAND (Owner & Admin only) ──────────────────────────────
    clean_q = query.lower().strip()
    if clean_q in ["update", "pull", "git pull", "update yourself", "self update", "pull latest code", "tillu update"]:
        ctx = await bot.get_context(message)
        await cmd_update(ctx)
        return

    # ── LIVE MINECRAFT PLAYERS CHECK (Natural language intent) ─────────────────
    is_standalone_players_cmd = (
        clean_q in ["players", "online", "list", "who is playing", "who is online", "kaun khel raha hai", "online players", "list players", "kaun online hai", "players online"]
        or (
            len(clean_q.split()) <= 7
            and bool(re.match(r'^(?:who\s+is\s+(?:playing|online)|list\s+players?|online\s+players?|kitne\s+(?:players?|log)\s+(?:khel\s+rahe|online)\s+hai|kaun\s+(?:khel\s+raha\s+hai|online\s+hai))', clean_q))
        )
    )
    if is_standalone_players_cmd:
        await handle_players_command(message.channel, message.author)
        return

    # ── NATURAL LANGUAGE VOICE CO-HOST INTENTS ──────────────────────────────
    is_vc_join = bool(re.search(
        r'(?:\bjoin\b.*?\b(?:vc|voice|call)\b|\b(?:vc|voice|call)\b.*?\b(?:join|aao|aa\s*jao|connect)\b)',
        clean_q,
        re.IGNORECASE
    ))
    if is_vc_join:
        if not getattr(message.author, "voice", None) or not message.author.voice.channel:
            opener = meme_engine.get_fresh_opener()
            await message.channel.send(f"❌ {opener} Pehle kisi voice channel me connect ho jao Sarkar, fir bulao!")
            return
        target_vc = message.author.voice.channel
        ok, status_msg, _ = await voice_cohost.join_channel(target_vc)
        opener = meme_engine.get_fresh_opener()
        memes = meme_engine.pick_fresh_memes("funny", count=1)
        meme_quote = f" ({memes[0]['text']})" if memes else ""
        await message.channel.send(f"🎙️ **Tillu VC Connected!** {opener} Main **{target_vc.name}** me aa gaya hoon Boss!{meme_quote}\n*(Commands: `!speak <text>`, `!vcroast`, `!vchype`, `!leavevc`)*")
        try:
            await voice_cohost.speak_text(message.guild, f"Pranam Boss! Tillu voice channel me haazir hai!")
        except Exception as ve:
            logging.debug(f"[AutoSpeak Error] {ve}")
        return

    is_vc_leave = bool(re.search(
        r'(?:\bleave\b.*?\b(?:vc|voice|call)\b|\b(?:vc|voice|call)\b.*?\b(?:leave|niklo|disconnect|chhod\s*do|bahaar\s*niklo)\b|\bdisconnect\s*(?:from\s*)?(?:vc|voice)\b)',
        clean_q,
        re.IGNORECASE
    ))
    if is_vc_leave:
        ok, status_msg = await voice_cohost.leave_channel(message.guild)
        await message.channel.send(f"🎙️ {status_msg}")
        return

    is_vc_roast = bool(re.search(
        r'\b(?:vc\s*roast|roast\s*in\s*vc|vc\s*me\s*roast)\b',
        clean_q,
        re.IGNORECASE
    ))
    if is_vc_roast:
        if not message.guild.voice_client:
            await message.channel.send("❌ Main voice channel me nahi hoon! Pehle `tillu join vc` bolo.")
            return
        target_user = message.mentions[0].display_name if message.mentions else message.author.display_name
        ok, msg, script = await voice_cohost.speak_roast(message.guild, target_user)
        await message.channel.send(f"🔥 **Tillu VC Roast ({target_user}):**\n> *\"{script}\"*")
        return

    is_vc_hype = bool(re.search(
        r'\b(?:vc\s*hype|hype\s*in\s*vc|clutch\s*hype)\b',
        clean_q,
        re.IGNORECASE
    ))
    if is_vc_hype:
        if not message.guild.voice_client:
            await message.channel.send("❌ Main voice channel me nahi hoon! Pehle `tillu join vc` bolo.")
            return
        ok, msg, script = await voice_cohost.speak_hype(message.guild, streamer_name="Aalu")
        await message.channel.send(f"⚡ **Stream Clutch Hype:**\n> *\"{script}\"*")
        return

    speak_match = re.search(
        r'(?:vc\s*me\s*bol(?:o)?|speak\s*in\s*vc|bol\s*vc\s*me)\s*[:\-]?\s*(.+)',
        clean_q,
        re.IGNORECASE
    )
    if speak_match:
        to_speak = speak_match.group(1).strip()
        if not message.guild.voice_client:
            await message.channel.send("❌ Main voice channel me nahi hoon! Pehle `tillu join vc` bolo.")
            return
        ok, msg = await voice_cohost.speak_text(message.guild, to_speak)
        await message.channel.send(f"🎙️ **Tillu:** {msg}\n> *\"{to_speak}\"*")
        return

    try:
        if hasattr(message, "channel") and hasattr(message.channel, "id"):
            last_channel_activity[message.channel.id] = time.time()
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
            if "livetiming" in custom_id or "live" in custom_id:
                await handle_livetiming_request(interaction)
            elif "members" in custom_id:
                await handle_members_request(interaction)
            elif "games" in custom_id or "topgames" in custom_id:
                await handle_topgames_request(interaction)
            elif "status" in custom_id:
                await handle_status_request(interaction, user=interaction.user, guild=interaction.guild)
            elif "start" in custom_id:
                await handle_start_request(interaction, user=interaction.user, guild=interaction.guild)
            elif "whitelist" in custom_id:
                await handle_whitelist_request(interaction, "", user=interaction.user, guild=interaction.guild)

# ── BACKGROUND KEEP-ALIVE HTTP SERVER & GUARDIAN ─────────────────────────────
async def health_handler(request):
    return web.Response(text=json.dumps({"status": "healthy", "service": "Tillu Stream Co-Host Bot", "time": time.time()}), content_type="application/json")

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
            live_info = await asyncio.to_thread(youtube_tracker.check_youtube_live_status)
            if live_info.get("is_live"):
                title = live_info.get("title") or "Streaming Live!"
                activity = discord.Activity(type=discord.ActivityType.streaming, name=f"🔴 LIVE: {title[:30]}", url=live_info.get("stream_url", "https://youtube.com/@AALU_CHIPAS"))
                await bot.change_presence(status=discord.Status.online, activity=activity)
            else:
                top = player_analytics.get_top_games()
                top_name = top[0][0] if top else "Community"
                activity = discord.Activity(type=discord.ActivityType.watching, name=f"@AALU_CHIPAS | {top_name}")
                await bot.change_presence(status=discord.Status.online, activity=activity)
        except Exception:
            pass
        await asyncio.sleep(300)

# ── SCHEDULED BACKGROUND LOOPS (Automated 24h Backup & Gaming Presence Sync) ───
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

@tasks.loop(hours=1)
async def scheduled_sync_loop():
    """Periodically snapshots gaming presence for all server members."""
    for g in bot.guilds:
        try:
            for member in g.members:
                if not member.bot and member.activities:
                    player_analytics.record_presence(member)
            logging.info(f"[AutoPresenceSync] {g.name}: Synced member gaming presence.")
        except Exception as ex:
            logging.error(f"[AutoPresenceSync] Error on {g.name}: {ex}")

@tasks.loop(minutes=5)
async def scheduled_voice_xp_loop():
    """Awards voice XP (15 XP/5 min) to active community members in voice channels."""
    for g in bot.guilds:
        try:
            for vc in g.voice_channels:
                for member in vc.members:
                    if not member.bot and not member.voice.afk:
                        loyalty_system.add_voice_xp(member.id, minutes=5, user_name=member.display_name)
        except Exception as ex:
            logging.debug(f"[AutoVoiceXPSync] {ex}")

# ── 5x DAILY AUTONOMOUS SELF-REFLECTION LOOP (Every 4.8 Hours) ───────────────
@tasks.loop(hours=4.8)
async def scheduled_self_reflection_loop():
    try:
        def _llm_reflect(prompt_text):
            return query_gemini(prompt_text, "TilluAuditor", is_admin=True, is_owner_user=True)

        res = await reflection_engine.execute_audit_cycle(
            prompt_mgr=prompt_mgr,
            rule_mgr=rule_mgr,
            llm_reflection_fn=_llm_reflect
        )
        logging.info(f"[Scheduled Self-Reflection 5x/Day] Cycle #{reflection_engine.audit_counter}: {res.get('success_rate', 100.0)}% success")
        for g in bot.guilds:
            try:
                up_ch = await get_or_create_update_channel(g)
                if up_ch and res.get("auto_learned_improvement"):
                    embed = discord.Embed(
                        title=f"🧠 Tillu Autonomous 5x Daily Self-Audit Report #{reflection_engine.audit_counter}",
                        description=(
                            f"**Performance:** `{res.get('success_rate', 100.0)}%` success over `{res.get('total_tasks', 0)}` tasks.\n\n"
                            f"**Auto-Learned Self-Improvement:**\n> {res.get('auto_learned_improvement')}"
                        ),
                        color=0x2ECC71,
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text="Autonomous Evolution Engine • 5x Daily • Synced to GitHub")
                    await up_ch.send(embed=embed)
            except Exception as se:
                logging.warning(f"[Scheduled Self-Reflection Notify Error] {se}")
    except Exception as e:
        logging.error(f"[Scheduled Self-Reflection Loop Error] {e}")

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
        # Discover and sync other bots in server
        try:
            await bot_orch.sync_guild_bots(guild)
        except Exception as bse:
            logging.warning(f"[BotOrchestrator Sync] {bse}")
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

    try:
        if not scheduled_voice_xp_loop.is_running():
            scheduled_voice_xp_loop.start()
            logging.info("[ScheduledVoiceXP] Voice XP loyalty loop started.")
    except Exception as vxe:
        logging.warning(f"[ScheduledVoiceXP Init] {vxe}")

    try:
        if not scheduled_self_reflection_loop.is_running():
            scheduled_self_reflection_loop.start()
            logging.info("[ScheduledSelfReflection] 5x Daily self-reflection audit loop started.")
    except Exception as rle:
        logging.warning(f"[ScheduledSelfReflection Init] {rle}")

    try:
        hot_reloader.start_watcher(interval_seconds=5.0)
        logging.info("[HotReloader] Automatic file watcher enabled in on_ready.")
    except Exception as hre:
        logging.warning(f"[HotReloader Init] {hre}")


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

