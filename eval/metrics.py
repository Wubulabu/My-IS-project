"""
eval/metrics.py
---------------
Standard information retrieval evaluation metrics.

All functions receive:
  retrieved : list of str  – ordered list of retrieved item IDs (best first)
  relevant  : set  of str  – ground-truth relevant item IDs

Supported metrics
-----------------
  precision_at_k   P@K
  recall_at_k      R@K
  f1_at_k          F1@K
  average_precision  AP (used to compute MAP)
  ndcg_at_k        NDCG@K
  mrr              Mean Reciprocal Rank (single query)
"""

import math


def precision_at_k(retrieved: list, relevant: set, k: int) -> float:
    """Fraction of top-K retrieved items that are relevant."""
    if k == 0:
        return 0.0
    top_k = retrieved[:k]
    hits  = sum(1 for item in top_k if item in relevant)
    return hits / k


def recall_at_k(retrieved: list, relevant: set, k: int) -> float:
    """Fraction of all relevant items found in top-K."""
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    hits  = sum(1 for item in top_k if item in relevant)
    return hits / len(relevant)


def f1_at_k(retrieved: list, relevant: set, k: int) -> float:
    p = precision_at_k(retrieved, relevant, k)
    r = recall_at_k(retrieved, relevant, k)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def average_precision(retrieved: list, relevant: set) -> float:
    """
    Compute AP for a single ranked list.
    AP = (1/|R|) * sum_{k: retrieved[k] in R} P@k
    """
    if not relevant:
        return 0.0
    hits, total = 0, 0.0
    for k, item in enumerate(retrieved, 1):
        if item in relevant:
            hits += 1
            total += hits / k
    return total / len(relevant)


def ndcg_at_k(retrieved: list, relevant: set, k: int) -> float:
    """
    Normalised Discounted Cumulative Gain @ K.
    Assumes binary relevance (1 if in relevant else 0).
    """
    def dcg(items):
        return sum(
            (1.0 / math.log2(i + 2))
            for i, item in enumerate(items)
            if item in relevant
        )

    top_k = retrieved[:k]
    ideal_len = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_len))
    if idcg == 0:
        return 0.0
    return dcg(top_k) / idcg


def reciprocal_rank(retrieved: list, relevant: set) -> float:
    """RR for a single query (first relevant item position)."""
    for k, item in enumerate(retrieved, 1):
        if item in relevant:
            return 1.0 / k
    return 0.0


# ── aggregate over a query set ────────────────────────────────────────────────
def evaluate_all(
    results_by_query: dict[str, list[str]],
    ground_truth    : dict[str, set[str]],
    ks              : list[int] = [5, 10],
) -> dict:
    """
    Compute MAP, MRR, P@K, R@K, NDCG@K over a full query set.

    Parameters
    ----------
    results_by_query : {query_id: [retrieved_id, …]}
    ground_truth     : {query_id: {relevant_id, …}}
    ks               : list of cut-offs

    Returns
    -------
    dict with keys like "P@5", "R@10", "NDCG@10", "MAP", "MRR"
    """
    metrics = {f"P@{k}": [] for k in ks}
    metrics.update({f"R@{k}":    [] for k in ks})
    metrics.update({f"F1@{k}":   [] for k in ks})
    metrics.update({f"NDCG@{k}": [] for k in ks})
    ap_list  = []
    mrr_list = []

    for qid, retrieved in results_by_query.items():
        relevant = ground_truth.get(qid, set())
        if not relevant:
            continue
        for k in ks:
            metrics[f"P@{k}"].append(precision_at_k(retrieved, relevant, k))
            metrics[f"R@{k}"].append(recall_at_k(retrieved, relevant, k))
            metrics[f"F1@{k}"].append(f1_at_k(retrieved, relevant, k))
            metrics[f"NDCG@{k}"].append(ndcg_at_k(retrieved, relevant, k))
        ap_list.append(average_precision(retrieved, relevant))
        mrr_list.append(reciprocal_rank(retrieved, relevant))

    averaged = {k: (sum(v) / len(v) if v else 0.0) for k, v in metrics.items()}
    averaged["MAP"] = sum(ap_list)  / len(ap_list)  if ap_list  else 0.0
    averaged["MRR"] = sum(mrr_list) / len(mrr_list) if mrr_list else 0.0
    return averaged
