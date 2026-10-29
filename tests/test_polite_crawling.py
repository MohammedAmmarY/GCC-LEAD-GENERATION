import requests

from scraper import website_crawler
from scraper.website_crawler import crawl_company_website, load_robots


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _ok(url, html="<html><body>page</body></html>"):
    return {"url": url, "success": True, "status_code": 200, "html": html, "error": None}


HOMEPAGE = '<html><body><a href="/about">About</a><a href="/careers">Careers</a><a href="/locations">Locations</a></body></html>'


def _fake_site(monkeypatch, fetched):
    def fake_fetch_page(url):
        fetched.append(url)
        return _ok(url, HOMEPAGE if url == "https://example.com" else "<html><body>x</body></html>")

    monkeypatch.setattr(website_crawler, "fetch_page", fake_fetch_page)


def _serve_robots(monkeypatch, status_code=200, text="", error=None):
    def fake_get(url, headers, timeout):
        assert url == "https://example.com/robots.txt"
        if error:
            raise error
        return FakeResponse(status_code, text)

    monkeypatch.setattr(website_crawler.requests, "get", fake_get)


def _enable_robots(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "RESPECT_ROBOTS_TXT", True)


# --- delay between requests ---------------------------------------------------


def test_crawler_waits_between_requests_but_not_before_the_first(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "CRAWL_DELAY_SECONDS", 2.0)
    waits = []
    monkeypatch.setattr(website_crawler.time, "sleep", waits.append)
    _fake_site(monkeypatch, [])

    crawl_company_website("https://example.com")

    assert waits == [2.0, 2.0, 2.0]  # one pause before each of the 3 extra pages


def test_no_waiting_when_the_delay_is_zero(monkeypatch):
    waits = []
    monkeypatch.setattr(website_crawler.time, "sleep", waits.append)
    _fake_site(monkeypatch, [])

    crawl_company_website("https://example.com")

    assert waits == []


# --- robots.txt ----------------------------------------------------------------


def test_load_robots_parses_rules_for_our_crawler(monkeypatch):
    _serve_robots(monkeypatch, text="User-agent: *\nDisallow: /careers\n")

    robots = load_robots("https://example.com")

    ua = website_crawler.settings.USER_AGENT
    assert robots.can_fetch(ua, "https://example.com/about") is True
    assert robots.can_fetch(ua, "https://example.com/careers") is False
    assert robots.can_fetch(ua, "https://example.com/careers/jobs") is False


def test_a_missing_broken_or_unreachable_robots_txt_means_no_restrictions(monkeypatch):
    _serve_robots(monkeypatch, status_code=404)
    assert load_robots("https://example.com") is None

    _serve_robots(monkeypatch, status_code=500)
    assert load_robots("https://example.com") is None

    _serve_robots(monkeypatch, error=requests.exceptions.Timeout())
    assert load_robots("https://example.com") is None


def test_disallowed_pages_are_skipped_reported_and_replaced_by_the_next_allowed_page(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "MAX_PAGES_PER_WEBSITE", 3)  # homepage + 2
    _enable_robots(monkeypatch)
    _serve_robots(monkeypatch, text="User-agent: *\nDisallow: /locations\n")
    fetched = []
    _fake_site(monkeypatch, fetched)

    result = crawl_company_website("https://example.com")

    assert "https://example.com/locations" not in fetched
    # /locations ranks first, is skipped, and its slot goes to the next pages
    assert fetched == ["https://example.com", "https://example.com/about", "https://example.com/careers"]
    assert result["skipped_by_robots"] == ["https://example.com/locations"]
    assert result["crawl_status"] == "success"


def test_pages_beyond_the_budget_are_not_reported_as_skipped(monkeypatch):
    monkeypatch.setattr(website_crawler.settings, "MAX_PAGES_PER_WEBSITE", 2)  # homepage + 1
    _enable_robots(monkeypatch)
    _serve_robots(monkeypatch, text="User-agent: *\nDisallow: /careers\n")  # would have ranked 3rd
    _fake_site(monkeypatch, [])

    result = crawl_company_website("https://example.com")

    assert result["skipped_by_robots"] == []


def test_a_homepage_blocked_by_robots_is_reported_and_not_fetched(monkeypatch):
    _enable_robots(monkeypatch)
    _serve_robots(monkeypatch, text="User-agent: *\nDisallow: /\n")
    fetched = []
    _fake_site(monkeypatch, fetched)

    result = crawl_company_website("https://example.com")

    assert result["crawl_status"] == "failed: robots_txt"
    assert fetched == []


def test_robots_txt_is_not_downloaded_when_the_setting_is_off(monkeypatch):
    def must_not_be_called(url, headers, timeout):
        raise AssertionError("robots.txt should not be requested")

    monkeypatch.setattr(website_crawler.requests, "get", must_not_be_called)
    _fake_site(monkeypatch, [])

    result = crawl_company_website("https://example.com")  # RESPECT_ROBOTS_TXT is off in tests

    assert result["crawl_status"] == "success"
    assert result["skipped_by_robots"] == []


def test_a_sites_own_crawl_delay_is_honoured_but_capped(monkeypatch):
    _enable_robots(monkeypatch)
    waits = []
    monkeypatch.setattr(website_crawler.time, "sleep", waits.append)
    _fake_site(monkeypatch, [])

    _serve_robots(monkeypatch, text="User-agent: *\nCrawl-delay: 5\n")
    crawl_company_website("https://example.com")
    assert set(waits) == {5.0}

    waits.clear()
    _serve_robots(monkeypatch, text="User-agent: *\nCrawl-delay: 60\n")
    crawl_company_website("https://example.com")
    assert set(waits) == {float(website_crawler.MAX_SITE_CRAWL_DELAY_SECONDS)}


def test_our_own_delay_wins_when_it_is_longer_than_the_sites(monkeypatch):
    _enable_robots(monkeypatch)
    monkeypatch.setattr(website_crawler.settings, "CRAWL_DELAY_SECONDS", 3.0)
    waits = []
    monkeypatch.setattr(website_crawler.time, "sleep", waits.append)
    _fake_site(monkeypatch, [])
    _serve_robots(monkeypatch, text="User-agent: *\nCrawl-delay: 1\n")

    crawl_company_website("https://example.com")

    assert set(waits) == {3.0}