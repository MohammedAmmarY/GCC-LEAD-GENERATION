"""
Try the Tavily Extract fallback on one site and show what comes back.
This makes a real Tavily call, so it uses credits.

Run with:
    python debug_extract.py https://the-company-site.com
"""

import sys

from scraper.website_crawler import crawl_with_extract

result = crawl_with_extract(sys.argv[1])

print("Status:", result["crawl_status"])
print("Pages:", result["pages_researched"])
print("Text length:", result["text_length"])
print("Emails found:", result["emails_found"])
for page in result["pages"]:
    print("-", page["url"], len(page["text"]), "chars:", page["text"][:150])