#!/usr/bin/env python3
"""Analyze enriched data statistics"""

import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("data/enriched_data.json", "r", encoding="utf-8"))

print(f"Total emojis enriched: {len(data)}")

# Category distribution
categories = {}
for char, info in data.items():
    cat = info.get("category", "None")
    categories[cat] = categories.get(cat, 0) + 1

print("\nCategory distribution:")
for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {count}")

# Status counts
success = sum(1 for v in data.values() if v.get("status") == "success")
not_found = sum(1 for v in data.values() if v.get("status") == "not_found")
print(f"\nStatus: Success={success}, Not Found={not_found}")

# Tags statistics
avg_tags = sum(len(v.get("related_tags", [])) for v in data.values()) / len(data)
print(f"Average tags per emoji: {avg_tags:.2f}")

# Find which emojis were not found
print("\nEmojis not found in emoji-data-python:")
for char, info in data.items():
    if info.get("status") == "not_found":
        print(f"  {char} - category: {info.get('category')}")
