#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from retrieval.bm25 import BM25Retriever

# Test BM25 directly
print("Loading BM25 retriever...")
bm25 = BM25Retriever()
bm25.load()

print(f"Records loaded: {len(bm25.records)}")
print(f"BM25 model loaded: {bm25.bm25 is not None}")

# Test search
queries = ['happy', 'smile', '😀']
for q in queries:
    results = bm25.search(q, top_k=5)
    print(f"\nQuery '{q}': {len(results)} results")
    for r in results[:2]:
        print(f"  {r['char']} ({r['en']}) - score {r['score']:.3f}")
