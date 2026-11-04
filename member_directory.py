"""
Tillu Member Directory & Tagging Manager
Provides robust Discord member discovery, role-based filtering, activity search,
and accurate <@user_id> tagging formatting.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
import discord

logger = logging.getLogger("TilluMemberDirectory")

class MemberDirectory:
    @staticmethod
    def format_tag(member: discord.Member) -> str:
        """Return clickable Discord mention tag."""
        return f"<@{member.id}>"

    @staticmethod
    def resolve_member(guild: discord.Guild, query: str) -> Optional[discord.Member]:
        """
        Intelligently resolves a member from a string query:
        Supports:
        - Direct Discord mention (<@123456789> or <@!123456789>)
        - Raw numeric user ID
        - Exact username or display name
        - Case-insensitive substring match
        """
        if not guild or not query:
            return None

        clean_q = query.strip()

        # Check for mention
        mention_match = re.match(r'<@!?(\d+)>', clean_q)
        if mention_match:
            uid = int(mention_match.group(1))
            return guild.get_member(uid)

        # Check for numeric ID
        if clean_q.isdigit():
            mem = guild.get_member(int(clean_q))
            if mem:
                return mem

        # Strip leading @
        clean_name = clean_q.lstrip('@').lower()

        # Exact match on name or nick
        for m in guild.members:
            if m.name.lower() == clean_name or (m.nick and m.nick.lower() == clean_name) or (m.global_name and m.global_name.lower() == clean_name):
                return m

        # Partial substring match
        for m in guild.members:
            if clean_name in m.name.lower() or (m.nick and clean_name in m.nick.lower()) or (m.global_name and clean_name in m.global_name.lower()):
                return m

        return None

    @staticmethod
    def get_role_by_name(guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
        """Finds role by exact or case-insensitive name."""
        clean = role_name.strip().lstrip('@').lower()
        for r in guild.roles:
            if r.name.lower() == clean:
                return r
        for r in guild.roles:
            if clean in r.name.lower() and not r.is_default():
                return r
        return None

    @classmethod
    def get_members_by_filter(
        cls,
        guild: discord.Guild,
        role_name: Optional[str] = None,
        online_only: bool = False,
        game_query: Optional[str] = None,
        exclude_bots: bool = False
    ) -> List[discord.Member]:
        """Filter guild members by role, online status, or game currently being played."""
        if not guild:
            return []

        members = list(guild.members)

        if exclude_bots:
            members = [m for m in members if not m.bot]

        if online_only:
            members = [m for m in members if m.status != discord.Status.offline]

        if role_name:
            target_role = cls.get_role_by_name(guild, role_name)
            if target_role:
                members = [m for m in members if target_role in m.roles]

        if game_query:
            g_clean = game_query.lower()
            filtered = []
            for m in members:
                for act in m.activities:
                    if getattr(act, "name", None) and g_clean in act.name.lower():
                        filtered.append(m)
                        break
            members = filtered

        return members

    @classmethod
    def format_member_list_embed(
        cls,
        guild: discord.Guild,
        members: List[discord.Member],
        title: str = "Server Members",
        role_filter: Optional[str] = None
    ) -> discord.Embed:
        """Create a clean Discord embed displaying tagged members with status."""
        embed = discord.Embed(
            title=f"👥 {title} ({len(members)})",
            color=0x5865F2,
            description=f"Server: **{guild.name}**" + (f" | Role: **{role_filter}**" if role_filter else "")
        )

        if not members:
            embed.description += "\n\n*Koi member nahi mila is criteria me.*"
            return embed

        # Group by status or display tags
        lines = []
        for i, m in enumerate(members[:35], start=1):  # Cap at 35 to prevent hitting embed limits
            status_emoji = "🟢" if m.status == discord.Status.online else ("🟡" if m.status == discord.Status.idle else ("🔴" if m.status == discord.Status.dnd else "⚪"))
            bot_tag = " `[BOT]`" if m.bot else ""
            activity_str = ""
            for act in m.activities:
                if getattr(act, "name", None):
                    activity_str = f" — *Playing {act.name}*"
                    break
            lines.append(f"{i}. {status_emoji} <@{m.id}>{bot_tag}{activity_str}")

        embed.add_field(name="Members List", value="\n".join(lines), inline=False)
        if len(members) > 35:
            embed.set_footer(text=f"+ {len(members) - 35} aur members hain.")

        return embed
