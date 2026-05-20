"""
eval/evaluate.py
----------------
Run the full evaluation pipeline over all retrieval methods and print a
comparison table.

Usage
-----
    cd IS/
    python eval/evaluate.py                  # BM25 + TF-IDF only (fast)
    python eval/evaluate.py --all            # include all retrieval methods
    python eval/evaluate.py --ablation       # MM-Hybrid ablation table
    python eval/evaluate.py --save results/  # save per-query CSV
"""

import json, os, sys, argparse, csv, time
from statistics import mean
from tabulate import tabulate

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from search_engine import EmojiSearchEngine
from eval.metrics  import evaluate_all

DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
QUERIES_F  = os.path.join(DATA_DIR, "eval_queries.json")
DATASET_F  = os.path.join(DATA_DIR, "emoji_dataset.json")


def load_queries(path: str = QUERIES_F):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_dataset() -> dict[str, dict]:
    """Return char → record mapping."""
    with open(DATASET_F, "r", encoding="utf-8") as f:
        records = json.load(f)
    return {r["char"]: r for r in records}


def run_retrieval(engine, queries, method, top_k=10) -> tuple[dict[str, list[str]], list[float]]:
    """Return ({query_id → [retrieved_char, …]}, per-query latency in ms)."""
    results: dict[str, list[str]] = {}
    latencies_ms: list[float] = []
    for q in queries:
        t0 = time.perf_counter()
        hits = engine.search(q["query"], method=method, top_k=top_k)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        results[q["id"]] = [h["char"] for h in hits]
    return results, latencies_ms


def percentile(values: list[float], p: float) -> float:
    """Simple percentile with linear interpolation."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    rank = (len(sorted_vals) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def build_ground_truth(queries) -> dict[str, set[str]]:
    return {q["id"]: set(q["relevant"]) for q in queries}


def print_table(rows, ks):
    """Print comparison table to stdout."""
    headers = ["Method", "MAP", "MRR"]
    for k in ks: headers += [f"P@{k}", f"R@{k}", f"F1@{k}", f"NDCG@{k}"]
    table = []
    for method, m in rows:
        row = [method, f"{m['MAP']:.4f}", f"{m['MRR']:.4f}"]
        for k in ks:
            row += [f"{m[f'P@{k}']:.4f}", f"{m[f'R@{k}']:.4f}", f"{m[f'F1@{k}']:.4f}", f"{m[f'NDCG@{k}']:.4f}"]
        table.append(row)
    print(tabulate(table, headers=headers, tablefmt="fancy_grid"))


def save_csv(rows, ks, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    out = os.path.join(save_dir, "comparison.csv")
    headers = ["Method", "MAP", "MRR"]
    for k in ks: headers += [f"P@{k}", f"R@{k}", f"F1@{k}", f"NDCG@{k}"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for method, m in rows:
            row = [method, m["MAP"], m["MRR"]]
            for k in ks:
                row += [m[f"P@{k}"], m[f"R@{k}"], m[f"F1@{k}"], m[f"NDCG@{k}"]]
            w.writerow(row)
    print(f"\n  Results saved → {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",  action="store_true",
                        help="Include all retrieval methods (requires model + index)")
    parser.add_argument("--ablation", action="store_true",
                        help="Run MM-Hybrid, without-visual, without-lexical, and visual-only")
    parser.add_argument("--save", default="",
                        help="Directory to save CSV results")
    parser.add_argument("--strict", action="store_true",
                        help="Stop immediately if any method fails")
    parser.add_argument("--queries", default=QUERIES_F,
                        help="Evaluation query JSON file")
    args = parser.parse_args()

    ks = [5, 10]
    if args.ablation:
        methods = ["mm_hybrid", "mm_hybrid_no_visual", "mm_hybrid_no_lexical", "visual"]
    else:
        methods = ["bm25", "tfidf"]
    if args.all and not args.ablation:
        methods += ["dense", "bi_encoder", "hnsw", "rerank", "hybrid", "visual", "mm_hybrid"]

    print("="*60)
    print("  Emoji IR System — Evaluation")
    print("="*60)

    # ── load ─────────────────────────────────────────────────────────────────
    print("\n[1/3] Loading search engine …")
    engine = EmojiSearchEngine()
    engine.load(methods=methods)

    print("[2/3] Loading evaluation queries …")
    queries = load_queries(args.queries)
    gt      = build_ground_truth(queries)
    print(f"  {len(queries)} queries, {sum(len(v) for v in gt.values())} total relevant items")

    # ── run ──────────────────────────────────────────────────────────────────
    print("[3/3] Running retrieval …")
    rows = []
    failures = []
    for method in methods:
        t0 = time.perf_counter()
        try:
            res, latencies_ms = run_retrieval(engine, queries, method, top_k=max(ks))
            elapsed = time.perf_counter() - t0
            m = evaluate_all(res, gt, ks=ks)
            rows.append((method, m))

            p50 = percentile(latencies_ms, 0.50)
            p95 = percentile(latencies_ms, 0.95)
            avg = mean(latencies_ms) if latencies_ms else 0.0

            print(
                f"  [{method:9s}] MAP={m['MAP']:.4f}  MRR={m['MRR']:.4f}  "
                f"NDCG@10={m['NDCG@10']:.4f}  ({elapsed:.2f}s, avg={avg:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms)"
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            failures.append((method, str(e)))
            print(f"  [{method:9s}] FAILED: {e}")
            if args.strict:
                raise

    # ── display ───────────────────────────────────────────────────────────────
    if rows:
        print("\n" + "="*60)
        print("  Comparison Table")
        print("="*60)
        try:
            print_table(rows, ks)
        except ImportError:
            # fallback if tabulate not installed
            for method, m in rows:
                print(f"  {method}: {m}")
    else:
        print("\nNo successful method run; nothing to compare.")

    if args.save and rows:
        save_csv(rows, ks, args.save)

    # ── analysis ──────────────────────────────────────────────────────────────
    if rows:
        print("\n[Analysis]")
        best_map = max(rows, key=lambda x: x[1]["MAP"])
        best_mrr = max(rows, key=lambda x: x[1]["MRR"])
        print(f"  Best MAP  → {best_map[0]}  ({best_map[1]['MAP']:.4f})")
        print(f"  Best MRR  → {best_mrr[0]}  ({best_mrr[1]['MRR']:.4f})")
        print("\n  Interpretation:")
        for method, m in rows:
            p5 = m["P@5"]; n10 = m["NDCG@10"]
            if p5 > 0.5:
                quality = "excellent"
            elif p5 > 0.3:
                quality = "good"
            elif p5 > 0.1:
                quality = "fair"
            else:
                quality = "baseline"
            print(f"  {method:9s}: P@5={p5:.3f}, NDCG@10={n10:.3f}  → {quality}")

    if failures:
        print("\n[Failures]")
        for method, err in failures:
            print(f"  {method:9s}: {err}")


if __name__ == "__main__":
    main()
