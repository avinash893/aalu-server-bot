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
{"action": "timeout", "member": "<name>", "minutes": <number>}
{"action": "none"}

Rules:
- "make this role:- <name> with this features ..." -> extract role_name cleanly, and parse color, hoist, mentionable, permissions.
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
        "lock", "unlock", "slowmode", "topic", "rename", "category", "clone", "clip", "post in",
        "permission", "creators", "admin"
    ]
    if not any(kw in clean_text for kw in MGMT_KEYWORDS):
        return False, None

    # ── HELPER: Fuzzy member finder ──────────────────────────────────────────
    def find_member_fuzzy(query: str) -> discord.Member | None:
        """Find member by mention, ID, exact name, nick, or partial name (case-insensitive)."""
        if message.mentions:
            return message.mentions[0]
        clean_q = re.sub(r'[^a-zA-Z0-9]', '', query).lower()
        # Exact match first
        for m in guild.members:
            nm = re.sub(r'[^a-zA-Z0-9]', '', m.name).lower()
            nk = re.sub(r'[^a-zA-Z0-9]', '', m.nick or '').lower()
            if str(m.id) == clean_q or nm == clean_q or nk == clean_q:
                return m
        # Partial match fallback
        for m in guild.members:
            nm = re.sub(r'[^a-zA-Z0-9]', '', m.name).lower()
            nk = re.sub(r'[^a-zA-Z0-9]', '', m.nick or '').lower()
            if clean_q in nm or clean_q in nk or nm in clean_q:
                return m
        return None

    # ── HELPER: Fuzzy role finder ─────────────────────────────────────────────
    def find_role_fuzzy(query: str) -> discord.Role | None:
        q = query.lower().strip()
        q_clean = re.sub(r'^(?:named?\s*[:\-]*\s*|role\s+)', '', q).strip()
        q_alnum = re.sub(r'[^a-zA-Z0-9]', '', q_clean)
        # Exact name match
        for r in guild.roles:
            if r.name.lower() == q or r.name.lower() == q_clean:
                return r
        # Alphanumeric match (handles "Named:- Creators" matching "Creators")
        for r in guild.roles:
            r_alnum = re.sub(r'[^a-zA-Z0-9]', '', r.name).lower()
            if q_alnum and (r_alnum == q_alnum or q_alnum in r_alnum or r_alnum in q_alnum):
                return r
        return None

    # ═════════════════════════════════════════════════════════════════════════
    # ── STEP 1: INSTANT LOCAL REGEX PARSING (0ms latency, zero network) ─────
    # ═════════════════════════════════════════════════════════════════════════

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
        for ch in guild.channels:
            if isinstance(ch, discord.TextChannel) and ch.name.lower() in clean_text and ch != message.channel:
                target_ch = ch
                break
        try:
            bot_only = any(w in clean_text for w in ["your", "tillu", "apne", "khud ke"])
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
            err = f"⚠️ Messages delete karne me error aaya: {e}"
            await message.channel.send(err)
            return True, err

    # 2. DELETE / REMOVE ROLE FROM SERVER
    # e.g., "remove the role Named:- Creators from discord", "delete role Creators"
    del_role_match = re.search(
        r'(?:delete|remove|hata\s+do)\s+(?:the\s+)?role\s+(?:named?\s*[:\-]*\s*|called?\s*[:\-]*\s*)?["\']?([^"\']+)["\']?(?:\s+from\s+(?:discord|server))?',
        clean_text
    )
    if del_role_match and not re.search(r'\bfrom\s+(?:<@|\b[a-zA-Z0-9_]{3,}\b)', clean_text):
        role_q = del_role_match.group(1).strip()
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
        r'(?:give|add|assign|de\s+do)\s+(?:role\s+)?["\']?([^"\'@<>\n]+?)["\']?\s+(?:role\s+)?to\s+(.+)',
        text,
        re.IGNORECASE
    )
    compound_match = re.search(
        r'create\s+(?:a\s+)?(?:new\s+)?role\s+(?:named?\s+)?["\']?([^"\':\n]+)["\']?'
        r'[\s\S]{0,60}?(?:add|give)\s+(.+?)\s+to\s+(?:it|that\s+role)',
        text,
        re.IGNORECASE | re.DOTALL
    )
    if compound_match:
        add_role_match = compound_match

    if add_role_match:
        role_query = add_role_match.group(1).strip()
        target_query = add_role_match.group(2).strip()

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
        target_member = find_member_fuzzy(target_query)
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
        r'(?:remove|take|hata\s+do)\s+role\s+["\']?([^"\']+)["\']?\s+from\s+(.+)',
        text,
        re.IGNORECASE
    )
    if rem_role_match:
        role_query = rem_role_match.group(1).strip()
        target_query = rem_role_match.group(2).strip()

        target_member = find_member_fuzzy(target_query)
        if not target_member:
            return True, f"❌ Member `{target_query}` nahi mila!"

        role = discord.utils.find(lambda r: r.name.lower() == role_query.lower(), guild.roles)
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

    # 14. CREATE CATEGORY
    cat_match = re.search(r'create\s+category\s+["\']?([^"\']+)["\']?', clean_text)
    if cat_match:
        cat_name = cat_match.group(1).strip()
        try:
            new_cat = await guild.create_category(name=cat_name, reason=f"Created by Tillu via {author.name}")
            return True, f"📂 **Category Created!** Nayi category `{new_cat.name}` ban gayi hai!"
        except Exception as e:
            return True, f"⚠️ Category create error: {e}"

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
            target = find_member_fuzzy(member_q)
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
        target = find_member_fuzzy(member_q)
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
        target = find_member_fuzzy(member_q)
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
        target = find_member_fuzzy(member_q)
        if not target:
            return True, f"❌ Member `{member_q}` nahi mila!"
        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
            await target.timeout(until, reason=f"Muted by Tillu via {author.name}")
            return True, f"🤫 {target.mention} ko {mins} min ke liye timeout kar diya!"
        except Exception as e:
            return True, f"⚠️ Timeout error: {e}"

    return False, None
