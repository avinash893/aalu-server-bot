"""
Tillu Autonomous Rule & Skill Manager with GitHub Cloud Auto-Sync
Allows Server Owner, Admins, and Moderators to dynamically teach Tillu new moderation rules,
chat filters, user restrictions, and server console triggers from Discord.
Syncs all learned rules to GitHub repository and hot-reloads in real time.
"""

import os
import sys
import json
import time
import re
import base64
import logging
import threading
import datetime
from typing import Optional, List, Dict, Any, Tuple
import requests
import discord

logger = logging.getLogger("TilluRules")

class RuleManager:
    def __init__(self, file_path: str = None, repo: str = None, token: str = None):
        self.file_path = file_path or os.path.join(os.path.dirname(__file__), "autonomous_rules.json")
        self.repo = repo or os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.remote_sha = None
        self.lock = threading.Lock()
        self.rules: Dict[str, Dict[str, Any]] = {}
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
        """Load rules from local JSON and sync with GitHub."""
        with self.lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        raw_r = data.get("rules", {})
                        if isinstance(raw_r, dict):
                            self.rules = raw_r
                        elif isinstance(raw_r, list):
                            self.rules = {r.get("id", f"rule_{i+1}"): r for i, r in enumerate(raw_r)}
                        logger.info(f"Loaded {len(self.rules)} autonomous rules from local file.")
                except Exception as e:
                    logger.warning(f"Error reading local rules file: {e}")

        self._fetch_remote()

    def _fetch_remote(self):
        """Fetch remote rules from GitHub without holding lock during HTTP."""
        if not self.repo or not self.token:
            return
        url = f"https://api.github.com/repos/{self.repo}/contents/autonomous_rules.json"
        try:
            r = requests.get(url, headers=self._get_github_headers(), timeout=10)
            if r.status_code == 200:
                res = r.json()
                new_sha = res.get("sha")
                raw_b64 = res.get("content", "")
                if raw_b64:
                    raw_str = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
                    remote_data = json.loads(raw_str)
                    remote_rules = remote_data.get("rules", {})
                    with self.lock:
                        self.remote_sha = new_sha
                        if isinstance(remote_rules, dict):
                            self.rules.update(remote_rules)
                        elif isinstance(remote_rules, list):
                            for i, r in enumerate(remote_rules):
                                rid = r.get("id", f"rule_{i+1}")
                                self.rules[rid] = r
                        logger.info(f"Synced {len(self.rules)} autonomous rules from GitHub repository.")
                        self._save_local_unlocked()
        except Exception as e:
            logger.warning(f"Failed to fetch autonomous rules from GitHub: {e}")

    def _save_local_unlocked(self):
        data = {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "count": len(self.rules),
            "rules": self.rules
        }
        try:
            tmp_path = self.file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            logger.error(f"Failed to write local rules file: {e}")

    def _push_remote(self, commit_message: str):
        """Push rules update to GitHub asynchronously without locking the entire thread."""
        if not self.repo or not self.token:
            return
        def _task():
            with self.lock:
                rules_snapshot = dict(self.rules)
                curr_sha = self.remote_sha

            url = f"https://api.github.com/repos/{self.repo}/contents/autonomous_rules.json"
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
                "count": len(rules_snapshot),
                "rules": rules_snapshot
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
                    logger.info(f"Autonomous rules successfully committed to GitHub ({commit_message})")
                else:
                    logger.warning(f"GitHub rules commit failed: HTTP {res.status_code} {res.text[:100]}")
            except Exception as e:
                logger.error(f"GitHub rules push exception: {e}")

        threading.Thread(target=_task, daemon=True).start()

    def add_rule(self, rule_data: Dict[str, Any], author: str = "Admin") -> Tuple[str, Dict[str, Any]]:
        """Add or update an autonomous rule, save locally and sync to GitHub."""
        with self.lock:
            rule_id = rule_data.get("id") or f"rule_{int(time.time() * 1000)}"
            rule_data["id"] = rule_id
            rule_data["author"] = author
            rule_data["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            self.rules[rule_id] = rule_data
            self._save_local_unlocked()
            self._push_remote(f"feat: Add autonomous rule '{rule_data.get('title', rule_id)}' via #update-tillu")
            return rule_id, rule_data

    def delete_rule(self, rule_id: str) -> bool:
        """Delete an autonomous rule and sync removal to GitHub."""
        with self.lock:
            if rule_id in self.rules:
                del self.rules[rule_id]
                self._save_local_unlocked()
                self._push_remote(f"chore: Remove autonomous rule '{rule_id}' via #update-tillu")
                return True
            return False

    def list_rules(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.rules.values())

    async def evaluate_message(self, message: discord.Message, server_cmd_fn) -> bool:
        """
        Evaluate an incoming Discord message against active autonomous rules.
        Returns True if a rule intercepted the message and took action (e.g. deleted message).
        """
        if not message.guild or message.author.bot:
            return False

        content_lower = message.content.lower().strip()
        author_id = message.author.id

        with self.lock:
            active_rules = list(self.rules.values())

        for rule in active_rules:
            rtype = rule.get("type", "")
            condition = rule.get("condition", {})
            action = rule.get("action", {})

            # 1. Check User Restriction (e.g., mute / block user)
            if rtype == "user_restriction":
                target_user_id = condition.get("user_id")
                is_target = False
                try:
                    if target_user_id:
                        clean_uid = str(target_user_id).strip("<@!> ")
                        if clean_uid.isdigit():
                            is_target = (author_id == int(clean_uid))
                except Exception:
                    is_target = False

                if is_target:
                    # Check if action is delete_message
                    if action.get("type") in ["delete_message", "mute", "timeout"]:
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        if action.get("type") in ["mute", "timeout"]:
                            mins = action.get("duration_minutes", 10)
                            try:
                                until = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
                                await message.author.timeout(until, reason=f"Autonomous Rule: {rule.get('title', 'Restricted')}")
                            except Exception as te:
                                logger.warning(f"Could not timeout user {author_id}: {te}")
                        return True

            # 2. Check Chat Moderation (e.g. prohibited keywords or pattern)
            elif rtype == "chat_moderation":
                pattern = condition.get("pattern", "")
                keywords = condition.get("keywords", [])
                matched = False

                if keywords:
                    if any(kw.lower() in content_lower for kw in keywords if kw):
                        matched = True
                elif pattern:
                    try:
                        if re.search(pattern, message.content, re.IGNORECASE):
                            matched = True
                    except Exception:
                        if pattern.lower() in content_lower:
                            matched = True

                if matched:
                    act_type = action.get("type", "delete_message")
                    if act_type in ["delete_message", "delete"]:
                        try:
                            await message.delete()
                        except Exception as de:
                            logger.warning(f"Failed to delete prohibited message: {de}")
                        reply_warn = action.get("warning_message")
                        if reply_warn:
                            try:
                                await message.channel.send(f"{message.author.mention} {reply_warn}", delete_after=6)
                            except Exception:
                                pass
                        return True

            # 3. Check Server Trigger (e.g. execute Minecraft command on chat trigger)
            elif rtype == "server_action":
                trigger_phrase = condition.get("phrase", "").lower()
                if trigger_phrase and re.search(rf'(?:\b|^){re.escape(trigger_phrase)}(?:\b|$)', content_lower):
                    mc_cmd = action.get("command")
                    if mc_cmd and server_cmd_fn:
                        try:
                            await server_cmd_fn(mc_cmd)
                            reply = action.get("reply_message")
                            if reply:
                                await message.channel.send(reply)
                        except Exception as se:
                            logger.error(f"Error running server action rule: {se}")
                        return True

            # 4. Custom Automated Reply Rule
            elif rtype == "custom_response":
                trigger_phrase = condition.get("phrase", "").lower()
                if trigger_phrase and re.search(rf'(?:\b|^){re.escape(trigger_phrase)}(?:\b|$)', content_lower):
                    reply = action.get("reply_message")
                    if reply:
                        try:
                            await message.reply(reply)
                        except Exception:
                            await message.channel.send(reply)
                        return True

        return False
