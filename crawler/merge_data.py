#!/usr/bin/env python3
"""
Merge enriched emoji data into the main dataset.

Strategy:
1. Load main dataset and enriched data
2. For each emoji in main dataset:
   - If enriched data exists:
     - Set category field (if not None)
     - Merge related_tags into keywords (deduplicate)
3. Save merged dataset
4. Create backup of original
"""

import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATASET_FILE = os.path.join(DATA_DIR, "emoji_dataset.json")
ENRICHED_FILE = os.path.join(DATA_DIR, "enriched_data.json")


def merge_keywords(existing_keywords, new_tags):
    """
    Merge new tags into existing keywords, avoiding duplicates.
    Returns deduplicated list.
    """
    # Convert all to lowercase for comparison
    existing_lower = {k.lower() for k in existing_keywords}

    # Add new tags that don't exist
    merged = list(existing_keywords)
    for tag in new_tags:
        if tag.lower() not in existing_lower and len(tag) > 1:
            merged.append(tag)
            existing_lower.add(tag.lower())

    return merged


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Merge enriched data into main dataset"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without saving"
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    # Load datasets
    print("Loading datasets...")
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    with open(ENRICHED_FILE, "r", encoding="utf-8") as f:
        enriched = json.load(f)

    print(f"Main dataset: {len(dataset)} emojis")
    print(f"Enriched data: {len(enriched)} emojis")
    print()

    # Statistics
    stats = {
        "category_added": 0,
        "category_skipped_none": 0,
        "category_skipped_exists": 0,
        "keywords_added": 0,
        "total_new_keywords": 0,
        "no_enrichment": 0,
    }

    # Preview some changes
    preview_count = 5
    previews = []

    # Merge data
    for record in dataset:
        char = record.get("char")
        if not char:
            continue

        enriched_data = enriched.get(char)
        if not enriched_data:
            stats["no_enrichment"] += 1
            continue

        # Store original for preview
        original_category = record.get("category", "")
        original_keywords_count = len(record.get("keywords", []))

        # Merge category
        new_category = enriched_data.get("category")
        if new_category and new_category != "None":
            if not record.get("category"):
                record["category"] = new_category
                stats["category_added"] += 1

                if len(previews) < preview_count:
                    previews.append(
                        {
                            "char": char,
                            "name": record.get("en", "")[:40],
                            "action": "category",
                            "old": original_category or "(empty)",
                            "new": new_category,
                        }
                    )
            else:
                stats["category_skipped_exists"] += 1
        else:
            stats["category_skipped_none"] += 1

        # Merge keywords
        related_tags = enriched_data.get("related_tags", [])
        if related_tags:
            existing_keywords = record.get("keywords", [])
            merged_keywords = merge_keywords(existing_keywords, related_tags)

            new_count = len(merged_keywords) - len(existing_keywords)
            if new_count > 0:
                record["keywords"] = merged_keywords
                stats["keywords_added"] += 1
                stats["total_new_keywords"] += new_count

                if len(previews) < preview_count * 2:
                    previews.append(
                        {
                            "char": char,
                            "name": record.get("en", "")[:40],
                            "action": "keywords",
                            "old": f"{len(existing_keywords)} keywords",
                            "new": f"{len(merged_keywords)} keywords (+{new_count})",
                        }
                    )

    # Print preview
    print("=" * 70)
    print("PREVIEW OF CHANGES")
    print("=" * 70)
    for p in previews[:10]:
        print(f"{p['char']} {p['name']:40}")
        print(f"  {p['action']:10}: {p['old']} → {p['new']}")
        print()

    # Print statistics
    print("=" * 70)
    print("MERGE STATISTICS")
    print("=" * 70)
    print(f"Categories added: {stats['category_added']}")
    print(f"Categories skipped (None): {stats['category_skipped_none']}")
    print(f"Categories skipped (exists): {stats['category_skipped_exists']}")
    print(f"Emojis with keyword enrichment: {stats['keywords_added']}")
    print(f"Total new keywords added: {stats['total_new_keywords']}")
    print(f"Emojis without enrichment: {stats['no_enrichment']}")
    print()

    if args.dry_run:
        print("DRY RUN MODE - No files modified")
        return

    # Confirm save
    print("=" * 70)
    if not args.yes:
        response = input("Proceed with merge? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Merge cancelled")
            return

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(DATA_DIR, f"emoji_dataset.premerge_{timestamp}.json")
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        backup_data = f.read()
    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(backup_data)
    print(f"Backup created: {backup_file}")

    # Save merged dataset
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"Merged dataset saved: {DATASET_FILE}")
    print("\n✓ Merge complete!")


if __name__ == "__main__":
    main()
