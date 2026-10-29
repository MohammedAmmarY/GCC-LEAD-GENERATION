"""
Tests for pipeline/lead_pipeline.py

Run with:  pytest tests/test_lead_pipeline.py -v

Every external call (search, crawling, LLM calls) is monkeypatched, so
these tests run instantly and never touch the network or a real API
key. They check that the pipeline wires stages together correctly, and
that a failure in one stage doesn't crash the whole run.
"""

from database.database import initialize_database
from database.models import (
    get_all_companies,
    get_contact_for_company,
    get_outreach_for_company,
    get_research_for_company,
)
from pipeline import lead_pipeline


def _patch_full_success_path(monkeypatch):
    monkeypatch.setattr(
        lead_pipeline,
        "find_official_website",
        lambda name: {"official_website": "https://example.com", "website_status": "found"},
    )
    monkeypatch.setattr(
        lead_pipeline,
        "crawl_company_website",
        lambda url: {
            "pages_researched": ["https://example.com"],
            "combined_text": "We are Example Corp, an industrial manufacturer.",
            "crawl_status": "success",
        },
    )
    monkeypatch.setattr(
        lead_pipeline,
        "analyze_company_website",
        lambda name, text: {
            "india_presence_status": "no_evidence_found",
            "india_gcc_evidence": "No mention of India found in the researched pages.",
            "research_summary": "Example Corp makes industrial equipment.",
            "qualification_notes": "[Heuristic] Possible fit - engineering-intensive, no existing India GCC found.",
        },
    )
    monkeypatch.setattr(
        lead_pipeline,
        "find_contact",
        lambda name, text: {
            "status": "found",
            "name": "Jane Doe",
            "title": "VP Engineering",
            "email": None,
            "linkedin_url": None,
            "source": "company website text",
        },
    )
    monkeypatch.setattr(
        lead_pipeline,
        "generate_outreach_email",
        lambda **kwargs: {"subject": "Quick question about your engineering operations", "body": "Hello Jane, ..."},
    )


def test_process_one_company_success_path(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    _patch_full_success_path(monkeypatch)

    result = lead_pipeline.process_one_company("Example Corp", db_path)

    assert result["stages"]["company"] == "created"
    assert result["stages"]["website_discovery"] == "found"
    assert result["stages"]["crawl"] == "success"
    assert result["stages"]["analysis"] == "success"
    assert result["stages"]["contact"] == "found"
    assert result["stages"]["email"] == "drafted"

    companies = get_all_companies(db_path)
    assert len(companies) == 1
    company_id = companies[0]["id"]

    research = get_research_for_company(company_id, db_path)
    assert research["india_presence_status"] == "no_evidence_found"

    contact = get_contact_for_company(company_id, db_path)
    assert contact["name"] == "Jane Doe"

    outreach = get_outreach_for_company(company_id, db_path)
    assert outreach["review_status"] == "pending_review"
    assert "Jane" in outreach["email_body"]


def test_process_one_company_stops_after_website_not_found(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    monkeypatch.setattr(
        lead_pipeline,
        "find_official_website",
        lambda name: {"official_website": None, "website_status": "not_found"},
    )

    result = lead_pipeline.process_one_company("Obscure Company", db_path)

    assert result["stages"]["website_discovery"] == "not_found"
    assert "crawl" not in result["stages"]  # never reached


def test_process_one_company_handles_analysis_failure_gracefully(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    monkeypatch.setattr(
        lead_pipeline,
        "find_official_website",
        lambda name: {"official_website": "https://example.com", "website_status": "found"},
    )
    monkeypatch.setattr(
        lead_pipeline,
        "crawl_company_website",
        lambda url: {
            "pages_researched": ["https://example.com"],
            "combined_text": "some text",
            "crawl_status": "success",
        },
    )

    def broken_analyze(name, text):
        raise ValueError("LLM did not return valid JSON")

    monkeypatch.setattr(lead_pipeline, "analyze_company_website", broken_analyze)

    result = lead_pipeline.process_one_company("Example Corp", db_path)

    assert result["stages"]["analysis"].startswith("failed:")
    assert "contact" not in result["stages"]  # never reached - can't email without analysis


def test_process_one_company_continues_after_contact_failure(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    _patch_full_success_path(monkeypatch)

    def broken_find_contact(name, text):
        raise ValueError("LLM did not return valid JSON")

    monkeypatch.setattr(lead_pipeline, "find_contact", broken_find_contact)

    result = lead_pipeline.process_one_company("Example Corp", db_path)

    assert result["stages"]["contact"].startswith("failed:")
    # Email generation should still be attempted, just without a named contact.
    assert result["stages"]["email"] == "drafted"


def test_process_many_companies_continues_after_one_failure(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    def flaky_find_official_website(name):
        if name == "Broken Company":
            raise ConnectionError("search API is down")
        return {"official_website": "https://example.com", "website_status": "found"}

    monkeypatch.setattr(lead_pipeline, "find_official_website", flaky_find_official_website)
    monkeypatch.setattr(
        lead_pipeline,
        "crawl_company_website",
        lambda url: {"pages_researched": [], "combined_text": "", "crawl_status": "failed: timeout"},
    )

    results = lead_pipeline.process_many_companies(["Broken Company", "Good Company"], db_path)

    assert len(results) == 2
    # The broken company's unexpected error is captured, not raised.
    assert "error" in results[0]
    # Processing continued to the second company.
    assert results[1]["stages"]["website_discovery"] == "found"
