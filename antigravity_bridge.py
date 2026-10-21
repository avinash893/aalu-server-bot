"""
Tillu Antigravity Agent Bridge
Enables Tillu to run directly on Google Antigravity's agentic runtime
using authenticated Google OAuth sessions (~/.gemini/oauth_creds.json)
independent of local PCs.
"""

import os
import shutil
import logging
from typing import Optional

logger = logging.getLogger("TilluAntigravityBridge")

# Ensure .gemini credentials exist in user's home directory on Linux
HOME_DIR = os.path.expanduser("~")
HOME_GEMINI = os.path.join(HOME_DIR, ".gemini")
LOCAL_GEMINI = os.path.join(os.path.dirname(__file__), ".gemini")

if os.path.exists(LOCAL_GEMINI) and not os.path.exists(HOME_GEMINI):
    try:
        shutil.copytree(LOCAL_GEMINI, HOME_GEMINI)
        logger.info(f"Copied Antigravity credentials from {LOCAL_GEMINI} to {HOME_GEMINI}")
    except Exception as e:
        logger.warning(f"Failed to copy credentials to {HOME_GEMINI}: {e}")

_SDK_AVAILABLE = False
try:
    from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    logger.info("google.antigravity SDK not installed in this environment; falling back to direct API mode.")


def is_antigravity_available() -> bool:
    """Check if Antigravity SDK is installed and valid credentials exist."""
    if not _SDK_AVAILABLE:
        return False
    creds_home = os.path.join(HOME_GEMINI, "oauth_creds.json")
    creds_local = os.path.join(LOCAL_GEMINI, "oauth_creds.json")
    return os.path.exists(creds_home) or os.path.exists(creds_local)


async def query_antigravity(prompt: str, system_instructions: str, author_name: str = "") -> Optional[str]:
    """
    Execute reasoning through the Google Antigravity Agent runtime.
    Returns generated agent response string, or None if unavailable/failed.
    """
    if not is_antigravity_available():
        return None

    try:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip() or None
        config = LocalAgentConfig(
            system_instructions=system_instructions,
            capabilities=CapabilitiesConfig(),
            api_key=gemini_key
        )
        async with Agent(config) as agent:
            resp = await agent.chat(prompt)
            if hasattr(resp, "text"):
                res_obj = resp.text
                if callable(res_obj):
                    text = await res_obj()
                else:
                    text = str(res_obj)
                return text.strip() if text else None
            return None
    except Exception as e:
        logger.warning(f"[Antigravity Agent] Runtime notice: {e}")
        return None
