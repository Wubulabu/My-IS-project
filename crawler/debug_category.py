#!/usr/bin/env python3
"""Debug script to find category and tags in page body"""

import sys
import json
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

url = "https://emojipedia.org/grinning-face"
print(f"Fetching: {url}\n")

html = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    },
).text

soup = BeautifulSoup(html, "lxml")

print("=" * 60)
print("SEARCHING FOR CATEGORY INFO")
print("=" * 60)

# Look for links containing category
links = soup.find_all("a", href=lambda x: x and "/categories/" in x)
print(f"Found {len(links)} links with /categories/ in href:\n")
for link in links[:10]:
    print(f"  {link.get('href')} -> {link.get_text(strip=True)}")

print("\n" + "=" * 60)
print("SEARCHING FOR TAGS/RELATED")
print("=" * 60)

# Look for sections with "related" or "similar"
for heading in soup.find_all(["h2", "h3", "h4"]):
    text = heading.get_text(strip=True).lower()
    if "related" in text or "similar" in text or "tag" in text:
        print(f"\n{heading.name}: {heading.get_text(strip=True)}")
        # Get next sibling content
        next_elem = heading.find_next_sibling()
        if next_elem:
            print(f"  Next sibling: {next_elem.name}")
            # Find all links in the section
            links = next_elem.find_all("a", href=True)[:10]
            for link in links:
                print(f"    - {link.get_text(strip=True)} ({link['href']})")

print("\n" + "=" * 60)
print("JSON-LD STRUCTURED DATA")
print("=" * 60)

scripts = soup.find_all("script", type="application/ld+json")
for i, script in enumerate(scripts):
    if script.string:
        try:
            data = json.loads(script.string)
            print(f"\nScript {i}:")
            print(json.dumps(data, indent=2)[:500])
        except:
            pass

print("\n" + "=" * 60)
print("NEXT.JS DATA (looking for __NEXT_DATA__)")
print("=" * 60)

next_data = soup.find("script", id="__NEXT_DATA__")
if next_data and next_data.string:
    try:
        data = json.loads(next_data.string)
        # Try to find category in the data
        data_str = json.dumps(data, indent=2)

        # Look for category mentions
        if "category" in data_str.lower():
            print("Found 'category' in Next.js data!")
            # Extract relevant parts
            lines = data_str.split("\n")
            for i, line in enumerate(lines):
                if "category" in line.lower():
                    # Print context around the line
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    print("\n".join(lines[start:end]))
                    print("---")

        print(f"\nTotal Next.js data size: {len(data_str)} chars")
        print(f"First 1000 chars:\n{data_str[:1000]}")
    except Exception as e:
        print(f"Error parsing Next.js data: {e}")
else:
    print("No __NEXT_DATA__ found")

print("\n" + "=" * 60)
print("ALL <a> WITH 'smileys' OR 'people' (common categories)")
print("=" * 60)
for link in soup.find_all("a", href=True):
    href = link.get("href", "").lower()
    text = link.get_text(strip=True).lower()
    if "smileys" in href or "smileys" in text or "people" in href or "people" in text:
        print(f"{link['href']} -> {link.get_text(strip=True)}")
