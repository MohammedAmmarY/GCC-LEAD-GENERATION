import pytest

from config import settings


@pytest.fixture(autouse=True)
def quiet_test_settings(monkeypatch):
    """
    Most tests use tiny fake pages and never touch the network, so:
    - the "thin content" check is switched off,
    - the crawler does not wait between requests,
    - robots.txt is not downloaded.
    Tests that check those behaviours turn them back on themselves.
    """
    monkeypatch.setattr(settings, "MIN_CONTENT_CHARS", 0)
    monkeypatch.setattr(settings, "CRAWL_DELAY_SECONDS", 0)
    monkeypatch.setattr(settings, "RESPECT_ROBOTS_TXT", False)