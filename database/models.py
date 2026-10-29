"""
Plain functions for reading and writing rows in the database.

Why this file exists:
We are deliberately NOT using an ORM (a library like SQLAlchemy that maps
Python classes to database tables automatically). An ORM hides the actual
SQL being run, which makes it harder to learn what's happening under the
hood. Instead, every function here contains a plain SQL string you can
read top to bottom.

Each function opens a connection, does one thing, and closes the
connection. That keeps things simple, at the small cost of not reusing
connections across calls - fine for our scale (10-50 companies/day).
"""

import json
import sqlite3

from database.database import get_connection


def insert_company(
    name: str,
    normalized_name: str,
    db_path: str | None = None,
) -> int | None:
    """
    Insert one company. Returns the new row's id, or None if a company
    with this normalized_name already exists (we treat normalized_name
    as the de-duplication key - see company_extractor.py for how it's
    built).
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO companies (name, normalized_name)
            VALUES (?, ?)
            """,
            (name, normalized_name),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # This fires when normalized_name already exists, because the
        # schema marks that column UNIQUE. We treat "already there" as
        # a normal, expected outcome, not an error - just skip it.
        return None
    finally:
        conn.close()


def get_all_companies(db_path: str | None = None) -> list[sqlite3.Row]:
    """
    Return every company row, most recently added first.
    Each row can be read like a dict, e.g. row["name"].
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM companies ORDER BY id DESC"
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_company_by_normalized_name(
    normalized_name: str,
    db_path: str | None = None,
) -> sqlite3.Row | None:
    """Look up a single company by its normalized name. Returns None if not found."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM companies WHERE normalized_name = ?",
            (normalized_name,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def update_company_website(
    company_id: int,
    official_website: str | None,
    website_status: str,
    db_path: str | None = None,
) -> None:
    """
    Save the result of website discovery (Stage 2) back onto a company
    row: the URL we found (or None) and a status string such as "found",
    "not_found", or "error: ...".
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE companies
            SET official_website = ?, website_status = ?
            WHERE id = ?
            """,
            (official_website, website_status, company_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_company_email(
    company_id: int,
    company_email: str | None,
    company_email_source: str | None = None,
    db_path: str | None = None,
) -> None:
    """
    Save the company's general contact email found on its website, and
    the URL of the page it was found on.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE companies SET company_email = ?, company_email_source = ? WHERE id = ?",
            (company_email, company_email_source, company_id),
        )
        conn.commit()
    finally:
        conn.close()

        
def insert_research(
    company_id: int,
    pages_researched: list[str],
    website_text: str,
    research_status: str,
    db_path: str | None = None,
    india_evidence: list[dict] | None = None,
) -> int:
    """
    Save the result of website crawling as a new research row.

    pages_researched and india_evidence are Python lists, and SQLite has
    no list column type, so both are stored as JSON text. india_evidence
    stays NULL (not "[]") when no pages were scanned, so the dashboard can
    tell "scan found nothing" apart from "scan never ran".
    """
    evidence_json = json.dumps(india_evidence) if india_evidence is not None else None
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO research
                (company_id, pages_researched, website_text, research_status, india_evidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (company_id, json.dumps(pages_researched), website_text, research_status, evidence_json),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_research_for_company(
    company_id: int,
    db_path: str | None = None,
) -> sqlite3.Row | None:
    """
    Return the most recent research row for a company, or None if it
    hasn't been researched yet. A company could in theory be researched
    more than once over time, so we order by id and take the latest.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM research WHERE company_id = ? ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def update_research_analysis(
    research_id: int,
    india_presence_status: str | None,
    india_gcc_evidence: str | None,
    research_summary: str | None,
    qualification_notes: str | None,
    research_status: str,
    db_path: str | None = None,
    company_profile: dict | None = None,
) -> None:
    """
    Save the result of the LLM's analysis onto an existing research row.
    company_profile is a small dictionary (industry, size, sites and the
    page each came from); it is stored as JSON text.
    """
    profile_json = json.dumps(company_profile) if company_profile is not None else None
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE research
            SET india_presence_status = ?,
                india_gcc_evidence = ?,
                research_summary = ?,
                qualification_notes = ?,
                research_status = ?,
                company_profile = ?
            WHERE id = ?
            """,
            (
                india_presence_status,
                india_gcc_evidence,
                research_summary,
                qualification_notes,
                research_status,
                profile_json,
                research_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_contact(
    company_id: int,
    name: str | None,
    title: str | None,
    email: str | None,
    linkedin_url: str | None,
    source: str | None,
    status: str,
    db_path: str | None = None,
) -> int:
    """Save the result of contact discovery (Stage 5) as a new contact row."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO contacts (company_id, name, title, email, linkedin_url, source, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (company_id, name, title, email, linkedin_url, source, status),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_contact_for_company(
    company_id: int,
    db_path: str | None = None,
) -> sqlite3.Row | None:
    """Return the most recent contact row for a company, or None if none exists."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM contacts WHERE company_id = ? ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def insert_outreach(
    company_id: int,
    subject: str,
    email_body: str,
    review_status: str = "pending_review",
    db_path: str | None = None,
) -> int:
    """
    Save a freshly-generated email draft (Stage 6). Always starts with
    review_status "pending_review" - a human must approve it in the
    dashboard before it is ever considered "ready to send" (this project
    never sends emails automatically, at any stage).
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO outreach (company_id, subject, email_body, review_status)
            VALUES (?, ?, ?, ?)
            """,
            (company_id, subject, email_body, review_status),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_outreach_for_company(
    company_id: int,
    db_path: str | None = None,
) -> sqlite3.Row | None:
    """Return the most recent email draft for a company, or None if none exists."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM outreach WHERE company_id = ? ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def update_outreach(
    outreach_id: int,
    subject: str,
    email_body: str,
    review_status: str,
    db_path: str | None = None,
) -> None:
    """
    Save a human's edits to an email draft and/or their review decision
    (e.g. "approved", "rejected"). Used by the Streamlit dashboard's
    review section - this is the ONLY function that changes review
    status, and it never sends anything anywhere.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE outreach
            SET subject = ?, email_body = ?, review_status = ?
            WHERE id = ?
            """,
            (subject, email_body, review_status, outreach_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_export_rows(db_path: str | None = None) -> list[dict]:
    """
    Return one flat dictionary per company, combining the company's
    latest website discovery, research, contact, and outreach results.
    Used to build the CSV export in the Streamlit dashboard.

    The subqueries like "(SELECT id FROM research WHERE company_id = c.id
    ORDER BY id DESC LIMIT 1)" pick out just the latest row per table for
    each company, since a company could in theory have more than one
    research/contact/outreach row over time.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                c.id AS company_id,
                c.name AS company_name,
                c.official_website,
                c.company_email,
                c.company_email_source,
                c.website_status,
                r.india_presence_status,
                r.india_gcc_evidence,
                r.research_summary,
                r.qualification_notes,
                r.research_status,
                r.company_profile AS company_profile_json,
                ct.name AS contact_name,
                ct.title AS contact_title,
                ct.email AS contact_email,
                ct.status AS contact_status,
                o.subject AS email_subject,
                o.email_body,
                o.review_status AS email_review_status
            FROM companies c
            LEFT JOIN research r ON r.id = (
                SELECT id FROM research WHERE company_id = c.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN contacts ct ON ct.id = (
                SELECT id FROM contacts WHERE company_id = c.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN outreach o ON o.id = (
                SELECT id FROM outreach WHERE company_id = c.id ORDER BY id DESC LIMIT 1
            )
            ORDER BY c.id DESC
            """
        )
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    # The company profile is stored as JSON text; spread it into plain
    # columns so the CSV is easy to read.
    for row in rows:
        profile = json.loads(row.pop("company_profile_json") or "{}")
        row["industry"] = profile.get("industry")
        row["size_stated"] = profile.get("size")
        row["sites_stated"] = profile.get("sites")
    return rows


def set_stage_status(
    company_id: int,
    stage: str,
    status: str,
    message: str | None = None,
    seconds: float | None = None,
    db_path: str | None = None,
) -> None:
    """
    Record how one pipeline stage ("website", "crawl", "analysis",
    "contact", "email") finished for a company: status is "ok" or
    "failed", message holds the error text if it failed, and seconds is
    how long it took. INSERT OR REPLACE keeps one row per company and
    stage, so a re-run simply overwrites the old result.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO stage_status
                (company_id, stage, status, message, seconds, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (company_id, stage, status, message, seconds),
        )
        conn.commit()
    finally:
        conn.close()


def get_stage_statuses(company_id: int, db_path: str | None = None) -> dict[str, sqlite3.Row]:
    """Return {stage name: row} for every stage recorded for a company."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM stage_status WHERE company_id = ?", (company_id,))
        return {row["stage"]: row for row in cursor.fetchall()}
    finally:
        conn.close()


def get_company_overview(db_path: str | None = None) -> list[dict]:
    """
    One row per company for the dashboard's main table and its filters:
    website status, the latest research and India status, the latest
    email draft's review status, and which pipeline steps failed.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                c.id,
                c.name,
                c.official_website,
                c.website_status,
                r.research_status,
                r.india_presence_status,
                o.review_status AS email_review_status,
                (SELECT COUNT(*) FROM stage_status s
                  WHERE s.company_id = c.id AND s.status = 'failed') AS failed_steps,
                (SELECT group_concat(s.stage, ', ') FROM stage_status s
                  WHERE s.company_id = c.id AND s.status = 'failed') AS failed_step_names
            FROM companies c
            LEFT JOIN research r ON r.id = (
                SELECT id FROM research WHERE company_id = c.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN outreach o ON o.id = (
                SELECT id FROM outreach WHERE company_id = c.id ORDER BY id DESC LIMIT 1
            )
            ORDER BY c.id DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()