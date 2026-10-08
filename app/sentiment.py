"""Lightweight finance-tuned sentiment scoring and ticker extraction.

A lexicon approach keeps the app dependency-free and fast. It understands
common market and social-media slang ("to the moon", "bagholder", rocket emoji).
"""
import math
import re

POSITIVE = {
    "beat": 2, "beats": 2, "surge": 2, "surges": 2, "soar": 2, "soars": 2, "rally": 2, "rallies": 2,
    "jump": 1.5, "jumps": 1.5, "gain": 1, "gains": 1, "rise": 1, "rises": 1, "up": 0.5, "higher": 1,
    "upgrade": 2.5, "upgraded": 2.5, "outperform": 2, "buy": 1, "bullish": 2.5, "bull": 1.5,
    "record": 1.5, "strong": 1.5, "growth": 1, "profit": 1, "profitable": 1.5, "boost": 1.5,
    "breakout": 2, "approval": 2, "approved": 2, "partnership": 1, "raises": 1, "raised": 1,
    "moon": 2, "mooning": 2, "calls": 1, "rocket": 2, "squeeze": 1.5, "undervalued": 1.5,
    "tendies": 1.5, "long": 0.5, "dividend": 0.5, "exceed": 1.5, "exceeds": 1.5, "optimistic": 1.5,
}
NEGATIVE = {
    "miss": 2, "misses": 2, "missed": 2, "plunge": 2.5, "plunges": 2.5, "crash": 2.5, "crashes": 2.5,
    "fall": 1, "falls": 1, "drop": 1.5, "drops": 1.5, "down": 0.5, "lower": 1, "slump": 2, "sink": 1.5,
    "downgrade": 2.5, "downgraded": 2.5, "underperform": 2, "sell": 1, "bearish": 2.5, "bear": 1.5,
    "weak": 1.5, "loss": 1.5, "losses": 1.5, "lawsuit": 2, "probe": 1.5, "investigation": 1.5,
    "recall": 1.5, "layoffs": 1.5, "cut": 1, "cuts": 1, "warning": 1.5, "warns": 1.5, "fraud": 3,
    "bankruptcy": 3, "puts": 1, "bagholder": 2, "bagholding": 2, "overvalued": 1.5, "dump": 2,
    "rugpull": 2.5, "short": 0.5, "fear": 1.5, "recession": 1.5, "tariff": 1, "tariffs": 1,
    "delay": 1, "delayed": 1, "halt": 1.5, "halted": 1.5, "pessimistic": 1.5,
}
EMOJI = {"🚀": 1.5, "🌙": 1, "💎": 1, "📈": 1.5, "🐂": 1.5, "📉": -1.5, "🐻": -1.5, "💀": -1, "🩸": -1.5}
NEGATORS = {"not", "no", "never", "isn't", "wasn't", "don't", "doesn't", "didn't", "won't", "cant", "can't"}

_WORD = re.compile(r"[a-z']+")


def score(text: str) -> float:
    """Return sentiment in [-1, 1]."""
    words = _WORD.findall(text.lower())
    total = 0.0
    for i, w in enumerate(words):
        v = POSITIVE.get(w, 0) - NEGATIVE.get(w, 0)
        if v and any(p in NEGATORS for p in words[max(0, i - 3):i]):
            v = -v
        total += v
    total += sum(text.count(e) * v for e, v in EMOJI.items())
    # Squash so a handful of strong words saturates near +/-1.
    return math.tanh(total / 4)


# Words that look like tickers in all-caps chatter but almost never are.
_NOT_TICKERS = {
    "A", "I", "AM", "AN", "AND", "ARE", "AS", "AT", "BE", "BY", "CEO", "CFO", "DD", "EPS", "ETF", "FOR",
    "FYI", "GDP", "IMO", "IN", "IPO", "IS", "IT", "ITM", "LOL", "OF", "ON", "OR", "OTM", "PE", "SEC",
    "SO", "THE", "TO", "USA", "US", "USD", "WSB", "YOLO", "ATH", "FOMO", "EOD", "AI", "EV", "FED",
    "CPI", "IRS", "ALL", "NEW", "NOW", "TLDR", "EDIT", "OP", "GO", "UP", "DOWN", "BUY", "SELL", "HOLD",
    "PUT", "PUTS", "CALL", "CALLS", "MY", "ME", "WE", "YOU", "HE", "SHE", "NOT", "JUST", "WHAT", "WHY",
}
_CASHTAG = re.compile(r"\$([A-Za-z]{1,5})\b")
_CAPS = re.compile(r"\b([A-Z]{2,5})\b")


def extract_tickers(text: str, known: set[str] | None = None) -> set[str]:
    """Find tickers in free text. $CASHTAGS always count; bare CAPS words only if in `known`."""
    found = {m.upper() for m in _CASHTAG.findall(text)}
    if known:
        found |= {m for m in _CAPS.findall(text) if m in known}
    return found - _NOT_TICKERS
