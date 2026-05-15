#!/usr/bin/env python3
"""Check missing emojis and their details"""

import sys
import json
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")

# Load enriched data
data = json.load(open("data/enriched_data.json", "r", encoding="utf-8"))

# Load main dataset for English names
dataset = json.load(open("data/emoji_dataset.json", "r", encoding="utf-8"))
emoji_names = {rec["char"]: rec.get("en", "Unknown") for rec in dataset}

# Find missing
missing = [
    (char, info) for char, info in data.items() if info.get("status") == "not_found"
]

print(f"Found {len(missing)} emojis without category:\n")

for char, info in missing:
    name = emoji_names.get(char, "Unknown")
    print(f"{char}  {name}")

    # Get Unicode info
    try:
        codepoints = [f"U+{ord(c):04X}" for c in char]
        print(f"   Codepoints: {' '.join(codepoints)}")

        # Try to get Unicode name
        try:
            unicode_name = unicodedata.name(char[0] if len(char) > 0 else char)
            print(f"   Unicode name: {unicode_name}")
        except:
            pass
    except:
        pass

    print()
