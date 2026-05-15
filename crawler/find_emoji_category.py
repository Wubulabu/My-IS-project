#!/usr/bin/env python3
"""Find which category the emoji belongs to"""

import sys
import re
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

html = open("crawler/sample_page.html", "r", encoding="utf-8").read()
soup = BeautifulSoup(html, "lxml")

print("=" * 60)
print('STRATEGY 1: Look for "Smileys" text near the emoji')
print("=" * 60)

# Find all text containing category names
categories = [
    "Smileys",
    "People",
    "Animals",
    "Nature",
    "Food",
    "Drink",
    "Activity",
    "Travel",
    "Places",
    "Objects",
    "Symbols",
    "Flags",
]

for cat in categories:
    # Find elements containing this category name (not in navigation)
    elements = soup.find_all(string=re.compile(cat, re.I))
    # Filter out navigation elements
    relevant = []
    for elem in elements:
        parent = elem.find_parent()
        # Skip if it's in a nav or has link to category list
        if (
            parent
            and parent.name != "a"
            and "navbar" not in str(parent.get("class", []))
        ):
            relevant.append(elem)

    if relevant:
        print(f"\n{cat}: Found {len(relevant)} mentions outside navigation")
        for r in relevant[:3]:
            parent = r.find_parent()
            print(
                f'  In <{parent.name}> classes={parent.get("class")}: "{str(r)[:100]}"'
            )

print("\n" + "=" * 60)
print("STRATEGY 2: Look in URL/slug")
print("=" * 60)
url = "https://emojipedia.org/grinning-face"
print(f"URL: {url}")
print("Slug: grinning-face")
print("This doesn't contain category info.")

print("\n" + "=" * 60)
print("STRATEGY 3: Check if category appears in heading/title area")
print("=" * 60)

h1 = soup.find("h1")
if h1:
    print(f"H1: {h1.get_text(strip=True)}")
    # Check siblings
    next_sibs = list(h1.next_siblings)[:5]
    print(f"Next {len(next_sibs)} siblings after H1:")
    for sib in next_sibs:
        if hasattr(sib, "name"):
            text = sib.get_text(strip=True)[:100]
            print(f"  <{sib.name}> classes={sib.get('class')}: {text}")

print("\n" + "=" * 60)
print("STRATEGY 4: Look for section headings")
print("=" * 60)

sections = soup.find_all(
    ["section", "div"], class_=lambda x: x and "section" in " ".join(x).lower()
)
print(f"Found {len(sections)} section-like elements")
for sec in sections[:5]:
    heading = sec.find(["h1", "h2", "h3"])
    if heading:
        print(f"{heading.name}: {heading.get_text(strip=True)[:80]}")

print("\n" + "=" * 60)
print("STRATEGY 5: Look for data attributes or IDs with category")
print("=" * 60)

cat_elems = soup.find_all(attrs={"data-category": True})
print(f"Elements with data-category: {len(cat_elems)}")
for elem in cat_elems[:5]:
    print(f"  {elem.name} data-category={elem.get('data-category')}")

cat_elems = soup.find_all(id=re.compile("categor", re.I))
print(f'\nElements with id containing "categor": {len(cat_elems)}')

print("\n" + "=" * 60)
print("STRATEGY 6: Look at all H2/H3 headings")
print("=" * 60)

for heading in soup.find_all(["h2", "h3"])[:15]:
    text = heading.get_text(strip=True)
    print(f"{heading.name}: {text}")
