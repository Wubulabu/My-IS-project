# Cross-Language Emoji Search System (IS)

一个面向课程与演示的跨语言 Emoji 信息检索系统。支持中文/英文查询，集成词法检索、语义检索、近似近邻与重排序，并提供可视化交互与评估工具。

## 核心能力

- 多算法检索：`BM25`、`TF-IDF`、`Dense`、`Bi-Encoder`、`HNSW`
- 统一检索门面：`search_engine.py` 一次接入，多方法切换
- 重排序增强：`retrieval/reranker.py` 改善首位命中（如 `fire` vs `fire engine`）
- 语义交互：向量算术、语义路径（SLERP）、相似 emoji 探索
- 评估体系：MAP / MRR / NDCG / P@K / R@K
- 数据富化：已完成 2315 条 emoji 的 category 全量补齐（空值 0）

## 当前数据状态

- 主数据集：`data/emoji_dataset.json`
- 记录数：`2315`
- `category` 空值：`0`
- `keywords` 平均长度：`9.72`
- 类别分布：9 大类（People & Body / Objects / Symbols / Flags / ...）

## 项目结构（精简）

```text
IS/
├── app.py                    # Flask API 与服务入口
├── search_engine.py          # 统一检索调度
├── preprocessing.py          # 索引构建
├── data_collection.py        # 初始数据采集
├── clean_data.py             # 数据清洗
├── crawler/
│   ├── enrich_from_unicode.py  # 结构化富化（category/tags）
│   ├── add_manual_categories.py
│   └── merge_data.py
├── retrieval/
│   ├── bm25.py
│   ├── tfidf.py
│   ├── dense.py
│   ├── bi_encoder.py
│   ├── hnsw_retriever.py
│   └── reranker.py
├── eval/
│   ├── metrics.py
│   └── evaluate.py
├── templates/
└── static/
```

## 快速开始

### 1) 安装依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate

pip install flask numpy openai emoji scikit-learn sentence-transformers rank-bm25 torch transformers tabulate

# 或使用固定版本依赖（推荐用于复现实验）
pip install -r requirements.txt
```

### 2) 数据与索引

```bash
python data_collection.py
python clean_data.py

# 富化与合并（已完成可跳过）
python crawler/enrich_from_unicode.py
python crawler/add_manual_categories.py
python crawler/merge_data.py --yes

python preprocessing.py
```

### 3) 启动服务

```bash
python app.py
```

打开：`http://127.0.0.1:5000`

## 评估

```bash
python eval/evaluate.py --all
```

增强版评估（方法级失败不阻塞整体，输出 avg/p50/p95 延迟）：

```bash
python eval/evaluate.py --all
# 若希望任一方法失败时立即停止：
python eval/evaluate.py --all --strict
```

API 延迟基准（用于课程报告中的效率指标）：

```bash
# 先启动服务: python app.py
python eval/benchmark_api.py --runs 3 --top-k 10
```

当前评测池已扩充到 1000 条查询（含原 50 条标注种子）；请以重新运行 `python eval/evaluate.py --all` 的结果为准更新最佳方法与指标。

## 说明

- 课程完整报告见：`report.docx`
- 生产环境请移除硬编码密钥，改用环境变量
