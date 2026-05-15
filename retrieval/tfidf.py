"""
retrieval/tfidf.py
------------------
TF-IDF retrieval over the emoji corpus using scikit-learn.
Supports multilingual queries via a custom tokeniser that handles CJK.
"""

import json, os, sys, re
import numpy as np
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from preprocessing import tokenize, build_doc_text
from retrieval.cache_utils import build_cache_meta, cache_meta_matches, save_cache_meta

DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATASET    = os.path.join(DATA_DIR, "emoji_dataset.json")
TFIDF_PKL  = os.path.join(DATA_DIR, "tfidf_model.pkl")
TFIDF_CACHE_KIND = "tfidf"


def _tokenizer(text: str) -> list[str]:
    """Pass-through for sklearn TfidfVectorizer that already tokenises."""
    return tokenize(text)


class TFIDFRetriever:
    """sklearn TF-IDF cosine-similarity retriever for emoji."""

    def __init__(self):
        self.vectorizer  = None
        self.tfidf_matrix = None
        self.records     = None

    # ── build / load ──────────────────────────────────────────────────────────
    def build(self, records: list[dict]):
        """Fit the TF-IDF model on the emoji corpus."""
        corpus = [build_doc_text(r) for r in records]
        self.vectorizer = TfidfVectorizer(
            tokenizer    = _tokenizer,
            token_pattern= None,
            min_df       = 1,
            sublinear_tf = True,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        self.records      = records
        # cache
        with open(TFIDF_PKL, "wb") as f:
            pickle.dump((self.vectorizer, self.tfidf_matrix), f)
        save_cache_meta(TFIDF_PKL, self._expected_meta(len(records)))
        return self

    def load(self):
        """Load a previously fitted model, building it if necessary."""
        with open(DATASET, "r", encoding="utf-8") as f:
            self.records = json.load(f)

        if os.path.exists(TFIDF_PKL) and cache_meta_matches(TFIDF_PKL, self._expected_meta(len(self.records))):
            with open(TFIDF_PKL, "rb") as f:
                self.vectorizer, self.tfidf_matrix = pickle.load(f)
        else:
            self.build(self.records)
        return self

    def _expected_meta(self, num_records: int) -> dict:
        return build_cache_meta(
            DATASET,
            kind=TFIDF_CACHE_KIND,
            extra={
                "num_records": num_records,
                "tokenizer": "preprocessing.tokenize",
                "doc_builder": "preprocessing.build_doc_text",
                "min_df": 1,
                "sublinear_tf": True,
            },
        )

    # ── search ────────────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if self.vectorizer is None:
            self.load()

        q_vec  = self.vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self.tfidf_matrix).flatten()
        top_idxs = np.argsort(-scores)[:top_k]

        results = []
        for rank, idx in enumerate(top_idxs, 1):
            if scores[idx] <= 0:
                break
            r = self.records[idx]
            results.append({
                "rank"      : rank,
                "score"     : float(scores[idx]),
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
    ret = TFIDFRetriever().load()
    for q in ["happy smile", "开心 笑", "cat", "爱心"]:
        hits = ret.search(q, top_k=5)
        print(f"\nQuery: {q!r}")
        for h in hits:
            print(f"  {h['rank']}. {h['char']}  {h['en']!r:30s} score={h['score']:.4f}")
