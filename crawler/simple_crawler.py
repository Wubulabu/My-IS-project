#!/usr/bin/env python3
"""简化版Emojipedia爬虫 - 方案B"""

import json, os, sys, time, random, re
from datetime import datetime
from urllib.parse import quote

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://emojipedia.org"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CRAWLED_FILE = os.path.join(DATA_DIR, "crawled_data.json")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]


def fetch_page(url):
    try:
        time.sleep(random.uniform(1.0, 2.5))
        resp = requests.get(
            url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10
        )
        return resp.text if resp.status_code == 200 else None
    except:
        return None


def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    data = {"category": None, "related_tags": []}

    # Get category from breadcrumb
    nav = soup.find("nav", class_="breadcrumb")
    if nav:
        links = nav.find_all("a")
        if len(links) >= 2:
            data["category"] = links[1].get_text().strip()

    # Get tags from meta
    meta = soup.find("meta", attrs={"name": "keywords"})
    if meta and meta.get("content"):
        tags = [t.strip() for t in meta["content"].split(",")]
        data["related_tags"] = [t for t in tags if t and len(t) > 1][:10]

    return data


def crawl_emoji(char, name):
    slug = re.sub(r"[^\w\-]", "", name.lower().replace(" ", "-"))
    url = f"{BASE_URL}/{slug}"

    html = fetch_page(url)
    if not html:
        search_url = f"{BASE_URL}/search?q={quote(char)}"
        html = fetch_page(search_url)
        if html:
            soup = BeautifulSoup(html, "lxml")
            link = soup.find("a", class_="emoji")
            if link and link.get("href"):
                url = BASE_URL + link["href"]
                html = fetch_page(url)

    if not html:
        return None

    data = parse_page(html)
    data["char"] = char
    data["source_url"] = url
    data["crawled_at"] = datetime.now().isoformat()
    return data


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    dataset_path = os.path.join(DATA_DIR, "emoji_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        emojis = json.load(f)

    limit = 50 if args.test else (args.limit or len(emojis))
    print(f"Crawling {limit} emojis...")

    results = {}
    start = time.time()

    for i, rec in enumerate(emojis[:limit]):
        char, name = rec.get("char"), rec.get("en", "")
        if not char or not name:
            continue

        print(f"[{i + 1}/{limit}] {name[:40]}... ", end="", flush=True)
        data = crawl_emoji(char, name)

        if data:
            results[char] = data
            print(
                f"OK (cat={data.get('category', 'N/A')}, tags={len(data.get('related_tags', []))})"
            )
        else:
            print("FAIL")

        if (i + 1) % 50 == 0:
            with open(CRAWLED_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n>>> Saved {len(results)} results")

    with open(CRAWLED_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start
    print(f"\nDone! {len(results)}/{limit} OK in {elapsed / 60:.1f} min")
    print(f"Saved to: {CRAWLED_FILE}")


if __name__ == "__main__":
    main()
