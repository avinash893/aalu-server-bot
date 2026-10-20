"""
Tillu Autonomous Discord Action Manager
Handles Discord server management tasks (roles, channels, message deletions, moderation)
initiated by Server Owner, Admins, and Moderators via natural language or direct commands.
"""

import re
import json
import datetime
import logging
import requests as _requests
import os
from typing import Optional, Tuple
import discord

logger = logging.getLogger("TilluDiscordActions")

_GROQ_SYSTEM = """You are a Discord server management action classifier for Tillu bot.
Given a natural language command from a privileged server admin/owner, extract the action as JSON.

Return ONLY valid JSON. No explanation. Possible actions:

{"action": "purge", "count": <number>, "channel": "<channel name or null>"}
{"action": "create_role", "role_name": "<name>", "color": "<hex/color name or null>", "hoist": <true/false/null>, "mentionable": <true/false/null>, "permissions": ["administrator", "kick_members", "ban_members", "manage_channels", "manage_messages", "manage_roles", "moderate_members", "view_audit_log"]}
{"action": "assign_role", "role_name": "<name>", "member": "<name/mention>"}
{"action": "create_and_assign_role", "role_name": "<name>", "member": "<name/mention>", "color": "<hex/color or null>", "hoist": <true/false/null>, "mentionable": <true/false/null>, "permissions": [...]}
{"action": "remove_role_from_server", "role_name": "<name>"}
{"action": "remove_role_from_member", "role_name": "<name>", "member": "<name/mention>"}
{"action": "create_channel", "channel_name": "<name>", "type": "text|voice", "topic": "<topic or null>", "slowmode": <seconds or null>, "private": <true/false/null>}
{"action": "delete_channel", "channel_name": "<name>"}
{"action": "lock_channel", "channel_name": "<current or name>"}
{"action": "unlock_channel", "channel_name": "<current or name>"}
{"action": "restrict_posting", "channel_name": "<name>", "allowed_roles": ["moderator","admin"]}
{"action": "rename_channel", "channel_name": "<old>", "new_name": "<new>"}
{"action": "create_category", "category_name": "<name>"}
{"action": "delete_category", "category_name": "<name>"}
{"action": "move_channel_to_category", "channel": "<name>", "category": "<name>"}
{"action": "group_channels", "category": "<name>", "keywords": ["<keyword1>", "<keyword2>"]}
{"action": "add_bot", "bot": "<name or id>"}
{"action": "lockdown_server"}
{"action": "unlock_server"}
{"action": "rename_server", "new_name": "<name>"}
{"action": "timeout", "member": "<name>", "minutes": <number>}
{"action": "backup_server"}
{"action": "list_backups"}
{"action": "restore_section", "section": "roles|categories|channels|permissions|server|channel|role", "target": "<name or null>"}
{"action": "none"}

Rules:
- "backup server" / "server backup" / "take backup" → backup_server
- "restore roles" / "restore channels" / "restore permissions" / "restore server" → restore_section with section
- "restore channel <name>" → restore_section with section "channel" and target "<name>"
- "restore role <name>" → restore_section with section "role" and target "<name>"
- "make this role:- <name> with this features ..." -> extract role_name cleanly, and parse color, hoist, mentionable, permissions.
- "create category X and move/group all Y stuff in it" → group_channels with category "X" and keywords ["Y"]
- "group the X things all in one group named X" → group_channels with category "X" and keywords ["X"]
- "add bot <name/id>" / "invite bot <name/id>" → add_bot with bot "<name/id>"
- "lockdown server" → lockdown_server
- "unlockdown server" → unlock_server

- "hoist" means display separately in member list (true/false).
- Colors: red, blue, green, yellow, orange, purple, pink, cyan, gold, dark_blue, dark_red, or hex like #ff0000.
- Permissions: administrator, kick_members, ban_members, manage_channels, manage_messages, manage_roles, moderate_members, view_audit_log.
- "remove the role X from discord" → remove_role_from_server
- "remove role X from @user" → remove_role_from_member
- "delete N messages/chats" → purge
- "only mods can post in #channel" → restrict_posting
- If action is not Discord-related → {"action": "none"}
"""


import random
import threading

_nv_raw = os.environ.get("NVIDIA_API_KEYS", "")
_nv_single = os.environ.get("NVIDIA_API_KEY", "")
_NVIDIA_KEYS = [k.strip() for k in _nv_raw.split(",") if k.strip()] or ([_nv_single] if _nv_single else [])

class _ActionNvidiaRoller:
    """Rolls NVIDIA keys after 5-10 successful uses or on 429."""
    def __init__(self, keys: list[str]):
        self.keys = keys
        self.current_idx = 0
        self.usage_count = 0
        self.roll_threshold = random.randint(5, 10)
        self.lock = threading.Lock()

    def get_key(self) -> str:
        with self.lock:
            if not self.keys:
                return ""
            return self.keys[self.current_idx % len(self.keys)]

    def record_success(self):
        with self.lock:
            self.usage_count += 1
            if self.usage_count >= self.roll_threshold:
                self.roll()

    def roll(self):
        with self.lock:
            if self.keys:
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                self.usage_count = 0
                self.roll_threshold = random.randint(5, 10)

_nv_roller = _ActionNvidiaRoller(_NVIDIA_KEYS)

def _nvidia_classify_action(text: str) -> dict:
    """Use NVIDIA NIM to classify the Discord action intent as primary AI option."""
    if not _NVIDIA_KEYS:
        return {}
    models = ["openai/gpt-oss-20b", "nvidia/nemotron-3.5-lightning-30b-a3b", "z-ai/glm-5.3-flash"]
    num_keys = len(_NVIDIA_KEYS)
    for _ in range(num_keys):
        key = _nv_roller.get_key()
        if not key:
            break
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        for model in models:
            try:
                r = _requests.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _GROQ_SYSTEM},
                            {"role": "user", "content": text}
                        ],
                        "max_tokens": 350,
                        "temperature": 0
                    },
                    timeout=5
                )
                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
                        match = re.search(r'\{[\s\S]*?\}', content)
                        if match:
                            parsed = json.loads(match.group(0))
                            if parsed.get("action") and parsed.get("action") != "none":
                                _nv_roller.record_success()
                                logger.info(f"[DiscordActionNVIDIA] Classified: {parsed}")
                                return parsed
                elif r.status_code == 429:
                    _nv_roller.roll()
                    break
            except Exception as ex:
                logger.debug(f"[DiscordActionNVIDIA] {model} err: {ex}")
                continue
        _nv_roller.roll()
    return {}

def _groq_classify_action(text: str) -> dict:
    """Use Groq to classify the Discord action intent as fallback. Returns dict or {}."""
    try:
        raw_keys = os.environ.get("GROQ_API_KEYS", "")
        single = os.environ.get("GROQ_API_KEY", "")
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()] or ([single] if single else [])
        if not keys:
            return {}
        # Fastest model first for sub-second classification
        models = [
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            "qwen/qwen3.8-27b"
        ]
        for key in keys:
            for model in models:
                try:
                    r = _requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": _GROQ_SYSTEM},
                                {"role": "user", "content": text}
                            ],
                            "max_tokens": 350,
                            "temperature": 0
                        },
                        timeout=3
                    )
                    if r.status_code == 200:
                        msg = r.json()["choices"][0].get("message", {})
                        content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
                        # Extract JSON (handles markdown codeblocks like ```json { ... } ```)
                        match = re.search(r'\{[\s\S]*?\}', content)
                        if match:
                            parsed = json.loads(match.group(0))
                            if parsed.get("action") and parsed.get("action") != "none":
                                logger.info(f"[DiscordActionAI] Classified: {parsed}")
                                return parsed
                    elif r.status_code == 429:
                        continue  # Try next model or key
                except Exception as ex:
                    logger.debug(f"[DiscordActionAI] {model} err: {ex}")
                    continue
    except Exception as e:
        logger.warning(f"[DiscordActionAI] classify error: {e}")
    return {}

COLOR_MAP = {
    "red": discord.Color.red(),
    "blue": discord.Color.blue(),
    "green": discord.Color.green(),
    "yellow": discord.Color.gold(),
    "orange": discord.Color.orange(),
    "purple": discord.Color.purple(),
    "pink": discord.Color.magenta(),
    "gold": discord.Color.gold(),
    "teal": discord.Color.teal(),
    "cyan": discord.Color.teal(),
    "dark_blue": discord.Color.dark_blue(),
    "dark_red": discord.Color.dark_red(),
    "blurple": discord.Color.blurple(),
    "grey": discord.Color.light_grey(),
    "gray": discord.Color.light_grey(),
    "white": discord.Color.from_rgb(255, 255, 255),
    "black": discord.Color.default(),
}

def parse_role_features(data: dict = None, raw_text: str = "") -> Tuple[dict, list]:
    """Parse role features (color, hoist, mentionable, permissions) from AI data or natural language text."""
    data = data or {}
    combined_text = f"{raw_text} {json.dumps(data) if data else ''}".lower()

    kwargs = {}
    details = []

    # 1. Color
    c_val = data.get("color") or data.get("colour")
    color_obj = None
    if c_val:
        c_str = str(c_val).lower().strip()
        if c_str.startswith("#"):
            try:
                color_obj = discord.Color(int(c_str.lstrip("#"), 16))
            except Exception:
                pass
        elif c_str in COLOR_MAP:
            color_obj = COLOR_MAP[c_str]

    if not color_obj:
        hex_match = re.search(r'#([0-9a-fA-F]{6})', combined_text)
        if hex_match:
            try:
                color_obj = discord.Color(int(hex_match.group(1), 16))
            except Exception:
                pass
        else:
            for cname, cobj in COLOR_MAP.items():
                if re.search(r'\b' + cname.replace('_', '[_ ]') + r'(?:\s+colou?r)?\b', combined_text):
                    color_obj = cobj
                    break

    if color_obj:
        kwargs["color"] = color_obj
        details.append(f"🎨 Color: `{color_obj}`")

    # 2. Hoist (Display separately in sidebar)
    hoist_val = data.get("hoist")
    if hoist_val is True or re.search(r'\b(hoist|separate|separately|alag\s+se)\b', combined_text):
        kwargs["hoist"] = True
        details.append("📌 Separate Display: Yes")
    elif hoist_val is False:
        kwargs["hoist"] = False

    # 3. Mentionable
    ment_val = data.get("mentionable")
    if ment_val is False or re.search(r'\b(not\s+mentionable|no\s+mention|mention\s+off)\b', combined_text):
        kwargs["mentionable"] = False
        details.append("🔕 Mentionable: No")
    else:
        kwargs["mentionable"] = True

    # 4. Permissions
    perms = set()
    raw_perms = data.get("permissions", [])
    if isinstance(raw_perms, list):
        for p in raw_perms:
            perms.add(str(p).lower().strip())

    PERM_MAP = {
        "administrator": ["admin", "administrator"],
        "kick_members": ["kick", "kick_members", "kick members"],
        "ban_members": ["ban", "ban_members", "ban members"],
        "manage_channels": ["manage_channels", "manage channel", "manage channels"],
        "manage_messages": ["manage_messages", "manage message", "delete messages", "manage messages"],
        "manage_roles": ["manage_roles", "manage role", "manage roles"],
        "view_audit_log": ["view_audit_log", "audit log"],
        "moderate_members": ["moderate_members", "timeout", "mute members"],
        "mention_everyone": ["mention_everyone", "mention everyone", "ping everyone"],
        "manage_guild": ["manage_server", "manage_guild", "manage server"],
    }

    perm_kwargs = {}
    for perm_attr, aliases in PERM_MAP.items():
        if any(a in perms for a in aliases) or any(re.search(r'\b' + re.escape(a) + r'\b', combined_text) for a in aliases):
            perm_kwargs[perm_attr] = True

    if perm_kwargs:
        kwargs["permissions"] = discord.Permissions(**perm_kwargs)
        formatted_perms = ", ".join(k.replace("_", " ").title() for k in perm_kwargs)
        details.append(f"🛡️ Permissions: {formatted_perms}")

    return kwargs, details

KNOWN_BOTS = {
    "carl": ("Carl-bot", "235148963503957990"),
    "carl-bot": ("Carl-bot", "235148963503957990"),
    "carlbot": ("Carl-bot", "235148963503957990"),
    "dyno": ("Dyno", "155149108183695360"),
    "mee6": ("MEE6", "159985870458322944"),
    "probot": ("ProBot", "282859044593598464"),
    "ticket tool": ("Ticket Tool", "557628352828014614"),
    "tickettool": ("Ticket Tool", "557628352828014614"),
    "ticket": ("Ticket Tool", "557628352828014614"),
    "disboard": ("DISBOARD", "302050872383242240"),
    "jockie music": ("Jockie Music", "411916947773587456"),
    "jockie": ("Jockie Music", "411916947773587456"),
    "rythm": ("Rythm", "235088799074484224"),
    "fredboat": ("FredBoat", "184405253096439808"),
    "yagpdb": ("YAGPDB.xyz", "204255221017214977"),
    "arcane": ("Arcane", "437808476106784770"),
    "tupperbox": ("Tupperbox", "431548175489531905"),
    "server stats": ("Server Stats", "458276815090384906"),
    "serverstats": ("Server Stats", "458276815090384906"),
    "dank memer": ("Dank Memer", "270904126974590976"),
    "dankmemer": ("Dank Memer", "270904126974590976"),
    "mudae": ("Mudae", "432610292342587392"),
    "loritta": ("Loritta", "297153970613387264"),
    "owo": ("OwO", "408785106942164992"),
    "hydra": ("Hydra", "547905866255433758"),
    "chip": ("Chip", "614247895048257536"),
    "groovy": ("Groovy", "234395307759108106"),
    "apollo": ("Apollo", "475744554910351370"),
    "suggestion": ("SuggestionBot", "493922624467599360"),
}

CAT_PATTERN = r'(?:cat[oeaiu]+g[oeaiu]+r[yei]+|group)'

def find_category_fuzzy(guild: discord.Guild, query: str) -> Optional[discord.CategoryChannel]:
    clean_q = re.sub(r'[^a-zA-Z0-9]', '', query).lower()
    for cat in guild.categories:
        if cat.name.lower() == query.lower() or re.sub(r'[^a-zA-Z0-9]', '', cat.name).lower() == clean_q:
            return cat
    for cat in guild.categories:
        c_alnum = re.sub(r'[^a-zA-Z0-9]', '', cat.name).lower()
        if clean_q and (clean_q in c_alnum or c_alnum in clean_q):
            return cat
    return None

def handle_add_bot_action(guild: discord.Guild, author: discord.Member, query: str) -> Tuple[Optional[discord.Embed], Optional[discord.ui.View], Optional[str]]:
    """Generate secure 1-click OAuth2 invite link to add any bot to the server (Moderator+ only)."""
    clean_q = query.lower().strip()
    clean_q = re.sub(r'^(?:add\s+bot|invite\s+bot|bot)\s*', '', clean_q).strip()
    clean_q = re.sub(r'\s+(?:to|in|into)\s+(?:this\s+)?(?:server|discord).*', '', clean_q).strip()

    id_match = re.search(r'\b(\d{17,20})\b', clean_q)
    bot_id = id_match.group(1) if id_match else None
    bot_name = f"Bot ({bot_id})" if bot_id else clean_q.title()

    if not bot_id:
        for k_alias, (k_name, k_id) in KNOWN_BOTS.items():
            if clean_q == k_alias or clean_q in k_alias or k_alias in clean_q:
                bot_name = k_name
                bot_id = k_id
                break

    if not bot_id:
        return None, None, f"🔍 `{query}` known bots directory me nahi mila!\nBolo: `tillu add bot <Application_ID>` ya direct Application ID provide karo (e.g. Carl-bot, MEE6, Dyno, ProBot, Ticket Tool, Disboard, etc.). [Top.gg Directory](https://top.gg) se bhi ID le sakte hain."

    invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&scope=bot%20applications.commands&permissions=8"

    embed = discord.Embed(
        title=f"🤖 Add {bot_name} to {guild.name}",
        description=(
            f"**Application ID:** `{bot_id}`\n"
            f"**Requested By:** {author.mention}\n"
            f"**Permissions:** `Administrator (Recommended for full features)`\n\n"
            f"👉 Neeche diye gaye button par click karke bot ko server me authorize aur add kar lo!"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Tillu Bot Manager • OAuth2 Secure Gateway")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=f"➕ Add {bot_name} to Server", url=invite_url, style=discord.ButtonStyle.link))
    return embed, view, None

async def group_channels_into_category(guild: discord.Guild, cat_name: str, keywords: list[str], author: discord.Member) -> Tuple[bool, str]:
    """Find or create category and group matching channels into it."""
    cat_clean = cat_name.strip().strip('"\'')
    if not cat_clean:
        cat_clean = "Grouped Channels"

    target_cat = find_category_fuzzy(guild, cat_clean)
    if not target_cat:
        try:
            target_cat = await guild.create_category(name=cat_clean.title(), reason=f"Created by Tillu via {author.name}")
        except Exception as e:
            return True, f"⚠️ Category create error: {e}"

    clean_kws = [k.lower().strip() for k in keywords if k.strip()]
    if not clean_kws:
        clean_kws = [cat_clean.lower()]

    matching_channels = []
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            continue
        if ch.category_id == target_cat.id:
            continue
        ch_norm = ch.name.lower().replace('-', ' ').replace('_', ' ')
        if any(kw in ch_norm or kw in ch.name.lower() for kw in clean_kws):
            matching_channels.append(ch)

    if not matching_channels:
        return True, f"📂 Category **{target_cat.name}** ready hai, lekin server me koi aisa channel nahi mila jisme `{', '.join(clean_kws)}` ho!"

    moved = []
    errors = []
    for ch in matching_channels:
        try:
            await ch.edit(category=target_cat, reason=f"Grouped into {target_cat.name} by Tillu via {author.name}")
            moved.append(ch.mention)
        except Exception as ex:
            errors.append(f"{ch.name} ({ex})")

    resp = f"📂 **Done Boss!** Category **{target_cat.name}** me `{len(moved)}` channels group/move kar diye gaye:\n" + ", ".join(moved)
    if errors:
        resp += f"\n*(Error moving: {', '.join(errors)})*"
    return True, resp

async def parse_and_execute_discord_action(
    message: discord.Message,
    author: discord.Member,
    guild: discord.Guild,
    text: str
) -> Tuple[bool, Optional[str]]:
    """
    Check if the user message contains a Discord server management command.
    Uses ultra-fast local regex parsing first (<0.1ms), then AI fallback only if needed.
    Returns (handled: bool, confirmation_message: Optional[str]).
    """
    if not guild or not isinstance(author, discord.Member):
        return False, None

    clean_text = text.lower().strip()

    # ── FAST BAILOUT: Skip immediately for normal conversation (0ms overhead) ──
    MGMT_KEYWORDS = [
        "role", "channel", "delete", "purge", "clear", "remove", "saaf", "hata", "mute", "timeout",
        "lock", "unlock", "slowmode", "topic", "rename", "category", "catogery", "catagory", "catagery",
        "clone", "clip", "post in", "permission", "creators", "admin", "backup", "restore", "snapshot",
        "sync", "claim", "drop", "group", "move", "shift", "bot", "add bot", "invite", "lockdown",
        "server", "transfer", "put"
    ]
    if not any(kw in clean_text for kw in MGMT_KEYWORDS):
        return False, None

    # ── HELPER: Fuzzy member finder ──────────────────────────────────────────
    async def find_member_fuzzy(query: str) -> discord.Member | None:
        """Find member by mention, ID, exact name, nick, or partial name with async fetch fallback."""
        if not query:
            return None
        my_id = guild.me.id if guild.me else (message._state.user.id if hasattr(message, "_state") else 0)

        # 1. Mention in query (<@123...>)
        m_id = re.search(r'<@!?(\d+)>', query)
        if m_id:
            uid = int(m_id.group(1))
            mem = guild.get_member(uid)
            if mem:
                return mem
            try:
                return await guild.fetch_member(uid)
            except Exception:
                pass

        # 2. Check message.mentions (excluding bot itself)
        user_mentions = [m for m in message.mentions if m.id != my_id]
        if user_mentions:
            clean_q = re.sub(r'[^a-zA-Z0-9]', '', query).lower()
            if not clean_q:
                return user_mentions[0]
            for m in user_mentions:
                if str(m.id) == clean_q or clean_q in m.name.lower() or (m.nick and clean_q in m.nick.lower()):
                    return m
            if len(user_mentions) == 1:
                return user_mentions[0]

        # 3. Direct ID query
        clean_q = re.sub(r'[^a-zA-Z0-9]', '', query).lower()
        if not clean_q:
            return None
        if clean_q.isdigit():
            uid = int(clean_q)
            mem = guild.get_member(uid)
            if mem:
                return mem
            try:
                return await guild.fetch_member(uid)
            except Exception:
                pass

        # 4. Exact name / nick match in cached members
        for m in guild.members:
            if m.id == my_id:
                continue
            nm = re.sub(r'[^a-zA-Z0-9]', '', m.name).lower()
            nk = re.sub(r'[^a-zA-Z0-9]', '', m.nick or '').lower()
            if nm == clean_q or nk == clean_q:
                return m

        # 5. Partial match fallback (length >= 3 to prevent false positives)
        if len(clean_q) >= 3:
            for m in guild.members:
                if m.id == my_id:
                    continue
                nm = re.sub(r'[^a-zA-Z0-9]', '', m.name).lower()
                nk = re.sub(r'[^a-zA-Z0-9]', '', m.nick or '').lower()
                if clean_q in nm or (nk and clean_q in nk):
                    return m
        return None

    # ── HELPER: Fuzzy role finder ─────────────────────────────────────────────
    def find_role_fuzzy(query: str) -> discord.Role | None:
        if not query:
            return None
        # Check role mention (<@&123456789>)
        r_id_m = re.search(r'<@&(\d+)>', query)
        if r_id_m:
            r = guild.get_role(int(r_id_m.group(1)))
            if r:
                return r

        q = query.lower().strip()
        q_clean = re.sub(r'^(?:named?\s*[:\-]*\s*|role\s+)', '', q).strip()
        q_alnum = re.sub(r'[^a-zA-Z0-9]', '', q_clean)
        if not q_alnum:
            return None
        # Check direct role ID
        if q_alnum.isdigit():
            r = guild.get_role(int(q_alnum))
            if r:
                return r
        # Exact name match
        for r in guild.roles:
            if r.name.lower() == q or r.name.lower() == q_clean:
                return r
        # Alphanumeric match
        for r in guild.roles:
            r_alnum = re.sub(r'[^a-zA-Z0-9]', '', r.name).lower()
            if r_alnum == q_alnum:
                return r
        # Substring match (require len >= 3)
        if len(q_alnum) >= 3:
            for r in guild.roles:
                r_alnum = re.sub(r'[^a-zA-Z0-9]', '', r.name).lower()
                if q_alnum in r_alnum or (len(r_alnum) >= 4 and r_alnum in q_alnum):
                    return r
        return None

    # ═════════════════════════════════════════════════════════════════════════
    # ── STEP 1: INSTANT LOCAL REGEX PARSING (0ms latency, zero network) ─────
    # ═════════════════════════════════════════════════════════════════════════

    # 0. BACKUP & RESTORE SERVER ARCHITECTURE
    if re.search(r'\b(?:create\s+|take\s+)?backup\s+(?:of\s+)?(?:this\s+)?(?:server|discord|guild)?\b', clean_text) or clean_text in ["tillu backup", "backup server", "server backup", "take backup"]:
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi backup le sakte hain!"
        import backup_manager
        success, msg, _ = backup_manager.create_backup(guild)
        return True, msg

    if re.search(r'\b(?:list\s+backups?|backups?\s+list|show\s+backups?)\b', clean_text):
        import backup_manager
        b_list = backup_manager.list_backups(guild.id)
        if not b_list:
            return True, "📂 Abhi tak koi backup snapshot create nahi hua hai. `tillu backup server` se create karo!"
        return True, f"📂 **Available Backups:**\n" + "\n".join(f"• `{b}`" for b in b_list[:5])

    restore_ch_m = re.search(r'restore\s+channel\s+(?:<#(\d+)>|#?([a-zA-Z0-9_\-]+))', clean_text)
    if restore_ch_m:
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi restore kar sakte hain!"
        import backup_manager
        ch_id = restore_ch_m.group(1)
        ch_name = restore_ch_m.group(2)
        if ch_id:
            resolved_ch = guild.get_channel(int(ch_id))
            ch_target = resolved_ch.name if resolved_ch else ch_id
        else:
            ch_target = (ch_name or "").strip()
        success, msg = await backup_manager.restore_section(guild, "channel", specific_target=ch_target)
        return True, msg

    restore_r_m = re.search(r'restore\s+role\s+["\']?([^"\']+)["\']?', clean_text)
    if restore_r_m:
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi restore kar sakte hain!"
        import backup_manager
        r_target = restore_r_m.group(1).strip()
        success, msg = await backup_manager.restore_section(guild, "role", specific_target=r_target)
        return True, msg

    restore_sec_m = re.search(r'restore\s+(roles?|channels?|categories|permissions?|server|all|architecture)', clean_text)
    if restore_sec_m:
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi restore kar sakte hain!"
        import backup_manager
        sec = restore_sec_m.group(1).rstrip('s')
        if sec in ["role", "channel", "permission"]:
            sec = sec + "s"
        elif sec in ["architecture", "all"]:
            sec = "server"
        success, msg = await backup_manager.restore_section(guild, sec)
        return True, msg

    # MINECRAFT LIVE SYNC
    if re.search(r'\b(?:sync\s+(?:roles?|minecraft|whitelist)|livesync)\b', clean_text) or clean_text in ["tillu sync", "sync roles", "sync now"]:
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi sync kar sakte hain!"
        import sync_manager
        reg = {}
        reg_file = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")
        if os.path.exists(reg_file):
            try:
                with open(reg_file, "r", encoding="utf-8-sig") as f:
                    reg = json.load(f)
            except Exception:
                pass
        checked, assigned = await sync_manager.sync_guild_roles(guild, reg)
        return True, f"✅ **Minecraft Live Sync Complete!** `{checked}` registered accounts check hue, `{assigned}` naye Whitelisted roles assign kiye gaye!"

    # MINECRAFT CHAT DROP CLAIM (Discord Vault Deposit)
    if re.search(r'\b(?:claim\s+(?:free\s+)?drop|claim\s+reward|take\s+drop|my\s+drop)\b', clean_text) or clean_text in ["claim drop", "tillu claim", "claim drop please"]:
        import rewards_manager
        success, reward, msg = rewards_manager.claim_drop(author.id)
        return True, f"{author.mention} {msg}"

    # MINECRAFT SEND CLAIMS TO ACCOUNT
    send_claims_m = re.search(r'(?:send\s+(?:my\s+)?claims?\s+to\s+(?:my\s+account|me|self|([a-zA-Z0-9_.* ]{3,20})))', clean_text)
    if send_claims_m:
        import rewards_manager
        reg_file = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")
        reg = {}
        if os.path.exists(reg_file):
            try:
                with open(reg_file, "r", encoding="utf-8-sig") as f:
                    reg = json.load(f)
            except Exception:
                pass
        target_q = (send_claims_m.group(1) or "").strip()
        linked_ign = reg.get(str(author.id), {}).get("ign")
        target_ign = linked_ign if (not target_q or target_q.lower() in ["my account", "me", "self", "my"]) else target_q
        if not target_ign:
            return True, f"❌ {author.mention}, tumhara koi Minecraft account linked nahi hai! Bolo: `tillu send my claims to <account_name>` ya pehle `!whitelist <your_ign>` karo."

        import sys
        _bot = sys.modules.get("bot") or sys.modules.get("__main__")
        cmd_fn = getattr(_bot, "panel_send_command", None)
        if not cmd_fn:
            try:
                import bot as _bot_mod
                cmd_fn = getattr(_bot_mod, "panel_send_command", None)
            except Exception:
                pass
        if not cmd_fn:
            cmd_fn = lambda c: (False, "Command function unavailable")

        import asyncio
        success, items, msg = await asyncio.to_thread(rewards_manager.send_claims_to_account, author.id, target_ign, cmd_fn)
        if not success:
            return True, f"{author.mention} {msg}"

        items_str = ", ".join(f"{it['emoji']} {it['name']}" for it in items)
        return True, f"🚀 **Done Boss!** {author.mention} ke `{len(items)}` claims **`{target_ign}`** ko in-game deliver kar diye gaye!\nItems: {items_str} 🎉"

    # MINECRAFT VAULT / PENDING CLAIMS INSPECTION
    if clean_text in ["tillu vault", "vault", "my claims", "tillu my claims"]:
        import rewards_manager
        pending = rewards_manager.get_pending_claims(author.id)
        if not pending:
            return True, f"📭 {author.mention}, tumhare vault me koi pending items nahi hain! Chat karo aur `!claim` se naya drop lo."
        items_list = ", ".join(f"{it['emoji']} {it['name']}" for it in pending)
        return True, f"🏦 **{author.mention}'s Vault ({len(pending)} items):** {items_list}\nIn-game lene ke liye bolo: `tillu send my claims to my account`!"

    if re.search(r'\b(?:drop\s+status|claim\s+status|check\s+drop)\b', clean_text):
        import rewards_manager
        can_claim, remaining, total = rewards_manager.get_drop_status(author.id)
        pending = rewards_manager.get_pending_claims(author.id)
        if can_claim:
            return True, f"🎉 {author.mention}, tumhara free drop ready hai! Claim karne ke liye `!claim` type karo! (Vault: `{len(pending)}` pending items)"
        mins = remaining // 60
        secs = remaining % 60
        return True, f"⏳ {author.mention}, agla drop claim karne ke liye **{mins}m {secs}s** wait karo. (Vault: `{len(pending)}` pending, Total Claims: `{total}`)"




    # 1. PURGE / DELETE MESSAGES
    # e.g., "tillu delete 10 messages", "purge 20", "delete 4 of your recent messages in admin"
    purge_match = re.search(
        r'(?:delete|purge|remove|clear|saaf\s+kar\s+do|hata\s+do)\s+(?:(?:last|recent|of\s+your\s+recent|your)\s+)?(\d{1,3})(?:\s+(?:of\s+(?:your\s+)?(?:recent\s+)?)?(?:messages?|chats?|msgs?))?',
        clean_text
    )
    if purge_match:
        count = min(int(purge_match.group(1)), 100)
        target_ch = message.channel
        # Check if another channel mentioned by name
        # Check channel mentions first
        if message.channel_mentions:
            target_ch = message.channel_mentions[0]
        else:
            for ch in guild.channels:
                if isinstance(ch, discord.TextChannel) and len(ch.name) >= 3 and re.search(rf'\b{re.escape(ch.name.lower())}\b', clean_text) and ch != message.channel:
                    target_ch = ch
                    break
        try:
            bot_only = any(w in clean_text for w in ["your", "tillu", "apne", "khud ke"])
            if bot_only:
                my_id = guild.me.id if guild.me else (message._state.user.id if hasattr(message, "_state") else message.author.id)
                deleted = await target_ch.purge(limit=min(count * 5, 100), check=lambda m: m.author.id == my_id)
            else:
                deleted = await target_ch.purge(limit=count + 1)
            actual = len(deleted)
            conf = f"🧹 **Done Boss!** `{actual}` messages delete kar diye {target_ch.mention} se!"
            sent = await message.channel.send(conf)
            try:
                await sent.delete(delay=6)
            except Exception:
                pass
            return True, None
        except Exception as e:
            err = f"⚠️ Messages delete karne me error aaya: {e}"
            return True, err

    # 2. DELETE / REMOVE ROLE FROM SERVER
    # e.g., "remove the role Named:- Creators from discord", "delete role Creators"
    del_role_match = re.search(
        r'(?:delete|remove|hata\s+do)\s+(?:the\s+)?role\s+(?:named?\s*[:\-]*\s*|called?\s*[:\-]*\s*)?["\']?([^"\']+)["\']?(?:\s+from\s+(?:discord|server))?',
        clean_text
    )
    if del_role_match and not re.search(r'\bfrom\s+(?!discord\b|server\b|guild\b)(?:<@|\b[a-zA-Z0-9_]{3,}\b)', clean_text):
        role_q = del_role_match.group(1).strip()
        role_q = re.sub(r'\s+from\s+(?:discord|server|guild)\s*$', '', role_q).strip()
        role = find_role_fuzzy(role_q)
        if role:
            try:
                r_name = role.name
                await role.delete(reason=f"Deleted by Tillu via {author.name}")
                return True, f"🗑️ **Role Deleted!** `{r_name}` role server se delete kar diya gaya hai!"
            except Exception as e:
                return True, f"⚠️ Role delete error: {e}"
        else:
            return True, f"❌ Role `{role_q}` nahi mila!"

    # 3. CREATE ROLE (without assigning)
    # e.g., "create role Creators", "make this role:- fhsfhif with this features something something", "make role VIP with red color, hoist, admin"
    create_role_match = re.search(
        r'(?:create|make|bana(?:\s+do)?)\s+(?:a\s+)?(?:new\s+)?(?:this\s+|ye\s+)?role\s*(?:named?\s*[:-]*\s*|called?\s*[:-]*\s*|[:-]+\s*)?["\']?([^"\'\n:]+?)["\']?(?:\s+(?:with|having|ke\s+saath)\s+(?:this\s+)?(?:features?\s*[:-]*\s*)?(.+))?$',
        text,
        re.IGNORECASE
    )
    if create_role_match and not re.search(r'(?:give|add|assign|de\s+do)', clean_text):
        role_name = create_role_match.group(1).strip().strip('"\'').title()
        features_str = create_role_match.group(2).strip() if create_role_match.group(2) else ""
        existing = find_role_fuzzy(role_name)
        if existing:
            return True, f"ℹ️ Role `{existing.name}` pehle se exist karta hai! Use karna ho to assign karo."
        try:
            role_kwargs, feat_details = parse_role_features(raw_text=features_str or text)
            if role_kwargs.get("permissions") and role_kwargs["permissions"].administrator:
                if not (author.guild_permissions.administrator or guild.owner_id == author.id):
                    return True, "🚫 Sirf Server Owner ya Administrators hi Administrator permissions wala role bana sakte hain!"
            new_role = await guild.create_role(
                name=role_name,
                reason=f"Created by Tillu via {author.name}",
                **role_kwargs
            )
            feat_msg = ("\n" + " | ".join(feat_details)) if feat_details else ""
            return True, f"🎭 **Role Created!** Naya role `{new_role.name}` ban gaya hai!{feat_msg}\nAssign karne ke liye bolna: `tillu give role {new_role.name} to @user`"
        except Exception as e:
            return True, f"⚠️ Role create error: {e}"


    # 4. GIVE / ADD ROLE (also handles: "create role X and add Y to it")
    # e.g., "tillu give role VIP to @user", "create role Creators and add uniqueumar to it"
    add_role_match = re.search(
        r'(?:give|add|assign|de\s+do)\s+(?:role\s+)?(?:<@&(\d+)>|["\']?([^"\'\n]+?)["\']?)\s+(?:role\s+)?to\s+(.+)',
        text,
        re.IGNORECASE
    )
    compound_match = re.search(
        r'create\s+(?:a\s+)?(?:new\s+)?role\s+(?:named?\s+)?["\']?([^"\':\n]+)["\']?'
        r'[\s\S]{0,60}?(?:add|give)\s+(.+?)\s+to\s+(?:it|that\s+role)',
        text,
        re.IGNORECASE | re.DOTALL
    )

    if add_role_match or compound_match:
        if compound_match:
            role_query = compound_match.group(1).strip()
            target_query = compound_match.group(2).strip()
        else:
            role_id = add_role_match.group(1)
            role_name_raw = add_role_match.group(2)
            role_query = role_id or (role_name_raw or "").strip()
            target_query = add_role_match.group(3).strip()

        # Find or create role
        role = find_role_fuzzy(role_query) or find_role_fuzzy(role_query.title())
        if not role:
            try:
                role = await guild.create_role(
                    name=role_query.title(),
                    mentionable=True,
                    reason=f"Auto-created by Tillu via {author.name}"
                )
            except Exception as re_err:
                return True, f"❌ Role `{role_query}` create nahi hua: {re_err}"

        # Find member (fuzzy)
        target_member = await find_member_fuzzy(target_query)
        if not target_member:
            return True, f"❌ Member `{target_query}` nahi mila! @mention karke try karo."

        try:
            await target_member.add_roles(role, reason=f"Assigned by Tillu via {author.name}")
            return True, f"✅ **Done Boss!** `{role.name}` role {target_member.mention} ko de diya gaya hai! 🎉"
        except Exception as e:
            return True, f"⚠️ Role assign error: {e}"

    # 5. REMOVE ROLE FROM MEMBER
    # e.g., "tillu remove role VIP from @user"
    rem_role_match = re.search(
        r'(?:remove|take|hata\s+do)\s+(?:role\s+)?(?:<@&(\d+)>|["\']?([^"\'\n]+?)["\']?)\s+from\s+(.+)',
        text,
        re.IGNORECASE
    )
    if rem_role_match:
        role_id = rem_role_match.group(1)
        role_name_raw = rem_role_match.group(2)
        role_query = role_id or (role_name_raw or "").strip()
        target_query = rem_role_match.group(3).strip()

        target_member = await find_member_fuzzy(target_query)
        if not target_member:
            return True, f"❌ Member `{target_query}` nahi mila!"

        role = find_role_fuzzy(role_query)
        if not role:
            return True, f"❌ Role `{role_query}` nahi mila!"

        try:
            await target_member.remove_roles(role, reason=f"Removed by Tillu via {author.name}")
            return True, f"🗑️ **Role Removed!** `{role.name}` role {target_member.mention} se hata diya gaya hai."
        except Exception as e:
            return True, f"⚠️ Role remove karne me error: {e}"

    # 6. RESTRICT POSTING BY ROLE
    # e.g., "only moderator or above can post in server clips"
    restrict_simple = re.search(
        r'(?:only\s+)?(.+?)\s+(?:or\s+above\s+)?(?:can|to)\s+(?:post|send|write)\s+in\s+(?:<#(\d+)>|#?([a-zA-Z0-9_\-]+))',
        clean_text,
        re.IGNORECASE
    )
    if restrict_simple:
        roles_text = restrict_simple.group(1).strip()
        ch_id = restrict_simple.group(2)
        ch_name_q = restrict_simple.group(3)

        target_ch = message.channel
        if ch_id:
            target_ch = guild.get_channel(int(ch_id)) or message.channel
        elif ch_name_q:
            found_ch = discord.utils.find(lambda c: c.name.lower().replace('-', '').replace('_', '') == ch_name_q.lower().replace('-', '').replace('_', ''), guild.channels)
            if found_ch:
                target_ch = found_ch

        if isinstance(target_ch, (discord.TextChannel, discord.ForumChannel)):
            try:
                await target_ch.set_permissions(guild.default_role, send_messages=False, reason=f"Restricted by Tillu via {author.name}")
                allowed_keywords = ['mod', 'moderator', 'admin', 'administrator', 'owner', 'staff', 'creator']
                granted = []
                for role in guild.roles:
                    rname = role.name.lower()
                    if any(kw in rname for kw in allowed_keywords):
                        await target_ch.set_permissions(role, send_messages=True, reason=f"Granted by Tillu via {author.name}")
                        granted.append(role.name)

                if granted:
                    return True, f"🔐 **Done Boss!** {target_ch.mention} ab sirf **{', '.join(granted)}** wale post kar sakte hain. Normal members ke liye send locked hai. ✅"
                else:
                    return True, f"⚠️ Koi matching privileged role nahi mila, lekin @everyone ka send_messages block kar diya gaya hai {target_ch.mention} me."
            except Exception as e:
                return True, f"⚠️ Channel permissions set karne me error: {e}"

    # 7. CREATE CHANNEL
    # e.g., "tillu create channel welcome-rules", "tillu create voice channel Gaming"
    create_ch_match = re.search(r'create\s+(?:(text|voice)\s+)?channel\s+["\']?([a-zA-Z0-9_\-]+)["\']?', clean_text)
    if create_ch_match:
        ch_type = create_ch_match.group(1) or "text"
        ch_name = create_ch_match.group(2).strip()
        try:
            if ch_type == "voice":
                new_ch = await guild.create_voice_channel(name=ch_name, reason=f"Created by Tillu via {author.name}")
            else:
                new_ch = await guild.create_text_channel(name=ch_name, reason=f"Created by Tillu via {author.name}")
            return True, f"📁 **Channel Created!** Naya channel {new_ch.mention} ban gaya hai! 🚀"
        except Exception as e:
            return True, f"⚠️ Channel create karne me error: {e}"

    # 8. DELETE CHANNEL
    # e.g., "tillu delete channel #test" or "delete channel old-chat"
    del_ch_match = re.search(r'delete\s+channel\s+(?:<#(\d+)>|["\']?([a-zA-Z0-9_\-]+)["\']?)', clean_text)
    if del_ch_match:
        ch_id = del_ch_match.group(1)
        ch_name = del_ch_match.group(2)
        target_ch = guild.get_channel(int(ch_id)) if ch_id else None
        if not target_ch and ch_name:
            target_ch = discord.utils.find(lambda c: c.name.lower() == ch_name.lower(), guild.channels)

        if not target_ch:
            return True, f"❌ Channel nahi mila!"

        try:
            old_name = target_ch.name
            await target_ch.delete(reason=f"Deleted by Tillu via {author.name}")
            return True, f"🗑️ **Channel Deleted!** Channel `#{old_name}` ko delete kar diya gaya hai."
        except Exception as e:
            return True, f"⚠️ Channel delete karne me error: {e}"

    # 9. LOCK / UNLOCK CHANNEL
    if any(p in clean_text for p in ["lock this channel", "lock channel", "channel lock kar do"]):
        try:
            await message.channel.set_permissions(guild.default_role, send_messages=False, reason=f"Locked by Tillu via {author.name}")
            return True, "🔒 **Channel Locked!** Normal members ab is channel me messages nahi bhej sakte."
        except Exception as e:
            return True, f"⚠️ Channel lock error: {e}"

    if any(p in clean_text for p in ["unlock this channel", "unlock channel", "channel unlock kar do"]):
        try:
            await message.channel.set_permissions(guild.default_role, send_messages=True, reason=f"Unlocked by Tillu via {author.name}")
            return True, "🔓 **Channel Unlocked!** Members ab is channel me messages bhej sakte hain."
        except Exception as e:
            return True, f"⚠️ Channel unlock error: {e}"

    # 10. RENAME CHANNEL
    rename_match = re.search(r'rename\s+(?:this\s+channel|channel\s+(?:<#(\d+)>|([a-zA-Z0-9_\-]+)))\s+(?:to\s+)?([a-zA-Z0-9_\-]+)', clean_text)
    if rename_match:
        ch_id = rename_match.group(1)
        ch_name = rename_match.group(2)
        new_name = rename_match.group(3)
        target_ch = message.channel
        if ch_id:
            target_ch = guild.get_channel(int(ch_id)) or message.channel
        elif ch_name:
            target_ch = discord.utils.find(lambda c: c.name.lower() == ch_name.lower(), guild.channels) or message.channel
        try:
            old = target_ch.name
            await target_ch.edit(name=new_name, reason=f"Renamed by Tillu via {author.name}")
            return True, f"✏️ **Channel Renamed!** `#{old}` ka naam badal kar `#{new_name}` kar diya gaya hai!"
        except Exception as e:
            return True, f"⚠️ Channel rename error: {e}"

    # 11. SET CHANNEL TOPIC
    topic_match = re.search(r'set\s+topic\s+(?:of\s+(?:this\s+channel|channel\s+(?:<#(\d+)>|([a-zA-Z0-9_\-]+))))?\s*(?:to\s+)?(.+)', text, re.IGNORECASE)
    if topic_match and "topic" in clean_text:
        ch_id = topic_match.group(1)
        ch_name = topic_match.group(2)
        new_topic = topic_match.group(3).strip()
        target_ch = message.channel
        if ch_id:
            target_ch = guild.get_channel(int(ch_id)) or message.channel
        elif ch_name:
            target_ch = discord.utils.find(lambda c: c.name.lower() == ch_name.lower(), guild.channels) or message.channel
        if isinstance(target_ch, discord.TextChannel):
            try:
                await target_ch.edit(topic=new_topic, reason=f"Topic updated by Tillu via {author.name}")
                return True, f"📝 **Channel Topic Updated!** {target_ch.mention} ka topic update ho gaya: `{new_topic}`"
            except Exception as e:
                return True, f"⚠️ Topic update error: {e}"

    # 12. SET SLOWMODE
    slowmode_match = re.search(r'(?:set\s+)?slowmode\s+(?:to\s+)?(\d+)\s*(?:s|sec|seconds?)?', clean_text)
    if slowmode_match:
        delay = int(slowmode_match.group(1))
        if isinstance(message.channel, discord.TextChannel):
            try:
                await message.channel.edit(slowmode_delay=delay, reason=f"Slowmode set by Tillu via {author.name}")
                if delay == 0:
                    return True, "⚡ **Slowmode Disabled!** Is channel me slowmode hata diya gaya hai."
                return True, f"⏱️ **Slowmode Set!** Is channel me `{delay}` seconds ka slowmode laga diya gaya hai."
            except Exception as e:
                return True, f"⚠️ Slowmode error: {e}"
    elif any(p in clean_text for p in ["disable slowmode", "remove slowmode", "slowmode off"]):
        if isinstance(message.channel, discord.TextChannel):
            try:
                await message.channel.edit(slowmode_delay=0, reason=f"Slowmode removed by Tillu via {author.name}")
                return True, "⚡ **Slowmode Disabled!** Slowmode hata diya gaya hai."
            except Exception as e:
                return True, f"⚠️ Slowmode disable error: {e}"

    # 13. HIDE / UNHIDE CHANNEL
    if any(p in clean_text for p in ["hide this channel", "hide channel", "channel chupao"]):
        try:
            await message.channel.set_permissions(guild.default_role, view_channel=False, reason=f"Hidden by Tillu via {author.name}")
            return True, "👁️‍🗨️ **Channel Hidden!** Normal members ab is channel ko nahi dekh sakte."
        except Exception as e:
            return True, f"⚠️ Hide channel error: {e}"

    if any(p in clean_text for p in ["unhide this channel", "unhide channel", "channel dikhao"]):
        try:
            await message.channel.set_permissions(guild.default_role, view_channel=True, reason=f"Unhidden by Tillu via {author.name}")
            return True, "👁️ **Channel Visible!** Normal members ab is channel ko dekh sakte hain."
        except Exception as e:
            return True, f"⚠️ Unhide channel error: {e}"

    # 14. ADD / INVITE BOT TO SERVER (Moderators & Above)
    # e.g., "tillu add bot Carl-bot", "invite bot 235148963503957990", "add bot mee6"
    add_bot_match = re.search(r'(?:add|invite)\s+bot\s+(.+)', clean_text)
    if add_bot_match:
        is_mod = (
            author.guild_permissions.manage_guild
            or author.guild_permissions.administrator
            or guild.owner_id == author.id
            or any(r.name.lower() in ['mod', 'moderator', 'admin', 'administrator', 'owner', 'staff'] for r in author.roles)
        )
        if not is_mod:
            return True, "🚫 **Permission Denied!** Sirf Server Owner, Administrators aur Moderators hi server me naye bots invite/add kar sakte hain!"

        bot_q = add_bot_match.group(1).strip()
        embed, view, msg = handle_add_bot_action(guild, author, bot_q)
        if embed:
            await message.channel.send(embed=embed, view=view)
            return True, None
        return True, msg

    # 15. CATEGORY & CHANNEL GROUPING MANAGEMENT
    # 15.1 Combined: "create category tillu and move all tillu related stuff like memory test and all in that"
    cat_create_and_move = re.search(
        rf'(?:create|make)\s+(?:a\s+)?(?:new\s+)?{CAT_PATTERN}\s+(?:named?\s*[:\-]*\s*|called?\s*[:\-]*\s*)?["\']?([a-zA-Z0-9_\- ]+?)["\']?\s+and\s+(?:move|group|put|shift)\s+(?:all\s+)?(.+?)\s+(?:in|into)\s+(?:that|it|category)',
        clean_text
    )
    if cat_create_and_move:
        cat_name = cat_create_and_move.group(1).strip()
        raw_filter = cat_create_and_move.group(2).strip()
        kws = set([cat_name.lower()])
        like_m = re.search(r'like\s+([^,]+)', raw_filter)
        if like_m:
            words = [w.strip() for w in re.split(r'[, ]+', like_m.group(1)) if w.strip() and w not in ["and", "all", "in", "that", "the", "stuff", "channels"]]
            kws.update(words)
        rel_m = re.search(r'([a-zA-Z0-9_\-]+)\s+related', raw_filter)
        if rel_m:
            kws.add(rel_m.group(1).strip())
        success, msg = await group_channels_into_category(guild, cat_name, list(kws), author)
        return True, msg

    # 15.2 Group: "group the tillu things all in one group named tillu"
    cat_group_things = re.search(
        rf'group\s+(?:all\s+)?(?:the\s+)?([a-zA-Z0-9_\-]+)\s+(?:things|channels?|stuff)\s+(?:all\s+in\s+one\s+group\s+named|into|in)\s+(?:{CAT_PATTERN}\s+)?["\']?([a-zA-Z0-9_\- ]+?)["\']?',
        clean_text
    )
    if cat_group_things:
        kw = cat_group_things.group(1).strip()
        cat_name = cat_group_things.group(2).strip()
        success, msg = await group_channels_into_category(guild, cat_name, [kw, cat_name], author)
        return True, msg

    # 15.3 Move all matching: "group all tillu stuff in tillu category" / "move all memory channels to category archive"
    cat_move_all = re.search(
        rf'(?:group|move|shift)\s+(?:all\s+)?([a-zA-Z0-9_\-]+)\s+(?:related\s+)?(?:things|stuff|channels?)\s+(?:in|into|to)\s+(?:{CAT_PATTERN}\s+)?["\']?([a-zA-Z0-9_\- ]+?)["\']?',
        clean_text
    )
    if cat_move_all and not re.search(r'^(?:move|shift)\s+(?:channel\s+)?<#\d+>', clean_text):
        kw = cat_move_all.group(1).strip()
        cat_name = cat_move_all.group(2).strip()
        success, msg = await group_channels_into_category(guild, cat_name, [kw, cat_name], author)
        return True, msg

    # 15.4 Move single channel to category: "move channel #rules to category Information"
    move_single_ch = re.search(
        rf'(?:move|shift)\s+(?:channel\s+)?(?:<#(\d+)>|#?([a-zA-Z0-9_\-]+))\s+(?:to|in|into)\s+(?:{CAT_PATTERN}\s+)?["\']?([a-zA-Z0-9_\- ]+?)["\']?',
        clean_text
    )
    if move_single_ch:
        ch_id = move_single_ch.group(1)
        ch_name = move_single_ch.group(2)
        cat_query = move_single_ch.group(3).strip()

        target_ch = guild.get_channel(int(ch_id)) if ch_id else None
        if not target_ch and ch_name:
            target_ch = discord.utils.find(lambda c: c.name.lower() == ch_name.lower(), guild.channels)

        if not target_ch:
            return True, f"❌ Channel `{ch_name or ch_id}` nahi mila!"

        target_cat = find_category_fuzzy(guild, cat_query)
        if not target_cat:
            try:
                target_cat = await guild.create_category(name=cat_query.title(), reason=f"Created by Tillu via {author.name}")
            except Exception as ce:
                return True, f"⚠️ Category create error: {ce}"

        try:
            await target_ch.edit(category=target_cat, reason=f"Moved by Tillu via {author.name}")
            return True, f"📂 **Channel Moved!** {target_ch.mention} ab category **{target_cat.name}** me shift ho gaya hai! ✅"
        except Exception as e:
            return True, f"⚠️ Channel move error: {e}"

    # 15.5 Delete Category: "delete category old-archive"
    del_cat_match = re.search(rf'(?:delete|remove|hata\s+do)\s+{CAT_PATTERN}\s+["\']?([^"\'\n:]+?)["\']?$', clean_text)
    if del_cat_match:
        cat_q = del_cat_match.group(1).strip()
        cat = find_category_fuzzy(guild, cat_q)
        if not cat:
            return True, f"❌ Category `{cat_q}` nahi mila!"
        try:
            c_name = cat.name
            await cat.delete(reason=f"Deleted by Tillu via {author.name}")
            return True, f"🗑️ **Category Deleted!** Category `{c_name}` delete kar diya gaya hai (channels safe hain)."
        except Exception as e:
            return True, f"⚠️ Category delete error: {e}"

    # 15.6 Standalone Create Category: "create category Staff Only"
    create_cat_match = re.search(rf'(?:create|make|bana(?:\s+do)?)\s+(?:a\s+)?(?:new\s+)?{CAT_PATTERN}\s*(?:named?\s*[:\-]*\s*|called?\s*[:\-]*\s*)?["\']?([^"\'\n:]+?)["\']?$', clean_text)
    if create_cat_match:
        cat_name = create_cat_match.group(1).strip()
        existing = find_category_fuzzy(guild, cat_name)
        if existing:
            return True, f"ℹ️ Category `{existing.name}` pehle se exist karta hai!"
        try:
            new_cat = await guild.create_category(name=cat_name.title(), reason=f"Created by Tillu via {author.name}")
            return True, f"📂 **Category Created!** Nayi category `{new_cat.name}` ban gayi hai!"
        except Exception as e:
            return True, f"⚠️ Category create error: {e}"

    # 15.7 SERVER LOCKDOWN & UNLOCKDOWN
    if any(p in clean_text for p in ["lockdown server", "server lockdown", "lock the server", "lock down server"]):
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi poora server lockdown kar sakte hain!"
        locked_cnt = 0
        for ch in guild.text_channels:
            try:
                await ch.set_permissions(guild.default_role, send_messages=False, reason=f"Server Lockdown by Tillu via {author.name}")
                locked_cnt += 1
            except Exception:
                pass
        return True, f"🚨 **SERVER LOCKDOWN ACTIVE!** `{locked_cnt}` text channels me @everyone ka send permission block kar diya gaya hai!"

    if any(p in clean_text for p in ["unlockdown server", "server unlockdown", "unlock the server", "lift lockdown"]):
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi server lockdown hata sakte hain!"
        unlocked_cnt = 0
        for ch in guild.text_channels:
            try:
                await ch.set_permissions(guild.default_role, send_messages=True, reason=f"Server Lockdown lifted by Tillu via {author.name}")
                unlocked_cnt += 1
            except Exception:
                pass
        return True, f"🟢 **SERVER LOCKDOWN LIFTED!** `{unlocked_cnt}` channels me send permission restore kar diya gaya hai!"

    # 15.8 RENAME SERVER
    rename_srv_match = re.search(r'(?:rename|change\s+name\s+of)\s+server\s+(?:to\s+)?["\']?([^"\']+)["\']?', clean_text)
    if rename_srv_match:
        if not (author.guild_permissions.manage_guild or author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi server rename kar sakte hain!"
        new_sname = rename_srv_match.group(1).strip()
        try:
            old_sname = guild.name
            await guild.edit(name=new_sname, reason=f"Renamed by Tillu via {author.name}")
            return True, f"👑 **Server Renamed!** Server ka naam `{old_sname}` se badal kar `{new_sname}` kar diya gaya hai!"
        except Exception as e:
            return True, f"⚠️ Server rename error: {e}"

    # 15. CLONE CHANNEL
    if "clone" in clean_text and "channel" in clean_text:
        target_ch = message.channel
        ch_m = re.search(r'<#(\d+)>', clean_text)
        if ch_m:
            target_ch = guild.get_channel(int(ch_m.group(1))) or message.channel
        try:
            cloned = await target_ch.clone(reason=f"Cloned by Tillu via {author.name}")
            return True, f"👥 **Channel Cloned!** Duplicate channel {cloned.mention} create kar diya gaya hai!"
        except Exception as e:
            return True, f"⚠️ Clone error: {e}"

    # 16. TIMEOUT / MUTE USER
    timeout_match = re.search(r'(?:timeout|mute|chup\s+kara\s+do)\s+(.+?)(?:\s+(?:for\s+)?(\d{1,4})\s*(?:m|min|minutes?))?$', text, re.IGNORECASE)
    if timeout_match and (message.mentions or re.search(r'\d{17,20}', text)):
        target_member = message.mentions[0] if message.mentions else None
        if not target_member:
            uid_m = re.search(r'\d{17,20}', text)
            if uid_m:
                target_member = guild.get_member(int(uid_m.group(0)))

        mins = int(timeout_match.group(2)) if timeout_match.group(2) else 10
        if target_member:
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
                await target_member.timeout(until, reason=f"Muted by Tillu on request of {author.name}")
                return True, f"🤫 **User Muted!** {target_member.mention} ko `{mins}` minute ke liye timeout kar diya gaya hai."
            except Exception as e:
                return True, f"⚠️ Timeout error: {e}"

    # 17. DISCORD KICK MEMBER
    discord_kick_m = re.search(r'\b(?:kick|remove\s+user|server\s+se\s+nikalo)\s+([^\n\r]+)', text, re.IGNORECASE)
    if discord_kick_m and (message.mentions or re.search(r'\d{17,20}', text) or "discord" in text.lower()):
        target_str = discord_kick_m.group(1).strip()
        target_member = await find_member_fuzzy(target_str)
        if target_member:
            if target_member.id == author.id:
                return True, "Arre boss! Aap khud ko kick kyu kar rahe ho? 😂"
            if target_member.top_role >= author.top_role and author.id != guild.owner_id:
                return True, "🚫 Aap apne se unchi ya barabar role wale member ko kick nahi kar sakte!"
            try:
                await target_member.kick(reason=f"Kicked from Discord by Tillu on command of {author.name}")
                return True, f"👢 **User Kicked from Discord:** `{target_member.display_name}` ({target_member.mention}) ko server se kick kar diya gaya hai!"
            except Exception as e:
                return True, f"⚠️ Discord kick failed: {e}"

    # 18. DISCORD BAN MEMBER
    discord_ban_m = re.search(r'\b(?:ban|server\s+ban|discord\s+ban)\s+([^\n\r]+)', text, re.IGNORECASE)
    if discord_ban_m and (message.mentions or re.search(r'\d{17,20}', text) or "discord" in text.lower()):
        target_str = discord_ban_m.group(1).strip()
        target_member = await find_member_fuzzy(target_str)
        if target_member:
            if target_member.id == author.id:
                return True, "Boss, main aapko ban nahi kar sakta! 👑"
            if target_member.top_role >= author.top_role and author.id != guild.owner_id:
                return True, "🚫 Aap apne se barabar ya unchi role wale member ko ban nahi kar sakte!"
            try:
                await guild.ban(target_member, reason=f"Banned from Discord by Tillu on command of {author.name}", delete_message_days=0)
                return True, f"🔨 **User Banned from Discord:** `{target_member.display_name}` ({target_member.mention}) ko permanent ban kar diya gaya hai!"
            except Exception as e:
                return True, f"⚠️ Discord ban failed: {e}"

    # 19. DISCORD UNBAN MEMBER
    discord_unban_m = re.search(r'\b(?:unban|un-ban)\s+(?:from\s+discord\s+)?([^\n\r]+)', text, re.IGNORECASE)
    if discord_unban_m and ("discord" in text.lower() or re.search(r'\d{17,20}', text)):
        target_str = discord_unban_m.group(1).strip()
        try:
            bans = [entry async for entry in guild.bans()]
            target_ban = None
            for b in bans:
                if str(b.user.id) == target_str or b.user.name.lower() == target_str.lower():
                    target_ban = b
                    break
            if target_ban:
                await guild.unban(target_ban.user, reason=f"Unbanned by Tillu on request of {author.name}")
                return True, f"✅ **User Unbanned from Discord:** `{target_ban.user.name}` ko unban kar diya gaya hai!"
            else:
                return True, f"🔍 Discord ban list me user `{target_str}` nahi mila."
        except Exception as e:
            return True, f"⚠️ Discord unban failed: {e}"

    # ═════════════════════════════════════════════════════════════════════════
    # ── STEP 2: AI ACTION CLASSIFICATION (NVIDIA AI Primary -> Groq Fallback) ─
    # ═════════════════════════════════════════════════════════════════════════
    import asyncio
    ai_result = await asyncio.to_thread(_nvidia_classify_action, text)
    if not ai_result or ai_result.get("action", "none") == "none":
        ai_result = await asyncio.to_thread(_groq_classify_action, text)
    ai_action = ai_result.get("action", "none")

    if ai_action == "purge":
        count = min(int(ai_result.get("count", 5)), 100)
        target_ch = message.channel
        ch_name = ai_result.get("channel")
        if ch_name and str(ch_name).lower() not in ["null", "none", "current", "", "this"]:
            clean_ch_name = re.sub(r'[^a-zA-Z0-9]', '', str(ch_name)).lower()
            found = discord.utils.find(lambda c: clean_ch_name in re.sub(r'[^a-zA-Z0-9]', '', c.name).lower(), guild.channels)
            if found and isinstance(found, discord.TextChannel):
                target_ch = found
        try:
            bot_only = any(w in text.lower() for w in ["your", "tillu", "apne", "khud ke", "sent by you"])
            if bot_only:
                my_id = guild.me.id if guild.me else message.author.id
                deleted = await target_ch.purge(limit=min(count * 5, 100), check=lambda m: m.author.id == my_id)
            else:
                deleted = await target_ch.purge(limit=count + 1)
            actual = len(deleted)
            conf = f"🧹 **Done Boss!** `{actual}` messages delete kar diye {target_ch.mention} se!"
            sent = await message.channel.send(conf)
            try:
                await sent.delete(delay=6)
            except Exception:
                pass
            return True, None
        except Exception as e:
            return True, f"⚠️ Purge error: {e}"

    elif ai_action in ("create_role", "create_and_assign_role"):
        role_name = ai_result.get("role_name", "").strip().title()
        if not role_name:
            return False, None
        existing = find_role_fuzzy(role_name)
        role_kwargs, feat_details = parse_role_features(data=ai_result, raw_text=text)
        if not existing:
            try:
                existing = await guild.create_role(
                    name=role_name,
                    reason=f"Created by Tillu via {author.name}",
                    **role_kwargs
                )
            except Exception as e:
                return True, f"⚠️ Role create error: {e}"
        else:
            try:
                if role_kwargs:
                    await existing.edit(reason=f"Updated features by Tillu via {author.name}", **role_kwargs)
            except Exception:
                pass

        feat_msg = ("\n" + " | ".join(feat_details)) if feat_details else ""
        msg = f"🎭 **Role Created!** `{existing.name}` ban gaya!{feat_msg}"
        if ai_action == "create_and_assign_role":
            member_q = ai_result.get("member", "")
            target = await find_member_fuzzy(member_q)
            if target:
                try:
                    await target.add_roles(existing, reason=f"Assigned by Tillu via {author.name}")
                    msg += f"\nAur {target.mention} ko assign kar diya! 🎉"
                except Exception as e:
                    msg += f" (Role assign error: {e})"
            else:
                msg += f"\n⚠️ Member `{member_q}` nahi mila, role create hua hai — manually assign karo."
        return True, msg

    elif ai_action == "assign_role":
        role_name = ai_result.get("role_name", "").strip()
        member_q = ai_result.get("member", "")
        role = find_role_fuzzy(role_name) or find_role_fuzzy(role_name.title())
        if not role:
            role_kwargs, _ = parse_role_features(data=ai_result, raw_text=text)
            try:
                role = await guild.create_role(
                    name=role_name.title(),
                    reason=f"Auto-created by Tillu via {author.name}",
                    **role_kwargs
                )
            except Exception as e:
                return True, f"⚠️ Role nahi mila aur create nahi hua: {e}"
        target = await find_member_fuzzy(member_q)
        if not target:
            return True, f"❌ Member `{member_q}` nahi mila! @mention karke try karo."
        try:
            await target.add_roles(role, reason=f"Assigned by Tillu via {author.name}")
            return True, f"✅ **Done!** `{role.name}` role {target.mention} ko de diya! 🎉"
        except Exception as e:
            return True, f"⚠️ Assign error: {e}"

    elif ai_action == "remove_role_from_server":
        role_name = ai_result.get("role_name", "").strip()
        role = find_role_fuzzy(role_name)
        if not role:
            return True, f"❌ Role `{role_name}` nahi mila!"
        try:
            await role.delete(reason=f"Deleted by Tillu via {author.name}")
            return True, f"🗑️ **Role Deleted!** `{role_name}` role server se delete kar diya!"
        except Exception as e:
            return True, f"⚠️ Role delete error: {e}"

    elif ai_action == "remove_role_from_member":
        role_name = ai_result.get("role_name", "").strip()
        member_q = ai_result.get("member", "")
        role = find_role_fuzzy(role_name)
        if not role:
            return True, f"❌ Role `{role_name}` nahi mila!"
        target = await find_member_fuzzy(member_q)
        if not target:
            return True, f"❌ Member `{member_q}` nahi mila!"
        try:
            await target.remove_roles(role, reason=f"Removed by Tillu via {author.name}")
            return True, f"✅ `{role.name}` role {target.mention} se hata diya!"
        except Exception as e:
            return True, f"⚠️ Remove error: {e}"

    elif ai_action == "create_channel":
        ch_name = ai_result.get("channel_name", "").strip().lower().replace(" ", "-")
        ch_type = ai_result.get("type", "text")
        topic = ai_result.get("topic")
        slowmode = ai_result.get("slowmode")
        is_private = ai_result.get("private", False)
        try:
            if ch_type == "voice":
                new_ch = await guild.create_voice_channel(name=ch_name, reason=f"Created by Tillu via {author.name}")
            else:
                ch_kwargs = {"name": ch_name, "reason": f"Created by Tillu via {author.name}"}
                if topic:
                    ch_kwargs["topic"] = str(topic)
                if slowmode and isinstance(slowmode, (int, float)):
                    ch_kwargs["slowmode_delay"] = int(slowmode)
                if is_private:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        author: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    }
                    ch_kwargs["overwrites"] = overwrites
                new_ch = await guild.create_text_channel(**ch_kwargs)
            return True, f"📁 **Channel Created!** {new_ch.mention} ready hai!"
        except Exception as e:
            return True, f"⚠️ Channel create error: {e}"


    elif ai_action == "delete_channel":
        ch_name = ai_result.get("channel_name", "").strip()
        target_ch = discord.utils.find(lambda c: ch_name.lower() in c.name.lower(), guild.channels)
        if not target_ch:
            return True, f"❌ Channel `{ch_name}` nahi mila!"
        try:
            old = target_ch.name
            await target_ch.delete(reason=f"Deleted by Tillu via {author.name}")
            return True, f"🗑️ Channel `#{old}` delete kar diya!"
        except Exception as e:
            return True, f"⚠️ Delete error: {e}"

    elif ai_action == "lock_channel":
        ch_name = ai_result.get("channel_name", "")
        target_ch = message.channel
        if ch_name and ch_name not in ["current", "this"]:
            found = discord.utils.find(lambda c: ch_name.lower() in c.name.lower(), guild.channels)
            if found:
                target_ch = found
        try:
            await target_ch.set_permissions(guild.default_role, send_messages=False, reason=f"Locked by Tillu via {author.name}")
            return True, f"🔒 **Locked!** {target_ch.mention} lock kar diya!"
        except Exception as e:
            return True, f"⚠️ Lock error: {e}"

    elif ai_action == "unlock_channel":
        ch_name = ai_result.get("channel_name", "")
        target_ch = message.channel
        if ch_name and ch_name not in ["current", "this"]:
            found = discord.utils.find(lambda c: ch_name.lower() in c.name.lower(), guild.channels)
            if found:
                target_ch = found
        try:
            await target_ch.set_permissions(guild.default_role, send_messages=True, reason=f"Unlocked by Tillu via {author.name}")
            return True, f"🔓 **Unlocked!** {target_ch.mention} open kar diya!"
        except Exception as e:
            return True, f"⚠️ Unlock error: {e}"

    elif ai_action == "restrict_posting":
        ch_name = ai_result.get("channel_name", "")
        allowed = [r.lower() for r in ai_result.get("allowed_roles", ["moderator", "admin"])]
        target_ch = message.channel
        if ch_name and ch_name not in ["current", "this", ""]:
            found = discord.utils.find(lambda c: ch_name.lower().replace(" ", "-").replace(" ", "_") in c.name.lower(), guild.channels)
            if found:
                target_ch = found
        try:
            await target_ch.set_permissions(guild.default_role, send_messages=False, reason=f"Restricted by Tillu via {author.name}")
            granted = []
            for role in guild.roles:
                if any(kw in role.name.lower() for kw in allowed + ["owner", "staff"]):
                    await target_ch.set_permissions(role, send_messages=True, reason=f"Granted by Tillu via {author.name}")
                    granted.append(role.name)
            return True, f"🔐 **Done!** {target_ch.mention} ab sirf **{', '.join(granted) or 'privileged roles'}** post kar sakte hain!"
        except Exception as e:
            return True, f"⚠️ Restrict error: {e}"

    elif ai_action == "rename_channel":
        ch_name = ai_result.get("channel_name", "")
        new_name = ai_result.get("new_name", "").strip().lower().replace(" ", "-")
        target_ch = message.channel
        if ch_name and ch_name not in ["current", "this"]:
            found = discord.utils.find(lambda c: ch_name.lower() in c.name.lower(), guild.channels)
            if found:
                target_ch = found
        try:
            old = target_ch.name
            await target_ch.edit(name=new_name, reason=f"Renamed by Tillu via {author.name}")
            return True, f"✏️ Channel `#{old}` → `#{new_name}` rename kar diya!"
        except Exception as e:
            return True, f"⚠️ Rename error: {e}"

    elif ai_action == "timeout":
        member_q = ai_result.get("member", "")
        mins = int(ai_result.get("minutes", 10))
        target = await find_member_fuzzy(member_q)
        if not target:
            return True, f"❌ Member `{member_q}` nahi mila!"
        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
            await target.timeout(until, reason=f"Muted by Tillu via {author.name}")
            return True, f"🤫 {target.mention} ko {mins} min ke liye timeout kar diya!"
        except Exception as e:
            return True, f"⚠️ Timeout error: {e}"

    elif ai_action == "backup_server":
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi backup le sakte hain!"
        import backup_manager
        success, msg, _ = backup_manager.create_backup(guild)
        return True, msg

    elif ai_action == "list_backups":
        import backup_manager
        b_list = backup_manager.list_backups(guild.id)
        if not b_list:
            return True, "📂 Abhi tak koi backup snapshot create nahi hua hai. `tillu backup server` se create karo!"
        return True, f"📂 **Available Backups:**\n" + "\n".join(f"• `{b}`" for b in b_list[:5])

    elif ai_action == "restore_section":
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi restore kar sakte hain!"
        import backup_manager
        section = ai_result.get("section", "server")
        target = ai_result.get("target") or ""
        success, msg = await backup_manager.restore_section(guild, section, specific_target=target)
        return True, msg

    elif ai_action == "create_category":
        cat_name = ai_result.get("category_name", "").strip()
        if not cat_name:
            return False, None
        existing = find_category_fuzzy(guild, cat_name)
        if existing:
            return True, f"ℹ️ Category `{existing.name}` pehle se exist karta hai!"
        try:
            new_cat = await guild.create_category(name=cat_name.title(), reason=f"Created by Tillu via {author.name}")
            return True, f"📂 **Category Created!** Nayi category `{new_cat.name}` ban gayi hai!"
        except Exception as e:
            return True, f"⚠️ Category create error: {e}"

    elif ai_action == "delete_category":
        cat_name = ai_result.get("category_name", "").strip()
        cat = find_category_fuzzy(guild, cat_name)
        if not cat:
            return True, f"❌ Category `{cat_name}` nahi mila!"
        try:
            c_name = cat.name
            await cat.delete(reason=f"Deleted by Tillu via {author.name}")
            return True, f"🗑️ **Category Deleted!** Category `{c_name}` delete kar diya gaya hai."
        except Exception as e:
            return True, f"⚠️ Category delete error: {e}"

    elif ai_action == "move_channel_to_category":
        ch_q = ai_result.get("channel", "")
        cat_q = ai_result.get("category", "")
        ch_id_m = re.search(r'\d{15,22}', str(ch_q))
        if ch_id_m:
            target_ch = guild.get_channel(int(ch_id_m.group(0)))
        else:
            clean_ch = str(ch_q).lower().strip().lstrip("#")
            target_ch = discord.utils.find(lambda c: c.name.lower() == clean_ch, guild.channels) or (
                discord.utils.find(lambda c: clean_ch in c.name.lower(), guild.channels) if len(clean_ch) >= 3 else None
            )
        if not target_ch:
            return True, f"❌ Channel `{ch_q}` nahi mila!"
        target_cat = find_category_fuzzy(guild, cat_q)
        if not target_cat:
            target_cat = await guild.create_category(name=cat_q.title(), reason=f"Created by Tillu via {author.name}")
        try:
            await target_ch.edit(category=target_cat, reason=f"Moved by Tillu via {author.name}")
            return True, f"📂 **Channel Moved!** {target_ch.mention} ab category **{target_cat.name}** me shift ho gaya hai!"
        except Exception as e:
            return True, f"⚠️ Channel move error: {e}"

    elif ai_action == "group_channels":
        cat_name = ai_result.get("category", "Grouped Channels")
        kws = ai_result.get("keywords", [cat_name])
        success, msg = await group_channels_into_category(guild, cat_name, kws, author)
        return True, msg

    elif ai_action == "add_bot":
        bot_q = ai_result.get("bot", "")
        is_mod = (
            author.guild_permissions.manage_guild
            or author.guild_permissions.administrator
            or guild.owner_id == author.id
            or any(r.name.lower() in ['mod', 'moderator', 'admin', 'administrator', 'owner', 'staff'] for r in author.roles)
        )
        if not is_mod:
            return True, "🚫 **Permission Denied!** Sirf Server Owner, Administrators aur Moderators hi bots add kar sakte hain!"
        embed, view, msg = handle_add_bot_action(guild, author, bot_q)
        if embed:
            await message.channel.send(embed=embed, view=view)
            return True, None
        return True, msg

    elif ai_action == "lockdown_server":
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi poora server lockdown kar sakte hain!"
        locked_cnt = 0
        for ch in guild.text_channels:
            try:
                await ch.set_permissions(guild.default_role, send_messages=False, reason=f"Server Lockdown by Tillu via {author.name}")
                locked_cnt += 1
            except Exception:
                pass
        return True, f"🚨 **SERVER LOCKDOWN ACTIVE!** `{locked_cnt}` text channels me send permission block ho gaya hai!"

    elif ai_action == "unlock_server":
        if not (author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi server lockdown hata sakte hain!"
        unlocked_cnt = 0
        for ch in guild.text_channels:
            try:
                await ch.set_permissions(guild.default_role, send_messages=True, reason=f"Server Lockdown lifted by Tillu via {author.name}")
                unlocked_cnt += 1
            except Exception:
                pass
        return True, f"🟢 **SERVER LOCKDOWN LIFTED!** `{unlocked_cnt}` channels me send permission restore kar diya gaya hai!"

    elif ai_action == "rename_server":
        if not (author.guild_permissions.manage_guild or author.guild_permissions.administrator or guild.owner_id == author.id):
            return True, "🚫 Sirf Server Owner ya Administrators hi server rename kar sakte hain!"
        new_sname = ai_result.get("new_name", "").strip()
        try:
            old_sname = guild.name
            await guild.edit(name=new_sname, reason=f"Renamed by Tillu via {author.name}")
            return True, f"👑 **Server Renamed!** Server ka naam `{old_sname}` → `{new_sname}` kar diya gaya!"
        except Exception as e:
            return True, f"⚠️ Server rename error: {e}"

    return False, None

