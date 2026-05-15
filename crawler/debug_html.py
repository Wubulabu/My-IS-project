#!/usr/bin/env python3
"""Debug script to inspect Emojipedia HTML structure"""

import sys
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
print("BREADCRUMB SEARCH")
print("=" * 60)
nav = soup.find("nav", class_="breadcrumb")
print(f"nav.breadcrumb: {nav}\n")

# Try other breadcrumb selectors
nav2 = soup.find("nav", {"aria-label": "breadcrumb"})
print(f"nav[aria-label=breadcrumb]: {nav2}\n")

ol = soup.find("ol", class_="breadcrumb")
print(f"ol.breadcrumb: {ol}\n")

print("=" * 60)
print("META KEYWORDS SEARCH")
print("=" * 60)
meta = soup.find("meta", attrs={"name": "keywords"})
print(f"meta[name=keywords]: {meta}\n")

# Try other meta tags
desc = soup.find("meta", attrs={"name": "description"})
print(f"meta[name=description]: {desc}\n")

print("=" * 60)
print("CATEGORY/HEADING SEARCH")
print("=" * 60)
# Look for headings
h1 = soup.find("h1")
print(f"h1: {h1}\n")

# Look for article sections
article = soup.find("article")
if article:
    print(f"article classes: {article.get('class')}\n")
    print(f"article first 500 chars:\n{str(article)[:500]}\n")

# Look for data attributes or structured data
scripts = soup.find_all("script", type="application/ld+json")
print(f"\nFound {len(scripts)} JSON-LD scripts")
if scripts:
    print(
        f"First script: {scripts[0].string[:300] if scripts[0].string else 'empty'}...\n"
    )

print("=" * 60)
print("ALL NAV ELEMENTS")
print("=" * 60)
for i, nav in enumerate(soup.find_all("nav")[:5]):
    print(f"Nav {i}: class={nav.get('class')}, aria-label={nav.get('aria-label')}")
    print(f"  Content preview: {str(nav)[:200]}\n")

print("=" * 60)
print("SECTIONS WITH 'category' or 'tag' in class/id")
print("=" * 60)
for elem in soup.find_all(
    class_=lambda x: x and ("category" in x.lower() or "tag" in x.lower())
):
    print(f"{elem.name}.{elem.get('class')}: {str(elem)[:200]}\n")

print("=" * 60)
print("HTML STRUCTURE (first 3000 chars)")
print("=" * 60)
print(soup.prettify()[:3000])
