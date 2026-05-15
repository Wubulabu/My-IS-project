import requests
import json

# Test with different methods
methods = ['bm25', 'tfidf', 'bi_encoder']
query = 'happy'

for method in methods:
    try:
        response = requests.post('http://localhost:5000/api/search', json={
            'query': query,
            'method': method,
            'top_k': 3
        }, timeout=30)
        data = response.json()
        print(f'\n{method.upper()}: count={data["count"]}, elapsed={data["elapsed"]}ms')
        if data.get('results'):
            results_str = ', '.join([f'{r["char"]}({r["en"]})' for r in data['results'][:3]])
            print(f'  Results: {results_str}')
        else:
            print(f'  Results: EMPTY')
            if data.get('error'):
                print(f'  Error: {data["error"]}')
    except Exception as e:
        print(f'\n{method.upper()}: ERROR - {e}')
