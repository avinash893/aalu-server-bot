"""
Tillu Server Architecture Backup & Selective Restore Manager
Backups complete Discord server architecture (roles, categories, channels, permissions overwrites)
and allows granular or full restoration of any section with exact permissions preserved.
"""

import os
import json
import logging
import asyncio
import datetime
from typing import Optional, Tuple, Dict, Any, List
import discord

logger = logging.getLogger("TilluBackupManager")

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def _serialize_overwrites(overwrites: Dict[Any, discord.PermissionOverwrite]) -> List[dict]:
    """Serialize channel/category permission overwrites into JSON-compatible list."""
    serialized = []
    for target, ow in overwrites.items():
        allow, deny = ow.pair()
        target_type = "role" if isinstance(target, discord.Role) else "member"
        serialized.append({
            "target_type": target_type,
            "target_id": target.id,
            "target_name": target.name,
            "allow": allow.value,
            "deny": deny.value,
        })
    return serialized


def _build_guild_snapshot(guild: discord.Guild) -> dict:
    """Capture full server architecture snapshot."""
    # 1. Roles
    roles_data = []
    for r in sorted(guild.roles, key=lambda x: x.position):
        if r.is_default():
            is_default = True
        else:
            is_default = False
        roles_data.append({
            "id": r.id,
            "name": r.name,
            "color": r.color.value,
            "hoist": r.hoist,
            "position": r.position,
            "permissions": r.permissions.value,
            "mentionable": r.mentionable,
            "is_default": is_default,
        })

    # 2. Categories
    categories_data = []
    for cat in sorted(guild.categories, key=lambda x: x.position):
        categories_data.append({
            "id": cat.id,
            "name": cat.name,
            "position": cat.position,
            "overwrites": _serialize_overwrites(cat.overwrites),
        })

    # 3. Channels
    channels_data = []
    for ch in sorted(guild.channels, key=lambda x: x.position):
        if isinstance(ch, discord.CategoryChannel):
            continue

        ch_type = "text"
        if isinstance(ch, discord.VoiceChannel):
            ch_type = "voice"
        elif isinstance(ch, discord.StageChannel):
            ch_type = "stage"
        elif hasattr(discord, "ForumChannel") and isinstance(ch, discord.ForumChannel):
            ch_type = "forum"

        channels_data.append({
            "id": ch.id,
            "name": ch.name,
            "type": ch_type,
            "category_name": ch.category.name if ch.category else None,
            "position": ch.position,
            "topic": getattr(ch, "topic", None),
            "slowmode_delay": getattr(ch, "slowmode_delay", 0),
            "nsfw": getattr(ch, "nsfw", False),
            "overwrites": _serialize_overwrites(ch.overwrites),
        })

    return {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "backup_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stats": {
            "roles_count": len(roles_data),
            "categories_count": len(categories_data),
            "channels_count": len(channels_data),
        },
        "roles": roles_data,
        "categories": categories_data,
        "channels": channels_data,
    }


def create_backup(guild: discord.Guild) -> Tuple[bool, str, dict]:
    """Create a new backup file for the given guild."""
    try:
        snapshot = _build_guild_snapshot(guild)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        ts_path = os.path.join(BACKUP_DIR, f"backup_{guild.id}_{ts}.json")
        latest_path = os.path.join(BACKUP_DIR, f"backup_{guild.id}_latest.json")

        with open(ts_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        stats = snapshot["stats"]
        msg = (
            f"💾 **Backup Complete!**\n"
            f"• Roles: `{stats['roles_count']}`\n"
            f"• Categories: `{stats['categories_count']}`\n"
            f"• Channels: `{stats['channels_count']}`\n"
            f"Snapshots saved to `{os.path.basename(ts_path)}` & latest snapshot."
        )
        return True, msg, snapshot
    except Exception as e:
        logger.error(f"Backup creation error: {e}", exc_info=True)
        return False, f"⚠️ Backup create failed: {e}", {}


def load_latest_backup(guild_id: int) -> Optional[dict]:
    """Load latest backup JSON for a guild."""
    latest_path = os.path.join(BACKUP_DIR, f"backup_{guild_id}_latest.json")
    if os.path.exists(latest_path):
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading latest backup: {e}")
    return None


def list_backups(guild_id: int) -> List[str]:
    """List available backup files for guild."""
    prefix = f"backup_{guild_id}_"
    files = []
    if os.path.exists(BACKUP_DIR):
        for fname in os.listdir(BACKUP_DIR):
            if fname.startswith(prefix) and fname.endswith(".json") and "latest" not in fname:
                files.append(fname)
    return sorted(files, reverse=True)


async def _rebuild_overwrites(
    guild: discord.Guild,
    raw_overwrites: List[dict]
) -> Dict[Any, discord.PermissionOverwrite]:
    """Convert serialized overwrite data back into Discord PermissionOverwrite objects."""
    overwrites = {}
    for item in raw_overwrites:
        target = None
        if item.get("target_type") == "role":
            # Match role by name or ID
            t_name = item.get("target_name")
            t_id = item.get("target_id")
            if item.get("target_name") == "@everyone":
                target = guild.default_role
            else:
                target = guild.get_role(t_id) or discord.utils.find(lambda r: r.name.lower() == str(t_name).lower(), guild.roles)
        else:
            t_id = item.get("target_id")
            target = guild.get_member(t_id)

        if target:
            allow_perm = discord.Permissions(item.get("allow", 0))
            deny_perm = discord.Permissions(item.get("deny", 0))
            overwrites[target] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

    return overwrites


async def restore_roles(guild: discord.Guild, snapshot: dict) -> Tuple[int, int]:
    """Restore roles from snapshot. Returns (created_count, updated_count)."""
    created, updated = 0, 0
    roles_data = snapshot.get("roles", [])

    for r_info in roles_data:
        r_name = r_info.get("name")
        if r_info.get("is_default") or r_name == "@everyone":
            # Update default role permissions
            try:
                perms = discord.Permissions(r_info.get("permissions", 0))
                await guild.default_role.edit(permissions=perms, reason="Tillu restore default role")
                updated += 1
            except Exception:
                pass
            continue

        existing = discord.utils.find(lambda r: r.name.lower() == r_name.lower(), guild.roles)
        color = discord.Color(r_info.get("color", 0))
        perms = discord.Permissions(r_info.get("permissions", 0))
        hoist = bool(r_info.get("hoist", False))
        mentionable = bool(r_info.get("mentionable", True))

        if not existing:
            try:
                await guild.create_role(
                    name=r_name,
                    color=color,
                    permissions=perms,
                    hoist=hoist,
                    mentionable=mentionable,
                    reason="Tillu backup restore role"
                )
                created += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Failed to create role {r_name}: {e}")
        else:
            try:
                await existing.edit(
                    color=color,
                    permissions=perms,
                    hoist=hoist,
                    mentionable=mentionable,
                    reason="Tillu backup restore role update"
                )
                updated += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"Failed to edit role {r_name}: {e}")

    return created, updated


async def restore_categories(guild: discord.Guild, snapshot: dict) -> Tuple[int, int]:
    """Restore categories with permissions overwrites. Returns (created_count, updated_count)."""
    created, updated = 0, 0
    cat_data = snapshot.get("categories", [])

    for c_info in cat_data:
        c_name = c_info.get("name")
        overwrites = await _rebuild_overwrites(guild, c_info.get("overwrites", []))
        existing = discord.utils.find(lambda c: c.name.lower() == c_name.lower(), guild.categories)

        if not existing:
            try:
                await guild.create_category(
                    name=c_name,
                    overwrites=overwrites,
                    position=c_info.get("position", 0),
                    reason="Tillu backup restore category"
                )
                created += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Failed to create category {c_name}: {e}")
        else:
            try:
                if overwrites:
                    for target, po in overwrites.items():
                        await existing.set_permissions(target, overwrite=po, reason="Tillu restore category permissions")
                        await asyncio.sleep(0.2)
                updated += 1
            except Exception as e:
                logger.warning(f"Failed to update category {c_name}: {e}")

    return created, updated


async def restore_channels(guild: discord.Guild, snapshot: dict) -> Tuple[int, int]:
    """Restore channels with category links and permission overwrites. Returns (created_count, updated_count)."""
    created, updated = 0, 0
    channels_data = snapshot.get("channels", [])

    for ch_info in channels_data:
        ch_name = ch_info.get("name")
        ch_type = ch_info.get("type", "text")
        cat_name = ch_info.get("category_name")
        overwrites = await _rebuild_overwrites(guild, ch_info.get("overwrites", []))

        # Find matching category
        cat_target = None
        if cat_name:
            cat_target = discord.utils.find(lambda c: c.name.lower() == cat_name.lower(), guild.categories)

        existing = discord.utils.find(lambda c: c.name.lower() == ch_name.lower(), guild.channels)

        if not existing:
            try:
                if ch_type == "voice":
                    await guild.create_voice_channel(
                        name=ch_name,
                        category=cat_target,
                        overwrites=overwrites,
                        position=ch_info.get("position", 0),
                        reason="Tillu backup restore voice channel"
                    )
                else:
                    await guild.create_text_channel(
                        name=ch_name,
                        category=cat_target,
                        overwrites=overwrites,
                        position=ch_info.get("position", 0),
                        topic=ch_info.get("topic"),
                        slowmode_delay=ch_info.get("slowmode_delay", 0),
                        nsfw=ch_info.get("nsfw", False),
                        reason="Tillu backup restore text channel"
                    )
                created += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Failed to create channel {ch_name}: {e}")
        else:
            # Channel exists, restore permissions and category
            try:
                edit_kwargs = {}
                if cat_target and existing.category != cat_target:
                    edit_kwargs["category"] = cat_target
                if ch_info.get("topic") and getattr(existing, "topic", None) != ch_info.get("topic"):
                    edit_kwargs["topic"] = ch_info.get("topic")

                if edit_kwargs:
                    await existing.edit(**edit_kwargs, reason="Tillu restore channel metadata")

                if overwrites:
                    for target, po in overwrites.items():
                        await existing.set_permissions(target, overwrite=po, reason="Tillu restore channel permissions")
                        await asyncio.sleep(0.2)
                updated += 1
            except Exception as e:
                logger.warning(f"Failed to update channel {ch_name}: {e}")

    return created, updated


async def restore_specific_channel(guild: discord.Guild, snapshot: dict, channel_name: str) -> Tuple[bool, str]:
    """Restore a specific single channel with its category, topic, and permission overwrites."""
    ch_target = channel_name.lower().strip().replace("#", "").replace(" ", "-")
    channels_data = snapshot.get("channels", [])

    matched = None
    for c in channels_data:
        if c.get("name", "").lower() == ch_target or ch_target in c.get("name", "").lower():
            matched = c
            break

    if not matched:
        return False, f"❌ Channel `{channel_name}` backup snapshot me nahi mila!"

    ch_name = matched.get("name")
    ch_type = matched.get("type", "text")
    cat_name = matched.get("category_name")
    overwrites = await _rebuild_overwrites(guild, matched.get("overwrites", []))

    cat_target = None
    if cat_name:
        cat_target = discord.utils.find(lambda c: c.name.lower() == cat_name.lower(), guild.categories)
        if not cat_target:
            # Recreate category if missing
            try:
                cat_target = await guild.create_category(name=cat_name, reason="Tillu restore parent category")
            except Exception:
                pass

    existing = discord.utils.find(lambda c: c.name.lower() == ch_name.lower(), guild.channels)
    try:
        if not existing:
            if ch_type == "voice":
                new_ch = await guild.create_voice_channel(
                    name=ch_name,
                    category=cat_target,
                    overwrites=overwrites,
                    reason="Tillu restore specific voice channel"
                )
            else:
                new_ch = await guild.create_text_channel(
                    name=ch_name,
                    category=cat_target,
                    overwrites=overwrites,
                    topic=matched.get("topic"),
                    slowmode_delay=matched.get("slowmode_delay", 0),
                    nsfw=matched.get("nsfw", False),
                    reason="Tillu restore specific text channel"
                )
            return True, f"✅ **Channel Restored!** {new_ch.mention} category `{cat_name or 'None'}` aur poore permissions ke saath wapas ban gaya!"
        else:
            if overwrites:
                for target, po in overwrites.items():
                    await existing.set_permissions(target, overwrite=po, reason="Tillu restore channel permissions")
            if cat_target and existing.category != cat_target:
                await existing.edit(category=cat_target)
            return True, f"✅ **Permissions Restored!** {existing.mention} ke saare permissions snapshot se reapply kar diye gaye hain!"
    except Exception as e:
        return False, f"⚠️ Restore channel failed: {e}"


async def restore_specific_role(guild: discord.Guild, snapshot: dict, role_name: str) -> Tuple[bool, str]:
    """Restore a specific role with its color, hoist, and permissions."""
    r_target = role_name.lower().strip()
    roles_data = snapshot.get("roles", [])

    matched = None
    for r in roles_data:
        if r.get("name", "").lower() == r_target or r_target in r.get("name", "").lower():
            matched = r
            break

    if not matched:
        return False, f"❌ Role `{role_name}` backup snapshot me nahi mila!"

    r_name = matched.get("name")
    color = discord.Color(matched.get("color", 0))
    perms = discord.Permissions(matched.get("permissions", 0))
    hoist = bool(matched.get("hoist", False))
    mentionable = bool(matched.get("mentionable", True))

    existing = discord.utils.find(lambda r: r.name.lower() == r_name.lower(), guild.roles)
    try:
        if not existing:
            new_role = await guild.create_role(
                name=r_name,
                color=color,
                permissions=perms,
                hoist=hoist,
                mentionable=mentionable,
                reason="Tillu restore specific role"
            )
            return True, f"✅ **Role Restored!** `{new_role.name}` original permissions, color, aur hoist ke saath recreate kar diya!"
        else:
            await existing.edit(
                color=color,
                permissions=perms,
                hoist=hoist,
                mentionable=mentionable,
                reason="Tillu restore specific role update"
            )
            return True, f"✅ **Role Updated!** `{existing.name}` ke original permissions aur settings restore kar diye gaye!"
    except Exception as e:
        return False, f"⚠️ Restore role failed: {e}"


async def restore_section(guild: discord.Guild, section: str, specific_target: str = "") -> Tuple[bool, str]:
    """
    Restore a specific section or item from the latest server snapshot.
    Supported sections: 'roles', 'categories', 'channels', 'permissions', 'channel <name>', 'role <name>', 'server'/'all'.
    """
    snapshot = load_latest_backup(guild.id)
    if not snapshot:
        return False, "❌ Koi backup snapshot nahi mila! Pehle `tillu backup server` chalao."

    sec = section.lower().strip()

    if sec in ("role", "specific_role") and specific_target:
        return await restore_specific_role(guild, snapshot, specific_target)

    if sec in ("channel", "specific_channel") and specific_target:
        return await restore_specific_channel(guild, snapshot, specific_target)

    if sec == "roles":
        c, u = await restore_roles(guild, snapshot)
        return True, f"🎭 **Roles Restored!** `{c}` naye roles create hue, `{u}` roles update hue."

    if sec == "categories":
        c, u = await restore_categories(guild, snapshot)
        return True, f"📂 **Categories Restored!** `{c}` categories create hue, `{u}` permissions update hue."

    if sec == "channels":
        # Make sure categories exist first
        await restore_categories(guild, snapshot)
        c, u = await restore_channels(guild, snapshot)
        return True, f"📁 **Channels Restored!** `{c}` channels create hue, `{u}` channels update hue."

    if sec == "permissions":
        _, cu = await restore_categories(guild, snapshot)
        _, chu = await restore_channels(guild, snapshot)
        return True, f"🔐 **Permissions Restored!** Category overwrites `{cu}` aur Channel overwrites `{chu}` reapply ho gaye."

    if sec in ("all", "server", "full"):
        r_c, r_u = await restore_roles(guild, snapshot)
        cat_c, cat_u = await restore_categories(guild, snapshot)
        ch_c, ch_u = await restore_channels(guild, snapshot)
        return True, (
            f"🏛️ **Full Server Architecture Restored!**\n"
            f"• Roles: `{r_c}` created, `{r_u}` updated\n"
            f"• Categories: `{cat_c}` created, `{cat_u}` updated\n"
            f"• Channels: `{ch_c}` created, `{ch_u}` updated with all permissions!"
        )

    return False, f"❓ Unknown section `{section}`. Allowed sections: `roles`, `categories`, `channels`, `permissions`, `server`, or `restore channel <name>` / `restore role <name>`."
