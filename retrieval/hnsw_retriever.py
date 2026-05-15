"""
retrieval/hnsw_retriever.py
---------------------------
HNSW（分层导航小世界）近似最近邻检索 —— 纯 Python/NumPy 实现。

无需 C++ 编译器，完整展示 HNSW 算法核心逻辑，适用于学术演示。

HNSW 算法原理
------------
HNSW（Hierarchical Navigable Small World Graph）由 Malkov & Yashunin (2018)
提出，核心思想来自两个观察：

  1. NSW（导航小世界图）：在欧氏/余弦空间中，局部连接近邻能产生"小世界"
     性质（平均路径长度为 O(log N)），因此贪心图搜索非常高效。
  2. 层次化（Hierarchical）：通过多层图（类似跳表/Skip-List），顶层图稀疏，
     包含长程"快捷"边，底层图稠密，精确描述邻域关系。

查询时从最顶层入口贪心下降，每层收缩候选集，直到底层精细定位 Top-K：
  - 构建复杂度: O(N · M · log N)
  - 查询复杂度: O(log N)    vs. 暴力 KNN 的 O(N · d)
  - 典型 Recall@10: >95%（ef=100 时）

本实现采用简化的单层 NSW + 暴力查询切换方案：
  • 构建阶段用 HNSW 图结构（M 个近邻边）
  • 查询阶段用 ef-search 最大堆扩展候选集
  • 提供 recall_vs_exact() 验证 ANN 精度

Reference: Malkov, Y.A. & Yashunin, D.A. (2020). Efficient and robust
approximate nearest neighbor search using Hierarchical Navigable Small
World graphs. IEEE Trans. on PAMI.
"""

import heapq
import json
import os
import random
import sys
import math
from typing import List, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from retrieval.cache_utils import build_cache_meta, cache_meta_matches, file_sha256, save_cache_meta

DATA_DIR  = os.path.dirname(os.path.dirname(__file__))
DATA_D    = os.path.join(DATA_DIR, "data")
DATASET   = os.path.join(DATA_D, "emoji_dataset.json")
EMB_FILE  = os.path.join(DATA_D, "bi_encoder_embeddings.npy")
HNSW_PKL  = os.path.join(DATA_D, "hnsw_graph.pkl")


# ── 纯 Python HNSW 核心 ───────────────────────────────────────────────────────
class HNSW:
    """
    分层导航小世界图（Hierarchical Navigable Small World）

    核心数据结构
    -----------
    layers  : list[dict[int, list[int]]]
              layers[lc][node_id] = [neighbor_id, ...]
    embeddings: np.ndarray  (N, D) ── 所有向量（已 L2 归一化）
    entry_point: int        ── 当前最高层的入口节点
    max_layer  : int        ── 当前最大层号

    关键超参数
    ----------
    M          : 每个节点在底层（layer 0）的最大边数
    M0         : 层 0 的最大边数（通常 2*M）
    mL         : 用于随机化层级选择的归一化因子（= 1 / ln(M)）
    ef_construction: 构建时搜索候选集大小（建图质量 vs. 速度权衡）
    ef_search  : 查询时搜索候选集大小（精度 vs. 速度权衡）
    """

    def __init__(self, M: int = 16, ef_construction: int = 100,
                 ef_search: int = 500):
        self.M               = M
        self.M0              = 2 * M     # 底层最大连接数
        self.mL              = 1.0 / math.log(M)   # 层级衰减因子
        self.ef_construction = ef_construction
        self.ef_search       = ef_search

        self.embeddings  : np.ndarray | None = None
        self.layers      : list[dict]  = []   # list of {node_id: [neighbor_ids]}
        self.entry_point : int         = -1
        self.max_layer   : int         = -1

    # ── 相似度 ─────────────────────────────────────────────────────────────────
    def _sim(self, i: int, j: int) -> float:
        """余弦相似度（已归一化向量 → 直接点积）。"""
        return float(self.embeddings[i] @ self.embeddings[j])

    def _sim_vec(self, q: np.ndarray, idx: int) -> float:
        """查询向量 q 与节点 idx 的相似度。"""
        return float(q @ self.embeddings[idx])

    # ── 层级随机化（HNSW 核心设计之一）──────────────────────────────────────────
    def _random_level(self) -> int:
        """
        为新节点随机指定最高层级 l。
        概率分布：P(l = k) = exp(-k / mL) · (1 - exp(-1 / mL))
        使得越高层节点越稀疏，形成类 Skip-List 的金字塔结构。
        """
        level = 0
        while random.random() < math.exp(-1.0 / self.mL) and level < 16:
            level += 1
        return level

    # ── ef 搜索（带候选队列的贪心搜索） ──────────────────────────────────────────
    def _search_layer(self, q: np.ndarray, entry: int, ef: int,
                      layer: int) -> List[Tuple[float, int]]:
        """
        在指定层中，从 entry 节点出发，用扩展候选集 ef 搜索最近邻。

        返回: 按相似度降序排列的 (sim, node_id) 最大堆列表

        算法：
          1. 初始化候选集 C（最小堆，按 -sim 排序）和结果集 W（最大堆）
          2. 反复从 C 弹出当前最优候选节点 c
          3. 遍历 c 的所有邻居 e（当前层）
          4. 若 sim(q,e) > W 中最差节点的相似度，将 e 加入 C 和 W
          5. 当 |W| 超过 ef 时，弹出最差元素
          6. 返回 W 作为候选结果
        """
        if entry not in self.layers[layer]:
            return []

        init_sim = self._sim_vec(q, entry)
        # C: min-heap by (-sim, id) ── 待探索候选集
        C = [(-init_sim, entry)]
        # W: max-heap by (sim, id) ── 当前最优结果集（用负号模拟最大堆）
        W = [(init_sim, entry)]
        visited = {entry}

        while C:
            neg_c_sim, c = heapq.heappop(C)
            c_sim = -neg_c_sim

            # 当 c 比 W 中最差元素还差时，提前终止
            if c_sim < W[0][0] and len(W) >= ef:
                break

            for e in self.layers[layer].get(c, []):
                if e in visited:
                    continue
                visited.add(e)
                e_sim = self._sim_vec(q, e)
                if e_sim > W[0][0] or len(W) < ef:
                    heapq.heappush(C, (-e_sim, e))
                    # W 用最小堆模拟，存 (sim, id)
                    heapq.heappush(W, (e_sim, e))
                    if len(W) > ef:
                        heapq.heappop(W)

        return sorted(W, reverse=True)   # 降序 (sim, id)

    # ── 添加单个向量 ─────────────────────────────────────────────────────────────
    def add_item(self, new_id: int):
        """将 new_id 节点按 HNSW 算法插入图中。"""
        l = self._random_level()                       # 随机目标层
        q = self.embeddings[new_id]

        # 扩展层列表
        while len(self.layers) <= l:
            self.layers.append({})

        if self.entry_point == -1:
            # 图为空，设为入口
            for lc in range(l + 1):
                self.layers[lc][new_id] = []
            self.entry_point = new_id
            self.max_layer   = l
            return

        ep   = self.entry_point
        # 从最顶层下降到 l+1 层（贪心 greedy descent，每层 ef=1）
        for lc in range(self.max_layer, l, -1):
            if lc < len(self.layers):
                candidates = self._search_layer(q, ep, ef=1, layer=lc)
                if candidates:
                    ep = candidates[0][1]

        # 从层 l 到层 0，逐层插入
        for lc in range(min(l, self.max_layer), -1, -1):
            if lc >= len(self.layers):
                self.layers.append({})

            M_lc = self.M0 if lc == 0 else self.M
            candidates = self._search_layer(
                q, ep, ef=self.ef_construction, layer=lc
            )
            # 选最近的 M_lc 个节点作为邻居
            neighbors = [c[1] for c in candidates[:M_lc] if c[1] != new_id]

            self.layers[lc].setdefault(new_id, [])
            for nb in neighbors:
                self.layers[lc][new_id].append(nb)
                self.layers[lc].setdefault(nb, []).append(new_id)
                # 裁剪 nb 的边数，保持 ≤ M_lc
                if len(self.layers[lc][nb]) > M_lc:
                    # 保留离 nb 最近的 M_lc 条边
                    nb_vec = self.embeddings[nb]
                    self.layers[lc][nb] = sorted(
                        self.layers[lc][nb],
                        key=lambda x: -(nb_vec @ self.embeddings[x]),
                    )[:M_lc]

            if candidates:
                ep = candidates[0][1]

        # 更新入口节点
        if l > self.max_layer:
            self.max_layer   = l
            self.entry_point = new_id

    # ── 批量构建 ──────────────────────────────────────────────────────────────
    def build(self, embeddings: np.ndarray):
        """
        逐节点插入构建 HNSW 图。
        embeddings: (N, D) 已 L2 归一化的向量矩阵
        """
        self.embeddings = embeddings.astype(np.float32)
        N = len(embeddings)
        print(f"  [HNSW] 构建图: {N} 个节点, M={self.M}, "
              f"ef_construction={self.ef_construction} …")
        for i in range(N):
            self.add_item(i)
            if i % 500 == 0 and i > 0:
                print(f"    进度: {i}/{N}")
        print(f"  [HNSW] 图构建完成, 层数: {self.max_layer + 1}")

    # ── 查询 ──────────────────────────────────────────────────────────────────
    def query(self, q: np.ndarray, top_k: int) -> List[Tuple[float, int]]:
        """
        HNSW 图查询。

        1. 从最顶层贪心下降（ef=1）到层 1
        2. 在底层（layer 0）用 ef_search 精细搜索

        时间复杂度 O(ef · M · log N) ≈ O(log N)

        Returns
        -------
        list of (sim, node_id) 降序排列
        """
        if self.entry_point == -1:
            return []
        q = q.astype(np.float32)
        ep = self.entry_point

        # 从顶层贪心下降到第 1 层
        for lc in range(self.max_layer, 0, -1):
            if lc < len(self.layers):
                candidates = self._search_layer(q, ep, ef=1, layer=lc)
                if candidates:
                    ep = candidates[0][1]

        # 底层精细搜索（ef = ef_search）
        candidates = self._search_layer(q, ep, ef=self.ef_search, layer=0)
        return candidates[:top_k]


# ── 检索器包装类 ───────────────────────────────────────────────────────────────
class HNSWRetriever:
    """
    基于纯 Python HNSW 实现的近似最近邻 Emoji 检索器。

    特点
    ----
    - 无需 C++ 编译器，纯 NumPy/heapq 实现
    - HNSW 图构建后持久化到 data/hnsw_graph.pkl
    - 查询时复杂度 O(log N)，通过 recall_vs_exact() 验证召回率
    """

    def __init__(self, M: int = 16, ef_construction: int = 80,
                 ef_search: int = 500):
        self.hnsw       = HNSW(M=M, ef_construction=ef_construction,
                               ef_search=ef_search)
        self.M = M
        self.ef_construction = ef_construction
        self.ef_search = ef_search
        self.records    = None
        self._encoder   = None

    def _lazy_encoder(self):
        """懒加载查询编码器（Bi-Encoder 只需要 tokenizer + model）。"""
        if self._encoder is None:
            from retrieval.bi_encoder import BiEncoderRetriever
            enc = BiEncoderRetriever()
            from transformers import AutoTokenizer, AutoModel
            from retrieval.bi_encoder import MODEL_NAME
            enc.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            enc.model     = AutoModel.from_pretrained(MODEL_NAME).to(enc.device)
            enc.model.eval()
            self._encoder = enc
        return self._encoder

    # ── load ──────────────────────────────────────────────────────────────────
    def load(self):
        """加载 Emoji 记录、向量和 HNSW 图索引。"""
        # 确保 Bi-Encoder 向量存在
        if not os.path.exists(EMB_FILE):
            print("  [HNSW] 未发现 Bi-Encoder 向量，先构建 …")
            from retrieval.bi_encoder import BiEncoderRetriever
            BiEncoderRetriever().load()

        with open(DATASET, "r", encoding="utf-8") as f:
            self.records = json.load(f)

        embeddings = np.load(EMB_FILE).astype(np.float32)

        if os.path.exists(HNSW_PKL) and cache_meta_matches(HNSW_PKL, self._expected_meta(len(self.records), embeddings)):
            print("  [HNSW] 加载缓存图索引 …")
            with open(HNSW_PKL, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.hnsw.layers       = [{int(k): v for k, v in layer.items()}
                                      for layer in state["layers"]]
            self.hnsw.entry_point  = state["entry_point"]
            self.hnsw.max_layer    = state["max_layer"]
            self.hnsw.M            = state["M"]
            self.hnsw.M0           = state["M0"]
            self.hnsw.mL           = state["mL"]
            self.hnsw.ef_search    = self.ef_search
            self.hnsw.ef_construction = state["ef_construction"]
            self.hnsw.embeddings   = embeddings
        else:
            self.hnsw.build(embeddings)
            # 序列化图结构为 plain dict（避免 pickle 类绑定问题）
            state = {
                "layers"      : [{str(k): v for k, v in layer.items()}
                                  for layer in self.hnsw.layers],
                "entry_point" : self.hnsw.entry_point,
                "max_layer"   : self.hnsw.max_layer,
                "M"           : self.hnsw.M,
                "M0"          : self.hnsw.M0,
                "mL"          : self.hnsw.mL,
                "ef_search"   : self.hnsw.ef_search,
                "ef_construction": self.hnsw.ef_construction,
            }
            with open(HNSW_PKL, "w", encoding="utf-8") as f:
                json.dump(state, f, separators=(",", ":"))
            save_cache_meta(HNSW_PKL, self._expected_meta(len(self.records), embeddings))
            print(f"  [HNSW] 图索引已保存 → {HNSW_PKL}")

        print(f"  [HNSW] 就绪: {len(self.records)} 个节点, "
              f"层数={self.hnsw.max_layer + 1}, ef_search={self.hnsw.ef_search}")
        return self

    def _expected_meta(self, num_records: int, embeddings: np.ndarray) -> dict:
        return build_cache_meta(
            DATASET,
            kind="hnsw_graph",
            extra={
                "num_records": num_records,
                "embedding_file": os.path.basename(EMB_FILE),
                "embedding_sha256": file_sha256(EMB_FILE),
                "embedding_shape": list(embeddings.shape),
                "M": self.M,
                "ef_construction": self.ef_construction,
            },
        )

    # ── 搜索 ──────────────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        HNSW 近似最近邻搜索。

        1. Bi-Encoder 在线编码 query → V_q（L2 归一化）
        2. HNSW 图查询（O(log N)）返回近似 Top-K
        3. 转换为 Emoji 结果列表
        """
        if self.records is None:
            self.load()

        enc   = self._lazy_encoder()
        q_vec = enc._encode_batch([query])[0]   # (D,) L2 归一化

        hits  = self.hnsw.query(q_vec.astype(np.float32), top_k=top_k)

        results = []
        for rank, (score, idx) in enumerate(hits, 1):
            r = self.records[idx]
            results.append({
                "rank"      : rank,
                "score"     : float(score),
                "char"      : r["char"],
                "codepoint" : r["codepoint"],
                "en"        : r["en"],
                "zh"        : r["zh"],
                "ja"        : r.get("ja", ""),
                "keywords"  : r["keywords"],
                "category"  : r["category"],
            })
        return results

    # ── ANN vs 精确 KNN 召回率验证 ───────────────────────────────────────────
    def recall_vs_exact(self, n_queries: int = 200, K: int = 10) -> float:
        """
        评测 HNSW ANN 相对于暴力精确 KNN 的 Top-K 召回率。

        Recall@K = |ANN_TopK ∩ Exact_TopK| / K

        Returns
        -------
        float : 平均 Recall@K（通常 >90%）
        """
        emb = self.hnsw.embeddings
        rng = np.random.default_rng(42)
        q_vecs = emb[rng.choice(len(emb), n_queries, replace=False)]
        recalls = []

        for q in q_vecs:
            # 精确 KNN（暴力）
            exact_scores = emb @ q.astype(np.float64)
            exact_top    = set(np.argsort(-exact_scores)[:K])
            # HNSW ANN
            hits    = self.hnsw.query(q, top_k=K)
            ann_top = {h[1] for h in hits}
            recalls.append(len(exact_top & ann_top) / K)

        mean_recall = float(np.mean(recalls))
        print(f"  [HNSW] Recall@{K} (ANN vs Exact KNN): "
              f"{mean_recall:.4f}  ({n_queries} 个随机查询)")
        return mean_recall


# ── 快速测试 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hnsw = HNSWRetriever(M=16, ef_construction=80, ef_search=50)
    hnsw.load()
    hnsw.recall_vs_exact()
    for q in ["happy smile", "大哭 难过", "fire flame", "cute cat"]:
        hits = hnsw.search(q, top_k=5)
        emojis = "  ".join(f"{h['char']}({h['score']:.3f})" for h in hits)
        print(f"  [{q}] → {emojis}")
