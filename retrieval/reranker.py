"""
Lightweight lexical reranking for emoji search.

This is deliberately not a neural cross-encoder.  It is a bounded lexical
adjustment layer used after candidate recall, mainly to improve exact-name
queries such as "fire" without overwhelming semantic ranking.
"""

from __future__ import annotations

import re


def _norm(text: str) -> str:
    return (text or "").lower().strip()


class LexicalBoostReranker:
    """Blend normalized candidate scores with exact/containment lexical signals."""

    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.model_name = model_name
        self.device = device
        self.model = True

    def load(self):
        return self

    def _get_exact_score(self, query: str, rec: dict) -> float:
        q = _norm(query)
        if not q:
            return 0.0

        en = _norm(rec.get("en", ""))
        zh = _norm(rec.get("zh", ""))
        aliases = [_norm(a) for a in rec.get("aliases", [])]
        keywords = [_norm(k) for k in rec.get("keywords", [])]
        zh_parts = [p for p in zh.split() if p]
        zh0 = zh_parts[0] if zh_parts else ""

        if q in {en, zh, zh0} or q in aliases:
            return 1.0

        if q in keywords or q in zh_parts:
            return 0.75

        en_words = [w for w in re.split(r"[^a-z0-9]+", en) if w]
        if q in en_words:
            return 0.65

        if en.startswith(q + " ") or zh.startswith(q):
            return 0.45

        if len(q) >= 2 and (q in en or q in zh):
            target = en if q in en else zh
            return min(0.40, len(q) / max(len(target), 1))

        if len(q) == 1 and q in zh:
            return 0.20

        return 0.0

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        *,
        semantic_weight: float = 1.0,
        lexical_weight: float = 0.20,
    ) -> list[dict]:
        if not candidates:
            return []

        raw_scores = [float(c.get("score", 0.0)) for c in candidates]
        lo, hi = min(raw_scores), max(raw_scores)
        span = hi - lo

        reranked = []
        for c in candidates:
            semantic = float(c.get("score", 0.0))
            if span > 1e-12:
                semantic_norm = (semantic - lo) / span
            else:
                semantic_norm = semantic

            lexical = self._get_exact_score(query, c)
            combined = semantic_weight * semantic_norm + lexical_weight * lexical

            out = c.copy()
            out["score"] = float(combined)
            out["base_score"] = semantic
            out["lexical_score"] = lexical
            reranked.append(out)

        reranked.sort(key=lambda x: -x["score"])
        for i, r in enumerate(reranked, 1):
            r["rank"] = i
        return reranked


# Backward-compatible name used by app.py and older tests.
CrossEncoderRetriever = LexicalBoostReranker


# ════════════════════════════════════════════════════════════════════════════════
# ─ NeuralReranker: SiliconFlow API-based Cross-Encoder Reranking (Qwen3)
# ════════════════════════════════════════════════════════════════════════════════

class NeuralReranker:
    """
    Neural cross-encoder reranking using SiliconFlow API (Qwen/Qwen3-Reranker-8B).
    
    Architecture:
      - Uses API for relevance scoring (no local model)
      - Scores all candidates in parallel batches
      - Better semantic understanding than lexical rules
      - Language-agnostic (works for Chinese, English, multilingual)
    
    API Configuration:
      - Model: Qwen/Qwen3-Reranker-8B
      - Input: [query, document] pairs
      - Output: Relevance scores [0.0-1.0]
    """
    
    def __init__(self):
        import os
        self.api_key = os.getenv("SF_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
        self.api_url = os.getenv("SF_BASE_URL", "https://api.siliconflow.cn/v1")
        self.model_name = "Qwen/Qwen3-Reranker-8B"
        self._fallback = LexicalBoostReranker()
    
    def load(self):
        return self
    
    def _get_exact_score(self, query: str, rec: dict) -> float:
        """
        Fallback lexical scoring for hybrid search compatibility.
        Uses same logic as LexicalBoostReranker.
        """
        q = _norm(query)
        if not q:
            return 0.0

        en = _norm(rec.get("en", ""))
        zh = _norm(rec.get("zh", ""))
        aliases = [_norm(a) for a in rec.get("aliases", [])]
        keywords = [_norm(k) for k in rec.get("keywords", [])]
        zh_parts = [p for p in zh.split() if p]
        zh0 = zh_parts[0] if zh_parts else ""

        if q in {en, zh, zh0} or q in aliases:
            return 1.0
        if q in keywords or q in zh_parts:
            return 0.75
        en_words = [w for w in re.split(r"[^a-z0-9]+", en) if w]
        if q in en_words:
            return 0.65
        if en.startswith(q + " ") or zh.startswith(q):
            return 0.45
        if len(q) >= 2 and (q in en or q in zh):
            target = en if q in en else zh
            return min(0.40, len(q) / max(len(target), 1))
        if len(q) == 1 and q in zh:
            return 0.20
        return 0.0

    def _get_rerank_scores_from_api(self, query: str, candidates: list[str]) -> list[float]:
        """Call SiliconFlow API to compute relevance scores."""
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Build pairs: [query, document]
        pairs = [[query, doc] for doc in candidates]
        
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": candidates,
        }
        
        response = requests.post(
            f"{self.api_url.rstrip('/')}/rerank",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        scores = [0.0] * len(candidates)
        
        for result in data["results"]:
            idx = result["index"]
            score = result["relevance_score"]
            scores[idx] = float(score)
        
        return scores
    
    def rerank(
        self,
        query: str,
        candidates: list[dict],
        *,
        semantic_weight: float = 1.0,
        lexical_weight: float = 0.0,  # Not used in neural mode
    ) -> list[dict]:
        """Rerank candidates using neural cross-encoder."""
        if not candidates:
            return []

        if not self.api_key:
            return self._fallback.rerank(
                query,
                candidates,
                semantic_weight=semantic_weight,
                lexical_weight=0.20,
            )
        
        # Build document representations
        docs = []
        for c in candidates:
            en = c.get("en", "")
            zh = c.get("zh", "")
            char = c.get("char", "")
            keywords = " ".join(c.get("keywords", []))
            doc = f"{char} {en} {zh} {keywords}".strip()
            docs.append(doc)
        
        # Get scores from API. Keep retrieval usable if the remote rerank API
        # is unavailable, misconfigured, or rate-limited.
        try:
            scores = self._get_rerank_scores_from_api(query, docs)
        except Exception:
            return self._fallback.rerank(
                query,
                candidates,
                semantic_weight=semantic_weight,
                lexical_weight=0.20,
            )
        
        # Combine with original scores
        reranked = []
        for i, c in enumerate(candidates):
            neural_score = scores[i] if i < len(scores) else 0.0
            base_score = float(c.get("score", 0.0))
            
            # Blend: neural score dominates, but preserve some base signal
            combined = semantic_weight * neural_score * 0.8 + 0.2 * base_score
            
            out = c.copy()
            out["score"] = float(combined)
            out["base_score"] = base_score
            out["neural_score"] = neural_score
            reranked.append(out)
        
        reranked.sort(key=lambda x: -x["score"])
        for i, r in enumerate(reranked, 1):
            r["rank"] = i
        return reranked
