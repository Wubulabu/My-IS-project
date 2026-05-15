#!/usr/bin/env python3
"""Test emoji-data-python package"""

import sys

sys.stdout.reconfigure(encoding="utf-8")

import emoji_data_python as edp

# Test finding an emoji
results = edp.find_by_shortname("grinning")
print(f"By shortname: {len(results)} results")

if results:
    e = results[0] if isinstance(results, list) else results
    print(f"Category: {e.category}")
    print(f"Name: {e.name}")
    print(f"Char: {e.char}")
    print(f"Short names: {e.short_names}")
else:
    e = None

# Try finding by character
print(f"\nSearching by unicode character '😀'...")
try:
    e2 = edp.find_by_unicode("😀")
    print(f"Result: {e2}")
    if e2:
        print(f"Category: {e2.category}")
        print(f"Name: {e2.name}")
except Exception as ex:
    print(f"Error: {ex}")

# List all available attributes
print(f"\nAll attributes: {dir(e) if e else 'none'}")

# Try all emojis
print(f"\nTotal emojis in library: {len(edp.emoji_data)}")
sample = edp.emoji_data[:5]
print("First 5 emojis:")
for emoji in sample:
    print(f"  {emoji.char} - {emoji.name} - category:{emoji.category}")
