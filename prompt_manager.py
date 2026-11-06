"""
Tillu Dynamic Prompt & Personality Manager with GitHub Cloud Auto-Sync
Allows Server Owner, Admins, and Moderators to dynamically update Tillu's personality,
behavioral rules, tone, and self-awareness live from chat without restarting the bot.
"""

import os
import json
import time
import base64
import logging
import threading
from typing import Dict, Any, List
import requests

logger = logging.getLogger("TilluPromptManager")

DEFAULT_CAPABILITIES = (
    "TILLU SYSTEM CAPABILITIES & SELF-AWARENESS:\n"
    "1. Live YouTube Live Timing API: Tillu checks owner's YouTube live broadcast timings, upcoming schedules, and stream links.\n"
    "2. Member Directory & Precise Tagging: Tillu knows server members, resolves member names/roles, and tags them properly with <@id>.\n"
    "3. Inter-Bot Command & Delegation: Tillu can command, delegate tasks, and trigger actions with other Discord bots in the server.\n"
    "4. Player Game History & Daily Audit: Tillu tracks members' public game presence, logs played games, and runs 24h daily community audits.\n"
    "5. Dynamic Hinglish Personality & 130+ Meme Engine: Actively prevents repetitive phrases ('Haan bhai', 'Bolo kya scene hai') by rotating across 130+ Bollywood, gaming, and Desi pop-culture memes with fresh openers.\n"
    "6. Full Discord Server Control & Cloud Memory: Administrator moderation rights, rule memory, and GitHub auto-sync."
)

class PromptManager:
    def __init__(self, file_path: str = None, repo: str = None, token: str = None):
        self.file_path = file_path or os.path.join(os.path.dirname(__file__), "tillu_personality.json")
        self.repo = repo or os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.remote_sha = None
        self.lock = threading.Lock()
        self.custom_instructions: List[Dict[str, str]] = []
        self.active_tone = "Dynamic, witty Indian streamer co-host (switching between sarcastic banter, funny memes, existential robot humor, and loyal brotherly support)."
        self.load()

    def _get_github_headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TilluBot/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def load(self):
        """Load personality data from local file and sync with GitHub."""
        with self.lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        self.custom_instructions = data.get("custom_instructions", [])
                        self.active_tone = data.get("active_tone", self.active_tone)
                        logger.info(f"Loaded {len(self.custom_instructions)} dynamic prompt instructions from local file.")
                except Exception as e:
                    logger.warning(f"Error reading local personality file: {e}")

        self._fetch_remote()

    def _fetch_remote(self):
        """Fetch remote personality settings from GitHub without holding lock during HTTP."""
        if not self.repo or not self.token:
            return
        url = f"https://api.github.com/repos/{self.repo}/contents/tillu_personality.json"
        try:
            r = requests.get(url, headers=self._get_github_headers(), timeout=10)
            if r.status_code == 200:
                res = r.json()
                new_sha = res.get("sha")
                raw_b64 = res.get("content", "")
                if raw_b64:
                    raw_str = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
                    data = json.loads(raw_str)
                    with self.lock:
                        self.remote_sha = new_sha
                        self.custom_instructions = data.get("custom_instructions", self.custom_instructions)
                        self.active_tone = data.get("active_tone", self.active_tone)
                        logger.info("Synced dynamic personality and prompt instructions from GitHub.")
                        self._save_local_unlocked()
        except Exception as e:
            logger.warning(f"Failed to fetch personality from GitHub: {e}")

    def _save_local_unlocked(self):
        data = {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "active_tone": self.active_tone,
            "custom_instructions": self.custom_instructions
        }
        try:
            tmp = self.file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error(f"Failed to write local personality file: {e}")

    def _push_remote(self, commit_message: str):
        if not self.repo or not self.token:
            return
        def _task():
            with self.lock:
                tone_snapshot = self.active_tone
                instructions_snapshot = list(self.custom_instructions)
                curr_sha = self.remote_sha

            url = f"https://api.github.com/repos/{self.repo}/contents/tillu_personality.json"
            headers = self._get_github_headers()
            if not curr_sha:
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        curr_sha = r.json().get("sha")
                except Exception:
                    pass

            data = {
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_tone": tone_snapshot,
                "custom_instructions": instructions_snapshot
            }
            content_str = json.dumps(data, indent=2, ensure_ascii=False)
            content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

            payload = {
                "message": commit_message,
                "content": content_b64
            }
            if curr_sha:
                payload["sha"] = curr_sha

            try:
                res = requests.put(url, headers=headers, json=payload, timeout=15)
                if res.status_code in (200, 201):
                    new_sha = res.json().get("content", {}).get("sha", curr_sha)
                    with self.lock:
                        self.remote_sha = new_sha
                    logger.info(f"Personality successfully committed to GitHub ({commit_message})")
            except Exception as e:
                logger.error(f"GitHub personality push exception: {e}")

        threading.Thread(target=_task, daemon=True).start()

    def add_instruction(self, instruction: str, author: str = "Admin") -> None:
        """Add a dynamic behavioral/personality instruction live and commit to GitHub."""
        with self.lock:
            self.custom_instructions.append({
                "instruction": instruction.strip(),
                "author": author,
                "added_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            })
            self._save_local_unlocked()
            self._push_remote(f"feat: Update Tillu dynamic prompt personality by {author}")

    def set_tone(self, new_tone: str, author: str = "Admin") -> None:
        """Set a new active personality tone."""
        with self.lock:
            self.active_tone = new_tone.strip()
            self._save_local_unlocked()
            self._push_remote(f"feat: Update Tillu tone to '{new_tone[:30]}' by {author}")

    def get_formatted_prompt_extension(self) -> str:
        """Returns living prompt extensions to append into AI system prompts."""
        with self.lock:
            parts = [DEFAULT_CAPABILITIES]
            if self.active_tone:
                parts.append(f"CURRENT DYNAMIC TONE OVERRIDE:\n{self.active_tone}")
            if self.custom_instructions:
                lines = [f"- {item['instruction']} (Added by {item.get('author', 'Admin')})" for item in self.custom_instructions]
                parts.append("DYNAMIC USER-TAUGHT BEHAVIORAL INSTRUCTIONS:\n" + "\n".join(lines))
            return "\n\n".join(parts)
