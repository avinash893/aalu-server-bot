"""
Tillu Viewer Leveling & Loyalty Badges Engine
Tracks community engagement (chatting, voice time, stream commands, predictions),
calculates XP and levels, awards prestigious badges, and provides custom titles.
"""

import os
import json
import time
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("TilluLoyaltySystem")

COOLDOWN_SECONDS = 60

BADGE_DEFINITIONS = {
    "chatterbox": {"name": "Chatterbox", "emoji": "💬", "desc": "Sent over 100 chat messages"},
    "veteran": {"name": "Stream Veteran", "emoji": "🎖️", "desc": "Reached Level 10"},
    "elite": {"name": "Clutch Legend", "emoji": "⚡", "desc": "Reached Level 25"},
    "meme_lord": {"name": "Meme Connoisseur", "emoji": "🎭", "desc": "Active meme culture enthusiast"},
    "high_roller": {"name": "High Roller", "emoji": "🎲", "desc": "Won 2,000+ coins in stream predictions"},
    "vip": {"name": "Aalu VIP", "emoji": "👑", "desc": "Community leader / Moderator"},
}

class LoyaltySystem:
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.loyalty_file = os.path.join(self.data_dir, "loyalty.json")
        self.users: Dict[str, Dict[str, Any]] = {}
        self._last_xp_time: Dict[str, float] = {}
        self.load()

    def load(self):
        if os.path.exists(self.loyalty_file):
            try:
                with open(self.loyalty_file, "r", encoding="utf-8") as f:
                    self.users = json.load(f)
            except Exception as e:
                logger.error(f"[Loyalty Load Error] {e}")

    def save(self):
        try:
            tmp = self.loyalty_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.loyalty_file)
        except Exception as e:
            logger.error(f"[Loyalty Save Error] {e}")

    def get_user_data(self, user_id: int, user_name: str = "") -> Dict[str, Any]:
        u_str = str(user_id)
        if u_str not in self.users:
            self.users[u_str] = {
                "name": user_name or f"User_{user_id}",
                "xp": 0,
                "messages": 0,
                "voice_minutes": 0,
                "badges": [],
                "custom_title": "Rookie Gamer"
            }
            self.save()
        elif user_name:
            self.users[u_str]["name"] = user_name
        return self.users[u_str]

    def xp_to_level(self, xp: int) -> int:
        """Level = floor(0.1 * sqrt(xp)) + 1"""
        if xp <= 0:
            return 1
        return int(0.1 * math.sqrt(xp)) + 1

    def level_to_min_xp(self, level: int) -> int:
        """Calculates minimum XP required for a given level."""
        if level <= 1:
            return 0
        return int(((level - 1) / 0.1) ** 2)

    def add_message_xp(self, user_id: int, user_name: str = "") -> Tuple[bool, int, int]:
        """Awards XP for chatting (with anti-spam cooldown). Returns (leveled_up, new_level, xp)."""
        now = time.time()
        u_str = str(user_id)
        if now - self._last_xp_time.get(u_str, 0) < COOLDOWN_SECONDS:
            u = self.get_user_data(user_id, user_name)
            u["messages"] = u.get("messages", 0) + 1
            return False, self.xp_to_level(u["xp"]), u["xp"]

        self._last_xp_time[u_str] = now
        u = self.get_user_data(user_id, user_name)
        old_level = self.xp_to_level(u["xp"])
        
        # Award 20 XP per message
        u["xp"] += 20
        u["messages"] = u.get("messages", 0) + 1
        new_level = self.xp_to_level(u["xp"])

        self._check_badges(u, user_id)
        self.save()
        leveled_up = new_level > old_level
        return leveled_up, new_level, u["xp"]

    def add_voice_xp(self, user_id: int, minutes: int, user_name: str = "") -> Tuple[bool, int]:
        """Awards XP for spending time in voice channel (15 XP/min)."""
        u = self.get_user_data(user_id, user_name)
        old_level = self.xp_to_level(u["xp"])
        u["xp"] += (minutes * 15)
        u["voice_minutes"] = u.get("voice_minutes", 0) + minutes
        new_level = self.xp_to_level(u["xp"])

        self._check_badges(u, user_id)
        self.save()
        return (new_level > old_level), new_level

    def _check_badges(self, u: Dict[str, Any], user_id: int):
        badges = set(u.get("badges", []))
        lvl = self.xp_to_level(u["xp"])

        if u.get("messages", 0) >= 100:
            badges.add("chatterbox")
        if lvl >= 10:
            badges.add("veteran")
            if u.get("custom_title") == "Rookie Gamer":
                u["custom_title"] = "Community Regular"
        if lvl >= 25:
            badges.add("elite")
            u["custom_title"] = "Clutch Master"

        u["badges"] = list(badges)

    def award_badge(self, user_id: int, badge_key: str, user_name: str = "") -> bool:
        if badge_key not in BADGE_DEFINITIONS:
            return False
        u = self.get_user_data(user_id, user_name)
        badges = set(u.get("badges", []))
        if badge_key not in badges:
            badges.add(badge_key)
            u["badges"] = list(badges)
            self.save()
            return True
        return False

    def get_progress_bar(self, xp: int, current_lvl: int, length: int = 10) -> Tuple[str, int, int, float]:
        min_xp = self.level_to_min_xp(current_lvl)
        next_xp = self.level_to_min_xp(current_lvl + 1)
        needed = max(1, next_xp - min_xp)
        gained = max(0, xp - min_xp)
        pct = min(1.0, max(0.0, gained / needed))

        filled = int(length * pct)
        empty = length - filled
        bar = "█" * filled + "░" * empty
        return bar, gained, needed, pct * 100.0

    def format_rank_card(self, user_id: int, user_name: str = "") -> Dict[str, Any]:
        u = self.get_user_data(user_id, user_name)
        xp = u.get("xp", 0)
        lvl = self.xp_to_level(xp)
        bar, gained, needed, pct = self.get_progress_bar(xp, lvl)

        if lvl >= 50:
            title = "Immortal Streamer 👑"
        elif lvl >= 25:
            title = "Clutch Warlord ⚡"
        elif lvl >= 15:
            title = "Chat Commander ⚔️"
        elif lvl >= 10:
            title = "Senior Member 🎖️"
        elif lvl >= 5:
            title = "Active Regular 🌟"
        else:
            title = "Newcomer 🌱"

        unlocked_badges = []
        for b_key in u.get("badges", []):
            if b_key in BADGE_DEFINITIONS:
                unlocked_badges.append(BADGE_DEFINITIONS[b_key])

        return {
            "name": u.get("name", user_name or f"User_{user_id}"),
            "level": lvl,
            "title": title,
            "xp": xp,
            "xp_gained": gained,
            "xp_needed": needed,
            "progress_percent": pct,
            "progress_bar": bar,
            "messages": u.get("messages", 0),
            "voice_hours": round(u.get("voice_minutes", 0) / 60.0, 1),
            "badges": unlocked_badges,
        }

    def get_top_viewers(self, limit: int = 10) -> List[Tuple[str, int, int, List[str]]]:
        sorted_users = sorted(
            self.users.items(),
            key=lambda item: item[1].get("xp", 0),
            reverse=True
        )
        res = []
        for u_id, u in sorted_users[:limit]:
            lvl = self.xp_to_level(u.get("xp", 0))
            badges = u.get("badges", [])
            badge_emojis = [BADGE_DEFINITIONS[b]["emoji"] for b in badges if b in BADGE_DEFINITIONS]
            res.append((u.get("name", f"User_{u_id}"), lvl, u.get("xp", 0), badge_emojis))
        return res

# Global Singleton
loyalty_system = LoyaltySystem()
