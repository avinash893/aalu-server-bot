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
{"action": "create_role", "role_name": "<name>"}
{"action": "assign_role", "role_name": "<name>", "member": "<name/mention>"}
{"action": "create_and_assign_role", "role_name": "<name>", "member": "<name/mention>"}
{"action": "remove_role_from_server", "role_name": "<name>"}
{"action": "remove_role_from_member", "role_name": "<name>", "member": "<name/mention>"}
{"action": "create_channel", "channel_name": "<name>", "type": "text|voice"}
{"action": "delete_channel", "channel_name": "<name>"}
{"action": "lock_channel", "channel_name": "<current or name>"}
{"action": "unlock_channel", "channel_name": "<current or name>"}
{"action": "restrict_posting", "channel_name": "<name>", "allowed_roles": ["moderator","admin"]}
{"action": "rename_channel", "channel_name": "<old>", "new_name": "<new>"}
{"action": "timeout", "member": "<name>", "minutes": <number>}
{"action": "none"}

Rules:
- "remove the role X from discord" → remove_role_from_server
- "remove role X from @user" → remove_role_from_member
- "delete N messages/chats" → purge
- "only mods can post in #channel" → restrict_posting
- If action is not Discord-related → {"action": "none"}
"""

def _groq_classify_action(text: str) -> dict:
    """Use Groq to classify the Discord action intent. Returns dict or {}."""
    try:
        import os
        raw_keys = os.environ.get("GROQ_API_KEYS", "")
        single = os.environ.get("GROQ_API_KEY", "")
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()] or ([single] if single else [])
        if not keys:
            return {}
        models = [
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b"
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
                            "max_tokens": 150,
                            "temperature": 0
                        },
                        timeout=8
                    )
                    if r.status_code == 200:
                        content = r.json()["choices"][0]["message"]["content"].strip()
                        # Extract JSON (handles markdown codeblocks like ```json { ... } ```)
                        match = re.search(r'\{[\s\S]*?\}', content)
                        if match:
                            parsed = json.loads(match.group(0))
                            if parsed.get("action") and parsed.get("action") != "none":
                                logger.info(f"[DiscordActionAI] Classified: {parsed}")
                                return parsed
                    elif r.status_code == 429:
                        break  # try next key
                except Exception as ex:
                    logger.debug(f"[DiscordActionAI] {model} err: {ex}")
                    continue
    except Exception as e:
        logger.warning(f"[DiscordActionAI] classify error: {e}")
    return {}

async def parse_and_execute_discord_action(
    message: discord.Message,
    author: discord.Member,
    guild: discord.Guild,
    text: str
) -> Tuple[bool, Optional[str]]:
    """
    Check if the user message contains a Discord server management command.
    Returns (handled: bool, confirmation_message: Optional[str]).
    """
    if not guild or not isinstance(author, discord.Member):
        return False, None

    clean_text = text.lower().strip()

    # ── FAST BAILOUT: Skip immediately for normal conversation (0ms overhead) ──
    MGMT_KEYWORDS = [
        "role", "channel", "delete", "purge", "remove", "saaf", "hata", "mute", "timeout",
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

    # ── AI-FIRST: Groq classifies action → execute structured result ──────────
    import asyncio
    ai_result = await asyncio.to_thread(_groq_classify_action, text)
    ai_action = ai_result.get("action", "none")

    if ai_action == "purge":
        count = min(int(ai_result.get("count", 5)), 100)
        # Optionally target a different channel by name (e.g. "admin", "chat")
        target_ch = message.channel
        ch_name = ai_result.get("channel")
        if ch_name and str(ch_name).lower() not in ["null", "none", "current", "", "this"]:
            clean_ch_name = re.sub(r'[^a-zA-Z0-9]', '', str(ch_name)).lower()
            found = discord.utils.find(lambda c: clean_ch_name in re.sub(r'[^a-zA-Z0-9]', '', c.name).lower(), guild.channels)
            if found and isinstance(found, discord.TextChannel):
                target_ch = found
        try:
            bot_only = any(w in text.lower() for w in ["your", "tillu", "apne", "khud ke", "sent by you"])
            deleted = []
            if bot_only:
                my_id = guild.me.id if guild.me else message.author.id
                def is_bot_msg(m):
                    return m.author.id == my_id
                deleted = await target_ch.purge(limit=min(count * 5, 100), check=is_bot_msg)
            else:
                deleted = await target_ch.purge(limit=count + 1)
            actual = len(deleted)
            conf = f"🧹 **Done Boss!** `{actual}` messages delete kar diye {target_ch.mention} se!"
            sent = await message.channel.send(conf)
            try:
                await sent.delete(delay=6)
            except Exception:
                pass
            return True, None  # already sent
        except Exception as e:
            return True, f"⚠️ Purge error: {e}"


    elif ai_action in ("create_role", "create_and_assign_role"):
        role_name = ai_result.get("role_name", "").strip().title()
        if not role_name:
            return False, None
        existing = find_role_fuzzy(role_name)
        if not existing:
            try:
                existing = await guild.create_role(name=role_name, mentionable=True, reason=f"Created by Tillu via {author.name}")
            except Exception as e:
                return True, f"⚠️ Role create error: {e}"
        msg = f"🎭 **Role Created!** `{existing.name}` ban gaya!"
        if ai_action == "create_and_assign_role":
            member_q = ai_result.get("member", "")
            target = find_member_fuzzy(member_q)
            if target:
                try:
                    await target.add_roles(existing, reason=f"Assigned by Tillu via {author.name}")
                    msg += f" Aur {target.mention} ko assign kar diya! 🎉"
                except Exception as e:
                    msg += f" (Role assign error: {e})"
            else:
                msg += f" ⚠️ Member `{member_q}` nahi mila, role create hua hai — manually assign karo."
        return True, msg

    elif ai_action == "assign_role":
        role_name = ai_result.get("role_name", "").strip()
        member_q = ai_result.get("member", "")
        role = find_role_fuzzy(role_name) or find_role_fuzzy(role_name.title())
        if not role:
            try:
                role = await guild.create_role(name=role_name.title(), mentionable=True, reason=f"Auto-created by Tillu via {author.name}")
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
        try:
            if ch_type == "voice":
                new_ch = await guild.create_voice_channel(name=ch_name, reason=f"Created by Tillu via {author.name}")
            else:
                new_ch = await guild.create_text_channel(name=ch_name, reason=f"Created by Tillu via {author.name}")
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

    # ai_action == "none" → fall through to regex patterns below
    # ─────────────────────────────────────────────────────────────────────────

    # 1. PURGE / DELETE MESSAGES (regex fallback)
    # e.g., "tillu delete 10 messages", "delete 4 of your recent messages in admin"
    purge_match = re.search(r'(?:delete|purge|remove|saaf\s+kar\s+do|hata\s+do)\s+(?:(?:last|recent|of\s+your\s+recent|your)\s+)?(\d{1,3})\s+(?:(?:of\s+(?:your\s+)?(?:recent\s+)?)?(?:messages?|chats?|msg))', clean_text)
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

    # 1b. DELETE / REMOVE ROLE FROM SERVER (regex fallback)
    # e.g., "remove the role Named:- Creators from discord", "delete role Creators"
    del_role_match = re.search(r'(?:delete|remove|hata\s+do)\s+(?:the\s+)?role\s+(?:named?\s*[:\-]*\s*|called?\s*[:\-]*\s*)?["\']?([^"\']+)["\']?(?:\s+from\s+(?:discord|server))?', clean_text)
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

    # 1a. CREATE ROLE (without assigning)
    # e.g., "create role Creators", "tillu create a role named VIP", "make role Creators"
    create_role_match = re.search(r'(?:create|make|bana)\s+(?:a\s+)?(?:new\s+)?role\s+(?:named?\s+|called?\s+)?["\']?([^"\']+)["\']?', clean_text)
    if create_role_match and not re.search(r'(?:give|add|assign)', clean_text):
        role_name = create_role_match.group(1).strip().title()
        existing = find_role_fuzzy(role_name)
        if existing:
            return True, f"ℹ️ Role `{existing.name}` pehle se exist karta hai! Use karna ho to assign karo."
        try:
            new_role = await guild.create_role(
                name=role_name,
                mentionable=True,
                reason=f"Created by Tillu via {author.name}"
            )
            return True, f"🎭 **Role Created!** Naya role `{new_role.name}` ban gaya hai! Assign karne ke liye bolna: `tillu give role {new_role.name} to @user`"
        except Exception as e:
            return True, f"⚠️ Role create error: {e}"

    # 2. GIVE / ADD ROLE  (also handles: "create role X and add Y to it")
    # e.g., "tillu give role VIP to @user", "create role Creators and add uniqueumar to it"
    add_role_match = re.search(r'(?:give|add|assign|de\s+do)\s+(?:role\s+)?["\']?([^"\'@<>\n]+?)["\']?\s+(?:role\s+)?to\s+(.+)', text, re.IGNORECASE)
    # Handle "create role X and add Y to it" — with re.DOTALL to cross newlines
    compound_match = re.search(
        r'create\s+(?:a\s+)?(?:new\s+)?role\s+(?:named?\s+)?["\']?([^"\':\n]+)["\']?'
        r'[\s\S]{0,60}?(?:add|give)\s+(.+?)\s+to\s+(?:it|that\s+role)',
        text, re.IGNORECASE | re.DOTALL
    )
    if compound_match:
        add_role_match = compound_match  # treat same way

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

    # 3. REMOVE ROLE
    # e.g., "tillu remove role VIP from @user"
    rem_role_match = re.search(r'(?:remove|take|hata\s+do)\s+role\s+["\']?([^"\']+)["\']?\s+from\s+(.+)', text, re.IGNORECASE)
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

    # 4. CREATE CHANNEL
    # 3b. SET CHANNEL PERMISSIONS BY ROLE (restrict posting to specific roles)
    # e.g., "only moderator or above can post in server clips"
    # e.g., "restrict posting in #clips to mods and admins"
    # e.g., "set server-clips so only moderators can post"
    restrict_match = re.search(
        r'(?:only|restrict|lock|set)\s+(?:posting\s+(?:in\s+)?|messages?\s+(?:in\s+)?)?'
        r'(?:(?:<#(\d+)>|#?([a-zA-Z0-9_\-]+))\s+)?'
        r'(?:to\s+|for\s+|so\s+only\s+)?'
        r'([a-zA-Z0-9\s,\+&]+?)\s*(?:and\s+above\s+)?(?:can\s+post|can\s+send|only|channel)?',
        clean_text, re.IGNORECASE
    )
    # simpler pattern to catch "only moderator or above can post in server clips"
    restrict_simple = re.search(
        r'(?:only\s+)?(.+?)\s+(?:or\s+above\s+)?(?:can|to)\s+(?:post|send|write)\s+in\s+(?:<#(\d+)>|#?([a-zA-Z0-9_\-]+))',
        clean_text, re.IGNORECASE
    )
    if restrict_simple:
        roles_text = restrict_simple.group(1).strip()
        ch_id = restrict_simple.group(2)
        ch_name_q = restrict_simple.group(3)

        # Find target channel
        target_ch = message.channel
        if ch_id:
            target_ch = guild.get_channel(int(ch_id)) or message.channel
        elif ch_name_q:
            found_ch = discord.utils.find(lambda c: c.name.lower().replace('-', '').replace('_', '') == ch_name_q.lower().replace('-', '').replace('_', ''), guild.channels)
            if found_ch:
                target_ch = found_ch

        if not isinstance(target_ch, (discord.TextChannel, discord.ForumChannel)):
            pass  # skip if not text
        else:
            try:
                # Step 1: Block @everyone from sending messages
                await target_ch.set_permissions(guild.default_role, send_messages=False, reason=f"Restricted by Tillu via {author.name}")

                # Step 2: Allow privileged roles to send
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

    # 4. CREATE CHANNEL
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


    # 5. DELETE CHANNEL
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

    # 6. LOCK / UNLOCK CHANNEL
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

    # 7. RENAME CHANNEL
    # e.g., "rename channel #test to announcement", "rename this channel to chill-chat"
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

    # 8. SET CHANNEL TOPIC
    # e.g., "set topic of this channel to Official Discussion", "set topic of #general to Welcome everyone"
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

    # 9. SET SLOWMODE
    # e.g., "set slowmode to 10s", "slowmode 5 seconds", "disable slowmode"
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

    # 10. HIDE / UNHIDE CHANNEL
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

    # 11. CREATE CATEGORY
    # e.g., "create category Staff Zone", "create category Gaming"
    cat_match = re.search(r'create\s+category\s+["\']?([^"\']+)["\']?', clean_text)
    if cat_match:
        cat_name = cat_match.group(1).strip()
        try:
            new_cat = await guild.create_category(name=cat_name, reason=f"Created by Tillu via {author.name}")
            return True, f"📂 **Category Created!** Nayi category `{new_cat.name}` ban gayi hai!"
        except Exception as e:
            return True, f"⚠️ Category create error: {e}"

    # 12. CLONE CHANNEL
    # e.g., "clone channel #general", "clone this channel"
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

    # 13. TIMEOUT / MUTE USER
    # e.g., "tillu mute @user for 10 minutes", "tillu timeout @user 15m"
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

    return False, None

