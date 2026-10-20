"""
Comprehensive Test Suite for Tillu Bot Upgrades:
1. Minecraft vs Discord Context Differentiation
2. Inter-Bot Orchestration & Capability Discovery
3. Task Telemetry & 5x Daily Self-Reflection Engine
4. Discord Action Parser & Safety Routing
"""

import os
import sys
import json
import asyncio
import unittest

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from context_classifier import classify_request, TargetSystem, ClassificationResult
from bot_orchestrator import BotOrchestrator, DEFAULT_KNOWN_BOT_PRESETS
from self_reflection import TaskTelemetryLogger, SelfReflectionEngine


class TestContextClassifier(unittest.TestCase):
    def setUp(self):
        self.known_bots = ["dyno", "mee6", "probot", "fredboat", "ticket tool", "giveawaybot"]

    def test_discord_moderation_with_mentions(self):
        # Ban/Kick with mention MUST be DISCORD
        res_ban = classify_request("ban <@123456789012345678> for trolling", has_discord_mention=True)
        self.assertEqual(res_ban.system, TargetSystem.DISCORD)
        self.assertEqual(res_ban.action, "discord_ban")

        res_kick = classify_request("kick <@987654321098765432> spammer", has_discord_mention=True)
        self.assertEqual(res_kick.system, TargetSystem.DISCORD)
        self.assertEqual(res_kick.action, "discord_kick")

        res_timeout = classify_request("timeout <@123456789012345678> 15m")
        self.assertEqual(res_timeout.system, TargetSystem.DISCORD)
        self.assertEqual(res_timeout.action, "discord_timeout")

    def test_minecraft_moderation_with_ign(self):
        # Ban/Kick with pure alphanumeric IGN MUST be MINECRAFT
        res_mc_ban = classify_request("ban Steve123 in game")
        self.assertEqual(res_mc_ban.system, TargetSystem.MINECRAFT)
        self.assertEqual(res_mc_ban.action, "mc_ban")

        res_mc_kick = classify_request("kick Herobrine99 from minecraft")
        self.assertEqual(res_mc_kick.system, TargetSystem.MINECRAFT)
        self.assertEqual(res_mc_kick.action, "mc_kick")

    def test_discord_channel_and_role_management(self):
        res_purge = classify_request("purge 50 messages")
        self.assertEqual(res_purge.system, TargetSystem.DISCORD)
        self.assertEqual(res_purge.action, "discord_purge")

        res_ch = classify_request("create voice channel named Gaming Lounge")
        self.assertEqual(res_ch.system, TargetSystem.DISCORD)
        self.assertIn(res_ch.action, ["discord_channel", "discord_management"])

        res_role = classify_request("give role Moderator to <@123456789012345678>")
        self.assertEqual(res_role.system, TargetSystem.DISCORD)
        self.assertIn(res_role.action, ["discord_role", "discord_management"])

    def test_minecraft_server_telemetry_and_actions(self):
        res_wl = classify_request("tillu whitelist me ProGamer_99")
        self.assertEqual(res_wl.system, TargetSystem.MINECRAFT)
        self.assertIn(res_wl.action, ["whitelist_add", "whitelist_request"])

        res_tps = classify_request("server ka tps check karo")
        self.assertEqual(res_tps.system, TargetSystem.MINECRAFT)
        self.assertEqual(res_tps.action, "mc_telemetry")

        res_coords = classify_request("oneblock spawn ke coords batao")
        self.assertEqual(res_coords.system, TargetSystem.MINECRAFT)
        self.assertEqual(res_coords.action, "mc_inquiry")

    def test_inter_bot_delegation(self):
        res_dyno = classify_request("tell dyno to warn <@123> spamming", known_bot_names=self.known_bots)
        self.assertEqual(res_dyno.system, TargetSystem.INTER_BOT)
        self.assertEqual(res_dyno.action, "delegate_command")

        res_fred = classify_request("tell fredboat to play lofi hip hop", known_bot_names=self.known_bots)
        self.assertEqual(res_fred.system, TargetSystem.INTER_BOT)
        self.assertEqual(res_fred.action, "delegate_command")

    def test_channel_context_short_circuit(self):
        res_wl_ch = classify_request("Notch", channel_name="minecraft-whitelist")
        self.assertEqual(res_wl_ch.system, TargetSystem.MINECRAFT)
        self.assertEqual(res_wl_ch.action, "whitelist_add")

        res_con_ch = classify_request("op Avinash893", channel_name="server-console")
        self.assertEqual(res_con_ch.system, TargetSystem.MINECRAFT)
        self.assertEqual(res_con_ch.action, "mc_console_command")


class TestBotOrchestrator(unittest.TestCase):
    def setUp(self):
        self.test_catalog_path = os.path.join(os.path.dirname(__file__), "test_catalog.json")
        self.orch = BotOrchestrator(catalog_path=self.test_catalog_path)

    def tearDown(self):
        if os.path.exists(self.test_catalog_path):
            os.remove(self.test_catalog_path)

    def test_preset_loading_and_inter_bot_context(self):
        self.orch.bots["111222333"] = {
            "id": 111222333,
            "name": "Dyno",
            "category": "Moderation",
            "prefix": ["?"],
            "skills": ["?warn", "?mute", "?slowmode"],
            "description": "Dyno moderation bot"
        }
        self.orch.bots["444555666"] = {
            "id": 444555666,
            "name": "FredBoat",
            "category": "Music",
            "prefix": [";;"],
            "skills": [";;play", ";;skip"],
            "description": "FredBoat music player"
        }
        self.orch.save()

        # Check reload
        new_orch = BotOrchestrator(catalog_path=self.test_catalog_path)
        self.assertIn("111222333", new_orch.bots)
        self.assertIn("444555666", new_orch.bots)

        context_str = new_orch.format_inter_bot_context()
        self.assertIn("Dyno", context_str)
        self.assertIn("FredBoat", context_str)
        self.assertIn("BOT_COMMAND:", context_str)


class TestSelfReflectionEngine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_telemetry_path = os.path.join(os.path.dirname(__file__), "test_telemetry.json")
        self.test_report_path = os.path.join(os.path.dirname(__file__), "test_audit_report.md")
        self.telemetry = TaskTelemetryLogger(file_path=self.test_telemetry_path)
        self.engine = SelfReflectionEngine(
            telemetry=self.telemetry,
            report_md_path=self.test_report_path
        )

    async def asyncTearDown(self):
        if os.path.exists(self.test_telemetry_path):
            os.remove(self.test_telemetry_path)
        if os.path.exists(self.test_report_path):
            os.remove(self.test_report_path)

    async def test_telemetry_recording_and_audit(self):
        # Log 4 tasks: 3 success, 1 failure
        self.telemetry.log_task("ban <@123>", "AdminUser", 12345, "staff-chat", 999, "DISCORD", "discord_ban", True, "User banned from Discord")
        self.telemetry.log_task("whitelist me Alex", "Player1", 67890, "whitelist", 888, "MINECRAFT", "whitelist_add", True, "Alex whitelisted")
        self.telemetry.log_task("purge 10", "ModUser", 11223, "general", 777, "DISCORD", "discord_purge", True, "Purged 10 messages")
        self.telemetry.log_task("tell dyno to ban", "ModUser", 11223, "general", 777, "INTER_BOT", "delegate_command", False, error_message="Bot not found")

        recent_tasks = self.telemetry.get_recent_tasks(count=10)
        self.assertEqual(len(recent_tasks), 4)

        # Run audit cycle
        dummy_llm = lambda p: "AI reflection test: Ensure bot names are validated before delegating commands."
        audit_res = await self.engine.execute_audit_cycle(
            prompt_mgr=None,
            rule_mgr=None,
            llm_reflection_fn=dummy_llm
        )

        self.assertEqual(audit_res["total_tasks"], 4)
        self.assertEqual(audit_res["success_count"], 3)
        self.assertEqual(audit_res["fail_count"], 1)
        self.assertEqual(audit_res["success_rate"], 75.0)
        self.assertTrue(os.path.exists(self.test_report_path))
        with open(self.test_report_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Tillu 5x Daily Self-Audit Report", content)
            self.assertIn("75.0%", content)


if __name__ == "__main__":
    unittest.main()
