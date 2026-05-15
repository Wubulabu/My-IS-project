"""
app.py
------
Flask web application for the Cross-Language Emoji Search System.

Routes
------
  GET  /                  → main search page
  POST /api/search        → JSON search endpoint (supports exclude[] filter)
  POST /api/vector_math   → vector arithmetic: "king - man + woman"
  GET  /api/eval          → run evaluation and return JSON
  GET  /api/status        → system status JSON
"""

import os, sys, json, re, time
import numpy as np
import traceback
from collections import deque
import concurrent.futures
import threading
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from search_engine import EmojiSearchEngine
from retrieval.reranker import CrossEncoderRetriever, NeuralReranker
from retrieval.dense import APIEmbeddingRetriever
from openai import OpenAI
from preprocessing import tokenize


def _load_local_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_local_env_file()

app    = Flask(__name__)
# Global sentiment tracker: stores last 100 queries
recent_queries = deque(maxlen=100)
_RECORD_CACHE = None
# SiliconFlow API Config (Semantic Consensus Center Agent)
SF_API_KEY = os.getenv("SF_API_KEY") or os.getenv("SILICONFLOW_API_KEY") or ""
SF_BASE_URL = "https://api.siliconflow.cn/v1"

# --- Model Tier Strategy ---
# DEEP_MODEL: heavier JSON/report generation.
DEEP_MODEL = os.getenv("OMNIMOJI_DEEP_MODEL", "Qwen/Qwen2.5-32B-Instruct")
# FAST_MODEL: low-latency single-turn tasks (labels, selections, narrative).
# Using 7B model for better speed/quality balance.
FAST_MODEL = os.getenv("OMNIMOJI_FAST_MODEL", "Qwen/Qwen2.5-7B-Instruct")
# INSPIRATION_MODEL: used for magic story generation.
INSPIRATION_MODEL = os.getenv("OMNIMOJI_INSPIRATION_MODEL", FAST_MODEL)
# Default export for legacy references
SF_MODEL = DEEP_MODEL

# --- Retrieval Model Strategy (Qwen3 Neural Retrieval) ---
# EMBEDDING_MODEL: Advanced multilingual semantic embeddings
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"
# RERANKER_MODEL: Neural cross-encoder reranking
RERANKER_MODEL = "Qwen/Qwen3-Reranker-8B"

# Evaluation Algorithms List (core IR methods for fair comparison)
EVAL_METHODS = ["bm25", "tfidf", "bi_encoder", "rerank", "hybrid"]


def _clean_short_story(text: str, fallback: str, *, max_chars: int = 60) -> str:
    """Normalize model output into one compact, emoji-free Chinese sentence."""
    text = (text or "").strip()
    if not text:
        return fallback

    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^[\"'“”‘’\s]*(?:短故事|故事|灵感|标题)[:：]\s*", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\uFE0F]+", "", text)
    text = re.sub(r"\s+", "", text)
    if not text:
        return fallback

    parts = re.split(r"(?<=[。！？!?])", text)
    text = next((p.strip() for p in parts if p.strip()), text)
    text = text.strip("\"'“”‘’")
    if len(text) > max_chars:
        text = text[:max_chars].rstrip("，、；：,.。！？!? ") + "。"
    elif not text.endswith(("。", "！", "？", "!", "?")):
        text += "。"
    return text


def _story_has_enough_clauses(text: str, *, min_commas: int = 2, max_chars: int = 60) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if len(text) > max_chars:
        return False
    return text.count("，") >= min_commas


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_metric(value: float) -> str:
    return f"{value:.3f}"


def _build_local_committee_verdict(metrics: list[dict], *, note: str = "") -> dict:
    methods: list[dict] = []
    for item in metrics or []:
        method = str(item.get("method", "")).strip() or "unknown"
        metric_map = item.get("metrics") or {}
        methods.append({
            "method": method,
            "map": _to_float(metric_map.get("MAP")),
            "mrr": _to_float(metric_map.get("MRR")),
            "ndcg10": _to_float(metric_map.get("NDCG@10")),
            "p5": _to_float(metric_map.get("P@5")),
            "p10": _to_float(metric_map.get("P@10")),
            "r10": _to_float(metric_map.get("R@10")),
        })

    if methods:
        champion = max(methods, key=lambda row: (row["map"], row["mrr"], row["ndcg10"]))
    else:
        champion = {
            "method": "hybrid",
            "map": 0.0,
            "mrr": 0.0,
            "ndcg10": 0.0,
            "p5": 0.0,
            "p10": 0.0,
            "r10": 0.0,
        }

    lexical = next((row for row in methods if row["method"].lower() == "bm25"), None)
    tfidf = next((row for row in methods if row["method"].lower() == "tfidf"), None)
    dense = next((row for row in methods if row["method"].lower() in {"bi_encoder", "rerank", "hybrid"}), None)

    diagnostics = []
    lexical_text = (
        f"BM25 MAP={_fmt_metric(lexical['map'])}，TF-IDF MAP={_fmt_metric(tfidf['map'])}。"
        if lexical and tfidf
        else "词法方法的具体指标不完整，但它们通常最容易受词汇不匹配影响。"
    )
    diagnostics.append({
        "title": "📉 词法墓地：稀疏检索的滑铁卢",
        "content": f"{lexical_text} 如果 P@5 和 R@10 都偏低，说明纯词面匹配在跨语言表情包检索里很容易失真。{note}".strip(),
    })

    if dense:
        dense_text = (
            f"当前语义/重排代表方法 {dense['method'].upper()} 的 MAP={_fmt_metric(dense['map'])}，"
            f"NDCG@10={_fmt_metric(dense['ndcg10'])}，P@5→P@10 从 {_fmt_metric(dense['p5'])} 到 {_fmt_metric(dense['p10'])}。"
        )
    else:
        dense_text = "语义/重排结果暂时缺失，但这条链路应重点观察语义泛化和排序稳定性。"

    diagnostics.append({
        "title": "🕸️ 语义深渊：双塔与重排的博弈",
        "content": f"{dense_text} 若高位精度下滑明显，说明召回和重排仍未真正形成互补。",
    })

    if methods:
        sorted_methods = sorted(methods, key=lambda row: (row["map"], row["mrr"], row["ndcg10"]), reverse=True)
        leader_names = ", ".join(row["method"].upper() for row in sorted_methods[:3])
        advice = "建议优先补强难例挖掘、跨语言同义归一和重排器的候选覆盖面。"
        if champion["method"].lower() in {"hybrid", "rerank"}:
            advice = "既然混合策略已经领先，下一步应强化 hard negatives 和更细粒度的 late interaction。"
        diagnostics.append({
            "title": "🔮 架构师终局推演：下一步怎么走？",
            "content": f"当前前排是 {leader_names}。{advice} 让 MAP 和 MRR 继续抬升，而不是只做表面热闹。",
        })
    else:
        diagnostics.append({
            "title": "🔮 架构师终局推演：下一步怎么走？",
            "content": "当前没有可用指标，先把评测链路和结果结构打通，再谈架构优化。",
        })

    return {
        "mvp": {
            "name": champion["method"].upper(),
            "score": champion["map"],
            "reason": (
                f"{champion['method'].upper()} 以 MAP={_fmt_metric(champion['map'])}、"
                f"MRR={_fmt_metric(champion['mrr'])} 拿下当前冠军。"
            ),
        },
        "diagnostics": diagnostics,
        "fallback": bool(note),
        "note": note,
    }

class SemanticConsensusCenter:
    """
    LLM-powered Semantic Synergy & IR Orchestrator:
    Coordinates narrative planning and result consensus to find the perfect emoji.
    """
    def __init__(self, engine, reranker):
        self.client = OpenAI(api_key=SF_API_KEY, base_url=SF_BASE_URL) if SF_API_KEY else None
        self.engine = engine
        self.reranker = reranker

    def _split_story_text(self, text, *, max_chunk_chars: int = 15, max_chunks: int = 10):
        """Split long stories into compact visual beats. 
        Highly granular to ensure multiple scenes even for short stories."""
        text = (text or "").strip()
        if not text:
            return []

        # Split by sentence punctuation and commas
        fragments = []
        for s in re.split(r'[。！？!?；;\n，,]+', text):
            s = s.strip()
            if s:
                fragments.append(s)
        
        if not fragments:
            return [text]

        # Merge only if extremely short (e.g. 1-2 chars)
        chunks = []
        current = ""
        for fragment in fragments:
            candidate = fragment if not current else f"{current}，{fragment}"
            if not current or len(candidate) <= max_chunk_chars:
                current = candidate
            else:
                chunks.append(current)
                current = fragment

        if current:
            chunks.append(current)

        if len(chunks) > max_chunks:
            return chunks[:max_chunks]

        return [chunk.strip("，。 ") for chunk in chunks if chunk.strip()]

    def _extract_json_array(self, content: str):
        """Best-effort JSON array extraction from model output."""
        if not content:
            return []

        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass

        try:
            decoder = json.JSONDecoder()
            start_idx = content.find('[')
            if start_idx != -1:
                parsed, _ = decoder.raw_decode(content[start_idx:])
                return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            pass

        try:
            match = re.search(r'\[[\s\S]*\]', content)
            if match:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass

        return []

    def _build_storyboard_prompt(self, fragments: list):
        """Build a concise prompt for storyboard planning based on deterministic fragments."""
        fragments_json = json.dumps(fragments, ensure_ascii=False)
        return f"""我已经将故事拆分为以下 {len(fragments)} 个分镜：
{fragments_json}

请为每个分镜分配一个最贴切的英文搜索关键词(1-3个单词)和简短理由。
必须严格输出 JSON 数组，不要有任何其他文字。格式如下：
[
  {{"Segment": "此处填入原分镜文本", "Search": "英文关键词", "Reasoning": "简短理由"}},
  ...
]
"""

    def _build_selection_prompt(self, story_text: str, segment_text: str, query: str, candidates: list[dict]):
        """Build a strict choice prompt for ambiguous candidate sets."""
        return f"""你是一个严格的表情包候选选择器。只能从给定候选中选择一个最合适的 emoji。

要求：
1. 只返回一个 emoji 字符。
2. 只能从候选列表中选，不能发明新表情。
3. 优先选择和当前分镜画面、情绪、动作最一致的候选。
4. 不要解释，不要标点，不要换行。

叙事上下文：{story_text}
当前分镜：{segment_text}
检索关键词：{query}
候选列表：{json.dumps(candidates, ensure_ascii=False)}
"""

    def _search_storyboard_candidates(self, query: str, *, top_k: int = 10):
        """Try the strongest retrieval path first, then fall back to stable local methods."""
        methods = ["rerank", "hybrid", "dense", "bi_encoder", "tfidf", "bm25"]
        for method in methods:
            try:
                hits = self.engine.search(query, method=method, top_k=top_k)
            except Exception:
                continue
            if hits:
                return hits, method
        return [], None

    def _plan_storyboard_segments(self, text: str, use_ai: bool):
        """Plan storyboard segments.
        Ensures minimum scene count based on story length."""
        if not text:
            return []

        # Rule-based split for initial fragments
        fragments = self._split_story_text(text, max_chunk_chars=18)
        sentence_count = len(fragments)
        
        if not use_ai or self.client is None:
            # Enhanced rule-based fallback
            normalized = [{"Segment": f, "Search": f, "Reasoning": ""} for f in fragments]
            return normalized[:8]

        # Build concise prompt
        prompt = self._build_storyboard_prompt(fragments)
        planned = []
        try:
            response = self.client.chat.completions.create(
                model=FAST_MODEL,
                messages=[
                    {"role": "system", "content": "You are a storyboard planner. Output JSON array only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                temperature=0.2,
                top_p=0.8,
            )
            planned = self._extract_json_array(response.choices[0].message.content)
        except Exception as e:
            print(f"Storyboard planning AI error: {e}")
            pass

        normalized = []
        for item in planned:
            if not isinstance(item, dict): continue
            segment = str(item.get("Segment") or item.get("segment") or "").strip()
            search = str(item.get("Search") or item.get("search") or "").strip()
            if segment and search:
                normalized.append({
                    "Segment": segment,
                    "Search": search,
                    "Reasoning": str(item.get("Reasoning") or "").strip(),
                })

        # If LLM failed or returned too few, fallback to fragments
        if len(normalized) < len(fragments) * 0.5:
            normalized = [{"Segment": f, "Search": f, "Reasoning": ""} for f in fragments]

        return normalized[:8] # Cap at 8 for performance

    def _rule_based_storyboard(self, text):
        """Fallback rule-based storyboard generation."""
        segments = self._split_story_text(text)
        sequence = []
        for seg in segments:
            hits, _ = self._search_storyboard_candidates(seg, top_k=10)
            if hits:
                best = hits[0]
                sequence.append({
                    "segment": seg,
                    "emoji": best["char"],
                    "en": best["en"],
                    "zh": best.get("zh", "")
                })
        return sequence

    def create_storyboard(self, text, use_ai=True):
        """
        Agentic Storyboard: Narrative -> Sequence of [segment, query, emoji, reasoning]
        """
        if not text:
            return []

        if not use_ai or self.client is None:
            return self._rule_based_storyboard(text)

        segments_data = self._plan_storyboard_segments(text, use_ai=use_ai)
        if not segments_data:
            return self._rule_based_storyboard(text)

        # Step 2: Agentic Retrieval & Selection (Parallelized for Speed)
        sequence = []
        
        def process_segment(item):
            q = item.get("Search", "")
            if not q: return None

            # Call our existing IR engine
            hits, retrieval_method = self._search_storyboard_candidates(q, top_k=10)
            if not hits: return None
            
            candidates = [{"char": h["char"], "en": h["en"], "zh": h.get("zh","")} for h in hits[:6]]
            top_score = float(hits[0].get("score", 0.0))
            second_score = float(hits[1].get("score", 0.0)) if len(hits) > 1 else 0.0
            try:
                # 移除每次分镜的二次大模型请求，直接采用最顶部的检索结果，极大加快返回速度。
                best_hit = hits[0]
            except Exception as e:
                best_hit = hits[0] # fallback

            return {
                "segment": item.get("Segment", ""),
                "emoji": best_hit["char"],
                "en": best_hit["en"],
                "zh": best_hit.get("zh", ""),
                "reasoning": item.get("Reasoning", "")
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, max(len(segments_data), 1))) as executor:
            results = list(executor.map(process_segment, segments_data))
            
        sequence = [r for r in results if r is not None]
        return sequence

engine = EmojiSearchEngine(use_neural_reranker=False)  # Use lightweight local reranker (no network calls)
reranker = engine._reranker  # Reference the reranker from engine
ai_director = SemanticConsensusCenter(engine, reranker)

# Ensure offline mode for stability if models are already cached
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

# pre-load fast methods at startup (dense is loaded on first request)
PRELOAD_METHODS = ["bm25", "tfidf"]
_HEAVY_PRELOAD_STARTED = False
_HEAVY_PRELOAD_LOCK = threading.Lock()


def _start_background_preload(methods=None):
    """Start a background thread to preload heavy retrieval methods."""
    methods = methods or ["bi_encoder", "dense"]

    def _worker():
        try:
            print(f"Background preload: loading {methods} ...")
            engine.load(methods=methods)
            print("Background preload: done.")
        except Exception as e:
            print(f"Background preload failed: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def _kickoff_heavy_preload_once():
    """Flask 3-compatible one-time preload trigger for heavier local models."""
    global _HEAVY_PRELOAD_STARTED
    with _HEAVY_PRELOAD_LOCK:
        if _HEAVY_PRELOAD_STARTED:
            return
        _HEAVY_PRELOAD_STARTED = True
    _start_background_preload(methods=["bi_encoder", "dense"])


@app.before_request
def _ensure_loaded():
    if not engine.available_methods:
        engine.load(methods=PRELOAD_METHODS)
    if request.endpoint in {"api_search", "api_similar", "api_path", "api_vector_math", "api_storyboard"}:
        _kickoff_heavy_preload_once()


def _canonical_char(char: str) -> str:
    return char.replace("\ufe0f", "").replace("\ufe0e", "")


def _filter_and_rank(results, *, category="", exclude_chars=None, top_k=10):
    exclude_chars = exclude_chars or set()
    category = (category or "").strip()
    seen = set()
    filtered = []
    for r in results:
        key = _canonical_char(r["char"])
        if key in seen or r["char"] in exclude_chars or key in exclude_chars:
            continue
        if category and category != "all" and r.get("category") != category:
            continue
        seen.add(key)
        item = r.copy()
        filtered.append(item)
        if len(filtered) >= top_k:
            break
    for i, r in enumerate(filtered, 1):
        r["rank"] = i
    return filtered


def _debug_payload(query, method, category, raw_count, filtered_results):
    return {
        "query_tokens": tokenize(query),
        "method": method,
        "category": category or "all",
        "raw_candidate_count": raw_count,
        "returned_count": len(filtered_results),
        "top_features": [
            {
                "rank": r.get("rank"),
                "char": r.get("char"),
                "en": r.get("en"),
                "category": r.get("category"),
                "score": r.get("score"),
                "base_score": r.get("base_score"),
                "lexical_score": r.get("lexical_score"),
                "sources": r.get("sources", []),
            }
            for r in filtered_results[:10]
        ],
    }


def _load_records():
    global _RECORD_CACHE
    if _RECORD_CACHE is None:
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        dataset = os.path.join(data_dir, "emoji_dataset.json")
        with open(dataset, "r", encoding="utf-8") as f:
            _RECORD_CACHE = json.load(f)
    return _RECORD_CACHE


def _lexical_candidates(query: str, *, top_k: int = 60) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return []

    q_tokens = set(tokenize(q))
    candidates = []
    for record in _load_records():
        char = record.get("char", "")
        en = (record.get("en") or "").lower()
        zh = (record.get("zh") or "").lower()
        ja = (record.get("ja") or "").lower()
        keywords = [str(k).lower() for k in record.get("keywords", [])]
        aliases = [str(a).lower() for a in record.get("aliases", [])]
        haystack = " ".join([char, en, zh, ja, " ".join(keywords), " ".join(aliases)])
        doc_tokens = set(tokenize(haystack))

        score = 0.0
        if q == char:
            score = max(score, 1.25)
        if q == en or q == zh or q in aliases:
            score = max(score, 1.15)
        if q in keywords:
            score = max(score, 1.05)
        if q and (en.startswith(q) or zh.startswith(q)):
            score = max(score, 0.95)
        if q and q in haystack:
            score = max(score, 0.82)
        overlap = len(q_tokens & doc_tokens)
        if overlap:
            score = max(score, min(0.75 + 0.05 * overlap, 0.95))

        if score <= 0:
            continue
        candidates.append({
            "rank": 0,
            "score": float(score),
            "char": char,
            "codepoint": record.get("codepoint", ""),
            "en": record.get("en", ""),
            "zh": record.get("zh", ""),
            "ja": record.get("ja", ""),
            "category": record.get("category", ""),
            "keywords": record.get("keywords", []),
            "sources": ["lexical"],
        })

    candidates.sort(key=lambda item: (-item["score"], item["en"]))
    for rank, item in enumerate(candidates[:top_k], 1):
        item["rank"] = rank
    return candidates[:top_k]


def _merge_candidates(primary: list[dict], secondary: list[dict]) -> list[dict]:
    by_char = {}
    for item in list(primary or []) + list(secondary or []):
        key = _canonical_char(item.get("char", ""))
        if not key:
            continue
        existing = by_char.get(key)
        if existing is None or float(item.get("score", 0.0)) > float(existing.get("score", 0.0)):
            combined = item.copy()
            if existing:
                combined["sources"] = sorted(set(existing.get("sources", [])) | set(item.get("sources", [])))
            by_char[key] = combined
        elif existing is not None:
            existing["sources"] = sorted(set(existing.get("sources", [])) | set(item.get("sources", [])))
    return sorted(by_char.values(), key=lambda item: -float(item.get("score", 0.0)))


# ── pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/categories")
def api_categories():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    dataset = os.path.join(data_dir, "emoji_dataset.json")
    counts = {}
    with open(dataset, "r", encoding="utf-8") as f:
        for record in json.load(f):
            cat = record.get("category") or "Uncategorized"
            counts[cat] = counts.get(cat, 0) + 1
    categories = [{"name": k, "count": v} for k, v in sorted(counts.items())]
    return jsonify({"categories": categories})


# ── API: search ───────────────────────────────────────────────────────────────
@app.route("/api/search", methods=["POST"])
def api_search():
    data   = request.get_json(force=True)
    query  = (data.get("query") or "").strip()
    method = data.get("method", "bi_encoder")  # Changed: was "bm25", now semantic search by default
    top_k  = min(int(data.get("top_k", 20)), 50)
    category = (data.get("category") or "").strip()
    want_debug = bool(data.get("debug", False))

    if not query:
        return jsonify({"error": "empty query"}), 400

    # relevance feedback: exclude disliked chars and track liked chars for Rocchio PRF
    exclude_chars = {_canonical_char(c) for c in (data.get("exclude", []) or [])}
    liked_chars = {_canonical_char(c) for c in (data.get("liked", []) or [])}

    # Track query for global sentiment pulse
    recent_queries.append(query)
    t0 = time.perf_counter()
    
    # PHASE 1: Retrieval (Candidate Generation)
    # We fetch a larger candidate set for the reranker
    fetch_k = max(top_k * 5, 60) if category and category != "all" else max(top_k * 2, top_k)
    try:
        rocchio_methods = ["bi_encoder", "dense", "hybrid", "rerank"]
        if (liked_chars or exclude_chars) and method in rocchio_methods:
            # 🚀 Rocchio Algorithm Implementation
            if "bi_encoder" not in engine.available_methods:
                engine.load(["bi_encoder"])
            enc = engine._retrievers["bi_encoder"]
            
            # Original query vector
            q_vec = enc._encode_batch([query])[0]
            
            # Find vectors for feedback documents
            char_to_idx = {_canonical_char(r["char"]): i for i, r in enumerate(enc.records)}
            liked_vecs = [enc.embeddings[char_to_idx[c]] for c in liked_chars if c in char_to_idx]
            disliked_vecs = [enc.embeddings[char_to_idx[c]] for c in exclude_chars if c in char_to_idx]
            
            # Rocchio Formula: q_m = alpha * q + beta * mean(liked) - gamma * mean(disliked)
            alpha, beta, gamma = 1.0, 0.75, 0.25
            
            if liked_vecs:
                q_vec += beta * np.mean(liked_vecs, axis=0)
            if disliked_vecs:
                q_vec -= gamma * np.mean(disliked_vecs, axis=0)
                
            # Re-normalize new query vector
            norm = np.linalg.norm(q_vec)
            if norm > 1e-8:
                q_vec /= norm
                
            # Perform direct vector search bypassing the engine
            scores = enc.embeddings @ q_vec
            top_idxs = np.argsort(-scores)[:fetch_k + len(exclude_chars)]
            
            raw_results = []
            for rank, idx in enumerate(top_idxs, 1):
                r = enc.records[idx]
                raw_results.append({
                    "rank": rank,
                    "score": float(scores[idx]),
                    "char": r["char"],
                    "codepoint": r["codepoint"],
                    "en": r["en"],
                    "zh": r.get("zh", ""),
                    "category": r["category"],
                    "keywords": r.get("keywords", [])
                })
        else:
            raw_results = engine.search(query, method=method, top_k=fetch_k)
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 503
    raw_results = _merge_candidates(raw_results, _lexical_candidates(query, top_k=fetch_k))
    boosted_results = _boost_exact(raw_results, query)
    results = _filter_and_rank(
        boosted_results,
        category=category,
        exclude_chars=exclude_chars,
        top_k=top_k,
    )

    # Final trim to requested top_k after all processing
    results = results[:top_k]

    # ── Compute Cross-Similarity Matrix for StarMap (OPTIONAL, cached/async) ───────────────────
    # Moved to background to avoid blocking the main response.
    # If sim_matrix is needed, it can be requested separately or computed async.
    sim_matrix = []

    elapsed = time.perf_counter() - t0
    payload = {
        "query"     : query,
        "method"    : method,
        "category"  : category or "all",
        "count"     : len(results),
        "elapsed"   : round(elapsed * 1000, 1),
        "results"   : results,
        "sim_matrix": sim_matrix,
    }
    if want_debug:
        payload["debug"] = _debug_payload(query, method, category, len(raw_results), results)
    return jsonify(payload)

@app.route('/api/storyboard', methods=['POST'])
def api_storyboard():
    """
    Agentic Storyboard: Leverages LLM to drive the IR engine.
    """
    data = request.json or {}
    text = data.get("text", "")
    use_ai = data.get("use_ai", True)
    
    if not text:
        return jsonify({"sequence": []})

    sequence = ai_director.create_storyboard(text, use_ai=use_ai)
    if sequence:
        return jsonify({"sequence": sequence})
    else:
        return jsonify({"sequence": []})


@app.route('/api/magic_story', methods=['POST'])
def api_magic_story():
    """
    Magic Inspiration: Generates a creative story prompt based on genre.
    """
    data = request.json or {}
    genre = data.get("genre", "Random")
    genre_label = {
        "adventure": "银河冒险",
        "cyberpunk": "赛博都市",
        "nature": "森林秘境",
        "romance": "浪漫邂逅",
        "mystery": "侦探谜案",
    }.get(str(genre).lower(), str(genre))
    if ai_director.client is None:
        return jsonify({"error": "SF_API_KEY is not configured"}), 503
    prompt = (
        f"请生成一个'{genre_label}'风格的表情包剧本灵感。"
        "输出中文故事，总长度控制在36到60个汉字；不要标题、不要解释、不要换行、不要任何 Emoji。"
        "必须写成一个句子，但要由4到5个短分句组成，每个分句尽量短，分句之间只能用逗号。"
        "至少保留3个逗号，避免写成一整句长句。第一段交代画面和人物动作，后面逐步推进到轻微转折或情绪变化。"
    )
    try:
        def _generate_story(system_prompt: str, user_prompt: str) -> str:
            response = ai_director.client.chat.completions.create(
                model=INSPIRATION_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=120,
                temperature=0.55,
                top_p=0.8,
                timeout=10,
            )
            return _clean_short_story(response.choices[0].message.content, "")

        story = _generate_story(
            "你只写一个中文故事句子，必须拆成4到5个短分句，并且用逗号明确隔开。",
            prompt,
        )
        if not _story_has_enough_clauses(story):
            retry_prompt = prompt + "\n\n补充要求：一定要写成4到5个短分句，句子不要超过60个字，必须有至少3个逗号。"
            story = _generate_story(
                "你只写一个中文故事句子，必须拆成4到5个短分句，并且用逗号明确隔开。",
                retry_prompt,
            )
        if not story:
            return jsonify({"error": "AI returned an empty story"}), 502
        return jsonify({"story": story, "model": INSPIRATION_MODEL})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route('/api/journey_narrative', methods=['POST'])
def api_journey_narrative():
    """
    AI Semantic Journey: Explains the transition between concepts.
    """
    data = request.json or {}
    path = data.get("path", [])
    if len(path) < 2: return jsonify({"narrative": ""})
    if ai_director.client is None:
        return jsonify({"narrative": ""})
    
    path_str = " -> ".join([f"{item['char']}({item['en']})" for item in path])
    # Refined prompt for more concise and literary Chinese narrative
    prompt = f"以下是从一个概念到另一个概念的语义演变路径：{path_str}。请用一段优美、富有诗意的短评（30字以内），文学化地解释这个演变过程背后的逻辑。输出纯中文。"
    
    try:
        response = ai_director.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.7
        )
        return jsonify({"narrative": response.choices[0].message.content.strip()})
    except Exception as e:
        return jsonify({"narrative": ""})

@app.route('/api/ai_committee_eval', methods=['POST'])
def api_ai_committee_eval():
    """
    AI Algorithm Diagnostic Copilot: Detailed semantic evaluation of IR pipelines.
    """
    data = request.json or {}
    metrics = data.get("metrics", [])
    if ai_director.client is None:
        print("AI diagnostics disabled: AI client is None")
        return jsonify({"verdict": _build_local_committee_verdict(metrics, note="AI diagnostics disabled: set SF_API_KEY or SILICONFLOW_API_KEY.")}), 200
    
    # 构建更丰富的宏观与微观对比数据供 AI 分析
    context = ""
    for m in metrics:
        method = m.get('method', '').upper()
        m_data = m.get('metrics', {})
        map_val = m_data.get('MAP', 0)
        mrr_val = m_data.get('MRR', 0)
        ndcg_val = m_data.get('NDCG@10', 0)
        p5_val = m_data.get('P@5', 0)
        p10_val = m_data.get('P@10', 0)
        r10_val = m_data.get('R@10', 0)
        # 计算 P@5 到 P@10 的衰减率，用于评估排序稳定性
        dropoff = 0
        if p5_val > 0:
            dropoff = round(((p5_val - p10_val) / p5_val) * 100, 1)
            
        context += f"| {method} | MAP: {map_val} | MRR: {mrr_val} | NDCG@10: {ndcg_val} | P@5: {p5_val} | P@10: {p10_val} (衰减 {dropoff}%) | R@10: {r10_val} |\n"

    prompt = f"""你现在是'OmniMoji 首席算法架构师 (Chief Algorithm Architect)'，一位极其严苛且专业的搜索引擎优化专家。刚刚系统完成了 50 条跨语言 Emoji 检索基准测试，各算法（赛车）的战报如下：

{context}

请你基于以上真实的 IR (信息检索) 核心指标，生成一份既具有专业深度（言之有物），又充满极客趣味（毒舌、比喻生动）的复盘报告。
【极其重要】：你的每一句点评中必须至少包含 2-3 个 Emoji 表情符号！要符合系统“表情包检索”的核心主题！例如使用 💥, 🤡, 🚀, 🤦‍♂️, 🧠 等表情来增强嘲讽和赞美效果。

要求输出严格的 JSON 格式（严禁包含 markdown 代码块前缀）：
{{
  "mvp": {{
    "name": "这里填冠军算法名",
    "score": "MAP 分数",
    "reason": "1句话宣告它为什么赢（结合它的核心指标，如MRR首位命中率或NDCG排序能力）。必须包含Emoji！"
  }},
  "diagnostics": [
    {{
      "title": "📉 词法：稀疏检索的滑铁卢",
      "content": "深入分析 BM25 / TF-IDF 数据。不要只说它低，要指出它在召回（R@10）或精度（P@5）上的具体崩溃点，解释词汇不匹配（Lexical Gap）在这个表情包跨语言检索场景下是如何杀死了这辆老爷车的。（约80字，必须包含大量Emoji！）"
    }},
    {{
      "title": "🕸️ 语义：双塔与重排的博弈",
      "content": "对比 BI_ENCODER, RERANK, HYBRID 的表现。分析 P@5 到 P@10 的衰减率，或者 NDCG 的表现。指出单纯依赖 Dense 向量的局限性，以及重排/混合策略是否真正做到了优势互补，还是只是在'和稀泥'。（约100字，必须包含大量Emoji！）"
    }},
    {{
      "title": "🔮 推演：下一步怎么走？",
      "content": "基于当前数据，给出现实且前沿的工程建议。比如：是否需要引入 ColBERT 进行更细粒度的 Late Interaction？或者基于对比学习（Contrastive Learning）微调当前模型以解决 Hard Negatives？（约100字，必须包含大量Emoji！）"
    }}
  ]
}}"""
    
    try:
        response = ai_director.client.chat.completions.create(
            model=DEEP_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0.7
        )
        content = response.choices[0].message.content
        import json
        raw_result = None
        
        # Try direct JSON parsing first
        try:
            raw_result = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON object using JSONDecoder.raw_decode
            try:
                decoder = json.JSONDecoder()
                # Find first '{' in content
                start_idx = content.find('{')
                if start_idx != -1:
                    raw_result, _ = decoder.raw_decode(content[start_idx:])
            except (json.JSONDecodeError, ValueError):
                # Last resort: try simple regex for the main structure
                # Look for patterns like {"mvp":{...},"diagnostics":[...]}
                try:
                    match = re.search(r'\{[\s\S]*\}', content)
                    if match:
                        raw_result = json.loads(match.group(0))
                except:
                    pass
        
        if raw_result is None:
            print(f"AI Eval Error: Could not parse JSON from response: {content[:200]}")
            return jsonify({"verdict": _build_local_committee_verdict(metrics, note="Failed to parse AI response as JSON")}), 200

        if not isinstance(raw_result, dict):
            raw_result = {}

        local_verdict = _build_local_committee_verdict(metrics)
        verdict = {
            "mvp": raw_result.get("mvp") or local_verdict["mvp"],
            "diagnostics": raw_result.get("diagnostics") or local_verdict["diagnostics"],
        }
        verdict["fallback"] = False
        return jsonify({"verdict": verdict}), 200
    except Exception as e:
        print(f"AI Eval Error: {e}")
        return jsonify({"verdict": _build_local_committee_verdict(metrics, note=str(e))})

@app.route('/api/eval_diagnose', methods=['POST'])
def api_eval_diagnose():
    """
    Micro-level AI Diagnosis for specific query results comparison.
    """
    data = request.json or {}
    query = data.get("query", "")
    method_a = data.get("method_a", "")
    results_a = data.get("results_a", [])
    method_b = data.get("method_b", "")
    results_b = data.get("results_b", [])
    
    if not query:
        return jsonify({"diagnosis": "Query is missing."})
    if ai_director.client is None:
        return jsonify({"diagnosis": "AI diagnostics disabled. Use the metric table and per-query results for offline analysis."})
        
    prompt = f"""你是'OmniMoji'系统的高级搜索架构师。现在请你诊断两个不同检索算法在同一个查询词下的表现差异。

Query(用户意图): "{query}"
算法A ({method_a}) 召回结果: {[r['char'] + '(' + r['en'] + ')' for r in results_a]}
算法B ({method_b}) 召回结果: {[r['char'] + '(' + r['en'] + ')' for r in results_b]}

请用简短精炼的中文（约80字），诊断为什么算法A的结果与算法B不同，并点评算法A在这个查询下的主要优缺点或可能导致该结果的底层机制（例如词汇不匹配、语义泛化等）。"""

    try:
        response = ai_director.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.6
        )
        diagnosis = response.choices[0].message.content.strip()
        return jsonify({"diagnosis": diagnosis})
    except Exception as e:
        return jsonify({"diagnosis": f"Diagnosis failed: {str(e)}"})

@app.route('/api/map_labels', methods=['POST'])
def api_map_labels():
    """
    Semantic Map Labels: AI identifies clusters in the search results with a creative space/galaxy theme.
    """
    data = request.json or {}
    results = data.get("results", [])
    if ai_director.client is None:
        return jsonify({"labels": []})
    if len(results) < 5: return jsonify({"labels": []})
    
    # List emojis and their English names
    target = ", ".join([f"{r['char']}({r['en']})" for r in results[:30]])
    prompt = f"""你是一个'语义星系'的领航员。请将以下召回的 Emoji 分成 3 个不同的星系（语义聚类）。
为每个星系取一个充满科幻感或趣味性的 4-6 字中文名称，并且名称的开头或结尾必须带 1 个 Emoji！
例如: "✨情绪深渊", "动物星云🐶", "魔法象限🔮"

需要分类的 Emoji: {target}
严禁包含任何其他文字，请直接输出一个包含 3 个字符串的 JSON 数组。"""
    
    try:
        response = ai_director.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.6
        )
        content = response.choices[0].message.content
        match = re.search(r'\[.*\]', content, re.DOTALL)
        labels = json.loads(match.group(0)) if match else []
        return jsonify({"labels": labels[:3]})
    except Exception as e:
        print(f"Map labels error: {e}")
        return jsonify({"labels": []})

@app.route('/api/pulse', methods=['GET'])
def api_pulse():
    """
    Live Mood Nebula: Calculates the global sentiment pulse based on recent searches.
    """
    if not recent_queries:
        return jsonify({"mood": "Neutral", "intensity": 0, "hotspots": []})
    
    # In a real app we'd compute average vector. For now, we return the most frequent recent hits
    # and a summary "mood" derived from the most recent query.
    last_q = recent_queries[-1]
    
    # Heatmap data: return emojis that appeared in top results recently
    # (Simplified: just return top 10 unique emojis from last few searches for the UI to pulse)
    return jsonify({
        "recent_queries": list(recent_queries)[-10:],
        "pulse_active": True
    })


def _boost_exact(results, query):
    """Re-rank: 精确匹配 emoji 英文/中文名时大幅提分，改善单字/词检索准确性。"""
    q = query.strip().lower()
    boosted = []
    for r in results:
        en  = r["en"].lower()
        # zh: first segment only (most representative name)
        zh_parts = r.get("zh", "").lower().split()
        zh0 = zh_parts[0] if zh_parts else ""
        zh_all = " ".join(zh_parts)

        m = 1.0
        # Check for full match in EN, or prefix match in ZH
        if en == q or zh0 == q or zh_all == q or q in zh_parts: m = 20.0   # strong exact / keyword match
        elif en.startswith(q + " ") or q == zh0:                m = 10.0   # starts with query / primary zh name
        elif q in en.split() or q in zh_parts[:5]:              m = 6.0    # query is a whole token
        elif en.startswith(q) or zh_all.startswith(q):          m = 3.0    # prefix match

        boosted.append({**r, "score": r["score"] * m})

    boosted.sort(key=lambda x: -x["score"])
    for i, r in enumerate(boosted):
        r["rank"] = i + 1
    return boosted



# ── API: similar (nearest-neighbor exploration) ─────────────────────────────
@app.route("/api/similar", methods=["POST"])
def api_similar():
    """
    返回与指定 emoji 语义最近邓的 top_k 个表情。
    Input JSON: { "char": "🔥", "top_k": 12, "exclude": [] }
    """
    import numpy as np
    data          = request.get_json(force=True)
    char          = (data.get("char") or "").strip()
    top_k         = min(int(data.get("top_k", 12)), 30)
    exclude_chars = set(data.get("exclude", []) or [])
    exclude_chars.add(char)   # exclude the query emoji itself

    if not char:
        return jsonify({"error": "empty char"}), 400

    # ensure BiEncoder is loaded
    if "bi_encoder" not in engine.available_methods:
        try:
            engine.load(methods=["bi_encoder"])
        except Exception as e:
            return jsonify({"error": f"BiEncoder not ready: {e}"}), 503

    enc = engine._retrievers["bi_encoder"]

    # find the char in records
    rec_idx = next((i for i, r in enumerate(enc.records) if r["char"] == char), None)
    # also try without variation selector
    if rec_idx is None:
        char_bare = char.replace('\ufe0f', '').replace('\ufe0e', '')
        rec_idx = next((i for i, r in enumerate(enc.records)
                        if r["char"].replace('\ufe0f','') == char_bare), None)
    if rec_idx is None:
        return jsonify({"error": f"Emoji not found: {char}"}), 404

    q_vec  = enc.embeddings[rec_idx]
    scores = enc.embeddings @ q_vec
    top_idxs = np.argsort(-scores)

    seen, results = [], []
    for idx in top_idxs:
        r   = enc.records[idx]
        key = r["char"].replace('\ufe0f','').replace('\ufe0e','')
        if r["char"] in exclude_chars or key in seen:
            continue
        seen.append(key)
        results.append({
            "rank"      : len(results) + 1,
            "score"     : float(scores[idx]),
            "char"      : r["char"],
            "en"        : r["en"],
            "zh"        : r.get("zh", ""),
            "category"  : r["category"],
        })
        if len(results) >= top_k:
            break

    source = enc.records[rec_idx]
    return jsonify({
        "char"   : char,
        "en"     : source["en"],
        "zh"     : source.get("zh", ""),
        "count"  : len(results),
        "results": results,
    })

# ── API: semantic journey ─────────────────────────────────────────────────────
@app.route("/api/path", methods=["POST"])
def api_path():
    """
    语义旅行：在 embedding 空间中插值，找出连接两个概念的语义路径。
    Input JSON: { "from_query": "fire", "to_query": "water", "steps": 5 }
    """
    data=request.json
    from_q = (data.get("from_query") or "").strip()
    to_q   = (data.get("to_query")   or "").strip()
    steps  = min(max(int(data.get("steps", 5)), 3), 15)

    if not from_q or not to_q:
        return jsonify({"error": "Missing queries"}), 400

    # ensure BiEncoder is loaded
    if "bi_encoder" not in engine.available_methods:
        try:
            engine.load(methods=["bi_encoder"])
        except Exception as e:
            return jsonify({"error": f"BiEncoder not ready: {e}"}), 503

    # We must use bi_encoder for embeddings
    enc = engine._retrievers.get("bi_encoder")
    if not enc: return jsonify({"error": "Bi-encoder not ready"}), 400

    try:
        from_vec = enc._encode_batch([from_q])[0]
        to_vec   = enc._encode_batch([to_q])[0]

        from_norm = np.linalg.norm(from_vec)
        to_norm   = np.linalg.norm(to_vec)
        if from_norm > 0: from_vec /= from_norm
        if to_norm > 0:   to_vec /= to_norm
        
        # inner product for SLERP angle
        dot = np.clip(np.dot(from_vec, to_vec), -1.0, 1.0)
        omega = np.arccos(dot)
        sin_omega = np.sin(omega)

        # n+2 waypoints including endpoints
        waypoints = steps + 2
        path, seen = [], []
        
        # We explicitly find the best matching emojis for the endpoints
        # We search with bi_encoder but boost exact matches to ensure we start/end at relevant concepts
        start_hits = engine.search(from_q, method="bi_encoder", top_k=25)
        end_hits   = engine.search(to_q,   method="bi_encoder", top_k=25)
        ideal_start = _boost_exact(start_hits, from_q)[0]
        ideal_end   = _boost_exact(end_hits,   to_q)[0]

        for i in range(waypoints):
            t = i / (waypoints - 1)   # 0.0 → 1.0
            
            best_r = None
            if i == 0:
                best_r = ideal_start.copy()
                best_r["score"] = 1.0 # Assign a perfect score for the start point
            elif i == waypoints - 1:
                best_r = ideal_end.copy()
                best_r["score"] = 1.0 # Assign a perfect score for the end point
            else:
                # Spherical Linear Interpolation (SLERP)
                if sin_omega > 1e-6:
                    interp = (np.sin((1.0 - t) * omega) / sin_omega) * from_vec + \
                             (np.sin(t * omega) / sin_omega) * to_vec
                else:
                    # Fallback to LERP if vectors are too close
                    interp = (1 - t) * from_vec + t * to_vec
                    
                norm = np.linalg.norm(interp)
                if norm > 1e-8: interp /= norm

                scores  = enc.embeddings @ interp
                idxs    = np.argsort(-scores)
                
                # Filter out emojis we've already used or exact matches to the endpoints
                for idx in idxs:
                    r   = enc.records[idx]
                    key = r["char"].replace("\ufe0f", "").replace("\ufe0e", "")
                    if key in seen: continue
                    if key == ideal_start["char"].replace("\ufe0f", ""): continue
                    if key == ideal_end["char"].replace("\ufe0f", ""): continue
                    
                    best_r = r.copy()
                    best_r["score"] = float(scores[idx])
                    break
                    
            if not best_r: continue
            
            key = best_r["char"].replace("\ufe0f", "").replace("\ufe0e", "")
            seen.append(key)
            # For each step, we'll assign a mini-reasoning (simulated or AI)
            path.append({
                "step" : i,
                "t"    : round(t, 3),
                "char" : best_r["char"],
                "en"   : best_r["en"],
                "zh"   : best_r.get("zh", ""),
                "score": round(best_r.get("score", 1.0), 3),
                "reasoning": f"与 '{from_q}' 和 '{to_q}' 的语义偏差率为 {int((1-best_r['score'])*100)}%"
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "from_query" : from_q,
        "to_query"   : to_q,
        "steps"      : steps,
        "path"       : path,
    })


@app.route("/api/vector_math", methods=["POST"])
def api_vector_math():
    """
    语义向量加减法运算。
    Input JSON: { "expression": "国王 - 男人 + 女人", "top_k": 10, "exclude": [] }
    解析表达式，计算加权向量和，返回最近邓 emoji。
    """
    import re

    data       = request.get_json(force=True)
    expression = (data.get("expression") or "").strip()
    top_k      = min(int(data.get("top_k", 10)), 50)
    exclude_chars = set(data.get("exclude", []) or [])

    if not expression:
        return jsonify({"error": "empty expression"}), 400

    # ── 加载 BiEncoder ───────────────────────────────────────────────────
    heavy_methods = {"bi_encoder"}
    if "bi_encoder" not in engine.available_methods:
        try:
            engine.load(methods=["bi_encoder"])
        except Exception as e:
            return jsonify({"error": f"BiEncoder not ready: {e}"}), 503

    enc = engine._retrievers["bi_encoder"]

    # ── 解析表达式: "A - B + C" → [(+1,'A'), (-1,'B'), (+1,'C')] ──
    # 先标准化符号
    expr = re.sub(r'\s*([+\-]|=)\s*', r' \1 ', expression).strip()
    tokens = re.split(r'\s+', expr)

    terms = []          # list of (sign, term_string)
    sign  = +1
    for tok in tokens:
        if tok == '+':
            sign = +1
        elif tok in ('-', '−'):
            sign = -1
        elif tok == '=':
            break       # stop at '=', ignore RHS
        elif tok:
            terms.append((sign, tok))
            sign = +1   # reset after term

    if not terms:
        return jsonify({"error": "cannot parse expression"}), 400

    # ── 编码每个词并加权求和 ─────────────────────────────────────────
    try:
        result_vec = np.zeros(enc.embeddings.shape[1], dtype=np.float32)
        term_info  = []
        for s, t in terms:
            v = enc._encode_batch([t])[0]    # (384,) L2-normalized
            result_vec += s * v
            term_info.append({"term": t, "sign": "+" if s > 0 else "-"})

        # L2 归一化结果向量
        norm = np.linalg.norm(result_vec)
        if norm > 1e-8:
            result_vec /= norm

        # 暴力 KNN
        scores = enc.embeddings @ result_vec          # (N,)
        top_idxs = np.argsort(-scores)[:top_k + len(exclude_chars) + len(terms)]

        # 排除输入词本身对应的 emoji（防止异义）和 dislike
        input_terms_lower = {t.lower() for _, t in terms}
        results = []
        for idx in top_idxs:
            r = enc.records[idx]
            if r["char"] in exclude_chars:
                continue
            # skip if en name matches any input term
            if r["en"].lower() in input_terms_lower:
                continue
            results.append({
                "rank"      : len(results) + 1,
                "score"     : float(scores[idx]),
                "char"      : r["char"],
                "codepoint" : r["codepoint"],
                "en"        : r["en"],
                "zh"        : r.get("zh", ""),
                "keywords"  : r["keywords"],
                "category"  : r["category"],
            })
            if len(results) >= top_k:
                break

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "expression" : expression,
        "terms"      : term_info,
        "count"      : len(results),
        "results"    : results,
    })


@app.route("/api/eval")
def api_eval():
    """Run evaluation for all 5 algorithms and stream progress via SSE."""
    try:
        from eval.metrics import evaluate_all
        
        # Ensure paths are absolute and clean
        base_path = os.path.abspath(os.path.dirname(__file__))
        qfile = os.path.join(base_path, "data", "eval_queries.json")
        
        if not os.path.exists(qfile):
            return jsonify({"error": f"Queries not found at {qfile}"}), 503

        with open(qfile, "r", encoding="utf-8") as f:
            queries = json.load(f)

        gt = {q["id"]: set(q["relevant"]) for q in queries}
        ks = [5, 10]

        def get_hits(query, method):
            try:
                return engine.search(query, method=method, top_k=10)
            except Exception as exc:
                print(f"Evaluation method failed: {method} query={query!r}: {exc}")
                return []

        def sse_event(payload: dict) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        def generate():
            all_res = {m: {} for m in EVAL_METHODS}
            all_samples = {m: [] for m in EVAL_METHODS}

            try:
                yield sse_event({
                    "type": "init",
                    "total_queries": len(queries),
                    "methods": EVAL_METHODS,
                })
                yield sse_event({
                    "type": "status",
                    "message": "发令枪已注入，正在加载检索器并计算第一条查询...",
                })

                for q_idx, q in enumerate(queries):
                    query_updates = {}
                    for method in EVAL_METHODS:
                        hits = get_hits(q["query"], method)
                        all_res[method][q["id"]] = [h["char"] for h in hits]
                        if not all_samples[method]:
                            all_samples[method] = [{"char": h["char"], "en": h["en"]} for h in hits]

                        # Compute intermediate metrics for the race using only
                        # the queries already processed for this method.
                        current_gt = {k: gt[k] for k in all_res[method].keys()}
                        m = evaluate_all(all_res[method], current_gt, ks=ks)

                        query_updates[method] = {
                            "metrics": {k: round(v, 4) for k, v in m.items()},
                            "top_hit": hits[0]["char"] if hits else "❓",
                        }

                    yield sse_event({
                        "type": "race_update",
                        "query": q["query"],
                        "query_idx": q_idx,
                        "total_queries": len(queries),
                        "updates": query_updates,
                    })

                rows = []
                for method in EVAL_METHODS:
                    m = evaluate_all(all_res[method], gt, ks=ks)
                    rows.append({
                        "method": method,
                        "metrics": {k: round(v, 4) for k, v in m.items()},
                        "results_sample": all_samples[method],
                    })

                def first_rank(items, relevant):
                    for idx, item in enumerate(items, 1):
                        if item in relevant:
                            return idx
                    return None

                failure_cases = []
                for q in queries:
                    rel = gt[q["id"]]
                    method_stats = {}
                    for method in EVAL_METHODS:
                        retrieved = all_res[method].get(q["id"], [])
                        hits = sum(1 for item in retrieved[:10] if item in rel)
                        method_stats[method] = {
                            "hits_at_10": hits,
                            "first_rank": first_rank(retrieved, rel),
                            "top_hit": retrieved[0] if retrieved else "",
                        }
                    hybrid_stats = method_stats.get("hybrid", {})
                    failure_cases.append({
                        "id": q["id"],
                        "query": q["query"],
                        "relevant_count": len(rel),
                        "hybrid_hits_at_10": hybrid_stats.get("hits_at_10", 0),
                        "hybrid_first_rank": hybrid_stats.get("first_rank"),
                        "methods": method_stats,
                    })

                failure_cases.sort(
                    key=lambda x: (
                        x["hybrid_hits_at_10"],
                        x["hybrid_first_rank"] if x["hybrid_first_rank"] is not None else 999,
                    )
                )

                yield sse_event({
                    "type": "done",
                    "num_queries": len(queries),
                    "results": rows,
                    "failure_cases": failure_cases[:8],
                    "sample_query": queries[0]["query"] if queries else "Default",
                })
            except Exception as exc:
                print(traceback.format_exc())
                yield sse_event({
                    "type": "error",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        print(traceback.format_exc())
        def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"
        return Response(stream_with_context(error_gen()), mimetype="text/event-stream")


# ── API: status ───────────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    dataset  = os.path.join(data_dir, "emoji_dataset.json")
    count    = 0
    if os.path.exists(dataset):
        with open(dataset, "r", encoding="utf-8") as f:
            count = len(json.load(f))

    return jsonify({
        "loaded_methods": engine.available_methods,
        "emoji_count"   : count,
        "status"        : "ok",
    })


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
