"""
Given a company name, find its official website.

Why this file exists:
This is the "decision" logic for website discovery - it looks at a list
of search results and picks the one most likely to be the company's own
site. It does NOT know anything about which search provider produced
those results (see search_provider.py for that). This separation means
we can test the decision logic with fake data, and swap search providers
without touching this file.
"""

from typing import Callable, Optional, TypedDict

from scraper import search_provider
from utils.url_utils import domain_matches_company, is_blocked_domain, is_valid_url, normalize_url


class WebsiteDiscoveryResult(TypedDict):
    official_website: Optional[str]
    website_status: str  # "found" | "not_found" | "error: <message>"


# A "SearchFunction" is anything shaped like search_provider.search:
# (query: str, max_results: int) -> list[SearchResult]. Accepting this
# as a parameter - instead of calling search_provider.search() directly
# inside this function - means tests can pass in a fake search function
# and never make a real network call. This is the whole function, not a
# framework - just a plain argument with a default value.
SearchFunction = Callable[[str, int], list[search_provider.SearchResult]]


def find_official_website(
    company_name: str,
    search_fn: SearchFunction = search_provider.search,
) -> WebsiteDiscoveryResult:
    """
    Search the web for the company and return the most likely official
    website. Statuses:
      "found"            - a result whose domain resembles the company name
      "found_unverified" - no domain resembled the name, so this is just
                           the top remaining search result. Check by hand.
      "not_found"        - nothing usable in the results
      "error: ..."       - the search itself failed
    """
    query = f"{company_name} official website"

    try:
        results = search_fn(query, 8)
    except Exception as error:
        return {
            "official_website": None,
            "website_status": f"error: {error}",
        }

    # Keep valid URLs that aren't on the blocklist (backstop for anything
    # the search provider's own exclusion missed).
    candidates = []
    for result in results:
        url = result.get("url", "")
        if url and is_valid_url(url) and not is_blocked_domain(url):
            candidates.append(url)

    # First choice: a result whose domain looks like the company name.
    for url in candidates:
        if domain_matches_company(company_name, url):
            return {"official_website": normalize_url(url), "website_status": "found"}

    # Fallback: the top remaining result, clearly flagged as unverified.
    if candidates:
        return {
            "official_website": normalize_url(candidates[0]),
            "website_status": "found_unverified",
        }

    return {"official_website": None, "website_status": "not_found"}
