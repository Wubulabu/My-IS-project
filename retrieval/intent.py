"""Intent-aware result adjustments shared by the web layer.

These boosts are deliberately narrow. They correct cases where broad semantic
matches, such as love-related scenes, outrank the literal shape the user asked
for, such as a heart emoji.
"""

from __future__ import annotations

import re
from typing import Iterable


def canonical_char(char: str) -> str:
    return (char or "").replace("\ufe0f", "").replace("\ufe0e", "")


HEART_INTENT_RE = re.compile(
    r"(\bheart(?:s)?\b|\bred heart\b|\blove heart\b|爱心|红心|心形|心型)",
    re.IGNORECASE,
)

PRIMARY_HEART_CHARS = {
    canonical_char(c)
    for c in [
        "❤",
        "❤️",
        "🩷",
        "🧡",
        "💛",
        "💚",
        "💙",
        "🩵",
        "💜",
        "🖤",
        "🩶",
        "🤍",
        "🤎",
        "💓",
        "💔",
        "💕",
        "💖",
        "💗",
        "💘",
        "💝",
        "💞",
        "💟",
        "❣",
        "❣️",
        "❤‍🔥",
        "❤️‍🔥",
        "❤‍🩹",
        "❤️‍🩹",
        "♥",
        "♥️",
    ]
}

RELATED_HEART_CHARS = {
    canonical_char(c)
    for c in [
        "😍",
        "😘",
        "🥰",
        "😻",
        "💑",
        "💏",
        "🫶",
    ]
}

NON_LITERAL_LOVE_TERMS = (
    "love letter",
    "love hotel",
    "love-you gesture",
    "love you gesture",
)

PRIMARY_HEART_NAMES = {
    "red heart",
    "pink heart",
    "orange heart",
    "yellow heart",
    "green heart",
    "blue heart",
    "light blue heart",
    "purple heart",
    "black heart",
    "grey heart",
    "gray heart",
    "white heart",
    "brown heart",
    "beating heart",
    "broken heart",
    "two hearts",
    "sparkling heart",
    "growing heart",
    "heart with arrow",
    "heart with ribbon",
    "revolving hearts",
    "heart decoration",
    "heart exclamation",
    "heart on fire",
    "mending heart",
    "heart suit",
}


def is_heart_intent(query: str) -> bool:
    q = (query or "").strip().lower()
    return bool(q and HEART_INTENT_RE.search(q))


def _lower_values(values: Iterable[object]) -> list[str]:
    return [str(value).strip().lower() for value in values if str(value).strip()]


def heart_relevance_tier(record: dict) -> float:
    """Return a task-specific tier for literal heart intent.

    3.0: literal heart symbols and decorated hearts.
    1.6: related heart-bearing faces/couples/hands.
    0.0: love-related but non-heart literals, such as love letter or hotel.
    """

    char_key = canonical_char(record.get("char", ""))
    en = (record.get("en") or "").lower().strip()
    zh = (record.get("zh") or "").lower().strip()
    keywords = _lower_values(record.get("keywords", []))
    aliases = _lower_values(record.get("aliases", []))
    text = " ".join([en, zh, " ".join(keywords), " ".join(aliases)])

    if en == "red heart":
        return 3.5

    if char_key in PRIMARY_HEART_CHARS or en in PRIMARY_HEART_NAMES:
        return 3.0

    if any(term in en for term in NON_LITERAL_LOVE_TERMS):
        return 0.0

    if char_key in RELATED_HEART_CHARS:
        return 1.6

    if "couple with heart" in en or "heart hands" in en:
        return 1.6
    if "heart-eyes" in en or "with hearts" in en:
        return 1.4
    if "anatomical heart" in en:
        return 0.8
    if "爱心" in keywords or "红心" in keywords or "心形" in text:
        return 1.4
    if "heart" in keywords or "heart" in aliases:
        return 0.8
    return 0.0


def apply_intent_boosts(results: list[dict], query: str) -> list[dict]:
    """Return copied, reranked results for known high-confidence intents."""

    if not is_heart_intent(query):
        return results

    boosted: list[dict] = []
    for item in results:
        out = item.copy()
        base = float(out.get("score", 0.0) or 0.0)
        tier = heart_relevance_tier(out)
        out["intent_score"] = tier
        if tier > 0:
            out["semantic_category"] = "Hearts & Love"
            out["score"] = base * (1.0 + 0.35 * tier) + 0.04 * tier
        elif any(term in (out.get("en") or "").lower() for term in NON_LITERAL_LOVE_TERMS):
            out["score"] = base * 0.72
        boosted.append(out)

    boosted.sort(key=lambda row: (-float(row.get("score", 0.0) or 0.0), -float(row.get("intent_score", 0.0) or 0.0)))
    for rank, item in enumerate(boosted, 1):
        item["rank"] = rank
    return boosted
