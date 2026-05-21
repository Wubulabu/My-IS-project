"""Shared evaluation-query loading and stratified sampling helpers."""

from __future__ import annotations

import json
import os
import random
from collections import Counter
from typing import Iterable


BASE_QUERY_FILE = os.path.join("data", "eval_queries.json")
MULTIMODAL_QUERY_FILE = os.path.join("data", "eval_queries_multimodal.json")

BUCKET_CORE = "core"
BUCKET_MULTIMODAL = "multimodal"
BUCKET_EXPANDED = "expanded"

DEFAULT_PROFILE = {
    BUCKET_MULTIMODAL: 0.45,
    BUCKET_CORE: 0.40,
    BUCKET_EXPANDED: 0.15,
}

BUCKET_ORDER = [BUCKET_MULTIMODAL, BUCKET_CORE, BUCKET_EXPANDED]


def load_queries(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _query_number(query_id: str) -> int | None:
    if not query_id or not query_id.startswith("q"):
        return None
    digits = query_id[1:]
    if not digits.isdigit():
        return None
    return int(digits)


def _copy_with_bucket(query: dict, bucket: str) -> dict:
    copied = query.copy()
    copied["_eval_bucket"] = bucket
    return copied


def load_evaluation_pools(
    *,
    base_query_file: str = BASE_QUERY_FILE,
    multimodal_query_file: str = MULTIMODAL_QUERY_FILE,
) -> dict[str, list[dict]]:
    """Load base and multimodal query files into named evaluation buckets.

    The first 50 base queries are the hand-curated cross-language/semantic set.
    Later base queries are the expanded exact-label/name pool, which is useful
    for regression coverage but should not dominate random live samples.
    """

    base_queries = load_queries(base_query_file)
    pools = {
        BUCKET_CORE: [],
        BUCKET_MULTIMODAL: [],
        BUCKET_EXPANDED: [],
    }

    for query in base_queries:
        number = _query_number(str(query.get("id", "")))
        bucket = BUCKET_CORE if number is not None and number <= 50 else BUCKET_EXPANDED
        pools[bucket].append(_copy_with_bucket(query, bucket))

    if os.path.exists(multimodal_query_file):
        for query in load_queries(multimodal_query_file):
            pools[BUCKET_MULTIMODAL].append(_copy_with_bucket(query, BUCKET_MULTIMODAL))

    return pools


def flatten_pools(pools: dict[str, list[dict]]) -> list[dict]:
    queries: list[dict] = []
    for bucket in BUCKET_ORDER:
        queries.extend(pools.get(bucket, []))
    for bucket, bucket_queries in pools.items():
        if bucket not in BUCKET_ORDER:
            queries.extend(bucket_queries)
    return queries


def pool_size(pools: dict[str, list[dict]]) -> int:
    return sum(len(items) for items in pools.values())


def bucket_counts(queries: Iterable[dict]) -> dict[str, int]:
    counts = Counter(query.get("_eval_bucket", "unknown") for query in queries)
    return {bucket: counts.get(bucket, 0) for bucket in BUCKET_ORDER if counts.get(bucket, 0)}


def _quota_counts(sample_size: int, profile: dict[str, float]) -> dict[str, int]:
    raw = {bucket: max(float(profile.get(bucket, 0.0)), 0.0) * sample_size for bucket in BUCKET_ORDER}
    counts = {bucket: int(raw[bucket]) for bucket in BUCKET_ORDER}
    remainder = sample_size - sum(counts.values())
    order = sorted(BUCKET_ORDER, key=lambda bucket: (raw[bucket] - counts[bucket], profile.get(bucket, 0.0)), reverse=True)
    for bucket in order[:remainder]:
        counts[bucket] += 1
    return counts


def stratified_eval_sample(
    pools: dict[str, list[dict]],
    *,
    sample_size: int,
    seed: str,
    profile: dict[str, float] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Return a deterministic balanced sample and its bucket breakdown."""

    total = pool_size(pools)
    if total <= 0:
        return [], {}

    target_size = min(max(int(sample_size), 1), total)
    weights = profile or DEFAULT_PROFILE
    quotas = _quota_counts(target_size, weights)
    rng = random.Random(seed)

    selected: list[dict] = []
    selected_keys: set[tuple[str, str]] = set()

    for bucket in BUCKET_ORDER:
        bucket_queries = list(pools.get(bucket, []))
        rng.shuffle(bucket_queries)
        take = min(len(bucket_queries), quotas.get(bucket, 0))
        for query in bucket_queries[:take]:
            selected.append(query)
            selected_keys.add((bucket, str(query.get("id", ""))))

    if len(selected) < target_size:
        leftovers: list[dict] = []
        for bucket in BUCKET_ORDER:
            for query in pools.get(bucket, []):
                key = (bucket, str(query.get("id", "")))
                if key not in selected_keys:
                    leftovers.append(query)
        rng.shuffle(leftovers)
        selected.extend(leftovers[: target_size - len(selected)])

    rng.shuffle(selected)
    return selected[:target_size], bucket_counts(selected[:target_size])
