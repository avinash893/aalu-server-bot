"""
Tillu 5x Daily Self-Reflection, Error Auditing & Autonomous Self-Upgrade Engine
Enables Tillu to:
1. Log all user tasks, classified intents, system targets, execution outcomes, and errors.
2. Automatically run a deep self-reflection audit 5 times daily (~every 4.8 hours).
3. Evaluate task success rate and diagnose any misrouted Minecraft vs Discord requests.
4. Formulate concrete dynamic improvements and inject them into Tillu's live prompt & rule memory.
5. Post audit summaries to #update-tillu and commit reflection history to GitHub.
"""

import os
import sys
import re
import json
import time
import uuid
import logging
import asyncio
import base64
import threading
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger("TilluSelfReflection")

class TaskTelemetryLogger:
    """Thread-safe persistent logger for all user interactions and task executions."""
    def __init__(self, file_path: str = None, max_records: int = 500):
        base_dir = os.path.dirname(__file__)
        self.file_path = file_path or os.path.join(base_dir, "data", "task_telemetry.json")
        self.max_records = max_records
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def log_task(
        self,
        query: str,
        user_name: str,
        user_id: int,
        channel_name: str,
        channel_id: int,
        classified_system: str,
        action_taken: str,
        success: bool = True,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
        response_preview: str = ""
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        entry = {
            "task_id": task_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": user_name,
            "user_id": user_id,
            "channel": channel_name,
            "channel_id": channel_id,
            "query": query[:300],
            "classified_system": classified_system,
            "action_taken": action_taken[:150],
            "success": success,
            "error": error_message[:250] if error_message else None,
            "duration_ms": round(duration_ms, 1),
            "response_preview": response_preview[:200]
        }

        with self.lock:
            records = self._read_unlocked()
            records.append(entry)
            if len(records) > self.max_records:
                records = records[-self.max_records:]
            self._write_unlocked(records)

        return task_id

    def _read_unlocked(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    return data.get("tasks", [])
            except Exception as e:
                logger.warning(f"Error reading task telemetry: {e}")
        return []

    def _write_unlocked(self, records: List[Dict[str, Any]]):
        data = {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_records": len(records),
            "tasks": records
        }
        tmp = self.file_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error(f"Failed writing telemetry: {e}")

    def get_recent_tasks(self, count: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            records = self._read_unlocked()
            return records[-count:]

    def get_tasks_since(self, iso_timestamp: str) -> List[Dict[str, Any]]:
        with self.lock:
            records = self._read_unlocked()
            if not iso_timestamp:
                return records
            return [r for r in records if r.get("timestamp", "") > iso_timestamp]


class SelfReflectionEngine:
    def __init__(
        self,
        telemetry: TaskTelemetryLogger,
        reflection_path: str = None,
        report_md_path: str = None,
        repo: str = None,
        token: str = None
    ):
        base_dir = os.path.dirname(__file__)
        self.telemetry = telemetry
        self.reflection_path = reflection_path or os.path.join(base_dir, "data", "self_reflection.json")
        self.report_md_path = report_md_path or os.path.join(base_dir, "logs", "daily_audit_report.md")
        self.repo = repo or os.environ.get("GITHUB_REPO", "avinash893/aalu-server-bot")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.lock = threading.Lock()
        self.last_audit_time = ""
        self.audit_counter = 0
        os.makedirs(os.path.dirname(self.report_md_path), exist_ok=True)
        self.load()

    def _get_github_headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TilluReflection/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def load(self):
        with self.lock:
            if os.path.exists(self.reflection_path):
                try:
                    with open(self.reflection_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        self.last_audit_time = data.get("last_audit_time", "")
                        self.audit_counter = data.get("audit_counter", 0)
                except Exception as e:
                    logger.warning(f"Error loading reflection state: {e}")

    def save(self, audit_summary: Dict[str, Any]):
        with self.lock:
            self.last_audit_time = audit_summary.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            self.audit_counter += 1
            data = {
                "last_audit_time": self.last_audit_time,
                "audit_counter": self.audit_counter,
                "last_audit_summary": audit_summary
            }
            tmp = self.reflection_path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.reflection_path)
            except Exception as e:
                logger.error(f"Failed writing reflection state: {e}")

        # Write markdown report
        try:
            with open(self.report_md_path, "w", encoding="utf-8") as f:
                f.write(self._format_markdown_report(audit_summary))
        except Exception as me:
            logger.warning(f"Failed writing markdown report: {me}")

        self._push_github()

    def _format_markdown_report(self, s: Dict[str, Any]) -> str:
        return f"""# 🧠 Tillu 5x Daily Self-Audit Report #{self.audit_counter}
**Generated:** {s.get('timestamp')}
**Time Window:** Tasks since {s.get('since', 'Initial Run')}

## 📊 Performance Metrics
- **Total Tasks Processed:** `{s.get('total_tasks', 0)}`
- **Successful Executions:** `{s.get('success_count', 0)}`
- **Failed Tasks / Errors:** `{s.get('fail_count', 0)}`
- **Success Rate:** `{s.get('success_rate', 100.0)}%`

## 🎯 Context Classification Breakdown
```json
{json.dumps(s.get('system_breakdown', {}), indent=2)}
```

## 🛠️ Diagnostics & Self-Corrections
{s.get('ai_reflection', 'All tasks executed within baseline performance. No system degradation detected.')}

---
*Autonomous Self-Reflection Engine • Synced to GitHub repository ({self.repo})*
"""

    def _push_github(self):
        if not self.repo or not self.token:
            return

        def _task():
            with self.lock:
                try:
                    with open(self.reflection_path, "r", encoding="utf-8") as f:
                        content_str = f.read()
                except Exception:
                    return

            url = f"https://api.github.com/repos/{self.repo}/contents/data/self_reflection.json"
            headers = self._get_github_headers()
            curr_sha = None
            try:
                r = requests.get(url, headers=headers, timeout=8)
                if r.status_code == 200:
                    curr_sha = r.json().get("sha")
            except Exception:
                pass

            payload = {
                "message": f"telemetry: Tillu 5x Daily Self-Audit #{self.audit_counter}",
                "content": base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
            }
            if curr_sha:
                payload["sha"] = curr_sha

            try:
                requests.put(url, headers=headers, json=payload, timeout=12)
                logger.info(f"Self-reflection audit #{self.audit_counter} synced to GitHub.")
            except Exception as pe:
                logger.warning(f"GitHub push reflection error: {pe}")

        threading.Thread(target=_task, daemon=True).start()

    async def execute_audit_cycle(
        self,
        prompt_mgr=None,
        rule_mgr=None,
        llm_reflection_fn=None,
        notification_channel=None
    ) -> Dict[str, Any]:
        """
        Executes an audit cycle over recent tasks.
        Evaluates task performance, extracts errors, formulates self-improvements,
        injects dynamic instructions, and notifies staff.
        """
        tasks = self.telemetry.get_tasks_since(self.last_audit_time)
        if not tasks:
            tasks = self.telemetry.get_recent_tasks(20)

        total = len(tasks)
        successes = sum(1 for t in tasks if t.get("success", True))
        fails = total - successes
        rate = round((successes / total * 100), 1) if total > 0 else 100.0

        system_breakdown: Dict[str, int] = {}
        error_logs: List[str] = []
        for t in tasks:
            sys_name = t.get("classified_system", "UNKNOWN")
            system_breakdown[sys_name] = system_breakdown.get(sys_name, 0) + 1
            if not t.get("success") or t.get("error"):
                error_logs.append(f"[{t.get('classified_system')}] Query: '{t.get('query')}' | Error: {t.get('error')}")

        ai_reflection_text = ""
        learned_improvement = ""
        if llm_reflection_fn and (error_logs or total > 0):
            try:
                ai_prompt = (
                    f"Perform a self-audit on these recent Tillu Discord bot tasks:\n"
                    f"- Total: {total}, Success: {successes}, Fails: {fails}, Rate: {rate}%\n"
                    f"- System breakdown: {system_breakdown}\n"
                    f"- Error samples: {error_logs[:5]}\n\n"
                    f"1. Summarize any confusion between Minecraft vs Discord requests.\n"
                    f"2. Suggest exactly 1 concrete behavioral instruction to improve robustness in 1-2 sentences."
                )
                ai_reflection_text = await asyncio.to_thread(llm_reflection_fn, ai_prompt)
                # Extract suggested instruction
                if "instruction:" in ai_reflection_text.lower():
                    m = re.search(r'instruction:\s*([^\n\r]+)', ai_reflection_text, re.IGNORECASE)
                    if m:
                        learned_improvement = m.group(1).strip()
            except Exception as ae:
                logger.warning(f"Error generating AI reflection: {ae}")

        if not ai_reflection_text:
            ai_reflection_text = f"Audit passed with {rate}% efficiency across {total} tasks. System stable."

        # Automatically apply learned improvement into prompt manager
        if learned_improvement and prompt_mgr:
            try:
                prompt_mgr.add_instruction(
                    f"[Self-Audit #{self.audit_counter + 1}] {learned_improvement}",
                    author="TilluSelfAudit"
                )
                logger.info(f"Injected self-learned improvement: {learned_improvement}")
            except Exception as ie:
                logger.warning(f"Could not inject prompt improvement: {ie}")

        audit_summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "since": self.last_audit_time or "Start",
            "total_tasks": total,
            "success_count": successes,
            "fail_count": fails,
            "success_rate": rate,
            "system_breakdown": system_breakdown,
            "errors_detected": len(error_logs),
            "ai_reflection": ai_reflection_text,
            "auto_learned_improvement": learned_improvement
        }

        self.save(audit_summary)

        # Notify Discord update channel if available
        if notification_channel:
            try:
                embed = discord.Embed(
                    title=f"🧠 Tillu 5x Daily Self-Audit #{self.audit_counter}",
                    description=(
                        f"**Task Health Analysis (Every 4.8 Hours):**\n"
                        f"• Tasks Evaluated: **{total}**\n"
                        f"• Success Rate: **{rate}%** (`{successes}` OK / `{fails}` Failed)\n"
                        f"• Intent Routing: `{json.dumps(system_breakdown)}`\n\n"
                        f"**Diagnostics & Evolution:**\n> {ai_reflection_text[:800]}"
                    ),
                    color=0x2ECC71 if rate >= 90 else 0xE67E22,
                    timestamp=discord.utils.utcnow()
                )
                if learned_improvement:
                    embed.add_field(name="🚀 Auto-Learned Robustness Rule", value=f"`{learned_improvement}`", inline=False)
                embed.set_footer(text=f"GitHub Synced • avinash893/aalu-server-bot • 5x Daily Self-Evolution Loop")
                await notification_channel.send(embed=embed)
            except Exception as ne:
                logger.warning(f"Failed sending audit embed: {ne}")

        return audit_summary
