import pytest

from scraper import search_provider


class FakeTavilyClient:
    """Records how it was called and returns canned answers - no network."""

    calls = []

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, query, max_results, exclude_domains):
        FakeTavilyClient.calls.append(("search", query, max_results, exclude_domains))
        return {"results": [{"url": "https://www.honeywell.com", "title": "Honeywell", "content": "snippet"}]}

    def extract(self, urls, extract_depth):
        FakeTavilyClient.calls.append(("extract", urls, extract_depth))
        return {
            "results": [
                {"url": "https://example.com", "raw_content": "Home page text"},
                {"url": "https://example.com/about", "content": "Older field name"},
            ],
            "failed_results": [{"url": "https://example.com/careers", "error": "not found"}],
        }


@pytest.fixture
def fake_tavily(monkeypatch):
    FakeTavilyClient.calls = []
    monkeypatch.setattr(search_provider, "TavilyClient", FakeTavilyClient)
    monkeypatch.setattr(search_provider.settings, "TAVILY_API_KEY", "tvly-test")
    return FakeTavilyClient


def test_search_asks_tavily_to_exclude_blocked_domains(fake_tavily):
    results = search_provider.search("Honeywell official website", 8)

    kind, query, max_results, exclude = fake_tavily.calls[0]
    assert (kind, query, max_results) == ("search", "Honeywell official website", 8)
    assert "linkedin.com" in exclude
    assert results == [{"url": "https://www.honeywell.com", "title": "Honeywell", "content": "snippet"}]


def test_extract_pages_uses_advanced_mode_and_returns_url_and_text(fake_tavily):
    pages = search_provider.extract_pages(["https://example.com", "https://example.com/about", "https://example.com/careers"])

    assert fake_tavily.calls[0][2] == "advanced"
    assert pages == [
        {"url": "https://example.com", "text": "Home page text"},
        {"url": "https://example.com/about", "text": "Older field name"},
    ]


def test_search_and_extract_need_an_api_key(monkeypatch):
    monkeypatch.setattr(search_provider.settings, "TAVILY_API_KEY", None)

    with pytest.raises(RuntimeError):
        search_provider.search("anything")
    with pytest.raises(RuntimeError):
        search_provider.extract_pages(["https://example.com"])