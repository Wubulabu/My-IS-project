import requests
import json

url = "http://localhost:5000/api/ai_committee_eval"
data = {
    "query": "test query",
    "metrics": [
        {"method": "bm25", "metrics": {"MAP": 0.8, "NDCG@10": 0.7}},
        {"method": "bi_encoder", "metrics": {"MAP": 0.9, "NDCG@10": 0.85}}
    ]
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")
