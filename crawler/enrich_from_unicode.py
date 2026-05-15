#!/usr/bin/env python3
"""
Enhanced emoji data crawler using emoji-data-python library
Adds category and keyword data to existing emoji dataset
"""

import json
import os
import sys
import unicodedata
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import emoji_data_python as edp

# Build lookup dictionaries for fast access
EMOJI_BY_CHAR = {e.char: e for e in edp.emoji_data}
EMOJI_BY_NAME = {}
for e in edp.emoji_data:
    name_lower = e.name.lower()
    if name_lower not in EMOJI_BY_NAME:
        EMOJI_BY_NAME[name_lower] = []
    EMOJI_BY_NAME[name_lower].append(e)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "enriched_data.json")


def find_emoji_data(char, name):
    """
    Find emoji data from emoji-data-python library.
    Try multiple strategies:
    1. Direct character lookup
    2. Name lookup
    3. Unicode name lookup (for variants)
    """
    # Strategy 1: Direct character lookup
    if char in EMOJI_BY_CHAR:
        return EMOJI_BY_CHAR[char]

    # Strategy 2: English name lookup
    name_lower = name.lower()
    if name_lower in EMOJI_BY_NAME:
        matches = EMOJI_BY_NAME[name_lower]
        return matches[0]  # Return first match

    # Strategy 3: Unicode name lookup
    try:
        unicode_name = unicodedata.name(char, "").lower()
        if unicode_name and unicode_name in EMOJI_BY_NAME:
            matches = EMOJI_BY_NAME[unicode_name]
            return matches[0]
    except:
        pass

    # Strategy 4: Partial name matching
    for db_name, emojis in EMOJI_BY_NAME.items():
        if name_lower in db_name or db_name in name_lower:
            return emojis[0]

    return None


def enrich_emoji(record):
    """
    Enrich a single emoji record with category and keywords.

    Returns dict with:
    - char: emoji character
    - category: Unicode consortium category (e.g., "Smileys & Emotion")
    - related_tags: list of alternative names/tags from emoji-data-python
    - source: where the data came from
    - enriched_at: timestamp
    """
    char = record.get("char")
    name = record.get("en", "")

    if not char:
        return None

    emoji_data = find_emoji_data(char, name)

    if not emoji_data:
        return {
            "char": char,
            "category": None,
            "related_tags": [],
            "source": "emoji-data-python",
            "enriched_at": datetime.now().isoformat(),
            "status": "not_found",
        }

    # Extract category
    category = emoji_data.category if emoji_data.category else None

    # Extract alternative names as tags
    tags = []

    # Add short names
    if hasattr(emoji_data, "short_names"):
        tags.extend(emoji_data.short_names)

    # Add main short name
    if hasattr(emoji_data, "short_name") and emoji_data.short_name:
        tags.append(emoji_data.short_name)

    # Clean up tags: remove duplicates, underscores, and empty strings
    tags = list(set(tags))
    tags = [t.replace("_", " ").strip() for t in tags if t]
    tags = [t for t in tags if len(t) > 1][:15]  # Limit to 15 tags

    return {
        "char": char,
        "category": category,
        "related_tags": tags,
        "source": "emoji-data-python",
        "enriched_at": datetime.now().isoformat(),
        "status": "success",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich emoji dataset with category data"
    )
    parser.add_argument(
        "--test", action="store_true", help="Process only first 50 emojis"
    )
    parser.add_argument("--limit", type=int, help="Limit number of emojis to process")
    args = parser.parse_args()

    # Load existing dataset
    dataset_path = os.path.join(DATA_DIR, "emoji_dataset.json")
    print(f"Loading dataset from: {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        emojis = json.load(f)

    total = len(emojis)
    limit = 50 if args.test else (args.limit or total)
    print(f"Processing {limit} out of {total} emojis...")
    print(f"emoji-data-python library has {len(edp.emoji_data)} emojis")
    print()

    results = {}
    stats = {"success": 0, "not_found": 0, "failed": 0}

    for i, record in enumerate(emojis[:limit]):
        char = record.get("char", "")
        name = record.get("en", "")

        if not char:
            continue

        print(f"[{i + 1}/{limit}] {char} {name[:40]:40} ... ", end="", flush=True)

        try:
            enriched = enrich_emoji(record)

            if enriched:
                results[char] = enriched
                status = enriched.get("status", "unknown")
                stats[status] = stats.get(status, 0) + 1

                cat = enriched.get("category", "N/A")
                tags = len(enriched.get("related_tags", []))
                print(f"✓ cat='{cat}', tags={tags}")
            else:
                stats["failed"] += 1
                print("✗ FAILED")

        except Exception as e:
            stats["failed"] += 1
            print(f"✗ ERROR: {e}")

        # Save progress every 100 records
        if (i + 1) % 100 == 0:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n>>> Progress saved: {len(results)} enriched\n")

    # Final save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)
    print(f"Total processed: {limit}")
    print(f"Success: {stats.get('success', 0)}")
    print(f"Not found: {stats.get('not_found', 0)}")
    print(f"Failed: {stats.get('failed', 0)}")
    print(f"\nOutput saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
