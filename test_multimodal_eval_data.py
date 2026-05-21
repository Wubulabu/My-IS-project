#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate the multimodal evaluation query file."""

import json


def test_multimodal_eval_queries_are_valid():
    with open("data/emoji_dataset.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
    with open("data/eval_queries_multimodal.json", "r", encoding="utf-8") as f:
        queries = json.load(f)

    dataset_chars = {record["char"] for record in dataset}
    ids = set()

    assert len(queries) >= 40
    for query in queries:
        assert query["id"] not in ids
        ids.add(query["id"])
        assert query.get("query", "").strip()
        assert query.get("lang") in {"en", "zh"}
        assert query.get("relevant")

        missing = [char for char in query["relevant"] if char not in dataset_chars]
        assert not missing, f"{query['id']} contains missing emoji: {missing}"


if __name__ == "__main__":
    test_multimodal_eval_queries_are_valid()
    print("multimodal eval query file is valid")
