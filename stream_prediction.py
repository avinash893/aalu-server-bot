"""
Tillu Stream Prediction & Betting Economy Engine
Allows viewers and community members to bet virtual Tillu Coins (🪙) on stream clutch moments,
match predictions, and gaming outcomes with real-time payout distribution.
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("TilluPredictionEconomy")

DEFAULT_STARTING_BALANCE = 500
DAILY_BONUS = 250

class PredictionEconomy:
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.economy_file = os.path.join(self.data_dir, "economy.json")
        self.predictions_file = os.path.join(self.data_dir, "predictions.json")
        self.wallets: Dict[str, Dict[str, Any]] = {}
        self.predictions: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self):
        if os.path.exists(self.economy_file):
            try:
                with open(self.economy_file, "r", encoding="utf-8") as f:
                    self.wallets = json.load(f)
            except Exception as e:
                logger.error(f"[Economy Load Error] {e}")

        if os.path.exists(self.predictions_file):
            try:
                with open(self.predictions_file, "r", encoding="utf-8") as f:
                    self.predictions = json.load(f)
            except Exception as e:
                logger.error(f"[Predictions Load Error] {e}")

    def save(self):
        try:
            tmp_eco = self.economy_file + ".tmp"
            with open(tmp_eco, "w", encoding="utf-8") as f:
                json.dump(self.wallets, f, indent=2, ensure_ascii=False)
            os.replace(tmp_eco, self.economy_file)

            tmp_pred = self.predictions_file + ".tmp"
            with open(tmp_pred, "w", encoding="utf-8") as f:
                json.dump(self.predictions, f, indent=2, ensure_ascii=False)
            os.replace(tmp_pred, self.predictions_file)
        except Exception as e:
            logger.error(f"[Economy Save Error] {e}")

    # ── WALLET & BALANCE ─────────────────────────────────────────────────────
    def get_wallet(self, user_id: int, user_name: str = "") -> Dict[str, Any]:
        u_str = str(user_id)
        if u_str not in self.wallets:
            self.wallets[u_str] = {
                "name": user_name or f"User_{user_id}",
                "coins": DEFAULT_STARTING_BALANCE,
                "last_daily": 0,
                "total_won": 0,
                "total_lost": 0,
                "bets_placed": 0
            }
            self.save()
        elif user_name:
            self.wallets[u_str]["name"] = user_name
        return self.wallets[u_str]

    def get_balance(self, user_id: int, user_name: str = "") -> int:
        return self.get_wallet(user_id, user_name).get("coins", 0)

    def add_coins(self, user_id: int, amount: int, user_name: str = "") -> int:
        w = self.get_wallet(user_id, user_name)
        w["coins"] = max(0, w.get("coins", 0) + amount)
        self.save()
        return w["coins"]

    def claim_daily(self, user_id: int, user_name: str = "") -> Tuple[bool, str, int]:
        w = self.get_wallet(user_id, user_name)
        now = time.time()
        last = w.get("last_daily", 0)
        cooldown = 24 * 3600

        if now - last < cooldown:
            remaining = int(cooldown - (now - last))
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            return False, f"Aapne pehle hi daily reward claim kiya hai! Agla reward **{hours}h {mins}m** me milega.", w["coins"]

        w["last_daily"] = now
        w["coins"] = w.get("coins", 0) + DAILY_BONUS
        self.save()
        return True, f"🎉 **+{DAILY_BONUS} Tillu Coins** mil gaye! Current balance: **{w['coins']} 🪙**", w["coins"]

    # ── PREDICTIONS / BETTING ────────────────────────────────────────────────
    def create_prediction(
        self,
        guild_id: int,
        question: str,
        option_a: str,
        option_b: str,
        duration_minutes: int = 5,
        creator_id: int = 0,
        creator_name: str = ""
    ) -> Dict[str, Any]:
        pred_id = uuid.uuid4().hex[:6].upper()
        now = time.time()
        ends_at = now + (duration_minutes * 60)

        pred = {
            "id": pred_id,
            "guild_id": guild_id,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "question": question,
            "option_a": option_a,
            "option_b": option_b,
            "created_at": now,
            "ends_at": ends_at,
            "status": "OPEN",  # OPEN, CLOSED, RESOLVED, CANCELLED
            "winner": None,
            "pool_a": 0,
            "pool_b": 0,
            "bets_a": {},  # user_id -> amount
            "bets_b": {}   # user_id -> amount
        }
        self.predictions[pred_id] = pred
        self.save()
        return pred

    def place_bet(
        self,
        user_id: int,
        prediction_id: str,
        option_choice: str,
        amount: int,
        user_name: str = ""
    ) -> Tuple[bool, str, Dict[str, Any]]:
        pred_id_str = str(prediction_id).upper()
        pred = self.predictions.get(pred_id_str)
        if not pred:
            return False, f"Prediction ID `{prediction_id}` nahi mili!", {}

        if pred["status"] != "OPEN":
            return False, f"Ye prediction abhi **{pred['status']}** hai, naye bets band hain!", {}

        if time.time() > pred["ends_at"]:
            pred["status"] = "CLOSED"
            self.save()
            return False, "Is prediction ka betting time khatam ho chuka hai!", {}

        if amount <= 0:
            return False, "Bet amount 1 coin se zyada hona chahiye!", {}

        u_str = str(user_id)
        w = self.get_wallet(user_id, user_name)
        if w["coins"] < amount:
            return False, f"Aapke paas sirf **{w['coins']} 🪙** hain, **{amount} 🪙** bet nahi kar sakte!", {}

        choice = str(option_choice).lower().strip()
        if choice in ("a", "option_a", "1", pred["option_a"].lower()):
            chosen = "A"
            opt_title = pred["option_a"]
        elif choice in ("b", "option_b", "2", pred["option_b"].lower()):
            chosen = "B"
            opt_title = pred["option_b"]
        else:
            return False, f"Invalid option! Chunein: `A` ({pred['option_a']}) ya `B` ({pred['option_b']})", {}

        # Deduct coins
        w["coins"] -= amount
        w["total_bet"] = w.get("total_bet", 0) + amount
        w["bets_placed"] = w.get("bets_placed", 0) + 1

        if chosen == "A":
            pred["pool_a"] += amount
            pred["bets_a"][u_str] = pred["bets_a"].get(u_str, 0) + amount
        else:
            pred["pool_b"] += amount
            pred["bets_b"][u_str] = pred["bets_b"].get(u_str, 0) + amount

        self.save()
        res = {
            "prediction_id": pred["id"],
            "question": pred["question"],
            "chosen_option": chosen,
            "chosen_label": opt_title,
            "amount": amount,
            "remaining_balance": w["coins"]
        }
        return True, f"✅ Bet placed! **{amount:,} 🪙** on **[{chosen}] {opt_title}**! (Balance: {w['coins']:,} 🪙)", res

    def resolve_prediction(self, pred_id: str, winning_option: str) -> Tuple[bool, str, Dict[str, Any]]:
        pred = self.predictions.get(str(pred_id).upper())
        if not pred:
            return False, f"Prediction ID `{pred_id}` nahi mili!", {}

        if pred["status"] == "RESOLVED":
            return False, "Ye prediction pehle hi resolve ho chuki hai!", {}

        choice = winning_option.lower().strip()
        if choice in ("a", "option_a", "1", pred["option_a"].lower()):
            winner = "A"
            win_title = pred["option_a"]
            winning_bets = pred["bets_a"]
            winning_pool = pred["pool_a"]
            total_pool = pred["pool_a"] + pred["pool_b"]
        elif choice in ("b", "option_b", "2", pred["option_b"].lower()):
            winner = "B"
            win_title = pred["option_b"]
            winning_bets = pred["bets_b"]
            winning_pool = pred["pool_b"]
            total_pool = pred["pool_a"] + pred["pool_b"]
        else:
            return False, f"Invalid winner! `A` ya `B` likhein.", {}

        pred["status"] = "RESOLVED"
        pred["winner"] = winner

        payouts: Dict[str, int] = {}
        if winning_pool > 0:
            for u_str, bet_amt in winning_bets.items():
                # Proportional share of the total pool
                share = (bet_amt / winning_pool) * total_pool
                payout = int(share)
                payouts[u_str] = payout
                if u_str in self.wallets:
                    self.wallets[u_str]["coins"] = self.wallets[u_str].get("coins", 0) + payout
                    self.wallets[u_str]["total_won"] = self.wallets[u_str].get("total_won", 0) + (payout - bet_amt)
        else:
            # If no one bet on the winner, refund everyone
            for u_str, bet_amt in pred["bets_a"].items():
                if u_str in self.wallets:
                    self.wallets[u_str]["coins"] += bet_amt
            for u_str, bet_amt in pred["bets_b"].items():
                if u_str in self.wallets:
                    self.wallets[u_str]["coins"] += bet_amt

        self.save()
        return True, f"🏆 Prediction resolved! Winner: **[{winner}] {win_title}**! Total payout: **{total_pool} 🪙**", {
            "winner": winner,
            "win_title": win_title,
            "total_pool": total_pool,
            "payouts_count": len(payouts),
            "payouts": payouts
        }

    def get_active_predictions(self, guild_id: int) -> List[Dict[str, Any]]:
        now = time.time()
        active = []
        for p in self.predictions.values():
            if p.get("guild_id") == guild_id and p.get("status") in ("OPEN", "CLOSED"):
                if p["status"] == "OPEN" and now > p["ends_at"]:
                    p["status"] = "CLOSED"
                active.append(p)
        return active

    def get_leaderboard(self, limit: int = 10) -> List[Tuple[str, int, int]]:
        sorted_users = sorted(
            self.wallets.items(),
            key=lambda item: item[1].get("coins", 0),
            reverse=True
        )
        result = []
        for u_id, w in sorted_users[:limit]:
            result.append((w.get("name", f"User_{u_id}"), w.get("coins", 0), w.get("total_won", 0)))
        return result

# Global Singleton
prediction_economy = PredictionEconomy()
