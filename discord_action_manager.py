"""
Tillu Autonomous Discord Action Manager
Handles Discord server management tasks (roles, channels, message deletions, moderation)
initiated by Server Owner, Admins, and Moderators via natural language or direct commands.
"""

import re
import datetime
import logging
from typing import Optional, Tuple
import discord

logger = logging.getLogger("TilluDiscordActions")

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
        return (
            discord.utils.find(lambda r: r.name.lower() == q, guild.roles) or
            discord.utils.find(lambda r: q in r.name.lower(), guild.roles)
        )

    # 1. PURGE / DELETE MESSAGES
    # e.g., "tillu delete 10 messages", "tillu purge 20 messages", "delete last 5 chats"
    purge_match = re.search(r'(?:delete|purge|remove|saaf\s+kar\s+do)\s+(?:last\s+)?(\d{1,3})\s+(?:messages?|chats?|msg)', clean_text)
    if purge_match:
        count = min(int(purge_match.group(1)), 100)
        try:
            # Delete trigger message + target count
            deleted = await message.channel.purge(limit=count + 1)
            actual = max(len(deleted) - 1, 0)
            conf = f"🧹 **Done Boss!** Maine is channel ke aakhri `{actual}` messages delete kar diye!"
            sent = await message.channel.send(conf)
            try:
                await sent.delete(delay=5)
            except Exception:
                pass
            return True, conf
        except Exception as e:
            err = f"⚠️ Messages delete karne me error aaya: {e}"
            await message.channel.send(err)
            return True, err

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
    # Also handle "create role X and add Y to it"
    compound_match = re.search(r'create\s+(?:a\s+)?(?:new\s+)?role\s+(?:named?\s+)?["\']?([^"\']+)["\']?\s+and\s+(?:add|give)\s+(.+?)\s+to\s+(?:it|that role)', text, re.IGNORECASE)
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

