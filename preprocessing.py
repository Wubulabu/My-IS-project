"""
preprocessing.py
----------------
Load emoji_dataset.json, build a searchable corpus, and persist the
processed index to data/index.json for use by the retrieval modules.

The corpus for each emoji is the concatenation of:
  en + zh + ja + de + fr + keywords + aliases + category
"""

import json
import os
import re
import pickle
import sys

# Force UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


DATA_DIR  = os.path.join(os.path.dirname(__file__), "data")
DATASET   = os.path.join(DATA_DIR, "emoji_dataset.json")
INDEX_OUT = os.path.join(DATA_DIR, "index.json")
CORPUS_PKL= os.path.join(DATA_DIR, "corpus.pkl")


# ── basic tokeniser (works for CJK + Latin) ──────────────────────────────────
ZH_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")

def tokenize(text: str) -> list[str]:
    """
    Simple whitespace + CJK character-level tokeniser.
    - Split Latin/other on whitespace / punctuation
    - Split CJK into individual characters
    """
    tokens = []
    for word in re.split(r"[\s,;:_\-\.!?\"\'()]+", text.lower()):
        if not word:
            continue
        # if the word contains CJK, split into chars
        if ZH_RE.search(word):
            for ch in word:
                if ch.strip():
                    tokens.append(ch)
        else:
            tokens.append(word)
    return [t for t in tokens if len(t) > 0]


def build_doc_text(record: dict) -> str:
    """Return the raw text blob for a single emoji record, with heavily boosted terms for precision."""
    en = record.get("en", "")
    zh = record.get("zh", "")
    keywords = " ".join(record.get("keywords", []))
    
    parts = [
        en,
        zh,
        record.get("ja", ""),
        record.get("de", ""),
        record.get("fr", ""),
        record.get("es", ""),
        record.get("ko", ""),
        record.get("category", ""),
        keywords,
        " ".join(record.get("aliases", [])),
        # Extract individual CJK characters for better Chinese single-char matching ("火")
        " ".join(ch for ch in zh if '\u4e00' <= ch <= '\u9fff')
    ]
    return " ".join(p for p in parts if p)


def build_index(records: list[dict]) -> dict:
    """
    Build an inverted index  token → list of doc ids  plus the tokenised
    corpus list (parallel to records).
    """
    corpus_tokens = []   # list[ list[str] ]
    corpus_text   = []   # list[str]  (for TF-IDF)
    inverted      = {}   # token → set of indices

    for idx, rec in enumerate(records):
        text   = build_doc_text(rec)
        tokens = tokenize(text)
        corpus_tokens.append(tokens)
        corpus_text.append(text)

        for tok in set(tokens):
            inverted.setdefault(tok, []).append(idx)

    return {
        "corpus_tokens": corpus_tokens,
        "corpus_text"  : corpus_text,
        "inverted"     : inverted,
    }


def main():
    if not os.path.exists(DATASET):
        raise FileNotFoundError(
            f"{DATASET} not found – run data_collection.py first"
        )

    print("Loading dataset …")
    with open(DATASET, "r", encoding="utf-8") as f:
        records = json.load(f)
    print(f"  {len(records)} records loaded")

    print("Building index …")
    index = build_index(records)

    # ── save lightweight JSON index ──────────────────────────────────────────
    json_index = {
        "corpus_text": index["corpus_text"],
        "inverted"   : {k: v for k, v in index["inverted"].items()},
    }
    with open(INDEX_OUT, "w", encoding="utf-8") as f:
        json.dump(json_index, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  JSON index saved → {INDEX_OUT}")

    # ── save tokenised corpus for BM25 (pickle) ──────────────────────────────
    with open(CORPUS_PKL, "wb") as f:
        pickle.dump(index["corpus_tokens"], f)
    print(f"  BM25 corpus saved → {CORPUS_PKL}")

    # ── vocab stats ──────────────────────────────────────────────────────────
    print(f"  Vocabulary size : {len(index['inverted']):,}")
    print(f"  Sample tokens   : {list(index['inverted'].keys())[:10]}")


if __name__ == "__main__":
    main()
