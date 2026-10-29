"""
Tests for scraper/company_extractor.py

Run with:  pytest tests/test_company_extractor.py -v
"""

from scraper.company_extractor import (
    clean_company_name,
    extract_companies_from_text,
    normalize_for_deduplication,
)


def test_clean_company_name_strips_whitespace():
    assert clean_company_name("  Caterpillar  ") == "Caterpillar"


def test_clean_company_name_removes_numbering():
    assert clean_company_name("1. Honeywell") == "Honeywell"
    assert clean_company_name("2) Emerson") == "Emerson"


def test_clean_company_name_removes_bullets():
    assert clean_company_name("- Rockwell Automation") == "Rockwell Automation"
    assert clean_company_name("• GE Vernova") == "GE Vernova"


def test_clean_company_name_collapses_spaces():
    assert clean_company_name("GE    Vernova") == "GE Vernova"


def test_normalize_for_deduplication_ignores_case_and_punctuation():
    assert normalize_for_deduplication("GE Vernova") == "ge vernova"
    assert normalize_for_deduplication("GE Vernova.") == "ge vernova"


def test_extract_companies_from_text_basic_list():
    raw_text = """
    Honeywell
    Caterpillar
    Emerson
    """
    result = extract_companies_from_text(raw_text)
    assert result == ["Honeywell", "Caterpillar", "Emerson"]


def test_extract_companies_from_text_removes_duplicates():
    raw_text = """
    Honeywell
    honeywell
    HONEYWELL.
    Caterpillar
    """
    result = extract_companies_from_text(raw_text)
    # Only the first-seen spelling is kept.
    assert result == ["Honeywell", "Caterpillar"]


def test_extract_companies_from_text_skips_blank_lines():
    raw_text = "Honeywell\n\n\nCaterpillar\n"
    result = extract_companies_from_text(raw_text)
    assert result == ["Honeywell", "Caterpillar"]


def test_extract_companies_from_text_handles_numbered_list():
    raw_text = "1. Honeywell\n2. Caterpillar\n3. Emerson"
    result = extract_companies_from_text(raw_text)
    assert result == ["Honeywell", "Caterpillar", "Emerson"]


def test_extract_companies_from_text_empty_input():
    assert extract_companies_from_text("") == []
