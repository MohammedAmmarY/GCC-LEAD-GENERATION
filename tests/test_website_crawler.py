"""
Tests for scraper/website_crawler.py

Run with:  pytest tests/test_website_crawler.py -v

None of these tests make real network calls. pytest's built-in
"monkeypatch" fixture temporarily replaces requests.get (or our own
fetch_page function) with a fake version for the duration of one test,
then automatically restores the original afterward.
"""

import requests

from scraper import website_crawler
from scraper.website_crawler import crawl_company_website, crawl_with_extract, find_relevant_links

class FakeResponse:
    """A minimal stand-in for requests.Response, just enough for our tests."""

    def __init__(self, status_code=200, text="<html><body>Hello</body></html>"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError()
            error.response = self
            raise error


# --- fetch_page ----------------------------------------------------------


def test_fetch_page_success(monkeypatch):
    def fake_get(url, headers, timeout):
        return FakeResponse(200, "<html><body>Hello World</body></html>")

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)

    result = fetch_page("https://example.com")

    assert result["success"] is True
    assert result["status_code"] == 200
    assert "Hello World" in result["html"]
    assert result["error"] is None


def test_fetch_page_handles_404(monkeypatch):
    def fake_get(url, headers, timeout):
        return FakeResponse(404, "Not Found")

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)

    result = fetch_page("https://example.com/missing")

    assert result["success"] is False
    assert result["status_code"] == 404
    assert result["error"] == "http_error_404"


def test_fetch_page_handles_500(monkeypatch):
    def fake_get(url, headers, timeout):
        return FakeResponse(500, "Server Error")

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)

    result = fetch_page("https://example.com/broken")

    assert result["success"] is False
    assert result["error"] == "http_error_500"


def test_fetch_page_handles_timeout(monkeypatch):
    def fake_get(url, headers, timeout):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)

    result = fetch_page("https://slow-site.com")

    assert result["success"] is False
    assert result["error"] == "timeout"


def test_fetch_page_handles_connection_error(monkeypatch):
    def fake_get(url, headers, timeout):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)

    result = fetch_page("https://does-not-exist.invalid")

    assert result["success"] is False
    assert result["error"] == "connection_error"


def test_fetch_page_handles_empty_page(monkeypatch):
    def fake_get(url, headers, timeout):
        return FakeResponse(200, "   ")

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)

    result = fetch_page("https://example.com/blank")

    assert result["success"] is False
    assert result["error"] == "empty_page"


# --- find_relevant_links ---------------------------------------------------


def test_find_relevant_links_filters_by_domain_and_keyword():
    html = """
    <a href="/about-us">About Us</a>
    <a href="/random-page">Random</a>
    <a href="https://other-site.com/about">Other site about</a>
    <a href="/careers">Careers</a>
    """
    links = find_relevant_links(html, "https://example.com", exclude_urls=set())

    assert "https://example.com/about-us" in links
    assert "https://example.com/careers" in links
    assert "https://example.com/random-page" not in links  # no relevant keyword
    assert "https://other-site.com/about" not in links  # different domain


def test_find_relevant_links_excludes_already_seen_urls():
    html = '<a href="/about-us">About</a>'
    links = find_relevant_links(
        html, "https://example.com", exclude_urls={"https://example.com/about-us"}
    )
    assert links == []


# --- crawl_company_website --------------------------------------------------


def test_crawl_company_website_success(monkeypatch):
    homepage_html = """
    <html><body>
        Welcome to Example Corp.
        <a href="/about">About</a>
        <a href="/careers">Careers</a>
    </body></html>
    """
    about_html = "<html><body>We are Example Corp, founded in 1990.</body></html>"

    def fake_fetch_page(url):
        if url == "https://example.com":
            return {"url": url, "success": True, "status_code": 200, "html": homepage_html, "error": None}
        if url == "https://example.com/about":
            return {"url": url, "success": True, "status_code": 200, "html": about_html, "error": None}
        if url == "https://example.com/careers":
            # Simulate a page that blocks scrapers - crawl should skip it
            # and keep going, not fail the whole crawl.
            return {"url": url, "success": False, "status_code": 403, "html": None, "error": "http_error_403"}
        raise AssertionError(f"unexpected url fetched: {url}")

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com")

    assert result["crawl_status"] == "success"
    assert "https://example.com" in result["pages_researched"]
    assert "https://example.com/about" in result["pages_researched"]
    assert "https://example.com/careers" not in result["pages_researched"]
    assert "Example Corp" in result["combined_text"]
    assert "founded in 1990" in result["combined_text"]


def test_crawl_company_website_homepage_failure(monkeypatch):
    def fake_fetch_page(url):
        return {"url": url, "success": False, "status_code": None, "html": None, "error": "timeout"}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://down-site.com")

    assert result["crawl_status"] == "failed: timeout"
    assert result["pages_researched"] == []
    assert result["combined_text"] == ""


def test_crawl_company_website_respects_max_pages(monkeypatch):
    # Limit to homepage + 1 extra page, even though 3 relevant links exist.
    monkeypatch.setattr(website_crawler.settings, "MAX_PAGES_PER_WEBSITE", 2)

    homepage_html = """
    <html><body>
        <a href="/about">About</a>
        <a href="/careers">Careers</a>
        <a href="/contact">Contact</a>
    </body></html>
    """

    fetched_urls = []

    def fake_fetch_page(url):
        fetched_urls.append(url)
        # The homepage needs to actually contain the links above so
        # find_relevant_links has something to discover; sub-pages can
        # return simple placeholder content.
        html = homepage_html if url == "https://example.com" else f"<html><body>{url}</body></html>"
        return {"url": url, "success": True, "status_code": 200, "html": html, "error": None}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com")

    assert len(result["pages_researched"]) == 2
    assert len(fetched_urls) == 2


def test_crawl_company_website_truncates_combined_text(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "MAX_TEXT_CHARS_FOR_LLM", 50)

    long_text_html = "<html><body>" + ("x" * 1000) + "</body></html>"

    def fake_fetch_page(url):
        return {"url": url, "success": True, "status_code": 200, "html": long_text_html, "error": None}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com")

    assert len(result["combined_text"]) == 50

    
def test_crawl_company_website_records_email_source_page(monkeypatch):
    homepage_html = '<html><body><a href="/contact">Contact</a></body></html>'
    contact_html = '<html><body>Write to info@example.com</body></html>'

    def fake_fetch_page(url):
        html = homepage_html if url == "https://example.com" else contact_html
        return {"url": url, "success": True, "status_code": 200, "html": html, "error": None}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com")

    assert result["emails_found"] == ["info@example.com"]
    assert result["email_sources"] == {"info@example.com": "https://example.com/contact"}


def test_crawl_company_website_email_on_every_page_credits_first_page(monkeypatch):
    html = '<html><body><a href="/contact">Contact</a> info@example.com</body></html>'

    def fake_fetch_page(url):
        return {"url": url, "success": True, "status_code": 200, "html": html, "error": None}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com")

    assert result["email_sources"] == {"info@example.com": "https://example.com"}


def test_find_relevant_links_treats_trailing_slash_as_same_page():
    html = '<a href="/about-us/">About</a><a href="/about-us">About again</a>'
    links = find_relevant_links(html, "https://example.com", exclude_urls=set())
    assert links == ["https://example.com/about-us/"]


def test_find_relevant_links_skips_homepage_even_with_trailing_slash():
    html = '<a href="/">Home</a><a href="/about">About</a>'
    links = find_relevant_links(html, "https://example.com", exclude_urls={"https://example.com"})
    assert links == ["https://example.com/about"]


def test_find_relevant_links_ignores_keywords_in_domain_name():
    html = '<a href="/blog">Blog</a><a href="/about">About</a>'
    links = find_relevant_links(html, "https://acmeengineering.com", exclude_urls=set())
    assert links == ["https://acmeengineering.com/about"]


def test_crawl_starts_from_site_root_even_if_given_a_deep_url(monkeypatch):
    fetched = []

    def fake_fetch_page(url):
        fetched.append(url)
        return {"url": url, "success": True, "status_code": 200, "html": "<html><body>Home</body></html>", "error": None}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com/us/en/about-us")

    assert fetched[0] == "https://example.com"
    assert result["pages_researched"][0] == "https://example.com"


def test_crawl_falls_back_to_given_url_when_root_fails(monkeypatch):
    def fake_fetch_page(url):
        if url == "https://example.com":
            return {"url": url, "success": False, "status_code": 403, "html": None, "error": "http_error_403"}
        return {"url": url, "success": True, "status_code": 200, "html": "<html><body>About us</body></html>", "error": None}

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com/about")

    assert result["crawl_status"] == "success"
    assert result["pages_researched"] == ["https://example.com/about"]


def _ok(url, html):
    return {"url": url, "success": True, "status_code": 200, "html": html, "error": None}


def test_find_relevant_links_puts_most_useful_pages_first():
    html = (
        '<a href="/news">News</a><a href="/careers">Careers</a>'
        '<a href="/locations">Locations</a><a href="/about">About</a>'
    )
    links = find_relevant_links(html, "https://example.com", exclude_urls=set())
    assert links == [
        "https://example.com/locations",
        "https://example.com/about",
        "https://example.com/careers",
        "https://example.com/news",
    ]


def test_crawl_returns_per_page_text_and_total_length(monkeypatch):
    homepage = '<html><body>Welcome <a href="/locations">Locations</a></body></html>'
    locations = "<html><body>We have an office in Pune.</body></html>"

    def fake_fetch_page(url):
        return _ok(url, homepage if url == "https://example.com" else locations)

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)

    result = crawl_company_website("https://example.com")

    assert result["crawl_status"] == "success"
    assert [p["url"] for p in result["pages"]] == ["https://example.com", "https://example.com/locations"]
    assert result["pages"][1]["text"] == "We have an office in Pune."
    assert result["text_length"] == sum(len(p["text"]) for p in result["pages"])
    assert result["pages_researched"] == ["https://example.com", "https://example.com/locations"]


def test_crawl_fetches_highest_priority_pages_when_budget_is_small(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "MAX_PAGES_PER_WEBSITE", 2)
    homepage = '<a href="/news">News</a><a href="/locations">Locations</a><a href="/about">About</a>'
    fetched = []

    def fake_fetch_page(url):
        fetched.append(url)
        return _ok(url, homepage if url == "https://example.com" else "<html><body>x</body></html>")

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)
    crawl_company_website("https://example.com")

    assert fetched == ["https://example.com", "https://example.com/locations"]


def test_crawl_gives_every_page_a_fair_share_of_the_text_limit(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "MAX_TEXT_CHARS_FOR_LLM", 1000)
    homepage = '<html><body>' + ("home " * 2000) + '<a href="/locations">Locations</a></body></html>'
    locations = "<html><body>Our office is in Pune.</body></html>"

    def fake_fetch_page(url):
        return _ok(url, homepage if url == "https://example.com" else locations)

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)
    result = crawl_company_website("https://example.com")

    assert len(result["combined_text"]) <= 1000
    assert "Our office is in Pune." in result["combined_text"]


def test_crawl_with_extract_asks_for_root_first_then_common_paths():
    asked = []

    def fake_extract(urls):
        asked.extend(urls)
        return []

    crawl_with_extract("https://example.com/us/en/about-us", extract_fn=fake_extract)

    assert asked[0] == "https://example.com"
    assert "https://example.com/locations" in asked
    assert "https://example.com/careers" in asked


def test_crawl_with_extract_builds_the_same_shape_as_the_normal_crawl():
    def fake_extract(urls):
        # Returned out of order, with a trailing slash and messy whitespace.
        return [
            {"url": "https://example.com/locations/", "text": "Our office\n\n  is in Pune."},
            {"url": "https://example.com", "text": "Welcome. Write to info@acme.com today."},
            {"url": "https://example.com/careers", "text": "   "},
        ]

    result = crawl_with_extract("https://example.com", extract_fn=fake_extract)

    assert result["crawl_status"] == "success"
    assert result["pages_researched"] == ["https://example.com", "https://example.com/locations/"]
    assert result["pages"][1]["text"] == "Our office is in Pune."
    assert result["text_length"] == sum(len(p["text"]) for p in result["pages"])
    assert "Our office is in Pune." in result["combined_text"]
    assert result["emails_found"] == ["info@acme.com"]
    assert result["email_sources"] == {"info@acme.com": "https://example.com"}


def test_crawl_with_extract_skips_pages_with_identical_text():
    def fake_extract(urls):
        return [
            {"url": "https://example.com/about", "text": "We build things."},
            {"url": "https://example.com/about-us", "text": "We build things."},
        ]

    result = crawl_with_extract("https://example.com", extract_fn=fake_extract)

    assert result["pages_researched"] == ["https://example.com/about"]


def test_crawl_with_extract_respects_the_page_limit(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "MAX_PAGES_PER_WEBSITE", 2)

    def fake_extract(urls):
        return [{"url": url, "text": f"text of {url}"} for url in urls]

    result = crawl_with_extract("https://example.com", extract_fn=fake_extract)

    assert result["pages_researched"] == ["https://example.com", "https://example.com/locations"]


def test_crawl_with_extract_reports_errors_and_empty_results():
    def broken(urls):
        raise RuntimeError("TAVILY_API_KEY is not set")

    failed = crawl_with_extract("https://example.com", extract_fn=broken)
    assert failed["crawl_status"] == "failed: extract_error: TAVILY_API_KEY is not set"
    assert failed["pages"] == [] and failed["text_length"] == 0

    empty = crawl_with_extract("https://example.com", extract_fn=lambda urls: [])
    assert empty["crawl_status"] == "failed: extract_no_content"