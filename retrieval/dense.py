"""
retrieval/dense.py
------------------
Dense multilingual retrieval using Sentence-Transformers.

Model: paraphrase-multilingual-MiniLM-L12-v2  (118 MB, supports 50+ languages)

At first run the model is downloaded; subsequent runs load from cache.
The emoji embeddings are computed once and cached to data/dense_embeddings.npy.
"""

import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from preprocessing import build_doc_text
from retrieval.cache_utils import build_cache_meta, cache_meta_matches, save_cache_meta

DATA_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATASET   = os.path.join(DATA_DIR, "emoji_dataset.json")
EMB_FILE  = os.path.join(DATA_DIR, "dense_embeddings.npy")

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between query vector a and matrix b."""
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return b_norm @ a_norm


class DenseRetriever:
    """Multilingual dense retrieval with Sentence-Transformers."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name  = model_name
        self.model       = None
        self.embeddings  = None   # shape (N, D)
        self.records     = None

    # ── load ──────────────────────────────────────────────────────────────────
    def load(self):
        from sentence_transformers import SentenceTransformer

        print(f"  [Dense] Loading model: {self.model_name} …")
        self.model = SentenceTransformer(self.model_name)

        with open(DATASET, "r", encoding="utf-8") as f:
            self.records = json.load(f)

        if os.path.exists(EMB_FILE) and cache_meta_matches(EMB_FILE, self._expected_meta(len(self.records))):
            print("  [Dense] Loading cached embeddings …")
            self.embeddings = np.load(EMB_FILE)
        else:
            self._build_embeddings()
        return self

    def _build_embeddings(self):
        """Encode all emoji docs and cache to disk."""
        print(f"  [Dense] Encoding {len(self.records)} emoji docs …")
        corpus = [build_doc_text(r) for r in self.records]
        self.embeddings = self.model.encode(
            corpus,
            batch_size    = 256,
            show_progress_bar = True,
            convert_to_numpy  = True,
        )
        np.save(EMB_FILE, self.embeddings)
        save_cache_meta(EMB_FILE, self._expected_meta(len(self.records)))
        print(f"  [Dense] Embeddings saved → {EMB_FILE}")

    def _expected_meta(self, num_records: int) -> dict:
        return build_cache_meta(
            DATASET,
            kind="dense_embeddings",
            extra={
                "num_records": num_records,
                "model_name": self.model_name,
                "doc_builder": "preprocessing.build_doc_text",
                "normalized": False,
            },
        )

    # ── search ────────────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if self.model is None:
            self.load()

        q_emb  = self.model.encode([query], convert_to_numpy=True)[0]
        scores = cosine_sim(q_emb, self.embeddings)
        top_idxs = np.argsort(-scores)[:top_k]

        results = []
        for rank, idx in enumerate(top_idxs, 1):
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


# ════════════════════════════════════════════════════════════════════════════════
# ─ APIEmbeddingRetriever: SiliconFlow API-based Dense Retrieval (Qwen3)
# ════════════════════════════════════════════════════════════════════════════════

class APIEmbeddingRetriever:
    """
    Dense retrieval using SiliconFlow API (Qwen/Qwen3-Embedding-8B).
    
    Architecture:
      - Uses API for embedding computation (no local model)
      - Maintains local embedding cache for emoji dataset
      - Searches via cosine similarity over cached vectors
      - Lazy loads embeddings on first search()
    
    API Configuration:
      - Model: Qwen/Qwen3-Embedding-8B (768-dim embeddings)
      - Dimensions: 768 (vs 384 for old MiniLM)
      - Language Support: Chinese, English, Multilingual
    """
    
    def __init__(self):
        import os
        self.api_key = os.getenv("SF_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
        self.api_url = os.getenv("SF_BASE_URL", "https://api.siliconflow.cn/v1")
        self.model_name = "Qwen/Qwen3-Embedding-8B"
        self.embeddings = None
        self.records = None
        self.cache_file = EMB_FILE.replace(".npy", "_qwen3_8b.npy")
        
    def _get_embedding_from_api(self, texts: list[str]) -> np.ndarray:
        """Call SiliconFlow API to compute embeddings."""
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model_name,
            "input": texts,
            "encoding_format": "float",
        }
        
        response = requests.post(
            f"{self.api_url}/embeddings",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        embeddings = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            embeddings.append(item["embedding"])
        
        return np.array(embeddings, dtype=np.float32)
    
    def load(self):
        """Load cached embeddings or compute from dataset."""
        import json
        
        with open(DATASET, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.records = data["emojis"] if isinstance(data, dict) and "emojis" in data else data
        if not self.api_key:
            raise RuntimeError("SF_API_KEY or SILICONFLOW_API_KEY is required for api_embed retrieval.")
        
        # Try to load from cache
        if os.path.exists(self.cache_file):
            self.embeddings = np.load(self.cache_file)
            print(f"[APIEmbedding] Loaded {len(self.embeddings)} cached embeddings from {self.cache_file}")
            return self
        
        # Build embeddings from API
        print("[APIEmbedding] Building embeddings using SiliconFlow API...")
        texts = [build_doc_text(r) for r in self.records]
        
        # Batch process to avoid token limits
        batch_size = 100
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            print(f"  Processing batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}...")
            batch_embeddings = self._get_embedding_from_api(batch)
            all_embeddings.append(batch_embeddings)
        
        self.embeddings = np.vstack(all_embeddings) if all_embeddings else np.array([])
        
        # Cache to disk
        np.save(self.cache_file, self.embeddings)
        print(f"[APIEmbedding] Cached {len(self.embeddings)} embeddings to {self.cache_file}")
        
        return self
    
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Search using API embedding + local cosine similarity."""
        if self.embeddings is None:
            self.load()
        
        # Encode query using API
        q_emb = self._get_embedding_from_api([query])[0]
        
        # Cosine similarity search
        scores = cosine_sim(q_emb, self.embeddings)
        top_idxs = np.argsort(-scores)[:top_k]
        
        results = []
        for rank, idx in enumerate(top_idxs, 1):
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
    ret = DenseRetriever().load()
    for q in ["happy smile", "开心 笑脸", "可爱的猫", "fire flames"]:
        hits = ret.search(q, top_k=5)
        print(f"\nQuery: {q!r}")
        for h in hits:
            print(f"  {h['rank']}. {h['char']}  {h['en']!r:30s} score={h['score']:.4f}")
