"""
Tests for database/database.py and database/models.py

Run with:  pytest tests/test_database.py -v

These tests use a temporary database file (via pytest's tmp_path fixture)
so they never touch your real data/leads.db.
"""

from database.database import initialize_database
from database.models import (
    get_all_companies,
    get_company_by_normalized_name,
    insert_company,
)


def test_initialize_database_creates_tables(tmp_path):
    db_path = str(tmp_path / "test.db")

    # Should run without raising an error, even on a brand-new file.
    initialize_database(db_path)


def test_insert_and_retrieve_company(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)

    assert company_id is not None

    companies = get_all_companies(db_path)
    assert len(companies) == 1
    assert companies[0]["name"] == "Honeywell"
    assert companies[0]["normalized_name"] == "honeywell"
    # New companies should start with "pending" website status.
    assert companies[0]["website_status"] == "pending"


def test_insert_duplicate_normalized_name_is_skipped(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    first_id = insert_company("Honeywell", "honeywell", db_path)
    second_id = insert_company("HONEYWELL.", "honeywell", db_path)

    assert first_id is not None
    assert second_id is None  # duplicate was rejected

    companies = get_all_companies(db_path)
    assert len(companies) == 1


def test_get_company_by_normalized_name_found(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    insert_company("Caterpillar", "caterpillar", db_path)

    result = get_company_by_normalized_name("caterpillar", db_path)

    assert result is not None
    assert result["name"] == "Caterpillar"


def test_get_company_by_normalized_name_not_found(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    result = get_company_by_normalized_name("does-not-exist", db_path)

    assert result is None
