"""
search_engine.py
----------------
Unified search interface that delegates to BM25 / TF-IDF / Dense retrievers.

Usage
-----
    from search_engine import EmojiSearchEngine

    engine = EmojiSearchEngine()
    engine.load(methods=["bm25", "tfidf", "dense"])

    results = engine.search("开心 笑", method="bm25", top_k=10)
    results = engine.search("happy face", method="dense", top_k=5)
"""

import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

from retrieval.bm25          import BM25Retriever
from retrieval.tfidf         import TFIDFRetriever
from retrieval.dense         import DenseRetriever, APIEmbeddingRetriever
from retrieval.bi_encoder    import BiEncoderRetriever
from retrieval.hnsw_retriever import HNSWRetriever
from retrieval.reranker      import LexicalBoostReranker, NeuralReranker
from retrieval.visual        import VisualRetriever


def canonical_char(char: str) -> str:
    return char.replace("\ufe0f", "").replace("\ufe0e", "")


class EmojiSearchEngine:
    """
    Facade over five retrieval methods.

    Parameters
    ----------
    methods : list of str
        Subset of {"bm25", "tfidf", "dense", "bi_encoder", "hnsw"} to load.
        dense/bi_encoder/hnsw are slow on first run (model download & encode).
    """

    METHOD_MAP = {
        "bm25"       : BM25Retriever,
        "tfidf"      : TFIDFRetriever,
        "dense"      : DenseRetriever,
        "api_embed"  : APIEmbeddingRetriever,  # NEW: SiliconFlow API embeddings
        "bi_encoder" : BiEncoderRetriever,
        "hnsw"       : HNSWRetriever,
        "visual"     : VisualRetriever,
    }
    SPECIAL_METHODS = {"rerank", "hybrid", "mm_hybrid", "mm_hybrid_no_visual", "mm_hybrid_no_lexical"}

    def __init__(self, use_neural_reranker: bool = True):
        """
        Initialize search engine.
        
        Parameters
        ----------
        use_neural_reranker : bool, default True
            If True, use NeuralReranker (Qwen3-Reranker-8B via API).
            If False, use LexicalBoostReranker (lightweight rules-based).
        """
        self._retrievers: dict = {}
        self._reranker = NeuralReranker() if use_neural_reranker else LexicalBoostReranker()
        self._use_neural_reranker = use_neural_reranker

    # ── loading ───────────────────────────────────────────────────────────────
    def load(self, methods: list[str] | None = None):
        """Instantiate and load the selected retrieval methods."""
        if methods is None:
            methods = ["bm25", "tfidf"]

        for m in methods:
            if m in self.SPECIAL_METHODS:
                if m == "rerank":
                    deps = ["bi_encoder"]
                elif m == "mm_hybrid_no_visual":
                    deps = ["bm25", "bi_encoder"]
                elif m.startswith("mm_hybrid"):
                    deps = ["bm25", "bi_encoder", "visual"]
                else:
                    deps = ["bm25", "bi_encoder"]
                self.load(deps)
                continue
            if m not in self.METHOD_MAP:
                choices = list(self.METHOD_MAP) + sorted(self.SPECIAL_METHODS)
                raise ValueError(f"Unknown method: {m!r}. Choose from {choices}")
            if m not in self._retrievers:
                print(f"Loading retriever: {m} …")
                self._retrievers[m] = self.METHOD_MAP[m]().load()
        return self

    # ── search ────────────────────────────────────────────────────────────────
    def search(
        self,
        query : str,
        method: str = "bm25",
        top_k : int = 10,
    ) -> list[dict]:
        """
        Search for emoji matching *query*.

        Returns
        -------
        list of dicts with keys: rank, score, char, codepoint, en, zh, ja,
        keywords, category.
        """
        if method == "visual":
            return self._search_visual(query, top_k=top_k)
        if method == "rerank":
            return self._search_rerank(query, top_k=top_k)
        if method == "hybrid":
            return self._search_hybrid(query, top_k=top_k)
        if method == "mm_hybrid":
            return self._search_mm_hybrid(query, top_k=top_k)
        if method == "mm_hybrid_no_visual":
            return self._search_mm_hybrid(query, top_k=top_k, variant="without_visual")
        if method == "mm_hybrid_no_lexical":
            return self._search_mm_hybrid(query, top_k=top_k, variant="without_lexical")
        if method not in self._retrievers:
            self.load(methods=[method])
        return self._retrievers[method].search(query, top_k=top_k)

    def _hits_from_vector_scores(self, records: list[dict], scores: np.ndarray, top_k: int) -> list[dict]:
        top_idxs = np.argsort(-scores)[:top_k]
        hits = []
        for rank, idx in enumerate(top_idxs, 1):
            r = records[int(idx)]
            hits.append({
                "rank"      : rank,
                "score"     : float(scores[int(idx)]),
                "char"      : r["char"],
                "codepoint" : r["codepoint"],
                "en"        : r["en"],
                "zh"        : r["zh"],
                "ja"        : r.get("ja", ""),
                "keywords"  : r["keywords"],
                "category"  : r["category"],
            })
        return hits

    def _search_visual(self, query: str, top_k: int = 10) -> list[dict]:
        self.load(["bi_encoder", "visual"])
        encoder = self._retrievers["bi_encoder"]
        q_vec = encoder._encode_batch([query])[0]
        return self._retrievers["visual"].search_with_query_vector(q_vec, top_k=top_k)

    def _search_rerank(self, query: str, top_k: int = 10) -> list[dict]:
        """Retrieve and rerank candidates using neural cross-encoder."""
        # Use API embeddings if already loaded, otherwise fallback to bi_encoder
        embed_method = "api_embed" if "api_embed" in self._retrievers else "bi_encoder"
        self.load([embed_method])
        candidates = self._retrievers[embed_method].search(query, top_k=max(top_k * 5, 40))
        return self._reranker.rerank(query, candidates)[:top_k]

    def _search_hybrid(self, query: str, top_k: int = 10) -> list[dict]:
        self.load(["bm25", "bi_encoder"])
        depth = max(top_k * 8, 80)
        bm25_hits = self._retrievers["bm25"].search(query, top_k=depth)
        bi_hits = self._retrievers["bi_encoder"].search(query, top_k=depth)
        candidates: dict[str, dict] = {}
        bm25_scores: dict[str, float] = {}
        semantic_scores: dict[str, float] = {}
        rank_bonus: dict[str, float] = {}
        sources: dict[str, set[str]] = {}

        for source, score_bucket, hits in [
            ("bm25", bm25_scores, bm25_hits),
            ("bi_encoder", semantic_scores, bi_hits),
        ]:
            for rank, hit in enumerate(hits, 1):
                key = canonical_char(hit["char"])
                candidates.setdefault(key, hit.copy())
                sources.setdefault(key, set()).add(source)
                score_bucket[key] = float(hit.get("score", 0.0))
                rank_bonus[key] = rank_bonus.get(key, 0.0) + (1.0 / (60.0 + rank))

        def normalize(values: dict[str, float]) -> dict[str, float]:
            if not values:
                return {}
            lo, hi = min(values.values()), max(values.values())
            span = hi - lo
            if span <= 1e-12:
                return {k: 0.5 for k in values}  # neutral signal when all scores are equal
            return {k: (v - lo) / span for k, v in values.items()}

        bm25_norm = normalize(bm25_scores)
        semantic_norm = normalize(semantic_scores)

        fused = []
        for key, hit in candidates.items():
            lexical = self._reranker._get_exact_score(query, hit)
            hit["score"] = (
                0.60 * semantic_norm.get(key, 0.0)
                + 0.25 * bm25_norm.get(key, 0.0)
                + 0.10 * lexical
                + 0.05 * rank_bonus.get(key, 0.0)
            )
            hit["base_score"] = semantic_scores.get(key, bm25_scores.get(key, 0.0))
            hit["lexical_score"] = lexical
            hit["sources"] = sorted(sources.get(key, []))
            fused.append(hit)

        fused.sort(key=lambda x: -x["score"])
        for i, hit in enumerate(fused, 1):
            hit["rank"] = i
        return fused[:top_k]

    def _search_mm_hybrid(self, query: str, top_k: int = 10, *, variant: str = "full") -> list[dict]:
        use_visual = variant != "without_visual"
        deps = ["bm25", "bi_encoder"] + (["visual"] if use_visual else [])
        self.load(deps)
        depth = max(top_k * 8, 80)

        bm25_hits = self._retrievers["bm25"].search(query, top_k=depth)
        encoder = self._retrievers["bi_encoder"]
        q_vec = encoder._encode_batch([query])[0]
        semantic_scores_arr = encoder.embeddings @ q_vec
        semantic_hits = self._hits_from_vector_scores(encoder.records, semantic_scores_arr, top_k=depth)
        visual_hits = self._retrievers["visual"].search_with_query_vector(q_vec, top_k=depth) if use_visual else []

        candidates: dict[str, dict] = {}
        bm25_scores: dict[str, float] = {}
        semantic_scores: dict[str, float] = {}
        visual_scores: dict[str, float] = {}
        rank_bonus: dict[str, float] = {}
        sources: dict[str, set[str]] = {}

        source_hits = [
            ("bm25", bm25_scores, bm25_hits),
            ("bi_encoder", semantic_scores, semantic_hits),
        ]
        if use_visual:
            source_hits.append(("visual", visual_scores, visual_hits))

        for source, score_bucket, hits in source_hits:
            for rank, hit in enumerate(hits, 1):
                key = canonical_char(hit["char"])
                candidates.setdefault(key, hit.copy())
                sources.setdefault(key, set()).add(source)
                score_bucket[key] = float(hit.get("score", 0.0))
                rank_bonus[key] = rank_bonus.get(key, 0.0) + (1.0 / (60.0 + rank))

        def normalize(values: dict[str, float]) -> dict[str, float]:
            if not values:
                return {}
            lo, hi = min(values.values()), max(values.values())
            span = hi - lo
            if span <= 1e-12:
                return {k: 0.5 for k in values}
            return {k: (v - lo) / span for k, v in values.items()}

        bm25_norm = normalize(bm25_scores)
        semantic_norm = normalize(semantic_scores)
        visual_norm = normalize(visual_scores)

        weights = {
            "semantic": 0.50,
            "visual": 0.20,
            "bm25": 0.20,
            "lexical": 0.07,
            "rank_bonus": 0.03,
        }
        if variant == "without_visual":
            weights.update({"semantic": 0.60, "visual": 0.0, "bm25": 0.30, "lexical": 0.07, "rank_bonus": 0.03})
        elif variant == "without_lexical":
            weights.update({"semantic": 0.54, "visual": 0.23, "bm25": 0.20, "lexical": 0.0, "rank_bonus": 0.03})

        fused = []
        for key, hit in candidates.items():
            lexical = self._reranker._get_exact_score(query, hit)
            semantic_component = semantic_norm.get(key, 0.0)
            visual_component = visual_norm.get(key, 0.0)
            bm25_component = bm25_norm.get(key, 0.0)
            rank_component = rank_bonus.get(key, 0.0)
            final_score = (
                weights["semantic"] * semantic_component
                + weights["visual"] * visual_component
                + weights["bm25"] * bm25_component
                + weights["lexical"] * lexical
                + weights["rank_bonus"] * rank_component
            )
            hit["score"] = final_score
            hit["base_score"] = semantic_scores.get(key, bm25_scores.get(key, visual_scores.get(key, 0.0)))
            hit["visual_score"] = visual_scores.get(key, 0.0)
            hit["bm25_score"] = bm25_scores.get(key, 0.0)
            hit["lexical_score"] = lexical
            hit["sources"] = sorted(sources.get(key, []))
            hit["fusion_variant"] = variant
            hit["modality_scores"] = {
                "semantic": semantic_component,
                "visual": visual_component,
                "bm25": bm25_component,
                "lexical": lexical,
                "rank_bonus": rank_component,
                "final": final_score,
                "weights": weights,
            }
            fused.append(hit)

        fused.sort(key=lambda x: -x["score"])
        for i, hit in enumerate(fused, 1):
            hit["rank"] = i
        return fused[:top_k]

    @property
    def available_methods(self) -> list[str]:
        return list(self._retrievers.keys())

    # ── convenience: search with all loaded methods ───────────────────────────
    def search_all(self, query: str, top_k: int = 10) -> dict[str, list[dict]]:
        return {m: self.search(query, method=m, top_k=top_k)
                for m in self._retrievers}


# ── quick smoke-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = EmojiSearchEngine()
    engine.load(methods=["bm25", "tfidf"])

    test_queries = ["happy smile", "开心", "cat animal", "爱心", "fire"]
    for q in test_queries:
        print(f"\n{'='*55}\nQuery: {q!r}")
        for m in engine.available_methods:
            hits = engine.search(q, method=m, top_k=5)
            emojis = "  ".join(h["char"] for h in hits)
            print(f"  [{m:5s}] {emojis}")
