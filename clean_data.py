
import json
import os
import re

DATA_DIR = "data"
IN_FILE = os.path.join(DATA_DIR, "emoji_dataset.json")
OUT_FILE = os.path.join(DATA_DIR, "emoji_dataset_cleaned.json")

def clean():
    if not os.path.exists(IN_FILE):
        print(f"Error: {IN_FILE} not found.")
        return

    with open(IN_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"Original records: {len(records)}")
    
    cleaned = []
    seen_chars = set()
    
    # ── Regex for basic CJK detection ──
    cjk_re = re.compile(r"[\u4e00-\u9fff]")

    for r in records:
        char = r.get("char")
        if not char or char in seen_chars:
            continue
        
        # 1. Basic string cleaning for all fields
        for key in ["en", "zh", "ja", "de", "fr", "es", "ar", "ko", "category"]:
            if key in r and isinstance(r[key], str):
                r[key] = r[key].strip()
        
        # 2. Skip if no basic identification exists
        if not r.get("en") and not r.get("zh"):
            continue

        # 3. Keyword enrichment & deduplication
        keywords = set(r.get("keywords", []))
        # Ensure en and zh name parts are in keywords
        if r.get("en"):
            keywords.update(r["en"].lower().split())
        if r.get("zh"):
            # Add Chinese chars as individual tokens
            keywords.update(list(r["zh"]))
            # Also add common segments if space-separated
            keywords.update(r["zh"].split())
        
        # Remove empty or junk keywords
        r["keywords"] = sorted([k for k in keywords if k.strip() and len(k) > 0])
        
        # 4. Seen tracking
        seen_chars.add(char)
        cleaned.append(r)

    # Sort by codepoint for consistency
    cleaned.sort(key=lambda x: x.get("codepoint", ""))

    print(f"Cleaned records: {len(cleaned)}")
    
    # Write back to a temp file first
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    # Replace original if successful
    os.replace(OUT_FILE, IN_FILE)
    print(f"Successfully cleaned and updated {IN_FILE}")

if __name__ == "__main__":
    clean()
