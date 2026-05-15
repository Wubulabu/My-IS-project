"""
API latency benchmark for the Emoji IR system.

Usage
-----
  python eval/benchmark_api.py
  python eval/benchmark_api.py --base-url http://127.0.0.1:5000 --runs 3 --top-k 10
"""

import argparse
import json
import time
from statistics import mean

import requests

DEFAULT_QUERIES = [
    "开心", "火", "猫", "dog", "love heart", "工作", "雨", "music",
    "angry", "winter", "snake", "party"
]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    vals = sorted(values)
    rank = (len(vals) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(vals) - 1)
    frac = rank - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def benchmark_search(base_url: str, method: str, queries: list[str], runs: int, top_k: int) -> dict:
    latencies = []
    errors = 0
    for _ in range(runs):
        for q in queries:
            body = {"query": q, "method": method, "top_k": top_k}
            t0 = time.perf_counter()
            try:
                resp = requests.post(f"{base_url}/api/search", json=body, timeout=120)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    latencies.append(elapsed_ms)
                else:
                    errors += 1
            except Exception:
                errors += 1

    return {
        "method": method,
        "samples": len(latencies),
        "errors": errors,
        "avg_ms": round(mean(latencies), 2) if latencies else 0.0,
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "min_ms": round(min(latencies), 2) if latencies else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--methods", nargs="*", default=["bm25", "tfidf", "bi_encoder"])
    parser.add_argument("--out", default="eval/benchmark_api_latest.json")
    args = parser.parse_args()

    report = {
        "base_url": args.base_url,
        "runs": args.runs,
        "top_k": args.top_k,
        "queries": DEFAULT_QUERIES,
        "results": [],
    }

    for method in args.methods:
        result = benchmark_search(args.base_url, method, DEFAULT_QUERIES, args.runs, args.top_k)
        report["results"].append(result)
        print(
            f"[{method:9s}] samples={result['samples']:3d} errors={result['errors']:2d} "
            f"avg={result['avg_ms']:7.2f}ms p50={result['p50_ms']:7.2f}ms p95={result['p95_ms']:7.2f}ms"
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Saved benchmark report to {args.out}")


if __name__ == "__main__":
    main()
