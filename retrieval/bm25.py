"""
retrieval/bm25.py
-----------------
BM25 retrieval over the emoji corpus.

Usage
-----
    from retrieval.bm25 import BM25Retriever
    bm25 = BM25Retriever()
    bm25.load()
    results = bm25.search("开心 笑", top_k=10)
    # results = [{"rank":1, "score":…, "char":"😀", "en":"…", "zh":"…"}, …]
"""

import json, os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rank_bm25 import BM25Okapi
from preprocessing import tokenize

DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATASET    = os.path.join(DATA_DIR, "emoji_dataset.json")
CORPUS_PKL = os.path.join(DATA_DIR, "corpus.pkl")


class BM25Retriever:
    """Wrap rank_bm25.BM25Okapi for emoji search."""

    def __init__(self):
        self.bm25    = None
        self.records = None

    # ── load ──────────────────────────────────────────────────────────────────
    def load(self):
        if not os.path.exists(CORPUS_PKL):
            raise FileNotFoundError(
                "corpus.pkl not found – run preprocessing.py first"
            )
        with open(CORPUS_PKL, "rb") as f:
            corpus_tokens = pickle.load(f)

        with open(DATASET, "r", encoding="utf-8") as f:
            self.records = json.load(f)

        self.bm25 = BM25Okapi(corpus_tokens)
        return self

    # ── search ────────────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if self.bm25 is None:
            self.load()

        q_tokens = tokenize(query)
        if not q_tokens:
            return []

        scores   = self.bm25.get_scores(q_tokens)
        top_idxs = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]

        # Filter to positive scores and normalize to [0, 1] for cross-method comparability
        positive_idxs = [i for i in top_idxs if scores[i] > 0]
        if not positive_idxs:
            return []
        max_score = scores[positive_idxs[0]]  # already sorted descending
        min_score = scores[positive_idxs[-1]] if len(positive_idxs) > 1 else 0.0
        score_span = max_score - min_score

        results = []
        for rank, idx in enumerate(positive_idxs, 1):
            if scores[idx] <= 0:
                break
            # Normalize to [0, 1]: best match = 1.0
            norm_score = (scores[idx] - min_score) / score_span if score_span > 1e-12 else 1.0
            r = self.records[idx]
            results.append({
                "rank"      : rank,
                "score"     : float(norm_score),
                "char"      : r["char"],
                "codepoint" : r["codepoint"],
                "en"        : r["en"],
                "zh"        : r["zh"],
                "ja"        : r.get("ja", ""),
                "keywords"  : r["keywords"],
                "category"  : r["category"],
            })
        return results


# ── quick smoke-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    ret = BM25Retriever().load()
    for q in ["happy smile", "开心 笑", "cat", "爱心"]:
        hits = ret.search(q, top_k=5)
        print(f"\nQuery: {q!r}")
        for h in hits:
            print(f"  {h['rank']}. {h['char']}  {h['en']!r:30s} score={h['score']:.3f}")
