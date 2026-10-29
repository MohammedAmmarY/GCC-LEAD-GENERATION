"""
One-off debugging script: shows the raw Tavily search results for a
company, and whether each one passes or fails the website-discovery
filters - so you can see exactly why a particular URL was (or wasn't)
chosen as the "official website".

Run with:
    python debug_discovery.py "Company Name"
"""

import sys

from scraper import search_provider
from utils.url_utils import get_domain, is_blocked_domain, is_valid_url

company_name = sys.argv[1] if len(sys.argv) > 1 else "Honeywell"
query = f"{company_name} official website"

print(f"Query: {query}\n")

results = search_provider.search(query, max_results=5)

for i, result in enumerate(results, start=1):
    url = result.get("url", "")
    print(f"{i}. {url}")
    print(f"   domain: {get_domain(url)!r}")
    print(f"   is_valid_url: {is_valid_url(url)}")
    print(f"   is_blocked_domain: {is_blocked_domain(url)}")
    print()
