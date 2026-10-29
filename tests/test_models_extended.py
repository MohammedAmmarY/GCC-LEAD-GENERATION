"""
Tests for the Stage 4-6 additions to database/models.py: research
analysis updates, contacts, outreach, and CSV export rows.

Run with:  pytest tests/test_models_extended.py -v
"""

from database.database import initialize_database
from database.models import (
    get_contact_for_company,
    get_export_rows,
    get_outreach_for_company,
    get_research_for_company,
    insert_company,
    insert_contact,
    insert_outreach,
    insert_research,
    update_outreach,
    update_research_analysis,
)


def test_update_research_analysis_saves_all_fields(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)
    research_id = insert_research(company_id, ["https://honeywell.com"], "some text", "success", db_path)

    update_research_analysis(
        research_id,
        india_presence_status="no_evidence_found",
        india_gcc_evidence="No mention of India found.",
        research_summary="Makes industrial automation equipment.",
        qualification_notes="[Heuristic] Possible fit.",
        research_status="analyzed",
        db_path=db_path,
    )

    research = get_research_for_company(company_id, db_path)
    assert research["india_presence_status"] == "no_evidence_found"
    assert research["research_status"] == "analyzed"
    assert research["qualification_notes"] == "[Heuristic] Possible fit."


def test_insert_and_get_contact(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)
    insert_contact(company_id, "Jane Doe", "VP Engineering", None, None, "company website text", "found", db_path)

    contact = get_contact_for_company(company_id, db_path)
    assert contact["name"] == "Jane Doe"
    assert contact["title"] == "VP Engineering"
    assert contact["status"] == "found"


def test_get_contact_for_company_returns_none_when_missing(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)

    assert get_contact_for_company(company_id, db_path) is None


def test_insert_and_get_outreach(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)
    insert_outreach(company_id, "Subject line", "Email body text", db_path=db_path)

    outreach = get_outreach_for_company(company_id, db_path)
    assert outreach["subject"] == "Subject line"
    assert outreach["review_status"] == "pending_review"  # default status


def test_update_outreach_changes_review_status_and_content(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)
    outreach_id = insert_outreach(company_id, "Original subject", "Original body", db_path=db_path)

    update_outreach(outreach_id, "Edited subject", "Edited body", "approved", db_path)

    outreach = get_outreach_for_company(company_id, db_path)
    assert outreach["subject"] == "Edited subject"
    assert outreach["email_body"] == "Edited body"
    assert outreach["review_status"] == "approved"


def test_get_export_rows_combines_all_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    company_id = insert_company("Honeywell", "honeywell", db_path)
    research_id = insert_research(company_id, ["https://honeywell.com"], "text", "success", db_path)
    update_research_analysis(
        research_id,
        "no_evidence_found",
        "No mention of India found.",
        "Makes industrial equipment.",
        "[Heuristic] Possible fit.",
        "analyzed",
        db_path,
    )
    insert_contact(company_id, "Jane Doe", "VP Engineering", None, None, "company website text", "found", db_path)
    insert_outreach(company_id, "Subject", "Body", db_path=db_path)

    rows = get_export_rows(db_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["company_name"] == "Honeywell"
    assert row["india_presence_status"] == "no_evidence_found"
    assert row["contact_name"] == "Jane Doe"
    assert row["email_subject"] == "Subject"


def test_get_export_rows_handles_company_with_no_research_yet(tmp_path):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    insert_company("Brand New Co", "brand new co", db_path)

    rows = get_export_rows(db_path)

    assert len(rows) == 1
    assert rows[0]["company_name"] == "Brand New Co"
    assert rows[0]["india_presence_status"] is None
    assert rows[0]["contact_name"] is None
