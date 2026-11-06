import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meme_engine import meme_engine, MEME_CATALOG, BANNED_REPETITIVE_STARTERS

class TestMemeEngine(unittest.TestCase):
    def test_total_memes_exceeds_100(self):
        count = meme_engine.get_total_count()
        self.assertGreaterEqual(count, 100, f"Expected at least 100 memes, got {count}")

    def test_categories_presence(self):
        cats = meme_engine.get_category_counts()
        expected = ["sarcastic", "funny", "gaming", "sad_sarcastic", "savage", "wholesome"]
        for exp in expected:
            self.assertIn(exp, cats, f"Missing category: {exp}")
            self.assertGreaterEqual(cats[exp], 10, f"Category {exp} has too few memes: {cats[exp]}")

    def test_anti_repetition_openers(self):
        openers = [meme_engine.get_fresh_opener() for _ in range(10)]
        for banned in BANNED_REPETITIVE_STARTERS:
            for op in openers:
                self.assertNotIn(banned, op.lower())

    def test_prompt_injection(self):
        inj = meme_engine.get_prompt_injection("sarcastic", "Are you a noob?")
        self.assertIn("ANTI-REPETITION", inj)
        self.assertIn("FORBIDDEN OVERUSED PHRASES", inj)
        self.assertIn("MEME INSPIRATION", inj)

    def test_fallback_variety(self):
        fallbacks = [meme_engine.get_fallback_meme_response("minecraft_deleted") for _ in range(5)]
        # Ensure not all 5 are identical
        self.assertGreater(len(set(fallbacks)), 1)

if __name__ == "__main__":
    unittest.main()
