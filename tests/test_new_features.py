"""
Unit tests for Tillu's 3 major features:
1. Voice Channel AI Co-Host (voice_cohost.py)
2. Stream Prediction & Betting Economy (stream_prediction.py)
3. Viewer Leveling & Loyalty Badges (loyalty_system.py)
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path so imports work cleanly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from voice_cohost import VoiceCoHost
from stream_prediction import PredictionEconomy
from loyalty_system import LoyaltySystem, BADGE_DEFINITIONS


class TestVoiceCoHost(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cohost = VoiceCoHost()

    def test_initialization(self):
        self.assertIsInstance(self.cohost.voice_clients, dict)
        self.assertIsInstance(self.cohost.is_speaking, dict)

    @patch("voice_cohost.VoiceCoHost.speak_text", new_callable=AsyncMock)
    async def test_speak_roast(self, mock_speak):
        mock_speak.return_value = (True, "Audio played")
        mock_guild = MagicMock()
        mock_guild.id = 123456

        ok, msg, script = await self.cohost.speak_roast(mock_guild, "Rohan")
        self.assertTrue(ok)
        self.assertIn("Rohan", script)
        mock_speak.assert_awaited_once()

    @patch("voice_cohost.VoiceCoHost.speak_text", new_callable=AsyncMock)
    async def test_speak_hype(self, mock_speak):
        mock_speak.return_value = (True, "Audio played")
        mock_guild = MagicMock()
        mock_guild.id = 123456

        ok, msg, script = await self.cohost.speak_hype(mock_guild, "Aalu")
        self.assertTrue(ok)
        self.assertIn("Aalu", script)
        mock_speak.assert_awaited_once()

    async def test_leave_channel_when_not_connected(self):
        mock_guild = MagicMock()
        mock_guild.id = 999999
        mock_guild.voice_client = None

        ok, msg = await self.cohost.leave_channel(mock_guild)
        self.assertFalse(ok)
        self.assertIn("nahi hoon", msg)


class TestPredictionEconomy(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.economy = PredictionEconomy(data_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_wallet_initialization_and_daily(self):
        w = self.economy.get_wallet(1001, "PlayerOne")
        self.assertEqual(w["coins"], 500)
        self.assertEqual(w["name"], "PlayerOne")

        # Claim daily bonus
        ok, msg, new_bal = self.economy.claim_daily(1001, "PlayerOne")
        self.assertTrue(ok)
        self.assertEqual(new_bal, 750)

        # Repeated daily within 24h should fail
        ok2, msg2, bal2 = self.economy.claim_daily(1001, "PlayerOne")
        self.assertFalse(ok2)
        self.assertEqual(bal2, 750)

    def test_prediction_creation_and_betting(self):
        pred = self.economy.create_prediction(
            guild_id=100,
            question="Will Aalu win the 1v3 clutch?",
            option_a="YES",
            option_b="NO",
            duration_minutes=5,
            creator_name="Aalu"
        )
        pred_id = pred["id"]
        self.assertIn(pred_id, self.economy.predictions)
        self.assertEqual(pred["status"], "OPEN")

        # Place bet for User 1 on YES (Option A)
        ok, msg, res = self.economy.place_bet(1001, pred_id, "A", 200, "User1")
        self.assertTrue(ok)
        self.assertEqual(res["remaining_balance"], 300)

        # Place bet for User 2 on NO (Option B)
        ok, msg, res = self.economy.place_bet(1002, pred_id, "B", 100, "User2")
        self.assertTrue(ok)
        self.assertEqual(res["remaining_balance"], 400)

        # Bet beyond balance should fail
        ok_fail, msg_fail, _ = self.economy.place_bet(1001, pred_id, "A", 99999, "User1")
        self.assertFalse(ok_fail)
        self.assertIn("bet nahi kar sakte", msg_fail)

    def test_prediction_resolution_and_payout(self):
        pred = self.economy.create_prediction(
            guild_id=100,
            question="Next game victory?",
            option_a="Win",
            option_b="Loss",
            duration_minutes=10
        )
        p_id = pred["id"]

        # User 1 bets 100 on A
        self.economy.place_bet(1001, p_id, "A", 100, "User1")
        # User 2 bets 100 on B
        self.economy.place_bet(1002, p_id, "B", 100, "User2")

        # Total pool = 200. Winner = A. User 1 gets 200 total payout (100 net profit).
        ok, msg, res = self.economy.resolve_prediction(p_id, "A")
        self.assertTrue(ok)
        self.assertEqual(res["total_pool"], 200)
        self.assertEqual(res["payouts_count"], 1)

        w1 = self.economy.get_wallet(1001)
        # Starting 500 - 100 + 200 payout = 600
        self.assertEqual(w1["coins"], 600)
        self.assertEqual(w1["total_won"], 100)

    def test_leaderboard(self):
        self.economy.get_wallet(1, "Alpha")
        self.economy.add_coins(1, 1000)
        self.economy.get_wallet(2, "Beta")
        self.economy.add_coins(2, 500)

        lb = self.economy.get_leaderboard(limit=5)
        self.assertGreaterEqual(len(lb), 2)
        self.assertEqual(lb[0][0], "Alpha")
        self.assertEqual(lb[1][0], "Beta")


class TestLoyaltySystem(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.loyalty = LoyaltySystem(data_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_xp_and_level_math(self):
        # Formula: int(0.1 * sqrt(xp)) + 1
        self.assertEqual(self.loyalty.xp_to_level(0), 1)
        self.assertEqual(self.loyalty.xp_to_level(100), 2)
        self.assertEqual(self.loyalty.xp_to_level(400), 3)
        self.assertEqual(self.loyalty.xp_to_level(8100), 10)

    def test_add_message_and_voice_xp(self):
        u_id = 2001
        # First message awards XP
        lvl_up, lvl, xp = self.loyalty.add_message_xp(u_id, "ViewerSam")
        self.assertEqual(xp, 20)

        # Voice XP awards 15 XP/min
        lvl_up, new_lvl = self.loyalty.add_voice_xp(u_id, minutes=10, user_name="ViewerSam")
        u = self.loyalty.get_user_data(u_id)
        # 20 + (10 * 15) = 170 XP
        self.assertEqual(u["xp"], 170)
        self.assertEqual(u["voice_minutes"], 10)

    def test_badge_unlocks(self):
        u_id = 2002
        u = self.loyalty.get_user_data(u_id, "GamerPro")
        u["messages"] = 150
        u["xp"] = 10000  # Level 11 -> Veteran unlocked
        self.loyalty._check_badges(u, u_id)

        self.assertIn("chatterbox", u["badges"])
        self.assertIn("veteran", u["badges"])

    def test_format_rank_card(self):
        u_id = 2003
        self.loyalty.add_voice_xp(u_id, minutes=75, user_name="StreamFan")
        card = self.loyalty.format_rank_card(u_id, "StreamFan")

        self.assertEqual(card["name"], "StreamFan")
        self.assertIn("█", card["progress_bar"])
        self.assertGreater(card["voice_hours"], 1.0)
        self.assertIn("title", card)

    def test_top_viewers(self):
        self.loyalty.add_voice_xp(1, minutes=100, user_name="UserTop1")
        self.loyalty.add_voice_xp(2, minutes=50, user_name="UserTop2")

        top = self.loyalty.get_top_viewers(limit=5)
        self.assertGreaterEqual(len(top), 2)
        self.assertEqual(top[0][0], "UserTop1")
        self.assertEqual(top[1][0], "UserTop2")


if __name__ == "__main__":
    unittest.main()
