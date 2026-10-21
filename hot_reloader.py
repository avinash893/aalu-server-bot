"""
Tillu Hot-Reload Engine & Automatic File Watcher
Enables in-memory zero-downtime reloads of submodules and background watching
for files uploaded via SFTP or modified on the host.
"""

import os
import sys
import time
import asyncio
import logging
import importlib
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("TilluHotReloader")

RELOADABLE_MODULES = [
    "antigravity_bridge",
    "context_classifier",
    "prompt_manager",
    "memory_manager",
    "rule_manager",
    "rewards_manager",
    "discord_action_manager",
    "minecraft_player_resolver",
    "backup_manager",
    "sync_manager",
    "self_reflection",
]

class HotReloader:
    """Manages dynamic in-memory reloading of Tillu submodules."""

    def __init__(self, watch_dir: Optional[str] = None):
        self.watch_dir = watch_dir or os.path.dirname(os.path.abspath(__file__))
        self._timestamps: Dict[str, float] = {}
        self._watcher_task: Optional[asyncio.Task] = None
        self._is_watching = False
        self.update_timestamps()

    def update_timestamps(self):
        """Record current file modification times for all reloadable modules."""
        for mod_name in RELOADABLE_MODULES:
            file_path = os.path.join(self.watch_dir, f"{mod_name}.py")
            if os.path.exists(file_path):
                try:
                    self._timestamps[mod_name] = os.path.getmtime(file_path)
                except OSError:
                    pass

    def reload_module(self, mod_name: str) -> Tuple[bool, str]:
        """Reload a specific module in sys.modules."""
        if mod_name not in sys.modules:
            try:
                mod = importlib.import_module(mod_name)
                return True, f"Imported new module '{mod_name}'"
            except Exception as e:
                return False, f"Failed to import '{mod_name}': {e}"

        try:
            mod = sys.modules[mod_name]
            importlib.reload(mod)
            file_path = os.path.join(self.watch_dir, f"{mod_name}.py")
            if os.path.exists(file_path):
                self._timestamps[mod_name] = os.path.getmtime(file_path)
            logger.info(f"[HotReloader] Successfully reloaded '{mod_name}'.")
            return True, f"Reloaded '{mod_name}'"
        except Exception as e:
            logger.error(f"[HotReloader] Failed to reload '{mod_name}': {e}")
            return False, f"Error reloading '{mod_name}': {e}"

    def reload_all(self) -> Dict[str, str]:
        """Reload all registered modules and return status report."""
        report = {}
        for mod_name in RELOADABLE_MODULES:
            success, msg = self.reload_module(mod_name)
            report[mod_name] = msg
        return report

    def check_for_changes(self) -> List[str]:
        """Check if any module files have been modified since last check."""
        changed = []
        for mod_name in RELOADABLE_MODULES:
            file_path = os.path.join(self.watch_dir, f"{mod_name}.py")
            if os.path.exists(file_path):
                try:
                    current_mtime = os.path.getmtime(file_path)
                    prev_mtime = self._timestamps.get(mod_name, 0.0)
                    if prev_mtime > 0 and current_mtime > prev_mtime:
                        changed.append(mod_name)
                    self._timestamps[mod_name] = current_mtime
                except OSError:
                    pass
        return changed

    async def auto_watch_loop(self, interval_seconds: float = 5.0):
        """Background coroutine that polls file timestamps and auto-reloads modified modules."""
        self._is_watching = True
        logger.info(f"[HotReloader] Automatic file watcher started (polling every {interval_seconds}s).")
        while self._is_watching:
            try:
                await asyncio.sleep(interval_seconds)
                changed_mods = self.check_for_changes()
                if changed_mods:
                    logger.info(f"[HotReloader] Detected changes in {changed_mods}. Auto-reloading in-memory...")
                    for mod_name in changed_mods:
                        ok, msg = self.reload_module(mod_name)
                        if ok:
                            logger.info(f"[HotReloader] [OK] {msg}")
                        else:
                            logger.warning(f"[HotReloader] [FAILED] {msg}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HotReloader] Exception in file watcher loop: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)

    def start_watcher(self, loop: Optional[asyncio.AbstractEventLoop] = None, interval_seconds: float = 5.0) -> asyncio.Task:
        """Start the background file watcher task."""
        if self._watcher_task and not self._watcher_task.done():
            return self._watcher_task

        current_loop = loop or asyncio.get_event_loop()
        self._watcher_task = current_loop.create_task(self.auto_watch_loop(interval_seconds=interval_seconds))
        return self._watcher_task

    def stop_watcher(self):
        """Stop the background file watcher task."""
        self._is_watching = False
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
