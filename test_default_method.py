#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests
import json

# Test default method (should now be bi_encoder)
response = requests.post('http://localhost:5000/api/search', json={
    'query': 'happy',
    'top_k': 5
})

data = response.json()
print(f"Default search for 'happy':")
print(f"  Method used: {data['method']}")
print(f"  Count: {data['count']}")
print(f"  Elapsed: {data['elapsed']}ms")

if data.get('results'):
    print(f"  Results:")
    for r in data['results']:
        print(f"    {r['char']} ({r['en']}) - score {r['score']:.3f}")
else:
    print(f"  Results: EMPTY")
