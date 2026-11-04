"""
Tillu Player Game History & Activity Analytics Engine
Tracks members' public Discord game presence, records playtime history,
identifies trending server games, and provides rich audit metrics.
"""

import os
import json
import time
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple
import discord

logger = logging.getLogger("TilluPlayerAnalytics")

class PlayerAnalytics:
    def __init__(self, file_path: Optional[str] = None):
        base_dir = os.path.dirname(__file__)
        self.file_path = file_path or os.path.join(base_dir, "data", "player_game_history.json")
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        with self.lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading game history file: {e}")
            return {}

    def _save(self):
        with self.lock:
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving game history: {e}")

    def record_presence(self, member: discord.Member) -> Optional[str]:
        """
        Inspects member activities and records active game sessions.
        Returns the game name if a game was detected.
        """
        if not member or member.bot:
            return None

        detected_game = None
        for act in member.activities:
            # Check for game activity or streaming game
            if act.type in (discord.ActivityType.playing, discord.ActivityType.streaming):
                name = getattr(act, "name", None)
                if name and name.strip() and name.strip() not in ("Spotify", "Custom Status"):
                    detected_game = name.strip()
                    break

        uid = str(member.id)
        now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        now_ts = time.time()

        if uid not in self.data:
            self.data[uid] = {
                "username": member.name,
                "display_name": member.display_name,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "current_game": detected_game,
                "last_active_ts": now_ts,
                "games": {}
            }

        user_entry = self.data[uid]
        user_entry["username"] = member.name
        user_entry["display_name"] = member.display_name
        user_entry["last_seen"] = now_iso

        prev_game = user_entry.get("current_game")

        if detected_game:
            user_entry["current_game"] = detected_game
            games = user_entry.setdefault("games", {})

            if detected_game not in games:
                games[detected_game] = {
                    "first_played": now_iso,
                    "last_played": now_iso,
                    "sessions": 1,
                    "estimated_minutes": 10
                }
            else:
                g_entry = games[detected_game]
                g_entry["last_played"] = now_iso
                # If continuing previous game within 30 min, increment playtime
                if prev_game == detected_game:
                    elapsed_min = max(1, min(30, int((now_ts - user_entry.get("last_active_ts", now_ts)) / 60)))
                    g_entry["estimated_minutes"] = g_entry.get("estimated_minutes", 0) + elapsed_min
                else:
                    g_entry["sessions"] = g_entry.get("sessions", 1) + 1

            user_entry["last_active_ts"] = now_ts
            self._save()
            return detected_game
        else:
            if prev_game:
                user_entry["current_game"] = None
                self._save()

        return None

    def scan_guild(self, guild: discord.Guild) -> int:
        """Scan all members currently online in the guild and record active games."""
        if not guild:
            return 0
        detected_count = 0
        for m in guild.members:
            if not m.bot and m.status != discord.Status.offline:
                res = self.record_presence(m)
                if res:
                    detected_count += 1
        return detected_count

    def get_player_history(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Return the game history for a specific member."""
        uid = str(user_id)
        return self.data.get(uid)

    def get_top_games(self, limit: int = 10) -> List[Tuple[str, int, int]]:
        """
        Returns top played games across all server members.
        Format: [(game_name, total_players, total_estimated_hours), ...]
        """
        game_stats: Dict[str, Dict[str, Any]] = {}
        for uid, user_data in self.data.items():
            for g_name, g_info in user_data.get("games", {}).items():
                if g_name not in game_stats:
                    game_stats[g_name] = {"players": set(), "minutes": 0}
                game_stats[g_name]["players"].add(uid)
                game_stats[g_name]["minutes"] += g_info.get("estimated_minutes", 0)

        results = []
        for g_name, stats in game_stats.items():
            results.append((
                g_name,
                len(stats["players"]),
                round(stats["minutes"] / 60, 1)
            ))

        # Sort by total players descending, then hours
        results.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return results[:limit]

    def get_daily_audit_metrics(self, guild: Optional[discord.Guild] = None) -> Dict[str, Any]:
        """Generate daily summary of gaming activity and community trends."""
        total_tracked_players = len(self.data)
        top_games = self.get_top_games(limit=5)

        # Count currently playing
        currently_playing: Dict[str, List[str]] = {}
        if guild:
            for m in guild.members:
                if not m.bot and m.status != discord.Status.offline:
                    for act in m.activities:
                        if act.type in (discord.ActivityType.playing, discord.ActivityType.streaming):
                            g_name = getattr(act, "name", "")
                            if g_name and g_name not in ("Spotify", "Custom Status"):
                                currently_playing.setdefault(g_name, []).append(f"<@{m.id}>")

        return {
            "total_players_tracked": total_tracked_players,
            "top_games": top_games,
            "currently_playing": currently_playing,
            "tracked_games_count": len(set(g for u in self.data.values() for g in u.get("games", {})))
        }

    def format_player_history_embed(self, member: discord.Member) -> discord.Embed:
        """Format an embed displaying a member's public game history."""
        hist = self.get_player_history(member.id)
        embed = discord.Embed(
            title=f"🎮 Game History: {member.display_name}",
            color=0x2ECC71,
            description=f"Public gaming history tracked for <@{member.id}>"
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        if not hist or not hist.get("games"):
            embed.description += "\n\n*Abhi tak koi game play session record nahi hua! Jab bhi ye koi game khelenge, Tillu track kar lega.*"
            return embed

        current = hist.get("current_game")
        if current:
            embed.add_field(name="🟢 Currently Playing", value=f"**{current}**", inline=False)

        games = hist.get("games", {})
        sorted_games = sorted(games.items(), key=lambda x: x[1].get("estimated_minutes", 0), reverse=True)

        lines = []
        for g_name, g_info in sorted_games[:10]:
            mins = g_info.get("estimated_minutes", 0)
            hours_str = f"{round(mins/60, 1)} hrs" if mins >= 60 else f"{mins} mins"
            sessions = g_info.get("sessions", 1)
            last_p = g_info.get("last_played", "Recently").split()[0]
            lines.append(f"• **{g_name}**: ~{hours_str} ({sessions} sessions, last: {last_p})")

        embed.add_field(name="🕹️ Played Games", value="\n".join(lines), inline=False)
        return embed
