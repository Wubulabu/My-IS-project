"""
retrieval/bi_encoder.py
-----------------------
完整的双编码器（Bi-Encoder）稠密向量检索算法实现。

算法原理
--------
采用 Siamese Network 架构（孪生网络），文档端和查询端共享同一个
Transformer 编码器权重，分别离线/在线映射到同一高维连续语义空间，
再通过余弦相似度完成排序。

阶段 1 ── 离线向量化（Offline Indexing）
  - 对每个 Emoji 描述 d_i，输入多语言 Transformer 模型
  - 多头自注意力机制输出 Token 隐藏状态矩阵 H ∈ R^{L×d_model}
  - 均值池化（Mean Pooling）：V_{d_i} = (1/L) * Σ h_t  (考虑 attention mask)
  - 得到定长向量 V_{d_i} ∈ R^{384}，缓存到磁盘

阶段 2 ── 在线查询映射（Online Query Encoding）
  - 用户输入 q → 同一 Transformer + Mean Pooling → V_q ∈ R^{384}

阶段 3 ── 余弦相似度 & Top-K 排序（Scoring & Ranking）
  - Score(q, d_i) = (V_q · V_{d_i}) / (‖V_q‖ · ‖V_{d_i}‖)
  - 对所有 N 个文档降序排列，返回 Top-K（暴力精确 KNN，O(N·d)）
"""

import json, os, sys
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from preprocessing import build_doc_text
from retrieval.cache_utils import build_cache_meta, cache_meta_matches, save_cache_meta

DATA_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATASET   = os.path.join(DATA_DIR, "emoji_dataset.json")
EMB_FILE  = os.path.join(DATA_DIR, "bi_encoder_embeddings.npy")

# 使用多语言 MiniLM（384维，支持50+语言）
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


# ── 核心：均值池化 ─────────────────────────────────────────────────────────────
def mean_pooling(model_output, attention_mask: torch.Tensor) -> torch.Tensor:
    """
    均值池化（Mean Pooling with Attention Mask Weighting）

    公式：V = Σ(h_t * mask_t) / Σ(mask_t)
    其中 mask_t ∈ {0,1}，对 [PAD] token 赋零权重，
    确保填充不影响句向量的语义中心。

    Parameters
    ----------
    model_output : BaseModelOutputWithPoolingAndCrossAttentions
        Transformer 模型输出。取 model_output[0] 即 Token 隐藏状态矩阵
        H ∈ R^{batch_size × seq_len × hidden_dim}
    attention_mask : torch.Tensor
        形状 (batch_size, seq_len)，1=真实 token，0=padding

    Returns
    -------
    torch.Tensor : shape (batch_size, hidden_dim)，每个样本的句向量
    """
    token_embeddings = model_output[0]               # (B, L, D)
    # 将 mask 扩展到与嵌入矩阵同维，方便逐元素相乘
    expanded_mask = attention_mask.unsqueeze(-1).expand(
        token_embeddings.size()
    ).float()
    # 加权求和 / mask 求和 → 得到 (B, D) 的归一化句向量
    sum_embeddings = torch.sum(token_embeddings * expanded_mask, dim=1)
    sum_mask       = torch.clamp(expanded_mask.sum(dim=1), min=1e-9)
    return sum_embeddings / sum_mask


# ── L2-归一化（方便快速余弦相似度计算）────────────────────────────────────────
def l2_normalize(v: np.ndarray) -> np.ndarray:
    """对最后一维做 L2 归一化，使余弦相似度退化为点积（更快）。"""
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(norms, 1e-10)


# ── 主类 ──────────────────────────────────────────────────────────────────────
class BiEncoderRetriever:
    """
    双编码器精确 KNN 检索器。

    特点
    ----
    - 直接使用 HuggingFace transformers，显式实现 Mean Pooling
    - 离线向量归一化，查询时仅做矩阵点乘（O(N·d)）
    - 支持 GPU（若可用）
    """

    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = 128):
        self.model_name = model_name
        self.batch_size = batch_size
        self.tokenizer  = None
        self.model      = None
        self.embeddings = None   # numpy (N, D)，已 L2 归一化
        self.records    = None
        self.device     = "cuda" if torch.cuda.is_available() else "cpu"

    # ── load / build ──────────────────────────────────────────────────────────
    def load(self):
        """加载模型与 Emoji 描述向量（如已缓存则直接读取）。"""
        print(f"  [BiEncoder] 设备: {self.device}")
        print(f"  [BiEncoder] 加载模型: {self.model_name} …")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model     = AutoModel.from_pretrained(self.model_name).to(self.device)
        self.model.eval()

        with open(DATASET, "r", encoding="utf-8") as f:
            self.records = json.load(f)

        if os.path.exists(EMB_FILE) and cache_meta_matches(EMB_FILE, self._expected_meta(len(self.records))):
            print("  [BiEncoder] 加载缓存向量 …")
            self.embeddings = np.load(EMB_FILE)
        else:
            self._build_embeddings()
        return self

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        """
        对一批文本进行 Tokenize → Transformer → Mean Pooling → L2 Normalize。
        返回形状 (batch, hidden_dim) 的 numpy 数组。
        """
        encoded = self.tokenizer(
            texts,
            padding        = True,
            truncation     = True,
            max_length     = 128,
            return_tensors = "pt",
        ).to(self.device)

        with torch.no_grad():
            output = self.model(**encoded)

        # Mean Pooling（核心步骤）
        vecs = mean_pooling(output, encoded["attention_mask"])
        vecs = vecs.cpu().numpy()
        return l2_normalize(vecs)   # 归一化后点积 = 余弦相似度

    def _build_embeddings(self):
        """离线编码全部 Emoji 文档并缓存。"""
        print(f"  [BiEncoder] 离线编码 {len(self.records)} 个 Emoji 文档 …")
        corpus = [build_doc_text(r) for r in self.records]
        all_vecs = []

        for i in range(0, len(corpus), self.batch_size):
            batch = corpus[i: i + self.batch_size]
            vecs  = self._encode_batch(batch)
            all_vecs.append(vecs)

            if (i // self.batch_size) % 5 == 0:
                print(f"    进度: {min(i + self.batch_size, len(corpus))}"
                      f"/{len(corpus)}")

        self.embeddings = np.vstack(all_vecs)   # (N, D)
        np.save(EMB_FILE, self.embeddings)
        save_cache_meta(EMB_FILE, self._expected_meta(len(self.records)))
        print(f"  [BiEncoder] 向量缓存 → {EMB_FILE}")
        print(f"  [BiEncoder] 向量矩阵形状: {self.embeddings.shape}")

    def _expected_meta(self, num_records: int) -> dict:
        return build_cache_meta(
            DATASET,
            kind="bi_encoder_embeddings",
            extra={
                "num_records": num_records,
                "model_name": self.model_name,
                "doc_builder": "preprocessing.build_doc_text",
                "max_length": 128,
                "pooling": "mean_pooling_attention_mask",
                "normalized": True,
            },
        )

    # ── 查询 ─────────────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        在线查询:
          1. 将 query 映射到同一语义空间 → V_q ∈ R^{384}
          2. 暴力 KNN：Score(q,d) = V_q · V_d（已归一化 = cosine）
          3. Top-K 降序排列返回

        时间复杂度 O(N · d)，N=5225，d=384，约 2M 次浮点乘法。
        """
        if self.model is None:
            self.load()

        # 阶段2：在线查询编码（Online Query Encoding）
        q_vec  = self._encode_batch([query])[0]          # (D,)

        # 阶段3：余弦相似度（退化为点积，因已 L2 归一化）
        # Score(q, d_i) = V_q · V_{d_i} / (‖V_q‖ · ‖V_{d_i}‖)
        #               = V_q · V_{d_i}  （归一化后）
        scores   = self.embeddings @ q_vec                # (N,)

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


# ── 快速测试 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ret = BiEncoderRetriever().load()
    for q in ["happy smile", "快气死了", "大哭 破防", "火焰 燃烧", "cute cat"]:
        hits = ret.search(q, top_k=5)
        emojis = "  ".join(f"{h['char']}({h['score']:.3f})" for h in hits)
        print(f"  [{q}] → {emojis}")
