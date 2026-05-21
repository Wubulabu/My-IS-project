"""
Tune MM-Hybrid fusion weights on a labeled emoji query set.

This script keeps CLIP frozen and only searches for better late-fusion
weights over the already-built BM25, Bi-Encoder, lexical, rank, and visual
signals. It is intended as a lightweight alternative to CLIP fine-tuning.

Usage
-----
    .venv\\Scripts\\python.exe eval\\tune_mm_hybrid.py --queries data\\eval_queries_multimodal.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from eval.metrics import evaluate_all
from search_engine import EmojiSearchEngine, MM_HYBRID_DEFAULT_WEIGHTS, MM_HYBRID_WEIGHT_KEYS, canonical_char


def load_queries(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    span = hi - lo
    if span <= 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / span for k, v in values.items()}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(float(weights.get(key, 0.0)), 0.0) for key in MM_HYBRID_WEIGHT_KEYS}
    total = sum(cleaned.values())
    if total <= 1e-12:
        return MM_HYBRID_DEFAULT_WEIGHTS.copy()
    return {key: cleaned[key] / total for key in MM_HYBRID_WEIGHT_KEYS}


def collect_query_signals(engine: EmojiSearchEngine, query: str, *, top_k: int) -> dict[str, dict]:
    depth = max(top_k * 8, 80)
    bm25_hits = engine._retrievers["bm25"].search(query, top_k=depth)

    encoder = engine._retrievers["bi_encoder"]
    q_vec = encoder._encode_batch([query])[0]
    semantic_scores_arr = encoder.embeddings @ q_vec
    semantic_hits = engine._hits_from_vector_scores(encoder.records, semantic_scores_arr, top_k=depth)
    visual_hits = engine._retrievers["visual"].search_with_query_vector(q_vec, top_k=depth)

    candidates: dict[str, dict] = {}
    bm25_scores: dict[str, float] = {}
    semantic_scores: dict[str, float] = {}
    visual_scores: dict[str, float] = {}
    rank_bonus: dict[str, float] = {}

    for source, score_bucket, hits in [
        ("bm25", bm25_scores, bm25_hits),
        ("bi_encoder", semantic_scores, semantic_hits),
        ("visual", visual_scores, visual_hits),
    ]:
        for rank, hit in enumerate(hits, 1):
            key = canonical_char(hit["char"])
            candidates.setdefault(key, hit.copy())
            score_bucket[key] = float(hit.get("score", 0.0))
            rank_bonus[key] = rank_bonus.get(key, 0.0) + (1.0 / (60.0 + rank))

    bm25_norm = normalize(bm25_scores)
    semantic_norm = normalize(semantic_scores)
    visual_norm = normalize(visual_scores)

    signals = {}
    for key, hit in candidates.items():
        signals[key] = {
            "char": hit["char"],
            "components": {
                "semantic": semantic_norm.get(key, 0.0),
                "visual": visual_norm.get(key, 0.0),
                "bm25": bm25_norm.get(key, 0.0),
                "lexical": engine._reranker._get_exact_score(query, hit),
                "rank_bonus": rank_bonus.get(key, 0.0),
            },
        }
    return signals


def rank_from_signals(signals: dict[str, dict], weights: dict[str, float], *, top_k: int) -> list[str]:
    normalized = normalize_weights(weights)
    rows = []
    for key, item in signals.items():
        components = item["components"]
        score = sum(normalized[name] * components.get(name, 0.0) for name in MM_HYBRID_WEIGHT_KEYS)
        rows.append((score, key, item["char"]))
    rows.sort(key=lambda row: (-row[0], row[1]))
    return [char for _, _, char in rows[:top_k]]


def evaluate_weights(
    signals_by_id: dict[str, dict[str, dict]],
    ground_truth: dict[str, set[str]],
    weights: dict[str, float],
    *,
    query_ids: list[str],
    top_k: int,
) -> dict:
    results = {
        qid: rank_from_signals(signals_by_id[qid], weights, top_k=top_k)
        for qid in query_ids
    }
    return evaluate_all(results, {qid: ground_truth[qid] for qid in query_ids}, ks=[5, 10])


def iter_weight_grid(step: float = 0.05):
    units = int(round(1.0 / step))
    semantic_min = int(round(0.35 / step))
    semantic_max = int(round(0.70 / step))
    visual_max = int(round(0.35 / step))
    bm25_min = int(round(0.05 / step))
    bm25_max = int(round(0.35 / step))
    lexical_max = int(round(0.15 / step))
    rank_max = int(round(0.10 / step))

    for semantic in range(semantic_min, semantic_max + 1):
        for visual in range(0, visual_max + 1):
            for bm25 in range(bm25_min, bm25_max + 1):
                for lexical in range(0, lexical_max + 1):
                    rank_bonus = units - semantic - visual - bm25 - lexical
                    if 0 <= rank_bonus <= rank_max:
                        yield {
                            "semantic": semantic * step,
                            "visual": visual * step,
                            "bm25": bm25 * step,
                            "lexical": lexical * step,
                            "rank_bonus": rank_bonus * step,
                        }


def metric_key(metrics: dict) -> tuple[float, float, float, float]:
    return (metrics["MAP"], metrics["NDCG@10"], metrics["MRR"], metrics["P@5"])


def find_best_weights(
    signals_by_id: dict[str, dict[str, dict]],
    ground_truth: dict[str, set[str]],
    *,
    query_ids: list[str],
    step: float,
    top_k: int,
) -> tuple[dict[str, float], dict]:
    best_weights = MM_HYBRID_DEFAULT_WEIGHTS.copy()
    best_metrics = evaluate_weights(signals_by_id, ground_truth, best_weights, query_ids=query_ids, top_k=top_k)
    for weights in iter_weight_grid(step):
        metrics = evaluate_weights(signals_by_id, ground_truth, weights, query_ids=query_ids, top_k=top_k)
        if metric_key(metrics) > metric_key(best_metrics):
            best_weights = weights
            best_metrics = metrics
    return normalize_weights(best_weights), best_metrics


def run_cross_validation(
    signals_by_id: dict[str, dict[str, dict]],
    ground_truth: dict[str, set[str]],
    *,
    query_ids: list[str],
    folds: int,
    step: float,
    top_k: int,
) -> dict:
    if folds <= 1:
        return {}

    fold_rows = []
    for fold in range(folds):
        test_ids = [qid for index, qid in enumerate(query_ids) if index % folds == fold]
        train_ids = [qid for qid in query_ids if qid not in test_ids]
        weights, train_metrics = find_best_weights(
            signals_by_id,
            ground_truth,
            query_ids=train_ids,
            step=step,
            top_k=top_k,
        )
        test_metrics = evaluate_weights(
            signals_by_id,
            ground_truth,
            weights,
            query_ids=test_ids,
            top_k=top_k,
        )
        fold_rows.append({
            "fold": fold + 1,
            "weights": weights,
            "train": train_metrics,
            "test": test_metrics,
        })

    return {
        "folds": fold_rows,
        "mean_test": {
            "MAP": mean(row["test"]["MAP"] for row in fold_rows),
            "MRR": mean(row["test"]["MRR"] for row in fold_rows),
            "P@5": mean(row["test"]["P@5"] for row in fold_rows),
            "NDCG@10": mean(row["test"]["NDCG@10"] for row in fold_rows),
        },
    }


def fmt_weights(weights: dict[str, float]) -> str:
    return ", ".join(f"{key}={weights[key]:.2f}" for key in MM_HYBRID_WEIGHT_KEYS)


def fmt_metrics(metrics: dict) -> str:
    return (
        f"MAP={metrics['MAP']:.4f} MRR={metrics['MRR']:.4f} "
        f"P@5={metrics['P@5']:.4f} NDCG@10={metrics['NDCG@10']:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default=os.path.join("data", "eval_queries_multimodal.json"))
    parser.add_argument("--step", type=float, default=0.05, help="Grid-search step size")
    parser.add_argument("--folds", type=int, default=4, help="Deterministic cross-validation folds")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--save", default="", help="Optional JSON path for full tuning output")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    query_ids = [q["id"] for q in queries]
    ground_truth = {q["id"]: set(q["relevant"]) for q in queries}

    print("[1/3] Loading retrievers")
    engine = EmojiSearchEngine(use_neural_reranker=False)
    engine.load(["bm25", "bi_encoder", "visual"])

    print("[2/3] Precomputing query signals")
    signals_by_id = {
        q["id"]: collect_query_signals(engine, q["query"], top_k=args.top_k)
        for q in queries
    }

    print("[3/3] Searching fusion weights")
    default_metrics = evaluate_weights(
        signals_by_id,
        ground_truth,
        MM_HYBRID_DEFAULT_WEIGHTS,
        query_ids=query_ids,
        top_k=args.top_k,
    )
    best_weights, best_metrics = find_best_weights(
        signals_by_id,
        ground_truth,
        query_ids=query_ids,
        step=args.step,
        top_k=args.top_k,
    )
    cv = run_cross_validation(
        signals_by_id,
        ground_truth,
        query_ids=query_ids,
        folds=args.folds,
        step=args.step,
        top_k=args.top_k,
    )

    print(f"\nQueries: {len(queries)}")
    print(f"Default weights: {fmt_weights(MM_HYBRID_DEFAULT_WEIGHTS)}")
    print(f"Default metrics: {fmt_metrics(default_metrics)}")
    print(f"\nBest full-set weights: {fmt_weights(best_weights)}")
    print(f"Best full-set metrics: {fmt_metrics(best_metrics)}")
    if cv:
        print(
            "\nCross-validation mean test: "
            f"MAP={cv['mean_test']['MAP']:.4f} "
            f"MRR={cv['mean_test']['MRR']:.4f} "
            f"P@5={cv['mean_test']['P@5']:.4f} "
            f"NDCG@10={cv['mean_test']['NDCG@10']:.4f}"
        )

    if args.save:
        os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "queries": args.queries,
                    "query_count": len(queries),
                    "default_weights": MM_HYBRID_DEFAULT_WEIGHTS,
                    "default_metrics": default_metrics,
                    "best_weights": best_weights,
                    "best_metrics": best_metrics,
                    "cross_validation": cv,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"\nSaved tuning report -> {args.save}")


if __name__ == "__main__":
    main()
