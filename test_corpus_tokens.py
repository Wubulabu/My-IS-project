#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import pickle
from collections import Counter

# Load corpus tokens
with open('data/corpus.pkl', 'rb') as f:
    corpus_tokens = pickle.load(f)

# Collect all unique tokens
all_tokens = []
for tokens in corpus_tokens:
    all_tokens.extend(tokens)

# Count token frequencies (excluding single chars)
token_counter = Counter(t for t in all_tokens if len(t) > 1)

print("Top 50 most frequent tokens (length > 1):")
for token, count in token_counter.most_common(50):
    print(f"  '{token}': {count}")

# Check for specific words
test_words = ['happy', 'smile', 'smiling', 'face', 'emoji', 'grin', 'joy']
print(f"\nLooking for specific words:")
for word in test_words:
    count = token_counter.get(word, 0)
    print(f"  '{word}': {count}")

print(f"\nTotal unique tokens: {len(token_counter)}")
print(f"Total token occurrences: {len(all_tokens)}")
