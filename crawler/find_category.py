#!/usr/bin/env python3
"""Find category list structure"""

import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

html = open("crawler/sample_page.html", "r", encoding="utf-8").read()
soup = BeautifulSoup(html, "lxml")

# Find the /smileys link
link = soup.find("a", href="/smileys")
if link:
    print("Found /smileys link")

    li = link.find_parent("li")
    print(f"Parent <li> classes: {li.get('class') if li else None}")

    ul = link.find_parent("ul")
    print(f"Parent <ul> classes: {ul.get('class') if ul else None}")

    if ul:
        lis = ul.find_all("li")
        print(f"\nTotal items in list: {len(lis)}")
        print("First 15 category items:")
        for item in lis[:15]:
            a = item.find("a")
            if a:
                print(f"  {a.get('href', '')} -> {a.get_text(strip=True)}")

# Now check if this is a navigation menu showing which category the current emoji belongs to
print("\n" + "=" * 60)
print("LOOKING FOR ACTIVE/SELECTED CATEGORY")
print("=" * 60)

# Look for data-active or aria-current attributes
active_links = soup.find_all("a", attrs={"data-active": "true"})
print(f"Found {len(active_links)} links with data-active=true:")
for link in active_links[:10]:
    print(f"  {link.get('href', '')} -> {link.get_text(strip=True)}")

# Look for aria-current
current_links = soup.find_all("a", attrs={"aria-current": True})
print(f"\nFound {len(current_links)} links with aria-current:")
for link in current_links[:10]:
    print(f"  {link.get('href', '')} -> {link.get_text(strip=True)}")

# Look for "active" class
active_class = soup.find_all(
    "a", class_=lambda x: x and "active" in " ".join(x).lower()
)
print(f'\nFound {len(active_class)} links with "active" in class:')
for link in active_class[:10]:
    print(f"  {link.get('href', '')} -> {link.get_text(strip=True)}")
    print(f"    classes: {link.get('class')}")
