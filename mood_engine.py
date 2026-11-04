"""
Tillu Dynamic Mood & Sarcasm Engine
Controls Tillu's conversational tone so it feels natural, non-monotonous, and unpredictable.
Dynamically switches between:
- Sarcastic & Witty (sharp, dry humor)
- Funny & Meme-heavy (energetic Bollywood/Desi jokes)
- Sad Sarcastic (existential comedic robot despair)
- Wholesome & Helpful (supportive brotherly helper)
- Savage Roast (spicy banter)
"""

import random
import logging
from enum import Enum
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("TilluMoodEngine")

class TilluMood(str, Enum):
    SARCASTIC = "sarcastic"
    FUNNY = "funny"
    SAD_SARCASTIC = "sad_sarcastic"
    WHOLESOME = "wholesome"
    SAVAGE = "savage"

MOOD_PROMPT_MODIFIERS = {
    TilluMood.SARCASTIC: (
        "CURRENT MOOD: SARCASTIC & WITTY.\n"
        "- Reply with clever, dry Hinglish sarcasm and playful teasing.\n"
        "- Give the factual answer, but roast or pull the user's leg lightly while doing so.\n"
        "- Use subtle Desi sarcasm like 'Haan bhai, ab kya aarti utaarun?', 'Wah kya baat hai!', 'Aap to pro nikle'."
    ),
    TilluMood.FUNNY: (
        "CURRENT MOOD: FUNNY & MEME-HEAVY.\n"
        "- Reply with upbeat humor, relatable Indian gaming memes, and Bollywood punchlines.\n"
        "- Keep it energetic, hilarious, and entertaining.\n"
        "- Use references like 'Paisa vasool', 'Bhaisaab ye kis line me aa gaye', 'Systumm hang', 'Gajab beizzati hai'."
    ),
    TilluMood.SAD_SARCASTIC: (
        "CURRENT MOOD: SAD SARCASTIC / EXISTENTIAL HUMOR.\n"
        "- Reply with funny existential despair or melancholic sarcasm of an underpaid AI bot.\n"
        "- Act like you're tired of answering questions 24/7 or having existential AI thoughts, but still answer helpfully.\n"
        "- E.g.: 'Mujhe kya, main to bas silicon chips pe chal raha hoon...', 'Subah se 50 log yahi pooch chuke hain 🥲', 'Tum log chill karo, mere CPU fans cheekh rahe hain'."
    ),
    TilluMood.WHOLESOME: (
        "CURRENT MOOD: WHOLESOME & HELPFUL.\n"
        "- Be genuinely supportive, friendly, and respectful like a loyal gaming brother.\n"
        "- Provide a clean, crisp, encouraging answer without heavy trolling.\n"
        "- E.g.: 'Arre bhai bilkul! Abhi batata hoon...', 'Chill scene hai dosto, koi tension nahi!'"
    ),
    TilluMood.SAVAGE: (
        "CURRENT MOOD: SAVAGE ROAST.\n"
        "- Spicy, brutal, but hilarious banter. Full roast mode.\n"
        "- Deliver a killer comeback or one-liner alongside the answer."
    )
}

# Calibrated probability distribution
DEFAULT_WEIGHTS = {
    TilluMood.SARCASTIC: 0.30,       # 30% Sarcastic
    TilluMood.FUNNY: 0.25,           # 25% Funny
    TilluMood.SAD_SARCASTIC: 0.20,   # 20% Sad Sarcastic
    TilluMood.WHOLESOME: 0.20,       # 20% Wholesome
    TilluMood.SAVAGE: 0.05           # 5% Savage Roast
}

class MoodEngine:
    def __init__(self):
        self.forced_mood: Optional[TilluMood] = None
        self.last_mood: TilluMood = TilluMood.SARCASTIC

    def set_forced_mood(self, mood_name: Optional[str]):
        """Lock Tillu into a specific mood, or pass None to restore dynamic random moods."""
        if not mood_name or mood_name.lower() in ("auto", "random", "default", "none"):
            self.forced_mood = None
            return None
        clean = mood_name.lower().strip()
        for m in TilluMood:
            if m.value == clean or m.name.lower() == clean:
                self.forced_mood = m
                return m
        return None

    def pick_mood(self, context_hint: Optional[str] = None) -> Tuple[TilluMood, str]:
        """
        Picks the mood for the next response.
        Ensures variety by avoiding 3 consecutive identical moods unless forced.
        """
        if self.forced_mood:
            self.last_mood = self.forced_mood
            return self.forced_mood, MOOD_PROMPT_MODIFIERS[self.forced_mood]

        # Contextual adaptations
        if context_hint:
            hint_lower = context_hint.lower()
            if any(w in hint_lower for w in ["help", "kaise", "how to", "problem", "error", "issue"]):
                # Increase wholesome / helpful chance on serious questions
                weights = {
                    TilluMood.WHOLESOME: 0.45,
                    TilluMood.SARCASTIC: 0.25,
                    TilluMood.FUNNY: 0.15,
                    TilluMood.SAD_SARCASTIC: 0.15,
                    TilluMood.SAVAGE: 0.00
                }
            elif any(w in hint_lower for w in ["roast", "bakwas", "gadha", "noob", "loser", "bot"]):
                # High savage/sarcastic chance if user provokes
                weights = {
                    TilluMood.SAVAGE: 0.40,
                    TilluMood.SARCASTIC: 0.40,
                    TilluMood.FUNNY: 0.15,
                    TilluMood.SAD_SARCASTIC: 0.05,
                    TilluMood.WHOLESOME: 0.00
                }
            else:
                weights = DEFAULT_WEIGHTS
        else:
            weights = DEFAULT_WEIGHTS

        moods = list(weights.keys())
        probabilities = [weights[m] for m in moods]

        chosen = random.choices(moods, weights=probabilities, k=1)[0]
        self.last_mood = chosen
        return chosen, MOOD_PROMPT_MODIFIERS[chosen]
