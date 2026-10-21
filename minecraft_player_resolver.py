"""
Tillu Minecraft Player Resolver & GriefPrevention Claim Manager
Discovers live player IGNs via DiscordSRV, console telemetry, whitelist registries,
and performs fuzzy matching to accurately target Bedrock (dot prefix) and Java players
for commands like GriefPrevention land claims (/adjustbonusclaimblocks).
"""

import os
import re
import json
import difflib
import logging
from typing import Optional, Set, List, Tuple
import discord

logger = logging.getLogger("TilluPlayerResolver")

PLAYERS_FILE = os.path.join(os.path.dirname(__file__), "known_minecraft_players.json")
REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")

DEFAULT_SEED_PLAYERS = [
    ".UNIQUE_UMAR_114",
    ".VAMPIRE674066",
    ".NAKEEBGAM",
    "AALU_CHIPAS",
    "Avinash893",
    "MrAalu"
]

_PLAYERS_CACHE: Set[str] = set()


def load_known_players() -> Set[str]:
    """Load known Minecraft player names from disk and default seeds."""
    global _PLAYERS_CACHE
    if _PLAYERS_CACHE:
        return set(_PLAYERS_CACHE)

    players = set(DEFAULT_SEED_PLAYERS)
    if os.path.exists(PLAYERS_FILE):
        try:
            with open(PLAYERS_FILE, "r", encoding="utf-8-sig") as f:
                saved = json.load(f)
                if isinstance(saved, list):
                    players.update(saved)
        except Exception as e:
            logger.warning(f"Error loading known players: {e}")

    # Also load from whitelist_registry.json if present
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8-sig") as f:
                reg = json.load(f)
                if isinstance(reg, dict):
                    for _, udata in reg.items():
                        ign = udata.get("ign")
                        if ign:
                            players.add(ign)
        except Exception as e:
            logger.warning(f"Error loading whitelist registry: {e}")

    _PLAYERS_CACHE = players
    return set(_PLAYERS_CACHE)


def save_known_players(players: Set[str]):
    """Persist known players to disk."""
    global _PLAYERS_CACHE
    _PLAYERS_CACHE = set(players)
    try:
        tmp = PLAYERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(list(_PLAYERS_CACHE)), f, indent=2)
        os.replace(tmp, PLAYERS_FILE)
    except Exception as e:
        logger.error(f"Failed to save known players: {e}")


def record_player(ign: str):
    """Register a new player IGN in memory and save to disk."""
    if not ign:
        return
    clean = ign.strip().strip('"\'`')
    if len(clean) >= 2 and re.match(r'^[a-zA-Z0-9_.* ]{2,25}$', clean):
        players = load_known_players()
        if clean not in players:
            players.add(clean)
            save_known_players(players)
            logger.info(f"Registered new Minecraft player: '{clean}'")


def normalize_name(s: str) -> str:
    """Strip all non-alphanumeric characters and lowercase."""
    return re.sub(r'[^a-zA-Z0-9]', '', s).lower()


def clean_player_query(query: str) -> str:
    """Strip common conversational and command filler words."""
    fluff = [
        r'\bin\s+minecraft\b', r'\bin\s+game\b', r'\bin\s+mc\b', r'\bminecraft\b', r'\bmc\b',
        r'\bko\b', r'\bde\s+do\b', r'\bto\b', r'\bfor\b', r'\bgive\b', r'\bclaim\b',
        r'\bunlimited\b', r'\bland\b', r'\bblocks?\b', r'\bplayer\b', r'\bign\b',
        r'\bchahiye\b', r'\ballocate\b', r'\bplease\b'
    ]
    cleaned = query
    for pat in fluff:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().strip('"\'`@')
    return cleaned


def resolve_closest_player(query: str, extra_candidates: Optional[List[str]] = None) -> Tuple[Optional[str], float]:
    """
    Fuzzy resolve player query to closest matching known Minecraft IGN.
    Handles Bedrock dot prefixes (e.g. '.UNIQUE_UMAR_114' vs 'unique umar').
    Returns (matched_ign, confidence).
    """
    clean_q = clean_player_query(query)
    q_norm = normalize_name(clean_q)
    if not q_norm:
        return None, 0.0

    all_cands = load_known_players()
    if extra_candidates:
        all_cands.update(extra_candidates)

    # 1. Exact match (ignoring case & leading dot)
    for c in all_cands:
        if c.lower().lstrip('.') == clean_q.lower().lstrip('.'):
            return c, 1.0

    # 2. Exact normalized alphanumeric match
    for c in all_cands:
        if normalize_name(c) == q_norm:
            return c, 0.99

    # 3. Normalized substring match (e.g. 'uniqueumar' in 'uniqueumar114')
    substring_matches = []
    for c in all_cands:
        c_norm = normalize_name(c)
        if q_norm in c_norm or (len(c_norm) >= 4 and c_norm in q_norm):
            diff = abs(len(c_norm) - len(q_norm))
            substring_matches.append((diff, c))
    if substring_matches:
        substring_matches.sort()
        return substring_matches[0][1], 0.95

    # 4. Fuzzy sequence matcher
    scored = []
    for c in all_cands:
        c_norm = normalize_name(c)
        ratio = difflib.SequenceMatcher(None, q_norm, c_norm).ratio()
        scored.append((ratio, c))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 0.55:
        return scored[0][1], scored[0][0]

    return None, 0.0


async def harvest_players_from_discord(
    bot: discord.Client,
    guild: Optional[discord.Guild] = None,
    console_channel_id: int = 1486114457674453083,
    chat_channel_id: int = 1456299736326733998
) -> Set[str]:
    """
    Scans recent messages from DiscordSRV chat and console channels to discover
    active or past player IGNs (including Bedrock dot-prefixed names).
    """
    discovered = load_known_players()
    channels_to_scan = []

    for ch_id in [console_channel_id, chat_channel_id]:
        ch = bot.get_channel(ch_id)
        if not ch:
            try:
                ch = await bot.fetch_channel(ch_id)
            except Exception:
                ch = None
        if ch and hasattr(ch, "history"):
            channels_to_scan.append(ch)

    for ch in channels_to_scan:
        try:
            async for msg in ch.history(limit=75):
                # 1. DiscordSRV Webhook author names (DiscordSRV uses player's IGN as webhook username!)
                if getattr(msg, "webhook_id", None) and msg.author and msg.author.name:
                    name = msg.author.name.strip()
                    if not any(w in name.lower() for w in ["server", "discordsrv", "bot", "console", "webhook"]):
                        discovered.add(name)

                # 2. Inspect message text / embeds
                text = msg.content or ""
                if msg.embeds:
                    for e in msg.embeds:
                        text += " " + (e.description or "") + " " + (e.title or "")

                # Whitelist list output
                wl_m = re.search(r'whitelisted player\(s\):\s*([^\n\r]+)', text, re.IGNORECASE)
                if wl_m:
                    raw_names = re.sub(r'[\r\n`]+', '', wl_m.group(1)).split(',')
                    for n in raw_names:
                        clean_n = n.strip()
                        if clean_n:
                            discovered.add(clean_n)

                # Online players list
                on_m = re.search(r'(?:players\s+online|There are \d+ .* players online):\s*([^\n\r]+)', text, re.IGNORECASE)
                if on_m:
                    raw_names = re.sub(r'[\r\n`]+', '', on_m.group(1)).split(',')
                    for n in raw_names:
                        clean_n = n.strip()
                        if clean_n:
                            discovered.add(clean_n)

                # Join / Leave logs
                join_m = re.findall(r'(?:Player\s+)?([a-zA-Z0-9_.*]{2,20})\s+(?:joined the game|joined the server|logged in)', text, re.IGNORECASE)
                for jn in join_m:
                    discovered.add(jn.strip())

                # Chat message tags <PlayerName> or [PlayerName]
                chat_tags = re.findall(r'[<\[]([a-zA-Z0-9_.*]{2,20})[>\]]', text)
                for tag in chat_tags:
                    if tag.lower() not in ["discordsrv", "discord", "server", "info", "warn", "error"]:
                        discovered.add(tag.strip())
        except Exception as scan_err:
            logger.warning(f"Error scanning channel {ch.id}: {scan_err}")

    # Check Discord members in guild
    if guild:
        for m in guild.members:
            if m.bot:
                continue
            # If member has "Whitelisted" role or explicit nickname
            has_wl = any("whitelist" in r.name.lower() for r in m.roles)
            if has_wl:
                discovered.add(m.name)
                if m.nick:
                    discovered.add(m.nick)

    save_known_players(discovered)
    return set(discovered)


async def execute_claim_land_command(
    player_ign: str,
    amount: int = 10000000,
    execute_server_command_fn = None
) -> Tuple[bool, str]:
    """
    Executes GriefPrevention console command to grant bonus claim blocks.
    Amount defaults to 10,000,000 (effectively unlimited claims).
    """
    if not execute_server_command_fn:
        return False, "Command dispatcher not available"

    clean_ign = player_ign.strip().strip('"\'`')
    quoted_ign = f'"{clean_ign}"' if " " in clean_ign else clean_ign

    # Primary command: /adjustbonusclaimblocks <player> <amount>
    primary_cmd = f"adjustbonusclaimblocks {quoted_ign} {amount}"
    ok1, resp1 = await execute_server_command_fn(primary_cmd)

    # Bedrock compatibility: If Bedrock IGN starts with '.', also execute without dot (or vice versa)
    if clean_ign.startswith("."):
        alt_ign = clean_ign[1:]
        alt_quoted = f'"{alt_ign}"' if " " in alt_ign else alt_ign
        await execute_server_command_fn(f"adjustbonusclaimblocks {alt_quoted} {amount}")
    else:
        alt_ign = f".{clean_ign}"
        alt_quoted = f'"{alt_ign}"' if " " in alt_ign else alt_ign
        await execute_server_command_fn(f"adjustbonusclaimblocks {alt_quoted} {amount}")

    return ok1, f"GriefPrevention: {amount:,} bonus claim blocks allocated to `{clean_ign}`"
