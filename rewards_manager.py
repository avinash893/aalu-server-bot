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


def get_pending_claims(user_id: int) -> list:
    """Get list of unclaimed items in user's vault."""
    data = _load_data()
    return data.get(str(user_id), {}).get("pending_claims", [])


def claim_drop(user_id: int) -> Tuple[bool, dict, str]:
    """
    Claim drop on Discord and save into user's rewards vault.
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

    # Save to user vault
    data = _load_data()
    uid = str(user_id)
    user_entry = data.get(uid, {})
    user_entry["last_claim_ts"] = int(time.time())
    user_entry["claims_count"] = user_entry.get("claims_count", 0) + 1
    user_entry["last_reward"] = reward["name"]

    pending = user_entry.get("pending_claims", [])
    pending.append({
        "name": reward["name"],
        "cmd": reward["cmd"],
        "rarity": reward["rarity"],
        "emoji": reward["emoji"],
        "claimed_at": int(time.time())
    })
    user_entry["pending_claims"] = pending
    data[uid] = user_entry
    _save_data(data)

    vault_count = len(pending)
    msg = (
        f"🎉 **{reward['emoji']} {reward['name']}** (`{reward['rarity']}`) tumhare Tillu Vault me add ho gaya hai!\n"
        f"📦 Tumhare paas total `{vault_count}` claim(s) pending hain.\n"
        f"In-game inventory me lene ke liye bolo: `tillu send my claims to my account` ya `tillu send my claims to <account_name>`!"
    )
    return True, reward, msg


def send_claims_to_account(user_id: int, target_ign: str, send_command_fn) -> Tuple[bool, list, str]:
    """
    Deliver all pending claims from user's vault to Minecraft account target_ign.
    Returns (success: bool, delivered_items: list, message: str).
    """
    import re
    data = _load_data()
    uid = str(user_id)
    user_entry = data.get(uid, {})
    pending = user_entry.get("pending_claims", [])

    if not pending:
        return False, [], "📭 Tumhare vault me koi pending claims nahi hain! Pehle `!claim` se naya drop lo."

    clean_ign = target_ign.strip().replace('"', '').replace("'", '').replace(";", "").replace("`", "")
    if not clean_ign or not re.match(r'^[a-zA-Z0-9_.* ]{3,20}$', clean_ign):
        return False, [], f"❌ Invalid Minecraft username `{target_ign}`!"

    delivered = []
    failed = []

    for item in pending:
        give_cmd = f"give {clean_ign} {item['cmd']}"
        ok, out = send_command_fn(give_cmd)
        if ok:
            delivered.append(item)
        else:
            failed.append((item, out))

    if not delivered and failed:
        return False, [], f"⚠️ Server pe items deliver nahi hue: `{failed[0][1]}`. Kya Minecraft server online hai?"

    try:
        title_cmd = f'title {clean_ign} actionbar {{"text":"🎁 Delivered {len(delivered)} Discord claims!","color":"gold"}}'
        send_command_fn(title_cmd)
    except Exception:
        pass

    # Update vault: keep any failed items, remove delivered ones
    user_entry["pending_claims"] = [f[0] for f in failed]
    data[uid] = user_entry
    _save_data(data)

    items_summary = "\n".join(f"• {it['emoji']} **{it['name']}** (`{it['rarity']}`)" for it in delivered)
    return True, delivered, f"🚀 **Successfully Delivered to `{clean_ign}`:**\n{items_summary}"

