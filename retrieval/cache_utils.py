"""
Small cache metadata helpers for retrieval artifacts.

The retrieval caches depend on the dataset, model name, and local preprocessing
choices.  A stale vector or sklearn cache can silently corrupt evaluation, so
each artifact gets a sidecar JSON file with the dependency fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any


CACHE_SCHEMA_VERSION = 2


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_meta_path(path: str) -> str:
    return f"{path}.meta.json"


def build_cache_meta(dataset_path: str, *, kind: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "kind": kind,
        "dataset_path": os.path.basename(dataset_path),
        "dataset_sha256": file_sha256(dataset_path),
    }
    if extra:
        meta.update(extra)
    return meta


def load_cache_meta(artifact_path: str) -> dict[str, Any] | None:
    meta_path = artifact_meta_path(artifact_path)
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache_meta(artifact_path: str, meta: dict[str, Any]) -> None:
    with open(artifact_meta_path(artifact_path), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


def cache_meta_matches(artifact_path: str, expected: dict[str, Any]) -> bool:
    current = load_cache_meta(artifact_path)
    return current == expected
