"""
data_collection.py
------------------
Build the multilingual emoji dataset from the `emoji` library's built-in
CLDR data. Outputs data/emoji_dataset.json, which is the single source of
truth for all downstream retrieval and evaluation code.

Fields per record
-----------------
  char       : the emoji character  (e.g. "😀")
  codepoint  : U+... string         (e.g. "U+1F600")
  en         : English CLDR name    (e.g. "grinning face")
  zh         : Chinese name         (e.g. "咧嘴笑的脸")
  ja         : Japanese name
  de         : German name
  fr         : French name
  keywords   : combined keyword list (English)
  category   : CLDR category string
  aliases    : list of :alias: tokens
"""

import json
import os
import re
import sys
import emoji as emoji_lib

# Force UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── built-in Chinese translation table ───────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from data.zh_map import ZH_MAP

# ── languages we want to extract ──────────────────────────────────────────────
LANGS = ["en", "zh", "ja", "de", "fr", "es", "ar", "ko"]

# ── output path ───────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(DATA_DIR, "emoji_dataset.json")


def _codepoint(char: str) -> str:
    """Return 'U+XXXX[+YYYY...]' for an emoji character."""
    return "+".join(f"U+{ord(c):04X}" for c in char)


def _clean_name(name: str) -> str:
    """Strip surrounding colons and replace underscores with spaces."""
    return re.sub(r"_", " ", name.strip(":")).strip()


def build_dataset() -> list[dict]:
    """Iterate over emoji.EMOJI_DATA and extract multilingual metadata."""
    records = []
    seen = set()

    for char, meta in emoji_lib.EMOJI_DATA.items():
        if char in seen:
            continue
        seen.add(char)

        # ── pull fields ──────────────────────────────────────────────────────
        en_name = _clean_name(meta.get("en", ""))
        if not en_name:
            continue  # skip entries with no English name

        record = {
            "char": char,
            "codepoint": _codepoint(char),
            "aliases": [_clean_name(a) for a in meta.get("alias", [])],
            "keywords": [],
            "category": meta.get("category", ""),
            "status": meta.get("status", ""),
        }

        # ── multilingual names ───────────────────────────────────────────────
        for lang in LANGS:
            raw = meta.get(lang, "")
            record[lang] = _clean_name(raw) if raw else ""

        # ── overlay Chinese from built-in ZH_MAP ─────────────────────────────
        if char in ZH_MAP:
            record["zh"] = ZH_MAP[char]

        # ── build keyword list (en name + aliases + zh name) ─────────────────
        kw_set = set()
        kw_set.update(en_name.lower().split())
        for alias in record["aliases"]:
            kw_set.update(alias.lower().split())
        # add individual Chinese characters from zh name to keywords
        zh_name = record.get("zh", "")
        if zh_name:
            kw_set.update(list(zh_name))   # each Chinese char as a token
        record["keywords"] = sorted(kw_set)

        records.append(record)

    return records


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("Building emoji dataset …")
    records = build_dataset()
    print(f"  Collected {len(records)} emoji records from emoji library")

    # ── merge meme / internet-culture records ─────────────────────────────────
    try:
        from data.meme_extra import MEME_RECORDS
        existing_chars = {r["char"] for r in records}
        added = 0
        for mr in MEME_RECORDS:
            char = mr["char"]
            # enrich keywords with CJK characters from zh field
            kw_set = set(mr.get("keywords", []))
            zh_name = mr.get("zh", "")
            if zh_name:
                kw_set.update(list(zh_name))   # individual CJK tokens
            mr["keywords"] = sorted(kw_set)

            # If the emoji char already exists (e.g. 🐧 for penguin),
            # supplement its zh/keywords; don't add a duplicate record.
            matched = next((r for r in records if r["char"] == char), None)
            if matched:
                # Append meme-specific zh words to existing record
                old_zh = matched.get("zh", "")
                new_zh = mr.get("zh", "")
                if new_zh and new_zh not in old_zh:
                    matched["zh"] = (old_zh + " " + new_zh).strip()
                extra_kw = set(mr.get("keywords", []))
                matched["keywords"] = sorted(set(matched["keywords"]) | extra_kw)
            else:
                # Ensure required fields exist
                mr.setdefault("ja", "")
                mr.setdefault("de", "")
                mr.setdefault("fr", "")
                mr.setdefault("es", "")
                mr.setdefault("ar", "")
                mr.setdefault("ko", "")
                records.append(mr)
                added += 1
        print(f"  Added {added} new meme records (enriched {len(MEME_RECORDS)-added} existing)")
    except ImportError as e:
        print(f"  [warn] Could not load meme_extra: {e}")

    print(f"  Total: {len(records)} records")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"  Saved → {OUT_FILE}")

    # ── quick sanity check ───────────────────────────────────────────────────
    sample = records[:3]
    for r in sample:
        print(f"  {r['char']}  en={r['en']!r:30s}  zh={r['zh']!r}")


if __name__ == "__main__":
    main()
