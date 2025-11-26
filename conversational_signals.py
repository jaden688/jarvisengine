from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass
class TurnSignals:
    """Lightweight per-turn signals derived from user text."""
    sentiment: float          # -1..1
    arousal: float            # 0..1
    directive: bool           # user wants brevity/precision
    confusion: float          # 0..1
    pace: float               # 0..1 (0=slow,1=fast)
    memory_density: float     # 0..1 suggested memory pressure


class SignalScorer:
    """
    Heuristic scorer for a single user message.
    Avoids external models; uses simple lexical cues + length.
    """

    POS_WORDS = {
        "great", "awesome", "love", "amazing", "thanks", "cool", "nice", "perfect",
        "good", "fantastic", "excellent", "sweet", "stoked", "hyped", "yay", "lol"
    }
    NEG_WORDS = {
        "bad", "hate", "angry", "pissed", "annoyed", "frustrated", "upset", "mad",
        "broken", "wtf", "ugh", "sucks", "terrible", "awful", "pain", "stupid"
    }
    DIRECTIVE_PHRASES = {
        "be concise", "concise please", "be brief", "briefly", "just answer", "short answer",
        "straight answer", "to the point", "get to the point", "no fluff", "skip the fluff",
        "no filler", "no bs", "no b.s.", "cut the fluff", "focus", "serious", "direct answer",
        "be direct", "keep it short", "short and direct"
    }
    CONFUSE_WORDS = {
        "confused", "lost", "stuck", "don't get", "not sure", "unclear", "huh", "what", "why"
    }

    def score(self, text: str) -> TurnSignals:
        t = text.lower()
        words = re.findall(r"[a-z']+", t)
        wlen = len(words)

        pos_hits = sum(1 for w in words if w in self.POS_WORDS)
        neg_hits = sum(1 for w in words if w in self.NEG_WORDS)
        sentiment = (pos_hits - neg_hits) / max(1, wlen)
        sentiment = max(-1.0, min(1.0, sentiment * 6.0))  # scale up, clamp

        directive = any(phrase in t for phrase in self.DIRECTIVE_PHRASES)
        confusion_hits = sum(1 for w in words if w in self.CONFUSE_WORDS) + t.count("?")
        confusion = max(0.0, min(1.0, confusion_hits / max(3, wlen)))

        # crude arousal: exclamations + uppercase + length
        exclaim = t.count("!")
        upper_hits = sum(1 for w in words if len(w) > 1 and w.isupper())
        arousal = (
            (wlen * 0.04) +                # ~0.4 at 10 words
            (0.25 if exclaim > 0 else 0.0) +
            max(0, exclaim - 1) * 0.05 +   # extra boost for multiple !
            (0.20 if upper_hits > 0 else 0.0)
        )
        arousal = max(0.0, min(1.0, arousal))

        # pace: based on brevity (shorter = faster) plus exclamations
        pace = (
            (min(wlen, 30) / 30.0) +       # 0..1 over first 30 words
            (0.10 if exclaim > 0 else 0.0)
        )
        pace = max(0.0, min(1.0, pace))

        # memory density suggestion: longer + more questions => higher
        memory_density = (
            (wlen / 35.0) +           # ~0.3 at 10 words, ~0.57 at 20
            (confusion_hits * 0.08)
        )
        memory_density = max(0.0, min(1.0, memory_density))

        return TurnSignals(
            sentiment=sentiment,
            arousal=arousal,
            directive=directive,
            confusion=confusion,
            pace=pace,
            memory_density=memory_density,
        )
