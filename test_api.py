
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_search():
    print(f"\n--- Testing Search: '开心' ---")
    payload = {"query": "开心", "method": "bm25", "top_k": 5}
    r = requests.post(f"{BASE_URL}/api/search", json=payload)
    data = r.json()
    print(f"Status: {r.status_code}")
    print(f"Elapsed: {data.get('elapsed')}ms")
    for res in data.get("results", []):
        print(f"  [{res['rank']}] {res['char']} (Score: {res['score']:.2f}) - {res['en']} / {res['zh']}")
    
    # Check similarity matrix presence
    matrix = data.get("sim_matrix", [])
    if matrix:
        print(f"Similarity Matrix: {len(matrix)}x{len(matrix)} (Ready for StarMap)")

def test_vector_math():
    print(f"\n--- Testing Vector Math: 'king - man + woman' ---")
    payload = {"expression": "king - man + woman", "top_k": 3}
    r = requests.post(f"{BASE_URL}/api/vector_math", json=payload)
    data = r.json()
    for res in data.get("results", []):
        print(f"  {res['char']} ({res['en']}) - Score: {res['score']:.3f}")

if __name__ == "__main__":
    try:
        test_search()
        test_vector_math()
    except Exception as e:
        print(f"Error connecting: {e}")
