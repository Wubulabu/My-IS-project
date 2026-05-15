import json
import os

data_path = r"c:\Users\sduu26\git\IS\data\emoji_dataset.json"

with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

count = 0
for r in data:
    zh = r.get("zh", "")
    if "爱心" in zh:
        # If zh is like "红心 爱心", replace it with just "红心" if "爱心" is already a separate word or redundant
        # Actually, let's just remove " 爱心" and "爱心 "
        new_zh = zh.replace(" 爱心", "").replace("爱心 ", "").strip()
        if not new_zh: # if it was just "爱心"
            new_zh = "爱心"
        if new_zh != zh:
            r["zh"] = new_zh
            count += 1

print(f"Updated {count} records in {data_path}")

with open(data_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
