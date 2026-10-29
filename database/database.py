"""
Owns the SQLite connection and table schema.

Why SQLite:
SQLite stores an entire database as a single file on disk (no separate
server process to install or run, unlike PostgreSQL/MySQL). That makes it
a good fit for a project running locally on one machine. Python has
built-in support for it via the standard "sqlite3" module - no extra
package needed.

This module's only job is: "give me a connection" and "make sure the
tables exist." All the actual SQL for reading/writing rows lives in
models.py, so this file stays small and focused.
"""

import sqlite3

from config import settings

# This SQL creates every table the project needs, only if they don't
# already exist. Running this multiple times is safe - "IF NOT EXISTS"
# means it won't wipe out existing data.
#
# We only create the "companies" table in Stage 1. The other tables
# (research, contacts, outreach) are included now so the schema is in
# one place, but the pipeline code that fills them comes in later stages.
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    official_website TEXT,
    company_email TEXT,
    company_email_source TEXT,
    website_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    pages_researched TEXT,
    website_text TEXT,
    india_presence_status TEXT,
    india_gcc_evidence TEXT,
    research_summary TEXT,
    qualification_notes TEXT,
    india_evidence TEXT,
    company_profile TEXT,
    research_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    name TEXT,
    title TEXT,
    email TEXT,
    linkedin_url TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'not_found',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    subject TEXT,
    email_body TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stage_status (
    company_id INTEGER NOT NULL REFERENCES companies(id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    seconds REAL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (company_id, stage)
);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """
    Open (and if needed, create) the SQLite database file, and return a
    connection to it.

    db_path lets tests point at a temporary throwaway database file
    instead of the real one, so tests never touch your real data.
    """
    settings.ensure_data_dir_exists()
    path = db_path or str(settings.DATABASE_PATH)

    conn = sqlite3.connect(path)

    # By default, sqlite3 returns each row as a plain tuple, e.g.
    # (1, "Honeywell", "honeywell"). With row_factory set like this,
    # rows behave like dictionaries too, e.g. row["name"], which is much
    # easier to read than row[1].
    conn.row_factory = sqlite3.Row

    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str) -> None:
    """Add a TEXT column to an existing table if an older database lacks it."""
    existing_columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing_columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")


def initialize_database(db_path: str | None = None) -> None:
    """
    Create every table defined in SCHEMA if it doesn't already exist,
    and add columns introduced after the first version.
    Safe to call every time the app starts.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)

        # Databases created before these columns existed need them added;
        # new databases already have them from SCHEMA.
        _add_column_if_missing(conn, "companies", "company_email")
        _add_column_if_missing(conn, "companies", "company_email_source")
        _add_column_if_missing(conn, "research", "india_evidence")
        _add_column_if_missing(conn, "research", "company_profile")

        conn.commit()
    finally:
        conn.close()
