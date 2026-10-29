"""
Wraps the Tavily search API behind one small function.

Why this file exists:
The rest of the app should not need to know or care which search
provider we use. If we ever switch from Tavily to Bing, Google Custom
Search, or something else, this should be the ONLY file that needs to
change - nothing in website_discovery.py (or anything built later)
should mention "Tavily" by name.
"""
from utils.url_utils import BLOCKED_DOMAINS

from typing import TypedDict

from tavily import TavilyClient

from config import settings


class SearchResult(TypedDict):
    url: str
    title: str
    content: str  # short snippet/summary the search API gives us about the page


def search(query: str, max_results: int = 6) -> list[SearchResult]:
    """
    Run a web search and return a list of results as plain dictionaries.

    Raises RuntimeError if no Tavily API key is configured, so a missing
    key fails loudly and clearly here, rather than causing a confusing
    error deep inside the Tavily library.
    """
    if not settings.TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY is not set. Add it to your .env file."
        )

    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    response = client.search(
        query=query,
        max_results=max_results,
        exclude_domains=sorted(BLOCKED_DOMAINS),
    )

    results: list[SearchResult] = []
    for item in response.get("results", []):
        results.append(
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
            }
        )
    return results


def extract_pages(urls: list[str]) -> list[dict]:
    """
    Ask Tavily to fetch these pages and return their cleaned text. Used
    only as a fallback for sites our own crawler can't read.

    Returns [{"url": ..., "text": ...}] for the pages that worked. Pages
    Tavily could not fetch are simply left out. "advanced" mode is used
    because it handles JavaScript-built pages.

    Raises RuntimeError if no Tavily API key is configured.
    """
    if not settings.TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY is not set. Add it to your .env file."
        )

    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    response = client.extract(urls=urls, extract_depth="advanced")

    pages: list[dict] = []
    for item in response.get("results", []):
        pages.append(
            {
                "url": item.get("url", ""),
                "text": item.get("raw_content") or item.get("content") or "",
            }
        )
    return pages