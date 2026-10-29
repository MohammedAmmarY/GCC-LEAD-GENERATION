"""
Fetches a company's website: the homepage plus a handful of relevant
pages (About, Careers, Locations, etc.), with limits and error handling
so one broken, slow, or blocking site never crashes the whole batch.

Why this file exists:
We deliberately do NOT crawl an entire website. That would be slow,
sometimes rude to the target server, and would hand the LLM far more
text than it needs. Instead we fetch the homepage, look for links whose
URL suggests they're relevant to our research (About, Careers,
Locations, Engineering...), and fetch a small, bounded number of those.
"""
import requests
import re
import time

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from config import settings
from scraper.content_parser import (
    build_combined_text,
    extract_emails,
    extract_links,
    extract_readable_text,
    is_same_domain,
)

from scraper import search_provider
from utils.url_utils import get_site_root, url_key

# Keywords that mark a link as worth fetching, in PRIORITY order: when
# there are more relevant links than we are allowed to fetch, pages
# matching earlier keywords are crawled first (locations and offices are
# where India mentions usually are).
RELEVANT_KEYWORDS = [
    "location",
    "office",
    "global",
    "about",
    "company",
    "career",
    "contact",
    "engineering",
    "technology",
    "leadership",
    "team",
    "service",
    "research",
    "news",
    "job",
]


def fetch_page(url: str) -> dict:
    """
    Fetch one page over HTTP(S) and return a result dictionary.

    This function never raises an exception - every possible failure
    (timeout, DNS/connection error, HTTP 4xx/5xx, an empty response) is
    caught here and turned into a clear {"success": False, "error": ...}
    result. That way the caller (crawl_company_website, and eventually
    the pipeline) can decide what to do next, instead of one bad website
    crashing the whole run.
    """
    headers = {
        "User-Agent": settings.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()  # raises HTTPError for 4xx/5xx responses

        if not response.text.strip():
            return {
                "url": url,
                "success": False,
                "status_code": response.status_code,
                "html": None,
                "error": "empty_page",
            }

        return {
            "url": url,
            "success": True,
            "status_code": response.status_code,
            "html": response.text,
            "error": None,
        }

    except requests.exceptions.Timeout:
        return {"url": url, "success": False, "status_code": None, "html": None, "error": "timeout"}

    except requests.exceptions.ConnectionError:
        # Covers DNS failures ("no such domain") and refused connections.
        return {"url": url, "success": False, "status_code": None, "html": None, "error": "connection_error"}

    except requests.exceptions.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        return {
            "url": url,
            "success": False,
            "status_code": status_code,
            "html": None,
            "error": f"http_error_{status_code}",
        }

    except requests.exceptions.TooManyRedirects:
        return {"url": url, "success": False, "status_code": None, "html": None, "error": "too_many_redirects"}

    except requests.exceptions.RequestException as error:
        # Catch-all for anything else requests can raise (invalid URL,
        # malformed response, etc.) - still reported, never swallowed
        # silently.
        return {"url": url, "success": False, "status_code": None, "html": None, "error": f"request_error: {error}"}


def find_relevant_links(html: str, base_url: str, exclude_urls: set[str]) -> list[str]:
    """
    Look through every link on a page and return the ones worth fetching,
    most useful first: on the same domain, not already fetched, and whose
    path contains one of RELEVANT_KEYWORDS. Links matching earlier
    keywords in that list come first; ties keep their page order.
    """
    all_links = extract_links(html, base_url)

    ranked: list[tuple[int, str]] = []
    # url_key() makes "https://x.com" and "https://x.com/" count as the
    # same page, so we never fetch one page twice.
    seen: set[str] = {url_key(url) for url in exclude_urls}

    for link in all_links:
        key = url_key(link)
        if key in seen:
            continue

        if not is_same_domain(link, base_url):
            continue

        # Look for keywords in the page's path only, not the domain name.
        parsed = urlparse(link)
        path_and_query = f"{parsed.path}?{parsed.query}".lower()
        matches = [
            position
            for position, keyword in enumerate(RELEVANT_KEYWORDS)
            if keyword in path_and_query
        ]
        if matches:
            ranked.append((min(matches), link))  # lower number = higher priority
            seen.add(key)

    ranked.sort(key=lambda item: item[0])  # sort is stable: ties keep page order
    return [link for _, link in ranked]


# A site's own robots.txt can ask crawlers to wait between requests. We
# honour that, but never wait longer than this because a site asks for it.
MAX_SITE_CRAWL_DELAY_SECONDS = 10


def load_robots(root_url: str) -> RobotFileParser | None:
    """
    Download and parse a site's robots.txt. Returns None when there is no
    usable one (it is missing, an error page, or the request failed),
    which we treat as "no restrictions".
    """
    try:
        response = requests.get(
            f"{root_url}/robots.txt",
            headers={"User-Agent": settings.USER_AGENT},
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


def _allowed(robots: RobotFileParser | None, url: str) -> bool:
    """True if there is no robots.txt, or it allows our crawler to fetch this URL."""
    return robots is None or robots.can_fetch(settings.USER_AGENT, url)


def _crawl_delay(robots: RobotFileParser | None) -> float:
    """Seconds to wait between requests: our setting, or the site's own Crawl-delay if longer."""
    delay = settings.CRAWL_DELAY_SECONDS
    if robots is not None:
        site_delay = robots.crawl_delay(settings.USER_AGENT)
        if site_delay:
            delay = max(delay, min(float(site_delay), MAX_SITE_CRAWL_DELAY_SECONDS))
    return delay


def _pause(seconds: float) -> None:
    """Wait between requests to the same site, so we don't hammer it."""
    if seconds > 0:
        time.sleep(seconds)


def _fetch_if_allowed(url: str, robots: RobotFileParser | None) -> dict:
    """fetch_page(), unless the site's robots.txt asks crawlers to stay away."""
    if not _allowed(robots, url):
        return {"url": url, "success": False, "status_code": None, "html": None, "error": "robots_txt"}
    return fetch_page(url)


def crawl_company_website(homepage_url: str) -> dict:
    """
    Fetch a company's homepage plus a bounded number of relevant pages.

    The crawl always starts from the site's root address, even if the URL
    we were given is a deeper page, so the real homepage is never skipped.
    If the root can't be fetched, it falls back to the URL we were given.

    It is polite: it waits settings.CRAWL_DELAY_SECONDS between requests
    to the site (longer if the site's robots.txt asks for that), and when
    settings.RESPECT_ROBOTS_TXT is on it skips pages the site's robots.txt
    disallows.

    Returns a dictionary with:
        pages_researched: list of URLs successfully fetched
        pages: [{"url": ..., "text": ...}] full cleaned text of each page
        text_length: total characters of text across all pages
        combined_text: all pages joined for the LLM, within
            settings.MAX_TEXT_CHARS_FOR_LLM (every page gets a fair share)
        crawl_status: "success" if the first page was fetched, otherwise
            "failed: <reason>" (for example "failed: robots_txt")
        emails_found: email addresses found on the fetched pages
        email_sources: {email: URL of the first page it was found on}
        skipped_by_robots: relevant pages we left out because of robots.txt
    """
    root_url = get_site_root(homepage_url)
    robots = load_robots(root_url) if settings.RESPECT_ROBOTS_TXT else None
    delay = _crawl_delay(robots)

    homepage_result = _fetch_if_allowed(root_url, robots)

    if not homepage_result["success"] and url_key(root_url) != url_key(homepage_url):
        _pause(delay)
        homepage_result = _fetch_if_allowed(homepage_url, robots)

    if not homepage_result["success"]:
        return {
            "pages_researched": [],
            "pages": [],
            "text_length": 0,
            "combined_text": "",
            "crawl_status": f"failed: {homepage_result['error']}",
            "emails_found": [],
            "email_sources": {},
            "skipped_by_robots": [],
        }

    start_url = homepage_result["url"]
    pages = [{"url": start_url, "text": extract_readable_text(homepage_result["html"])}]

    email_sources: dict[str, str] = {}
    for email in extract_emails(homepage_result["html"]):
        email_sources.setdefault(email, start_url)

    remaining_page_budget = max(settings.MAX_PAGES_PER_WEBSITE - 1, 0)

    candidate_links = find_relevant_links(
        homepage_result["html"],
        start_url,
        exclude_urls={start_url},
    )

    # Pages we wanted but robots.txt disallows are left out and reported;
    # the freed slots go to the next allowed pages.
    skipped_by_robots = [
        link for link in candidate_links[:remaining_page_budget] if not _allowed(robots, link)
    ]
    links_to_fetch = [link for link in candidate_links if _allowed(robots, link)][:remaining_page_budget]

    for link in links_to_fetch:
        _pause(delay)
        page_result = fetch_page(link)

        if page_result["success"]:
            pages.append({"url": page_result["url"], "text": extract_readable_text(page_result["html"])})
            for email in extract_emails(page_result["html"]):
                email_sources.setdefault(email, page_result["url"])

    return {
        "pages_researched": [page["url"] for page in pages],
        "pages": pages,
        "text_length": sum(len(page["text"]) for page in pages),
        "combined_text": build_combined_text(pages, settings.MAX_TEXT_CHARS_FOR_LLM),
        "crawl_status": "success",
        "emails_found": list(email_sources),
        "email_sources": email_sources,
        "skipped_by_robots": skipped_by_robots,
    }


# Pages asked for when fetching a site through the extraction service,
# which cannot follow links the way our own crawler does. A page that
# doesn't exist simply comes back as a failure.
EXTRACT_FALLBACK_PATHS = [
    "/locations",
    "/about",
    "/about-us",
    "/careers",
    "/contact",
    "/contact-us",
]


def crawl_with_extract(homepage_url: str, extract_fn=search_provider.extract_pages) -> dict:
    """
    Fallback for sites our own crawler can't read: blocked with HTTP 403,
    or built with JavaScript so almost no text comes back. Instead of
    downloading the pages ourselves, ask the search provider's extraction
    service to fetch them and return clean text.

    It cannot follow links like crawl_company_website does, so it asks for
    the site's root plus a few common page paths (EXTRACT_FALLBACK_PATHS).
    Returns a dictionary in the same shape as crawl_company_website.
    extract_fn can be replaced in tests so no real API call is made.
    """
    root_url = get_site_root(homepage_url)
    urls = [root_url] + [root_url + path for path in EXTRACT_FALLBACK_PATHS]

    failed = {
        "pages_researched": [],
        "pages": [],
        "text_length": 0,
        "combined_text": "",
        "emails_found": [],
        "email_sources": {},
    }

    try:
        extracted = extract_fn(urls)
    except Exception as error:
        return {**failed, "crawl_status": f"failed: extract_error: {error}"}

    # Keep our requested order (root first) no matter how the service
    # returns the results.
    order = {url_key(url): position for position, url in enumerate(urls)}
    extracted = sorted(extracted, key=lambda page: order.get(url_key(page["url"]), len(urls)))

    pages: list[dict] = []
    seen_texts: set[str] = set()
    for item in extracted:
        text = re.sub(r"\s+", " ", item.get("text", "")).strip()
        # Skip empty pages, and pages that are the same text again (for
        # example /about and /about-us redirecting to one page).
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        pages.append({"url": item["url"], "text": text})

    pages = pages[: settings.MAX_PAGES_PER_WEBSITE]

    if not pages:
        return {**failed, "crawl_status": "failed: extract_no_content"}

    email_sources: dict[str, str] = {}
    for page in pages:
        for email in extract_emails(page["text"]):
            email_sources.setdefault(email, page["url"])

    return {
        "pages_researched": [page["url"] for page in pages],
        "pages": pages,
        "text_length": sum(len(page["text"]) for page in pages),
        "combined_text": build_combined_text(pages, settings.MAX_TEXT_CHARS_FOR_LLM),
        "crawl_status": "success",
        "emails_found": list(email_sources),
        "email_sources": email_sources,
    }