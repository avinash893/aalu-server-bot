"""
Tillu Minecraft Chat Drops & In-Game Reward Claim Manager
Awards Minecraft items (diamonds, iron, enchanted books, totems) to Discord users who chat.
Uses minecraftmcp panel command integration to deliver drops directly to players' inventories.
"""

import os
import json
import time
import random
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("TilluChatDrops")

REWARDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_rewards.json")
CLAIM_COOLDOWN_SECONDS = 7200  # 2 hours cooldown between free drops

# ── DROP ITEM POOL (Balanced with weights and rarities) ────────────────────────
DROP_TABLE = [
    # Common (Weight: 60)
    {
        "name": "16x Iron Ingots",
        "cmd": "iron_ingot 16",
        "rarity": "Common",
        "color": 0xBDC3C7,
        "emoji": "⚪",
        "weight": 25,
    },
    {
        "name": "16x Gold Ingots",
        "cmd": "gold_ingot 16",
        "rarity": "Common",
        "color": 0xF1C40F,
        "emoji": "🟡",
        "weight": 20,
    },
    {
        "name": "32x Golden Carrots",
        "cmd": "golden_carrot 32",
        "rarity": "Common",
        "color": 0xE67E22,
        "emoji": "🥕",
        "weight": 15,
    },

    # Rare (Weight: 27)
    {
        "name": "5x Diamonds",
        "cmd": "diamond 5",
        "rarity": "Rare",
        "color": 0x3498DB,
        "emoji": "💎",
        "weight": 15,
    },
    {
        "name": "8x Emeralds",
        "cmd": "emerald 8",
        "rarity": "Rare",
        "color": 0x2ECC71,
        "emoji": "🟢",
        "weight": 12,
    },

    # Epic (Weight: 8)
    {
        "name": "1x Netherite Scrap",
        "cmd": "netherite_scrap 1",
        "rarity": "Epic",
        "color": 0x8E44AD,
        "emoji": "🟤",
        "weight": 4,
    },
    {
        "name": "1x Enchanted Golden Apple",
        "cmd": "enchanted_golden_apple 1",
        "rarity": "Epic",
        "color": 0x9B59B6,
        "emoji": "🍎",
        "weight": 4,
    },

    # Legendary (Weight: 5)
    {
        "name": "1x Totem of Undying",
        "cmd": "totem_of_undying 1",
        "rarity": "Legendary",
        "color": 0xE74C3C,
        "emoji": "🛡️",
        "weight": 2,
    },
    {
        "name": "Enchanted Book: Mending",
        "cmd": 'enchanted_book{StoredEnchantments:[{id:"mending",lvl:1}]} 1',
        "rarity": "Legendary",
        "color": 0xE74C3C,
        "emoji": "📖",
        "weight": 1,
    },
    {
        "name": "Enchanted Book: Sharpness V",
        "cmd": 'enchanted_book{StoredEnchantments:[{id:"sharpness",lvl:5}]} 1',
        "rarity": "Legendary",
        "color": 0xE74C3C,
        "emoji": "📖",
        "weight": 1,
    },
    {
        "name": "Enchanted Book: Protection IV",
        "cmd": 'enchanted_book{StoredEnchantments:[{id:"protection",lvl:4}]} 1',
        "rarity": "Legendary",
        "color": 0xE74C3C,
        "emoji": "📖",
        "weight": 1,
    },
]


def _load_data() -> dict:
    if os.path.exists(REWARDS_FILE):
        try:
            with open(REWARDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_data(data: dict):
    try:
        with open(REWARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save rewards data: {e}")


def record_chat_activity(user_id: int):
    """Mark that user has chatted in Discord and is qualified for drop claims."""
    data = _load_data()
    uid = str(user_id)
    user_entry = data.get(uid, {})
    user_entry["messages_count"] = user_entry.get("messages_count", 0) + 1
    user_entry["last_chat_ts"] = int(time.time())
    data[uid] = user_entry
    _save_data(data)


def get_drop_status(user_id: int) -> Tuple[bool, int, int]:
    """
    Check if user is eligible to claim a drop.
    Returns (can_claim: bool, remaining_seconds: int, total_claims: int).
    """
    data = _load_data()
    uid = str(user_id)
    entry = data.get(uid, {})

    msg_count = entry.get("messages_count", 0)
    last_claim = entry.get("last_claim_ts", 0)
    claims_count = entry.get("claims_count", 0)
    now = int(time.time())

    # User must have sent at least 1 message
    if msg_count < 1:
        return False, 0, claims_count

    elapsed = now - last_claim
    if elapsed >= CLAIM_COOLDOWN_SECONDS:
        return True, 0, claims_count
    return False, CLAIM_COOLDOWN_SECONDS - elapsed, claims_count


def roll_random_reward() -> dict:
    """Select a random reward weighted by rarity."""
    weights = [r["weight"] for r in DROP_TABLE]
    return random.choices(DROP_TABLE, weights=weights, k=1)[0]


def claim_drop(user_id: int, ign: str, send_command_fn) -> Tuple[bool, dict, str]:
    """
    Claim drop and deliver in-game via Minecraft MCP panel command.
    Returns (success: bool, reward_dict: dict, status_message: str).
    """
    can_claim, remaining, total_claims = get_drop_status(user_id)
    if not can_claim and remaining > 0:
        mins = remaining // 60
        secs = remaining % 60
        return False, {}, f"⏳ Agla free drop claim karne ke liye **{mins}m {secs}s** wait karo!"
    elif not can_claim and remaining == 0:
        return False, {}, "💬 Drop claim karne ke liye pehle Discord chat me thodi baat karo!"

    # Roll reward
    reward = roll_random_reward()
    clean_ign = ign.strip().replace('"', '').replace("'", '').replace(";", "")

    # Execute console commands in Minecraft
    give_cmd = f"give {clean_ign} {reward['cmd']}"
    title_cmd = f'title {clean_ign} actionbar {{"text":"🎁 Discord Chat Drop: {reward["name"]}!","color":"gold"}}'

    success, out = send_command_fn(give_cmd)
    try:
        send_command_fn(title_cmd)
    except Exception:
        pass

    if not success:
        logger.warning(f"Failed to dispatch give command to {clean_ign}: {out}")
        return False, {}, f"⚠️ Minecraft console me reward deliver nahi hua: `{out}`. Kya server online hai?"

    # Update record
    data = _load_data()
    uid = str(user_id)
    user_entry = data.get(uid, {})
    user_entry["last_claim_ts"] = int(time.time())
    user_entry["claims_count"] = user_entry.get("claims_count", 0) + 1
    user_entry["last_reward"] = reward["name"]
    data[uid] = user_entry
    _save_data(data)

    msg = f"🎉 **{reward['emoji']} {reward['name']}** (`{reward['rarity']}`) tumhare Minecraft inventory me deliver kar diya gaya hai!"
    return True, reward, msg
