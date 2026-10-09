"""
Tillu Memory & Knowledge Manager with GitHub Cloud Auto-Sync
Maintains persistent, topic-keyed memories and facts for Tillu Discord Bot.
Syncs changes bidirectionally with the GitHub repository.
"""

import os
import sys
import json
import time
import re
import base64
import logging
import threading
import requests

logger = logging.getLogger("TilluMemory")

def normalize_topic(topic: str) -> str:
    """Normalize a topic key to lowercase alphanumeric with underscores."""
    if not topic:
        return "general"
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', topic.lower().strip())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:60] if clean else "general"

class MemoryManager:
    def __init__(self, file_path: str = None, repo: str = None, token: str = None):
        self.file_path = file_path or os.path.join(os.path.dirname(__file__), "tillu_memory.json")
        self.repo = repo or os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.remote_sha = None
        self.lock = threading.Lock()
        self.memories: dict[str, dict] = {}
        
        self.load()

    def _get_github_headers(self) -> dict:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def load(self):
        """Load memories from local JSON file and pull latest from GitHub if available."""
        with self.lock:
            # 1. Load local file first
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_m = data.get("memories", {})
                        if isinstance(raw_m, list):
                            self.memories = {}
                            for idx, item in enumerate(raw_m):
                                if isinstance(item, dict):
                                    fact = item.get("fact") or item.get("content", "")
                                    topic = item.get("topic") or (normalize_topic(fact[:30]) if fact else f"memory_{idx+1}")
                                    self.memories[topic] = {
                                        "topic": topic,
                                        "content": fact,
                                        "updated_by": item.get("added_by", "System"),
                                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                                    }
                        elif isinstance(raw_m, dict):
                            self.memories = raw_m
                        else:
                            self.memories = {}
                        logger.info(f"Loaded {len(self.memories)} memories from local file.")
                except Exception as e:
                    logger.warning(f"Error reading local memory file: {e}")
            
            # 2. Sync from GitHub API in background / initial load
            self._fetch_remote()

    def _fetch_remote(self):
        """Fetch remote memory from GitHub."""
        if not self.repo or not self.token:
            return
        url = f"https://api.github.com/repos/{self.repo}/contents/tillu_memory.json"
        try:
            r = requests.get(url, headers=self._get_github_headers(), timeout=10)
            if r.status_code == 200:
                res = r.json()
                self.remote_sha = res.get("sha")
                raw_b64 = res.get("content", "")
                if raw_b64:
                    raw_str = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
                    remote_data = json.loads(raw_str)
                    remote_mems = remote_data.get("memories", {})
                    # Merge or adopt remote memories (support dict or list)
                    if isinstance(remote_mems, list):
                        for idx, item in enumerate(remote_mems):
                            if isinstance(item, dict):
                                fact = item.get("fact") or item.get("content", "")
                                topic = item.get("topic") or (normalize_topic(fact[:30]) if fact else f"memory_{idx+1}")
                                self.memories[topic] = {
                                    "topic": topic,
                                    "content": fact,
                                    "updated_by": item.get("added_by", "System"),
                                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                                }
                        self._write_local_file()
                        logger.info(f"Synced {len(self.memories)} memories from GitHub repository.")
                    elif isinstance(remote_mems, dict) and remote_mems:
                        self.memories.update(remote_mems)
                        self._write_local_file()
                        logger.info(f"Synced {len(self.memories)} memories from GitHub repository.")
            elif r.status_code == 404:
                # If remote doesn't exist yet, save local to remote
                self._push_remote()
        except Exception as e:
            logger.warning(f"Remote GitHub fetch note: {e}")

    def _write_local_file(self):
        """Write current memories to local disk."""
        data = {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "count": len(self.memories),
            "memories": self.memories
        }
        try:
            tmp_path = self.file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            logger.error(f"Failed to write local memory file: {e}")

    def _push_remote(self):
        """Push memory updates to GitHub repository."""
        if not self.repo or not self.token:
            return
        def _task():
            with self.lock:
                url = f"https://api.github.com/repos/{self.repo}/contents/tillu_memory.json"
                # Check current sha if unknown
                headers = self._get_github_headers()
                if not self.remote_sha:
                    try:
                        r = requests.get(url, headers=headers, timeout=10)
                        if r.status_code == 200:
                            self.remote_sha = r.json().get("sha")
                    except Exception:
                        pass

                data = {
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "count": len(self.memories),
                    "memories": self.memories
                }
                content_str = json.dumps(data, indent=2, ensure_ascii=False)
                content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

                payload = {
                    "message": f"Update Tillu memory ({len(self.memories)} items)",
                    "content": content_b64
                }
                if self.remote_sha:
                    payload["sha"] = self.remote_sha

                try:
                    res = requests.put(url, headers=headers, json=payload, timeout=15)
                    if res.status_code in (200, 201):
                        self.remote_sha = res.json().get("content", {}).get("sha", self.remote_sha)
                        logger.info(f"Successfully pushed memory update to GitHub ({self.repo})!")
                    else:
                        logger.warning(f"GitHub memory push returned {res.status_code}: {res.text[:200]}")
                except Exception as ex:
                    logger.error(f"GitHub memory push exception: {ex}")

        # Run non-blocking in daemon thread
        threading.Thread(target=_task, daemon=True).start()

    def add_or_update(self, topic: str, content: str, author: str = "Admin") -> tuple[str, str, bool]:
        """
        Add or overwrite a memory entry on the same topic.
        Returns (clean_topic, content, was_overwritten).
        """
        clean_topic = normalize_topic(topic)
        content_clean = content.strip()
        with self.lock:
            was_overwritten = clean_topic in self.memories
            self.memories[clean_topic] = {
                "topic": clean_topic,
                "content": content_clean,
                "updated_by": author,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            }
            self._write_local_file()

        # Trigger background cloud push
        self._push_remote()
        return clean_topic, content_clean, was_overwritten

    def delete(self, topic: str) -> bool:
        """Delete a topic from memory."""
        clean_topic = normalize_topic(topic)
        with self.lock:
            if clean_topic in self.memories:
                del self.memories[clean_topic]
                self._write_local_file()
                self._push_remote()
                return True
        return False

    def get_all(self) -> dict[str, dict]:
        with self.lock:
            return dict(self.memories)

    def get_formatted_context(self) -> str:
        """Format active memories to inject into Gemini prompt."""
        with self.lock:
            if not self.memories:
                return ""
            lines = [
                "[TILLU PERSISTENT MEMORY & LEARNED FACTS (HIGHEST FACTUAL PRIORITY)]:",
                "The following facts have been learned directly from the Server Owner and Moderators. ALWAYS follow these facts strictly over any assumptions:"
            ]
            for key, val in self.memories.items():
                content = val.get("content", "").replace("\n", " ")
                lines.append(f"- [{key}]: {content}")
            lines.append("(End of learned facts. Strictly obey these!)")
            return "\n".join(lines)

    def parse_bulk_input(self, text: str, author: str = "Admin") -> list[tuple[str, str, bool]]:
        """
        Parse raw text or JSON input containing one or multiple memories.
        Supports:
        - JSON object: {"topic": "...", "content": "..."}
        - JSON key-value map: {"topic1": "val1", "topic2": "val2"}
        - JSON list of objects: [{"topic": "...", "content": "..."}]
        - Plain text key-value lines: 'topic: content' or 'topic = content' or 'Topic: ... | Content: ...'
        """
        results = []
        clean = text.strip()

        # Try JSON
        if (clean.startswith("{") and clean.endswith("}")) or (clean.startswith("[") and clean.endswith("]")):
            try:
                data = json.loads(clean)
                if isinstance(data, dict):
                    if "topic" in data and "content" in data:
                        results.append(self.add_or_update(str(data["topic"]), str(data["content"]), author))
                    else:
                        for k, v in data.items():
                            if isinstance(v, (str, int, float, bool)):
                                results.append(self.add_or_update(str(k), str(v), author))
                            elif isinstance(v, dict) and "content" in v:
                                results.append(self.add_or_update(str(k), str(v["content"]), author))
                            else:
                                results.append(self.add_or_update(str(k), json.dumps(v), author))
                    return results
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "topic" in item and "content" in item:
                            results.append(self.add_or_update(str(item["topic"]), str(item["content"]), author))
                    if results:
                        return results
            except Exception:
                pass

        # Try line by line or pipe separated
        for line in clean.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Pipe format: Topic: ... | Content: ...
            if "|" in line:
                parts = line.split("|", 1)
                t_part = parts[0].replace("topic:", "").replace("Topic:", "").strip()
                c_part = parts[1].replace("content:", "").replace("Content:", "").strip()
                if t_part and c_part:
                    results.append(self.add_or_update(t_part, c_part, author))
                    continue

            # Colon / Equals format: key: value or key = value
            m = re.match(r'^([^:=]+)[:=]\s*(.+)$', line)
            if m:
                t = m.group(1).strip().lstrip("-* ")
                c = m.group(2).strip()
                if t and c:
                    results.append(self.add_or_update(t, c, author))
                    continue

        # If nothing matched, treat the whole text as a general memory or single entry
        if not results and len(clean) > 3:
            first_words = clean.split()[:3]
            auto_topic = "_".join(first_words)
            results.append(self.add_or_update(auto_topic, clean, author))

        return results
