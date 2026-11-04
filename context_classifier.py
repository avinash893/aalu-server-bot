"""
Tillu Context & Intent Classifier (Streamer & Community Edition)
Intelligently differentiates user intent across:
1. YOUTUBE_LIVE (Owner stream timings, live status, upcoming broadcast schedule)
2. MEMBER_DIR (Listing server members, searching members, formatting <@id> tags)
3. INTER_BOT (Discovering, commanding, or delegating tasks to other Discord bots)
4. PLAYER_ANALYTICS (Member gaming history, played games, server game stats)
5. DISCORD (Roles, channels, moderation, purge, server settings)
6. MEMORY / RULE (Remembering facts, learning guidelines)
7. GENERAL_CHAT (Hinglish conversation with dynamic mood engine)
"""

import re
import json
import logging
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("TilluContextClassifier")

class TargetSystem(str, Enum):
    YOUTUBE_LIVE = "YOUTUBE_LIVE"
    MEMBER_DIR = "MEMBER_DIR"
    INTER_BOT = "INTER_BOT"
    PLAYER_ANALYTICS = "PLAYER_ANALYTICS"
    DISCORD = "DISCORD"
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


# Keyword Indicators
DISCORD_KEYWORDS = {
    "role", "roles", "channel", "channels", "category", "categories",
    "purge", "clear chat", "delete messages", "delete chats", "clear messages",
    "timeout", "mute user", "unmute user", "deafen", "undeafen", "voice channel",
    "vc", "slowmode", "lock channel", "unlock channel", "lockdown", "server backup",
    "restore backup", "audit log", "permissions", "hoist", "mentionable", "discord",
    "in discord", "discord server", "server icon", "server name", "rename server"
}

YOUTUBE_LIVE_KEYWORDS = {
    "live", "stream", "timing", "schedule", "yt", "youtube", "aalu live",
    "kab aayega", "stream kab", "live kab", "live timing", "stream timing",
    "broadcast", "kitne baje", "stream time", "live status", "is aalu live"
}

MEMBER_KEYWORDS = {
    "member", "members", "tag karo", "tag them", "ping karo", "who all",
    "kaun kaun", "list members", "sabko tag", "tag member", "tag all"
}

PLAYER_ANALYTICS_KEYWORDS = {
    "game history", "what does he play", "kaunsa game khelta", "games played",
    "game stats", "top games", "khelte hain", "khelta hai", "most played",
    "gaming history", "active games", "currently playing"
}


def classify_intent(
    query: str,
    channel_name: str = "",
    channel_id: int = 0,
    has_discord_mention: bool = False,
    known_bot_names: Optional[List[str]] = None
) -> ClassificationResult:
    """
    High-precision deterministic and heuristic classifier that resolves whether
    a user's prompt is targeting YouTube Live, Member Tagging, Another Bot,
    Player Game Analytics, Discord Admin, Memory, or General Chat.
    """
    q_clean = query.strip()
    q_lower = q_clean.lower()
    known_bots = [b.lower() for b in (known_bot_names or [])]

    # 1. YOUTUBE LIVE & STREAM TIMING
    if any(k in q_lower for k in ["live kab", "stream kab", "live timing", "stream timing", "live status", "aalu live"]):
        return ClassificationResult(
            system=TargetSystem.YOUTUBE_LIVE,
            action="get_live_timing",
            confidence=0.98,
            reasoning="User explicitly asked for owner YouTube live stream timing or status."
        )

    if any(k in q_lower for k in ["live", "stream"]) and any(k in q_lower for k in ["kab", "timing", "time", "schedule", "aayega", "shuru", "aata hai"]):
        return ClassificationResult(
            system=TargetSystem.YOUTUBE_LIVE,
            action="get_live_timing",
            confidence=0.95,
            reasoning="Pattern matches query about stream schedule or live broadcast timing."
        )

    # 2. INTER-BOT DELEGATION DETECTION
    for bot_name in known_bots:
        if bot_name in q_lower and bot_name != "tillu":
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

    # 3. PLAYER GAME HISTORY & ANALYTICS
    if any(k in q_lower for k in ["game history", "gaming history", "games played", "top games"]):
        return ClassificationResult(
            system=TargetSystem.PLAYER_ANALYTICS,
            action="player_history" if has_discord_mention else "top_games",
            confidence=0.95,
            reasoning="Query matches player game history or top played games analytics."
        )

    if any(k in q_lower for k in ["kya khelta hai", "kaunsa game khelta", "khel raha hai"]) and (has_discord_mention or "all" in q_lower or "sab" in q_lower):
        return ClassificationResult(
            system=TargetSystem.PLAYER_ANALYTICS,
            action="player_history",
            confidence=0.92,
            reasoning="Query asking what game a member or members play."
        )

    # 4. MEMBER DIRECTORY & TAGGING
    if any(k in q_lower for k in ["who all are the member", "who are the members", "kaun kaun members", "list members", "sab members", "member list"]):
        return ClassificationResult(
            system=TargetSystem.MEMBER_DIR,
            action="list_members",
            confidence=0.96,
            reasoning="Query asking for server member directory."
        )

    tag_match = re.search(r'\b(?:tag|ping)\s+([^\n\r]+)', q_lower)
    if tag_match and not any(k in q_lower for k in ["role", "channel"]):
        return ClassificationResult(
            system=TargetSystem.MEMBER_DIR,
            action="tag_member",
            confidence=0.92,
            reasoning="User instructed Tillu to tag or ping a member.",
            parameters={"target": tag_match.group(1).strip()}
        )

    # 5. DISCORD MODERATION & MANAGEMENT
    discord_mention_pattern = r'<@!?[0-9]+>'
    has_mention_in_text = bool(re.search(discord_mention_pattern, q_clean)) or has_discord_mention

    # BAN:
    ban_match = re.search(r'\b(?:ban|nikal\s+do|hata\s+do)\s+([^\n\r]+)', q_clean, re.IGNORECASE)
    if ban_match and has_mention_in_text:
        return ClassificationResult(
            system=TargetSystem.DISCORD,
            action="discord_ban",
            confidence=0.98,
            reasoning="Discord user mention provided for ban action.",
            parameters={"target": ban_match.group(1).strip()}
        )

    # KICK:
    kick_match = re.search(r'\b(?:kick)\s+([^\n\r]+)', q_clean, re.IGNORECASE)
    if kick_match and has_mention_in_text:
        return ClassificationResult(
            system=TargetSystem.DISCORD,
            action="discord_kick",
            confidence=0.98,
            reasoning="Discord user mention provided for kick action.",
            parameters={"target": kick_match.group(1).strip()}
        )

    # MUTE / TIMEOUT:
    timeout_match = re.search(r'\b(?:mute|timeout|shant\s+kar)\s+([^\n\r]+)', q_clean, re.IGNORECASE)
    if timeout_match and has_mention_in_text:
        return ClassificationResult(
            system=TargetSystem.DISCORD,
            action="discord_timeout",
            confidence=0.98,
            reasoning="Discord user mention provided for timeout/mute action.",
            parameters={"target": timeout_match.group(1).strip()}
        )

    # PURGE / DELETE MESSAGES:
    if any(k in q_lower for k in ["purge", "clear chat", "delete messages", "clear messages"]):
        m_count = re.search(r'\b(\d+)\b', q_clean)
        count = int(m_count.group(1)) if m_count else 10
        return ClassificationResult(
            system=TargetSystem.DISCORD,
            action="purge_messages",
            confidence=0.98,
            reasoning="Request to purge or clear Discord messages.",
            parameters={"count": count}
        )

    # ROLES & CHANNELS:
    if any(k in q_lower for k in ["create role", "give role", "remove role", "delete role", "create channel", "lock channel", "unlock channel"]):
        return ClassificationResult(
            system=TargetSystem.DISCORD,
            action="discord_admin_action",
            confidence=0.95,
            reasoning="Discord server structure or role modification request."
        )

    # 6. MEMORY & RULES
    if any(q_lower.startswith(prefix) for prefix in ["remember", "yaad rakh", "sikho", "learn rule", "add rule", "rule:"]):
        return ClassificationResult(
            system=TargetSystem.RULE if "rule" in q_lower else TargetSystem.MEMORY,
            action="store_rule" if "rule" in q_lower else "store_memory",
            confidence=0.98,
            reasoning="Explicit directive to store memory or rule."
        )

    # 7. MINECRAFT LEGACY QUERIES (HANDLED GRACEFULLY)
    if any(k in q_lower for k in ["minecraft", "smp", "whitelist", "server ip", "paper mc", "hexacraft"]):
        return ClassificationResult(
            system=TargetSystem.GENERAL_CHAT,
            action="minecraft_server_deleted",
            confidence=0.90,
            reasoning="User asked about Minecraft server which has been shut down and deleted."
        )

    # 8. GENERAL CHAT (FALLBACK)
    return ClassificationResult(
        system=TargetSystem.GENERAL_CHAT,
        action="chat_reply",
        confidence=0.85,
        reasoning="Conversational query or banter meant for Tillu AI."
    )

# Backward compatibility alias
classify_request = classify_intent
