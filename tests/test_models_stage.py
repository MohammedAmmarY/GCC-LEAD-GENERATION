import sqlite3

from database.database import initialize_database
from database.models import (
    get_research_for_company,
    get_stage_statuses,
    insert_company,
    insert_research,
    set_stage_status,
)


def test_set_and_get_stage_status_overwrites_on_rerun(tmp_path):
    db = str(tmp_path / "t.db")
    initialize_database(db)
    company_id = insert_company("Honeywell", "honeywell", db)

    set_stage_status(company_id, "analysis", "failed", "503 busy", 4.2, db)
    set_stage_status(company_id, "crawl", "ok", None, 1.5, db)
    set_stage_status(company_id, "analysis", "ok", None, 3.1, db)

    statuses = get_stage_statuses(company_id, db)
    assert set(statuses) == {"analysis", "crawl"}
    assert statuses["analysis"]["status"] == "ok"
    assert statuses["analysis"]["message"] is None
    assert statuses["crawl"]["seconds"] == 1.5


def test_insert_research_keeps_old_positional_db_path_and_stores_evidence(tmp_path):
    db = str(tmp_path / "t.db")
    initialize_database(db)
    company_id = insert_company("Honeywell", "honeywell", db)

    # Old call style (db_path as the 5th positional argument) still works.
    insert_research(company_id, ["https://honeywell.com"], "text", "success", db)
    assert get_research_for_company(company_id, db)["india_evidence"] is None

    evidence = [{"page": "https://honeywell.com", "text": "Office in Pune", "locations": ["Pune"], "center_terms": []}]
    insert_research(company_id, ["https://honeywell.com"], "text", "success", db_path=db, india_evidence=evidence)
    assert '"Pune"' in get_research_for_company(company_id, db)["india_evidence"]

    insert_research(company_id, [], "", "failed: timeout", db_path=db, india_evidence=[])
    assert get_research_for_company(company_id, db)["india_evidence"] == "[]"


def test_initialize_database_migrates_an_old_database(tmp_path):
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE, official_website TEXT,
            website_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE research (id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
            pages_researched TEXT, website_text TEXT, india_presence_status TEXT, india_gcc_evidence TEXT,
            research_summary TEXT, qualification_notes TEXT,
            research_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT (datetime('now')));
        """
    )
    conn.commit()
    conn.close()

    initialize_database(db)
    initialize_database(db)  # safe to run twice

    conn = sqlite3.connect(db)
    company_columns = [row[1] for row in conn.execute("PRAGMA table_info(companies)")]
    research_columns = [row[1] for row in conn.execute("PRAGMA table_info(research)")]
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    conn.close()

    assert "company_email" in company_columns and "company_email_source" in company_columns
    assert "india_evidence" in research_columns
    assert "stage_status" in tables