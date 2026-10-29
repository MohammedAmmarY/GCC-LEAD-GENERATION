import json

from ai import website_analyzer
from ai.website_analyzer import clean_company_profile
from database.database import initialize_database
from database.models import (
    get_company_overview,
    get_export_rows,
    get_research_for_company,
    insert_company,
    insert_outreach,
    insert_research,
    set_stage_status,
    update_research_analysis,
)


def test_clean_company_profile_keeps_text_and_nulls_the_rest():
    raw = {
        "industry": " Industrial automation ",
        "industry_source": "https://acme.com/about",
        "size": 5000,
        "size_source": "",
        "sites": None,
        "unexpected": "ignored",
    }
    assert clean_company_profile(raw) == {
        "industry": "Industrial automation",
        "industry_source": "https://acme.com/about",
        "size": "5000",
        "size_source": None,
        "sites": None,
        "sites_source": None,
    }


def test_clean_company_profile_handles_missing_or_wrong_type():
    empty = {field: None for field in website_analyzer.PROFILE_FIELDS}
    assert clean_company_profile(None) == empty
    assert clean_company_profile("a string") == empty
    assert clean_company_profile({"industry": True}) == empty


def _reply(extra):
    base = {
        "india_presence_status": "no_evidence_found",
        "india_gcc_evidence": "none",
        "research_summary": "summary",
        "qualification_notes": "[Heuristic] ok",
    }
    base.update(extra)
    return json.dumps(base)


def test_analyzer_returns_a_cleaned_profile(monkeypatch):
    reply = _reply({"company_profile": {"industry": "Pumps", "industry_source": "https://acme.com", "size": "About 900 employees"}})
    monkeypatch.setattr(website_analyzer, "call_llm", lambda system, user, max_tokens=1024: reply)

    result = website_analyzer.analyze_company_website("Acme", "text")

    assert result["company_profile"]["industry"] == "Pumps"
    assert result["company_profile"]["size"] == "About 900 employees"
    assert result["company_profile"]["sites"] is None


def test_analyzer_still_works_when_the_reply_has_no_profile(monkeypatch):
    monkeypatch.setattr(website_analyzer, "call_llm", lambda system, user, max_tokens=1024: _reply({}))

    result = website_analyzer.analyze_company_website("Acme", "text")

    assert all(value is None for value in result["company_profile"].values())


def test_prompt_asks_for_profile_facts_with_sources_and_no_guessing():
    assert "company_profile" in website_analyzer.SYSTEM_PROMPT
    assert "industry_source" in website_analyzer.SYSTEM_PROMPT
    assert "Never estimate" in website_analyzer.SYSTEM_PROMPT


def test_export_handles_companies_without_a_profile(tmp_path):
    db = str(tmp_path / "t.db")
    initialize_database(db)
    insert_company("Plain Co", "plain co", db)

    row = get_export_rows(db)[0]

    assert row["industry"] is None and row["size_stated"] is None and row["sites_stated"] is None


def test_update_research_analysis_still_accepts_the_old_positional_call(tmp_path):
    db = str(tmp_path / "t.db")
    initialize_database(db)
    company_id = insert_company("Honeywell", "honeywell", db)
    research_id = insert_research(company_id, [], "text", "success", db)

    # db_path as the 7th positional argument, exactly as older code called it
    update_research_analysis(research_id, "no_evidence_found", "none", "summary", "notes", "analyzed", db)

    research = get_research_for_company(company_id, db)
    assert research["research_status"] == "analyzed"
    assert research["company_profile"] is None


def test_company_overview_has_latest_statuses_and_failed_step_names(tmp_path):
    db = str(tmp_path / "t.db")
    initialize_database(db)
    company_id = insert_company("Acme", "acme", db)
    research_id = insert_research(company_id, [], "text", "success", db)
    update_research_analysis(research_id, "clear_india_gcc_evidence", "e", "s", "n", "analyzed", db)
    insert_outreach(company_id, "Hi", "Body", db_path=db)
    set_stage_status(company_id, "crawl", "ok", None, 1.0, db)
    set_stage_status(company_id, "contact", "failed", "503", 1.0, db)
    set_stage_status(company_id, "email", "failed", "busy", 1.0, db)
    insert_company("Bare Co", "bare co", db)

    rows = {row["name"]: row for row in get_company_overview(db)}

    acme = rows["Acme"]
    assert acme["india_presence_status"] == "clear_india_gcc_evidence"
    assert acme["email_review_status"] == "pending_review"
    assert acme["failed_steps"] == 2
    assert set(acme["failed_step_names"].split(", ")) == {"contact", "email"}

    bare = rows["Bare Co"]
    assert bare["research_status"] is None and bare["failed_steps"] == 0 and bare["failed_step_names"] is None
    assert [row["name"] for row in get_company_overview(db)] == ["Bare Co", "Acme"]  # newest first