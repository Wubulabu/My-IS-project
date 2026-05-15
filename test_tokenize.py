#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from preprocessing import tokenize, build_doc_text

# Test tokenize
test_queries = ['happy', 'smile', 'happy face', '😀']
for q in test_queries:
    tokens = tokenize(q)
    print(f"tokenize('{q}') = {tokens}")

# Test building doc text for a sample emoji
import json
with open('data/emoji_dataset.json', 'r', encoding='utf-8') as f:
    records = json.load(f)
    
# Find an emoji with "happy" or "smile" in it
for r in records[:50]:
    if 'smile' in r.get('en', '').lower() or 'happy' in r.get('en', '').lower():
        text = build_doc_text(r)
        tokens = tokenize(text)
        print(f"\nEmoji: {r['char']} ({r['en']})")
        print(f"  Doc text: {text[:100]}...")
        print(f"  Tokens (first 10): {tokens[:10]}")
        break
