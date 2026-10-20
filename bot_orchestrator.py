"""
Tillu Inter-Bot Orchestrator & Autonomous Discovery Engine
Enables Tillu to:
1. Discover all other Discord bots in the server.
2. Inspect their roles, permissions, registered slash commands, and prefixes.
3. Automatically analyze any newly joined bot via AI to learn its capabilities and syntax.
4. Maintain a persistent bot directory (data/bot_catalog.json) synced with GitHub.
5. Provide contextual knowledge to Tillu's brain so Tillu can control or delegate tasks to them.
"""

import os
import sys
import json
import time
import logging
import asyncio
import re
import base64
import threading
from typing import Dict, Any, List, Optional
import discord
import requests

logger = logging.getLogger("TilluBotOrchestrator")

DEFAULT_KNOWN_BOT_PRESETS = {
    "dyno": {
        "prefix": ["?"],
        "category": "Moderation / Management",
        "description": "Full moderation bot with warnings, slowmode, auto-roles, and utility.",
        "skills": ["?warn <user> <reason>", "?mute <user> <time>", "?slowmode <sec>", "?afk"]
    },
    "mee6": {
        "prefix": ["!"],
        "category": "Leveling / Moderation",
        "description": "XP levels, welcome cards, custom commands, and auto-moderation.",
        "skills": ["!levels", "!rank", "!give-xp <user> <amt>"]
    },
    "probot": {
        "prefix": ["#"],
        "category": "Economy / Utility",
        "description": "Multipurpose Arabic/English bot with credits economy, levels, and voice tracking.",
        "skills": ["#credits", "#rep <user>", "#daily"]
    },
    "carl-bot": {
        "prefix": ["?"],
        "category": "Reaction Roles / Logs",
        "description": "Automated reaction roles, advanced audit logs, and modlogs.",
        "skills": ["?rr make", "?echo <text>", "?logs"]
    },
    "fredboat": {
        "prefix": [";;"],
        "category": "Music",
        "description": "Music player for YouTube, Soundcloud, and radio streams.",
        "skills": [";;play <song>", ";;skip", ";;stop", ";;queue"]
    },
    "ticket tool": {
        "prefix": ["$"],
        "category": "Support Tickets",
        "description": "Private channel ticketing system for support requests.",
        "skills": ["$panel", "$ticket", "$close"]
    },
    "giveawaybot": {
        "prefix": ["g!"],
        "category": "Giveaways",
        "description": "Automated server giveaways and prize draws.",
        "skills": ["g!start <time> <prize>", "g!reroll", "g!end"]
    }
}


class BotOrchestrator:
    def __init__(self, catalog_path: str = None, repo: str = None, token: str = None):
        base_dir = os.path.dirname(__file__)
        self.catalog_path = catalog_path or os.path.join(base_dir, "data", "bot_catalog.json")
        self.repo = repo or os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.lock = threading.Lock()
        self.bots: Dict[str, Dict[str, Any]] = {}
        os.makedirs(os.path.dirname(self.catalog_path), exist_ok=True)
        self.load()

    def _get_github_headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TilluBotOrchestrator/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def load(self):
        """Loads bot catalog from disk and merges default presets."""
        with self.lock:
            if os.path.exists(self.catalog_path):
                try:
                    with open(self.catalog_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        self.bots = data.get("bots", {})
                        logger.info(f"Loaded {len(self.bots)} bot profiles from catalog.")
                except Exception as e:
                    logger.warning(f"Error reading bot catalog: {e}")

    def save(self):
        """Saves bot directory to local disk and triggers GitHub backup."""
        with self.lock:
            data = {
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_bots": len(self.bots),
                "bots": self.bots
            }
            tmp = self.catalog_path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.catalog_path)
            except Exception as e:
                logger.error(f"Failed writing bot catalog: {e}")

        self._push_github()

    def _push_github(self):
        """Non-blocking GitHub cloud backup for bot catalog."""
        if not self.repo or not self.token:
            return

        def _task():
            with self.lock:
                data = {
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "total_bots": len(self.bots),
                    "bots": self.bots
                }
            url = f"https://api.github.com/repos/{self.repo}/contents/data/bot_catalog.json"
            headers = self._get_github_headers()
            curr_sha = None
            try:
                r = requests.get(url, headers=headers, timeout=8)
                if r.status_code == 200:
                    curr_sha = r.json().get("sha")
            except Exception:
                pass

            payload = {
                "message": f"feat: Update Tillu bot directory ({len(data['bots'])} bots)",
                "content": base64.b64encode(json.dumps(data, indent=2).encode('utf-8')).decode('utf-8')
            }
            if curr_sha:
                payload["sha"] = curr_sha

            try:
                requests.put(url, headers=headers, json=payload, timeout=12)
                logger.info("Bot catalog synced to GitHub.")
            except Exception as pe:
                logger.warning(f"GitHub push bot catalog error: {pe}")

        threading.Thread(target=_task, daemon=True).start()

    def get_known_bot_names(self) -> List[str]:
        """Returns list of bot names active in the catalog."""
        with self.lock:
            return [b.get("name", "").lower() for b in self.bots.values() if b.get("name")]

    async def sync_guild_bots(self, guild: discord.Guild, llm_analyzer_fn=None):
        """
        Scans guild members, identifies bots, pulls registered commands,
        and uses AI to fill capability profiles.
        """
        if not guild:
            return

        bot_members = [m for m in guild.members if m.bot and m.id != guild.me.id]
        logger.info(f"Scanning guild '{guild.name}' for bots. Found: {len(bot_members)}")

        # Fetch guild application commands if accessible
        guild_slash_commands: Dict[int, List[str]] = {}
        try:
            app_cmds = await guild.fetch_application_commands()
            for cmd in app_cmds:
                app_id = cmd.application_id
                guild_slash_commands.setdefault(app_id, []).append(f"/{cmd.name}")
        except Exception as se:
            logger.debug(f"Could not fetch guild application commands (normal for bot permissions): {se}")

        updated = False
        for m in bot_members:
            m_id = str(m.id)
            if m_id not in self.bots:
                logger.info(f"Discovered new bot: {m.name} ({m_id}). Analyzing capabilities...")
                profile = await self.analyze_and_register_bot(m, guild, guild_slash_commands.get(m.id, []), llm_analyzer_fn)
                self.bots[m_id] = profile
                updated = True

        if updated:
            self.save()

    async def analyze_and_register_bot(
        self,
        bot_member: discord.Member,
        guild: discord.Guild,
        slash_cmds: List[str] = None,
        llm_analyzer_fn=None
    ) -> Dict[str, Any]:
        """Analyzes a bot using presets + LLM heuristics."""
        slash_cmds = slash_cmds or []
        lower_name = bot_member.name.lower().strip()

        # Check presets first
        preset = None
        for p_key, p_val in DEFAULT_KNOWN_BOT_PRESETS.items():
            if p_key in lower_name:
                preset = p_val
                break

        roles = [r.name for r in bot_member.roles if r.name != "@everyone"]
        base_profile = {
            "id": bot_member.id,
            "name": bot_member.name,
            "discriminator": bot_member.discriminator,
            "joined_at": bot_member.joined_at.isoformat() if bot_member.joined_at else None,
            "roles": roles,
            "slash_commands": slash_cmds,
            "prefix": preset.get("prefix", ["!"]) if preset else ["!"],
            "category": preset.get("category", "Utility / Integration") if preset else "General Bot",
            "description": preset.get("description", f"Discord bot active in {guild.name}.") if preset else f"Bot active in {guild.name}.",
            "skills": preset.get("skills", []) if preset else slash_cmds,
            "analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }

        # If LLM analyzer function is available, generate dynamic profile
        if llm_analyzer_fn and not preset:
            try:
                ai_info = await asyncio.to_thread(llm_analyzer_fn, bot_member.name, roles, slash_cmds)
                if isinstance(ai_info, dict):
                    base_profile.update(ai_info)
            except Exception as ae:
                logger.warning(f"LLM analysis failed for bot {bot_member.name}: {ae}")

        return base_profile

    def get_bot_by_name(self, name_query: str) -> Optional[Dict[str, Any]]:
        """Finds a bot profile by name or alias."""
        clean = name_query.lower().strip()
        with self.lock:
            for b in self.bots.values():
                b_name = b.get("name", "").lower()
                if clean in b_name or b_name in clean:
                    return b
        return None

    def format_inter_bot_context(self) -> str:
        """
        Formats active bot capabilities as an enriched system prompt block
        so Tillu knows how to control and collaborate with other bots.
        """
        with self.lock:
            if not self.bots:
                return ""

            lines = [
                "[INTER-BOT COLLABORATION & CONTROL SYSTEM]:",
                "Tillu has high-level coordinator authority over other Discord bots in this server.",
                "Here are the other active bots and how to invoke/delegate their capabilities:"
            ]
            for b in self.bots.values():
                b_name = b.get("name")
                cat = b.get("category", "General")
                prefix = ", ".join(b.get("prefix", ["!"]))
                skills = ", ".join(b.get("skills", [])[:4]) or "Standard commands"
                lines.append(f"- **{b_name}** ({cat}) | Prefix: `{prefix}` | Skills: `{skills}`")

            lines.append("If a Server Owner or Admin tells you to command another bot (e.g., 'tillu tell dyno to warn X', 'play music using FredBoat'):")
            lines.append("Emit: BOT_COMMAND: <exact_prefixed_command_or_instructions>")
            lines.append("Tillu will automatically dispatch or assist the user with that bot!")
            return "\n".join(lines)
