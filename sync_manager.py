"""
Tillu Minecraft Live Sync Manager
Automatically synchronizes Minecraft in-game whitelist status and ranks with Discord roles.
"""

import logging
import asyncio
from typing import Tuple, Dict, Any, Optional
import discord

logger = logging.getLogger("TilluLiveSync")

WHITELIST_ROLE_NAME = "Whitelisted"


async def get_or_create_whitelist_role(guild: discord.Guild) -> Optional[discord.Role]:
    """Find or create the 'Whitelisted' role on Discord."""
    role = discord.utils.find(lambda r: r.name.lower() == WHITELIST_ROLE_NAME.lower(), guild.roles)
    if not role:
        try:
            role = await guild.create_role(
                name=WHITELIST_ROLE_NAME,
                color=discord.Color.green(),
                mentionable=False,
                reason="Tillu Minecraft Live Sync auto-created Whitelisted role"
            )
            logger.info(f"Created role '{WHITELIST_ROLE_NAME}' in {guild.name}")
        except Exception as e:
            logger.error(f"Failed to create Whitelisted role in {guild.name}: {e}")
            return None
    return role


async def sync_single_member(guild: discord.Guild, member: discord.Member, ign: str) -> bool:
    """Ensure a specific registered player has the Whitelisted Discord role."""
    role = await get_or_create_whitelist_role(guild)
    if not role:
        return False

    if role not in member.roles:
        try:
            await member.add_roles(role, reason=f"Minecraft Live Sync: linked IGN '{ign}'")
            logger.info(f"Assigned Whitelisted role to {member.name} (IGN: {ign})")
            return True
        except Exception as e:
            logger.warning(f"Failed to assign Whitelisted role to {member.name}: {e}")
            return False
    return False


async def remove_single_member_sync(guild: discord.Guild, member: discord.Member) -> bool:
    """Remove Whitelisted role from member when unwhitelisted."""
    role = discord.utils.find(lambda r: r.name.lower() == WHITELIST_ROLE_NAME.lower(), guild.roles)
    if role and role in member.roles:
        try:
            await member.remove_roles(role, reason="Minecraft Live Sync: unwhitelisted")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove Whitelisted role from {member.name}: {e}")
    return False


async def sync_guild_roles(guild: discord.Guild, registry: dict) -> Tuple[int, int]:
    """
    Scan all members and sync Whitelisted roles for registered Minecraft players.
    Returns (total_checked, total_assigned).
    """
    if guild.me and not guild.me.guild_permissions.manage_roles:
        logger.warning(f"Bot lacks manage_roles permission in {guild.name}; cannot sync whitelist roles.")
        return 0, 0

    role = await get_or_create_whitelist_role(guild)
    if not role:
        return 0, 0

    assigned = 0
    checked = 0

    if not getattr(guild, "chunked", True):
        try:
            await guild.chunk()
        except Exception:
            pass

    for user_id_str, data in registry.items():
        try:
            uid = int(user_id_str)
        except ValueError:
            continue

        member = guild.get_member(uid)
        if not member:
            try:
                member = await guild.fetch_member(uid)
                await asyncio.sleep(0.2)  # Respect Discord API rate limit pacing
            except Exception:
                member = None

        if member:
            checked += 1
            if role not in member.roles:
                try:
                    ign = data.get("ign", "Player")
                    await member.add_roles(role, reason=f"Minecraft Live Sync audit (IGN: {ign})")
                    assigned += 1
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Error syncing role for {member.name}: {e}")

    return checked, assigned
