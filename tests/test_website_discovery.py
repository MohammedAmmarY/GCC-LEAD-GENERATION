"""
Tests for scraper/website_discovery.py

Run with:  pytest tests/test_website_discovery.py -v

These tests never call the real Tavily API. Instead, we write small fake
"search functions" that return canned results, and pass them in via the
search_fn parameter. This is possible specifically because
find_official_website() accepts the search function as an argument
instead of importing and calling Tavily directly.
"""

from scraper.website_discovery import find_official_website


def test_picks_first_non_blocked_result():
    def fake_search(query: str, max_results: int):
        return [
            {"url": "https://www.linkedin.com/company/honeywell", "title": "", "content": ""},
            {"url": "https://www.honeywell.com", "title": "Honeywell", "content": ""},
            {"url": "https://en.wikipedia.org/wiki/Honeywell", "title": "", "content": ""},
        ]

    result = find_official_website("Honeywell", search_fn=fake_search)

    assert result["website_status"] == "found"
    assert result["official_website"] == "https://www.honeywell.com"


def test_skips_multiple_blocked_domains_in_a_row():
    def fake_search(query: str, max_results: int):
        return [
            {"url": "https://www.linkedin.com/company/emerson", "title": "", "content": ""},
            {"url": "https://en.wikipedia.org/wiki/Emerson_Electric", "title": "", "content": ""},
            {"url": "https://www.crunchbase.com/organization/emerson", "title": "", "content": ""},
            {"url": "https://www.emerson.com", "title": "Emerson", "content": ""},
        ]

    result = find_official_website("Emerson", search_fn=fake_search)

    assert result["website_status"] == "found"
    assert result["official_website"] == "https://www.emerson.com"


def test_returns_not_found_when_all_results_are_blocked():
    def fake_search(query: str, max_results: int):
        return [
            {"url": "https://www.linkedin.com/company/xyz", "title": "", "content": ""},
            {"url": "https://en.wikipedia.org/wiki/Xyz", "title": "", "content": ""},
        ]

    result = find_official_website("Some Obscure Company", search_fn=fake_search)

    assert result["website_status"] == "not_found"
    assert result["official_website"] is None


def test_returns_not_found_when_no_results():
    def fake_search(query: str, max_results: int):
        return []

    result = find_official_website("Nonexistent Company", search_fn=fake_search)

    assert result["website_status"] == "not_found"
    assert result["official_website"] is None


def test_skips_invalid_urls():
    def fake_search(query: str, max_results: int):
        return [
            {"url": "not-a-real-url", "title": "", "content": ""},
            {"url": "https://www.caterpillar.com", "title": "Caterpillar", "content": ""},
        ]

    result = find_official_website("Caterpillar", search_fn=fake_search)

    assert result["website_status"] == "found"
    assert result["official_website"] == "https://www.caterpillar.com"


def test_normalizes_the_chosen_url():
    def fake_search(query: str, max_results: int):
        return [{"url": "https://www.rockwellautomation.com/", "title": "", "content": ""}]

    result = find_official_website("Rockwell Automation", search_fn=fake_search)

    # trailing slash should be stripped by normalize_url
    assert result["official_website"] == "https://www.rockwellautomation.com"


def test_search_function_error_is_captured_not_raised():
    def broken_search(query: str, max_results: int):
        raise ConnectionError("network is down")

    result = find_official_website("Honeywell", search_fn=broken_search)

    assert result["official_website"] is None
    assert result["website_status"].startswith("error:")


def test_prefers_result_whose_domain_matches_company_name():
    def fake_search(query: str, max_results: int):
        return [
            {"url": "https://www.industry-news-site.com/honeywell-story", "title": "", "content": ""},
            {"url": "https://www.honeywell.com", "title": "", "content": ""},
        ]

    result = find_official_website("Honeywell", search_fn=fake_search)

    assert result["website_status"] == "found"
    assert result["official_website"] == "https://www.honeywell.com"


def test_falls_back_to_first_result_flagged_unverified():
    def fake_search(query: str, max_results: int):
        return [{"url": "https://www.tcs.com", "title": "", "content": ""}]

    result = find_official_website("Tata Consultancy Services", search_fn=fake_search)

    assert result["website_status"] == "found_unverified"
    assert result["official_website"] == "https://www.tcs.com"
