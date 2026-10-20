"""
Tillu Context & Intent Classifier
Intelligently differentiates whether a user's request is meant for:
1. MINECRAFT (in-game actions, Paper/Bedrock console, whitelist, player telemetry, server power)
2. DISCORD (channel/role/category management, Discord moderation, purge, timeouts, Discord bans)
3. INTER_BOT (discovering, learning, controlling, or delegating tasks to other Discord bots)
4. MEMORY (facts to remember, learn, or recall)
5. GENERAL_CHAT (Hinglish conversation, streaming co-host jokes, memes, Q&A)
"""

import re
import json
import logging
from enum import Enum
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("TilluContextClassifier")

class TargetSystem(str, Enum):
    MINECRAFT = "MINECRAFT"
    DISCORD = "DISCORD"
    INTER_BOT = "INTER_BOT"
    MEMORY = "MEMORY"
    RULE = "RULE"
    GENERAL_CHAT = "GENERAL_CHAT"

class ClassificationResult:
    def __init__(
        self,
        system: TargetSystem,
        action: str,
        confidence: float,
        reasoning: str,
        parameters: Optional[Dict[str, Any]] = None,
        is_ambiguous: bool = False
    ):
        self.system = system
        self.action = action
        self.confidence = confidence
        self.reasoning = reasoning
        self.parameters = parameters or {}
        self.is_ambiguous = is_ambiguous

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system.value,
            "action": self.action,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "parameters": self.parameters,
            "is_ambiguous": self.is_ambiguous
        }

    def __repr__(self):
        return f"<ClassificationResult system={self.system.value} action={self.action} conf={self.confidence:.2f}>"


# ── Explicit Keyword Indicators ──────────────────────────────────────────────
DISCORD_KEYWORDS = {
    "role", "roles", "channel", "channels", "category", "categories",
    "purge", "clear chat", "delete messages", "delete chats", "clear messages",
    "timeout", "mute user", "unmute user", "deafen", "undeafen", "voice channel",
    "vc", "slowmode", "lock channel", "unlock channel", "lockdown", "server backup",
    "restore backup", "audit log", "permissions", "hoist", "mentionable", "discord",
    "in discord", "discord server", "server icon", "server name", "rename server"
}

MINECRAFT_KEYWORDS = {
    "minecraft", "mc", "in-game", "in game", "ingame", "paper", "spigot", "bukkit",
    "bedrock", "java", "geyser", "floodgate", "ign", "whitelist", "whitelisted",
    "unwhitelist", "console", "rcon", "tps", "gamemode", "tp", "teleport", "coords",
    "oneblock", "one block", "smp", "hexacraft", "pterodactyl", "panel", "server ip",
    "server port", "mc port", "mc ip", "spawn", "kit", "arena", "superheroes",
    "op", "deop", "say", "give", "kill", "time set", "weather", "datapack"
}

INTER_BOT_KEYWORDS = {
    "tell bot", "ask bot", "command bot", "run bot", "use bot", "bot command",
    "delegate to", "using bot", "play song", "play music", "warn user with",
    "ticket tool", "dyno", "probot", "mee6", "carl-bot", "fredboat", "hydra"
}


def classify_request(
    query: str,
    channel_name: str = "",
    channel_id: int = 0,
    has_discord_mention: bool = False,
    known_bot_names: Optional[list] = None
) -> ClassificationResult:
    """
    High-precision deterministic and heuristic classifier that resolves whether
    a user's prompt is targeting Minecraft, Discord, an external Bot, or General Chat.
    """
    q_clean = query.strip()
    q_lower = q_clean.lower()
    known_bots = [b.lower() for b in (known_bot_names or [])]

    # 1. CHANNEL CONTEXT SHORT-CIRCUITS
    ch_lower = channel_name.lower()
    if "whitelist" in ch_lower:
        # Check if user sent a raw IGN or whitelist request
        ign_match = re.search(r'^(?:!wl\s+|!whitelist\s+|whitelist\s+me\s+)?([a-zA-Z0-9_.* ]{3,20})$', q_clean)
        if ign_match:
            return ClassificationResult(
                system=TargetSystem.MINECRAFT,
                action="whitelist_add",
                confidence=0.99,
                reasoning="Message in dedicated whitelist channel with IGN pattern.",
                parameters={"ign": ign_match.group(1).strip()}
            )

    if "console" in ch_lower:
        return ClassificationResult(
            system=TargetSystem.MINECRAFT,
            action="mc_console_command",
            confidence=0.95,
            reasoning="Command dispatched directly inside Minecraft console channel.",
            parameters={"raw_command": q_clean}
        )

    # 2. INTER-BOT DELEGATION DETECTION
    for bot_name in known_bots:
        if bot_name in q_lower:
            # Pattern like "tell <bot> to <action>" or "<bot> play <song>" or "use <bot> for <action>"
            pattern = rf'\b(?:tell|ask|use|run|command)\s+{re.escape(bot_name)}\s+(?:to\s+)?(.+)'
            m = re.search(pattern, q_lower)
            if m:
                return ClassificationResult(
                    system=TargetSystem.INTER_BOT,
                    action="delegate_command",
                    confidence=0.95,
                    reasoning=f"User explicitly instructed delegation to Discord bot '{bot_name}'.",
                    parameters={"bot_name": bot_name, "instruction": m.group(1).strip()}
                )
            if re.search(rf'^{re.escape(bot_name)}\s+(.+)', q_lower):
                m2 = re.search(rf'^{re.escape(bot_name)}\s+(.+)', q_lower)
                return ClassificationResult(
                    system=TargetSystem.INTER_BOT,
                    action="delegate_command",
                    confidence=0.92,
                    reasoning=f"User prefixed command with Discord bot name '{bot_name}'.",
                    parameters={"bot_name": bot_name, "instruction": m2.group(1).strip()}
                )

    # 3. DISCORD MODERATION DISAMBIGUATION (Ban / Kick / Mute / Timeout)
    # Critical distinction: Ban with @mention is ALWAYS Discord, Ban with alphanumeric IGN is Minecraft.
    discord_mention_pattern = r'<@!?[0-9]+>'
    has_mention_in_text = bool(re.search(discord_mention_pattern, q_clean)) or has_discord_mention

    # BAN:
    ban_match = re.search(r'\b(?:ban|nikal\s+do|hata\s+do)\s+([^\n\r]+)', q_clean, re.IGNORECASE)
    if ban_match:
        target_str = ban_match.group(1).strip()
        # Explicit Discord context words
        if any(w in q_lower for w in ["from discord", "in discord", "server ban", "discord se", "discord ban"]):
            return ClassificationResult(
                system=TargetSystem.DISCORD,
                action="discord_ban",
                confidence=0.98,
                reasoning="User explicitly specified Discord ban.",
                parameters={"target": target_str}
            )
        # If targeting a Discord @mention or Discord ID
        if has_mention_in_text or re.match(r'^\d{17,20}$', target_str):
            return ClassificationResult(
                system=TargetSystem.DISCORD,
                action="discord_ban",
                confidence=0.95,
                reasoning="Target contains a Discord user mention or Discord user ID.",
                parameters={"target": target_str}
            )
        # Explicit Minecraft context words
        if any(w in q_lower for w in ["in mc", "in minecraft", "mc ban", "game se", "minecraft se", "console"]):
            return ClassificationResult(
                system=TargetSystem.MINECRAFT,
                action="mc_ban",
                confidence=0.98,
                reasoning="User explicitly specified Minecraft in-game ban.",
                parameters={"target": target_str}
            )
        # If target looks like a pure Minecraft IGN (no spaces, 3-16 chars alphanumeric)
        clean_ign = re.sub(r'["\']', '', target_str).split()[0]
        if re.match(r'^[a-zA-Z0-9_]{3,16}$', clean_ign):
            return ClassificationResult(
                system=TargetSystem.MINECRAFT,
                action="mc_ban",
                confidence=0.85,
                reasoning="Target matches standard Minecraft IGN syntax without Discord mention.",
                parameters={"ign": clean_ign}
            )

    # KICK:
    kick_match = re.search(r'\b(?:kick)\s+([^\n\r]+)', q_clean, re.IGNORECASE)
    if kick_match:
        target_str = kick_match.group(1).strip()
        if any(w in q_lower for w in ["from discord", "in discord", "discord se"]):
            return ClassificationResult(
                system=TargetSystem.DISCORD,
                action="discord_kick",
                confidence=0.98,
                reasoning="User explicitly specified Discord kick.",
                parameters={"target": target_str}
            )
        if has_mention_in_text or re.match(r'^\d{17,20}$', target_str):
            return ClassificationResult(
                system=TargetSystem.DISCORD,
                action="discord_kick",
                confidence=0.95,
                reasoning="Kick target is a Discord mention or Discord user ID.",
                parameters={"target": target_str}
            )
        clean_ign = re.sub(r'["\']', '', target_str).split()[0]
        if re.match(r'^[a-zA-Z0-9_]{3,16}$', clean_ign):
            return ClassificationResult(
                system=TargetSystem.MINECRAFT,
                action="mc_kick",
                confidence=0.85,
                reasoning="Kick target matches Minecraft IGN syntax.",
                parameters={"ign": clean_ign}
            )

    # TIMEOUT / MUTE:
    if re.search(r'\b(?:timeout|mute|shant\s+kar|chup\s+kar)\b', q_lower):
        if any(w in q_lower for w in ["in discord", "discord se", "voice", "vc", "chats?"]) or has_mention_in_text:
            return ClassificationResult(
                system=TargetSystem.DISCORD,
                action="discord_timeout",
                confidence=0.95,
                reasoning="Mute/timeout directed at a Discord user or channel.",
                parameters={"query": q_clean}
            )
        if any(w in q_lower for w in ["in mc", "in minecraft", "game me"]):
            return ClassificationResult(
                system=TargetSystem.MINECRAFT,
                action="mc_console_command",
                confidence=0.90,
                reasoning="Mute requested in Minecraft game server.",
                parameters={"raw_command": f"mute {q_clean}"}
            )

    # 4. DISCORD SERVER & ROLE & CHANNEL MANAGEMENT
    # Purge / Clear messages
    if re.search(r'\b(?:purge|clear|delete)\s+(\d+)\s*(?:messages?|chats?|msg)?\b', q_lower) or re.search(r'\b(?:delete|clear)\s+(?:last\s+)?(\d+)\b', q_lower):
        return ClassificationResult(
            system=TargetSystem.DISCORD,
            action="discord_purge",
            confidence=0.99,
            reasoning="Clear/purge message command is exclusively a Discord action."
        )

    # Roles / Channels / Categories
    discord_structural_words = ["role", "roles", "channel", "channels", "category", "categories", "backup server", "lock channel", "unlock channel", "slowmode"]
    if any(re.search(rf'\b{w}\b', q_lower) for w in discord_structural_words):
        # Exclude Minecraft in-game roles/kits like "superhero kit"
        if not any(mc in q_lower for mc in ["kit", "superhero", "arena class", "mc role"]):
            return ClassificationResult(
                system=TargetSystem.DISCORD,
                action="discord_management",
                confidence=0.95,
                reasoning="Command targets Discord server structure (role/channel/category/backup)."
            )

    # 5. MINECRAFT WHITELIST / PLAYERS / POWER / STATUS
    # Whitelist
    if re.search(r'\b(?:whitelist|whitelisted|wl)\b', q_lower):
        return ClassificationResult(
            system=TargetSystem.MINECRAFT,
            action="whitelist_request",
            confidence=0.95,
            reasoning="Whitelist actions strictly pertain to Minecraft server access."
        )

    # Server Power (Start / Stop / Restart)
    if re.search(r'\b(?:start|boot|chalu|on\s*kar|turn\s*on|restart|reboot)\b', q_lower):
        if any(w in q_lower for w in ["server", "minecraft", "mc", "game", "panel", "hexacraft"]):
            return ClassificationResult(
                system=TargetSystem.MINECRAFT,
                action="server_power",
                confidence=0.95,
                reasoning="Server power action targets the Minecraft game server."
            )

    # Player count / online players
    if re.search(r'\b(?:players?|who\s+is\s+(?:playing|online)|kaun\s+khel\s+raha|kitne\s+players?|kitne\s+log\s+khel)\b', q_lower):
        return ClassificationResult(
            system=TargetSystem.MINECRAFT,
            action="mc_players",
            confidence=0.95,
            reasoning="Query asks for active players in the Minecraft server."
        )

    # Server IP / Port / Connection
    if re.search(r'\b(?:ip|port|address|kaise\s+join\s+kare|how\s+to\s+join|server\s+version)\b', q_lower):
        return ClassificationResult(
            system=TargetSystem.MINECRAFT,
            action="mc_connection_info",
            confidence=0.95,
            reasoning="Query asks for Minecraft server connection details."
        )

    # Minecraft In-Game Telemetry / Mechanics (tps, coords, oneblock, smp, lag)
    if any(re.search(rf'\b{re.escape(w)}\b', q_lower) for w in ["tps", "coords", "coordinates", "oneblock", "smp", "gamemode", "datapack", "spigot", "paper"]):
        return ClassificationResult(
            system=TargetSystem.MINECRAFT,
            action="mc_telemetry" if ("tps" in q_lower or "lag" in q_lower) else "mc_inquiry",
            confidence=0.92,
            reasoning="Query references Minecraft gameplay mechanics, performance (TPS/lag), or coordinates."
        )

    # 6. MEMORY & RULES
    if re.search(r'\b(?:yaad\s*rakh|remember\s*this|note\s*this|learn\s*this)\b', q_lower):
        return ClassificationResult(
            system=TargetSystem.MEMORY,
            action="remember_fact",
            confidence=0.95,
            reasoning="User instructed Tillu to memorize a fact."
        )

    if re.search(r'\b(?:from\s+now\s+on|ab\s+se|whenever\s+someone|naya\s+rule)\b', q_lower):
        return ClassificationResult(
            system=TargetSystem.RULE,
            action="create_rule",
            confidence=0.90,
            reasoning="User is establishing an autonomous behavioral rule."
        )

    # 7. DEFAULT TO GENERAL CHAT / AI CO-HOST
    return ClassificationResult(
        system=TargetSystem.GENERAL_CHAT,
        action="general_chat",
        confidence=0.80,
        reasoning="General conversation, Q&A, Hinglish banter, or unconstrained query."
    )
