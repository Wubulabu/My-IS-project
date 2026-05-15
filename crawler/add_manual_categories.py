#!/usr/bin/env python3
"""Manually add categories for the 12 missing emojis"""

import sys
import json
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

# Manual category mapping based on emoji meanings
MANUAL_CATEGORIES = {
    "🇨🇶": {  # Sark (flag)
        "category": "Flags",
        "related_tags": ["flag", "sark"],
    },
    "🛘": {  # landslide
        "category": "Travel & Places",
        "related_tags": ["landslide", "disaster", "warning"],
    },
    "🪉": {  # harp
        "category": "Objects",
        "related_tags": ["harp", "music", "instrument"],
    },
    "🪎": {  # treasure chest
        "category": "Objects",
        "related_tags": ["treasure", "chest", "pirate"],
    },
    "🪏": {  # shovel
        "category": "Objects",
        "related_tags": ["shovel", "tool", "dig"],
    },
    "🪾": {  # leafless tree
        "category": "Animals & Nature",
        "related_tags": ["tree", "leafless", "winter"],
    },
    "🫆": {  # fingerprint
        "category": "People & Body",
        "related_tags": ["fingerprint", "identity", "biometric"],
    },
    "🫈": {  # hairy creature
        "category": "Smileys & Emotion",
        "related_tags": ["creature", "hairy", "monster"],
    },
    "🫍": {  # orca
        "category": "Animals & Nature",
        "related_tags": ["orca", "whale", "killer whale"],
    },
    "🫜": {  # root vegetable
        "category": "Food & Drink",
        "related_tags": ["vegetable", "root", "food"],
    },
    "🫟": {  # splatter
        "category": "Smileys & Emotion",
        "related_tags": ["splatter", "splash", "liquid"],
    },
    "🫪": {  # distorted face
        "category": "Smileys & Emotion",
        "related_tags": ["face", "distorted", "weird"],
    },
}

# Load enriched data
with open("data/enriched_data.json", "r", encoding="utf-8") as f:
    enriched_data = json.load(f)

print("Adding manual categories for 12 missing emojis...\n")

updates = 0
for char, manual_info in MANUAL_CATEGORIES.items():
    if char in enriched_data:
        old_status = enriched_data[char].get("status")

        # Update the entry
        enriched_data[char].update(
            {
                "category": manual_info["category"],
                "related_tags": manual_info["related_tags"],
                "source": "manual_annotation",
                "enriched_at": datetime.now().isoformat(),
                "status": "success",
            }
        )

        updates += 1
        print(
            f"✓ {char} : {old_status} → success (category: {manual_info['category']})"
        )
    else:
        print(f"✗ {char} : Not found in enriched_data.json")

# Save updated data
with open("data/enriched_data.json", "w", encoding="utf-8") as f:
    json.dump(enriched_data, f, ensure_ascii=False, indent=2)

print(f"\n✓ Updated {updates} emojis")
print("Saved to: data/enriched_data.json")

# Verify
not_found_count = sum(
    1 for v in enriched_data.values() if v.get("status") == "not_found"
)
success_count = sum(1 for v in enriched_data.values() if v.get("status") == "success")

print(f"\nFinal status:")
print(f"  Success: {success_count}/{len(enriched_data)}")
print(f"  Not found: {not_found_count}/{len(enriched_data)}")
