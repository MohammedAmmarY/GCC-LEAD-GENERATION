"""
Tests for utils/url_utils.py

Run with:  pytest tests/test_url_utils.py -v
"""

from utils.url_utils import (
    get_domain,
    is_blocked_domain,
    is_valid_url,
    normalize_url,
    domain_matches_company,
    url_key,
)


def test_get_domain_strips_www_and_path():
    assert get_domain("https://www.honeywell.com/us/en/about") == "honeywell.com"


def test_get_domain_handles_no_www():
    assert get_domain("https://honeywell.com") == "honeywell.com"


def test_get_domain_handles_subdomain():
    assert get_domain("https://in.linkedin.com/company/honeywell") == "in.linkedin.com"


def test_is_blocked_domain_true_for_exact_match():
    assert is_blocked_domain("https://www.linkedin.com/company/honeywell") is True


def test_is_blocked_domain_true_for_subdomain_match():
    assert is_blocked_domain("https://in.linkedin.com/company/honeywell") is True


def test_is_blocked_domain_true_for_linkedin_shortener():
    assert is_blocked_domain("https://lnkd.in/abc123") is True


def test_is_blocked_domain_false_for_real_company_site():
    assert is_blocked_domain("https://www.honeywell.com") is False


def test_is_valid_url_accepts_http_and_https():
    assert is_valid_url("https://honeywell.com") is True
    assert is_valid_url("http://honeywell.com") is True


def test_is_valid_url_rejects_bad_input():
    assert is_valid_url("") is False
    assert is_valid_url("not a url") is False
    assert is_valid_url("mailto:someone@honeywell.com") is False


def test_normalize_url_adds_missing_scheme():
    assert normalize_url("honeywell.com") == "https://honeywell.com"


def test_normalize_url_strips_trailing_slash():
    assert normalize_url("https://honeywell.com/") == "https://honeywell.com"


def test_normalize_url_leaves_clean_url_unchanged():
    assert normalize_url("https://honeywell.com") == "https://honeywell.com"

def test_domain_matches_company_basic_names():
    assert domain_matches_company("Honeywell", "https://www.honeywell.com") is True
    assert domain_matches_company("Rockwell Automation", "https://www.rockwellautomation.com") is True
    assert domain_matches_company("JEC DESIGN CONSULTANTS", "https://jecdesignconsultants.com") is True


def test_domain_matches_company_ignores_legal_suffixes():
    assert domain_matches_company("Honeywell International Inc.", "https://www.honeywell.com/us/en") is True
    assert domain_matches_company("PMI Corp", "https://www.pmicorp.com") is True


def test_domain_matches_company_rejects_unrelated_domains():
    assert domain_matches_company("Emerson", "https://news.example.com/emerson-story") is False
    assert domain_matches_company("Tata Consultancy Services", "https://www.tcs.com") is False


def test_domain_matches_company_is_strict_for_very_short_names():
    assert domain_matches_company("GE", "https://ge.com") is True
    assert domain_matches_company("GE", "https://www.image.com") is False


def test_url_key_treats_equivalent_urls_as_the_same():
    assert url_key("https://example.com") == url_key("https://example.com/")
    assert url_key("https://Example.com/About/") == url_key("https://example.com/About")
    assert url_key("https://example.com/a#top") == url_key("https://example.com/a")


def test_url_key_keeps_different_pages_different():
    assert url_key("https://example.com/a") != url_key("https://example.com/b")
    assert url_key("https://example.com/a?p=1") != url_key("https://example.com/a?p=2")