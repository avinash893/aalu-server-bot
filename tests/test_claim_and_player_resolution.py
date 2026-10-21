"""
Unit tests for Minecraft Player Resolution & GriefPrevention Land Claims
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from context_classifier import classify_request, TargetSystem
import minecraft_player_resolver as mc_resolver


class TestClaimAndPlayerResolution(unittest.TestCase):
    def test_fuzzy_player_resolution(self):
        cands = [".UNIQUE_UMAR_114", ".VAMPIRE674066", ".NAKEEBGAM", "AALU_CHIPAS", "Avinash893"]
        
        res1, conf1 = mc_resolver.resolve_closest_player("unique umar", extra_candidates=cands)
        self.assertEqual(res1, ".UNIQUE_UMAR_114")
        self.assertGreaterEqual(conf1, 0.90)

        res2, conf2 = mc_resolver.resolve_closest_player("unique umar in minecraft", extra_candidates=cands)
        self.assertEqual(res2, ".UNIQUE_UMAR_114")
        self.assertGreaterEqual(conf2, 0.90)

        res3, conf3 = mc_resolver.resolve_closest_player("vampire", extra_candidates=cands)
        self.assertEqual(res3, ".VAMPIRE674066")

        res4, conf4 = mc_resolver.resolve_closest_player("nakeeb", extra_candidates=cands)
        self.assertEqual(res4, ".NAKEEBGAM")

    def test_context_classification_claims(self):
        res1 = classify_request("Tillu give unlimited claim land to unique umar in minecraft")
        self.assertEqual(res1.system, TargetSystem.MINECRAFT)
        self.assertEqual(res1.action, "mc_claim_blocks")

        res2 = classify_request("give 5000 claim blocks to unique umar")
        self.assertEqual(res2.system, TargetSystem.MINECRAFT)
        self.assertEqual(res2.action, "mc_claim_blocks")

        res3 = classify_request("unique umar ko unlimited claim land de do")
        self.assertEqual(res3.system, TargetSystem.MINECRAFT)
        self.assertEqual(res3.action, "mc_claim_blocks")

    def test_discord_role_regex_does_not_hijack_claims(self):
        import re
        pat = r'(?:give|add|assign|de\s+do)\s+(?:role\s+<@&(\d+)>|<@&(\d+)>|role\s+["\']?([^"\'\n]+?)["\']?|["\']?([^"\'\n]+?)["\']?\s+role)\s+to\s+(.+)'
        
        # Minecraft claim query MUST NOT match
        m_claim = re.search(pat, "give unlimited claim land to unique umar in minecraft", re.IGNORECASE)
        self.assertIsNone(m_claim)

        # Discord role query MUST match
        m_role = re.search(pat, "give role VIP to @uniqueumar", re.IGNORECASE)
        self.assertIsNotNone(m_role)
        role_q = m_role.group(1) or m_role.group(2) or m_role.group(3) or m_role.group(4)
        self.assertEqual(role_q, "VIP")


if __name__ == "__main__":
    unittest.main()
