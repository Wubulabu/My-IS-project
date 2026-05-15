#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

with open('data/emoji_dataset.json', 'r', encoding='utf-8') as f:
    records = json.load(f)

# Search for 'happy' in the dataset
happy_count = 0
for r in records:
    if 'happy' in (r.get('en') or '').lower():
        happy_count += 1
        if happy_count <= 3:
            print(f"Found: {r['char']} ({r['en']})")

print(f"\nTotal emojis with 'happy': {happy_count}")

# Search for 'smile' in the dataset
smile_count = 0
for r in records:
    if 'smile' in (r.get('en') or '').lower():
        smile_count += 1
        if smile_count <= 3:
            print(f"Found: {r['char']} ({r['en']})")

print(f"Total emojis with 'smile': {smile_count}")
