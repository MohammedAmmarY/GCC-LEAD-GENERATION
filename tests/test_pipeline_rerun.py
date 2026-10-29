import json

import pytest

from database.database import initialize_database
from database.models import (
    get_all_companies,
    get_outreach_for_company,
    get_research_for_company,
    get_stage_statuses,
)
from pipeline import lead_pipeline

PAGE_TEXT = "Example Corp builds equipment. Our engineering center in Pune supports global teams."


class Calls:
    """Counts how many times each stage's function was called."""

    def __init__(self):
        self.counts = {"discover": 0, "crawl": 0, "analyze": 0, "contact": 0, "email": 0}


def _patch_stages(monkeypatch, calls, analysis_fails_times=0):
    state = {"analysis_failures_left": analysis_fails_times}

    def fake_discover(name):
        calls.counts["discover"] += 1
        return {"official_website": "https://acmecorp.com", "website_status": "found"}

    def fake_crawl(url):
        calls.counts["crawl"] += 1
        return {
            "pages_researched": ["https://acmecorp.com"],
            "pages": [{"url": "https://acmecorp.com", "text": PAGE_TEXT}],
            "text_length": len(PAGE_TEXT),
            "combined_text": PAGE_TEXT,
            "crawl_status": "success",
            "emails_found": ["info@acmecorp.com"],
            "email_sources": {"info@acmecorp.com": "https://acmecorp.com"},
        }

    def fake_analyze(name, text):
        calls.counts["analyze"] += 1
        calls.last_llm_input = text
        if state["analysis_failures_left"] > 0:
            state["analysis_failures_left"] -= 1
            raise RuntimeError("503 UNAVAILABLE: model is busy")
        return {
            "india_presence_status": "clear_india_gcc_evidence",
            "india_gcc_evidence": "Engineering center in Pune (https://acmecorp.com).",
            "research_summary": "Example Corp builds equipment.",
            "qualification_notes": "[Heuristic] Already present in India.",
        }

    def fake_contact(name, text):
        calls.counts["contact"] += 1
        return {"status": "not_found", "name": None, "title": None, "email": None, "linkedin_url": None, "source": None}

    def fake_email(**kwargs):
        calls.counts["email"] += 1
        return {"subject": "Subject", "body": "Hello, ... [Your Name]"}

    monkeypatch.setattr(lead_pipeline, "find_official_website", fake_discover)
    monkeypatch.setattr(lead_pipeline, "crawl_company_website", fake_crawl)
    monkeypatch.setattr(lead_pipeline, "analyze_company_website", fake_analyze)
    monkeypatch.setattr(lead_pipeline, "find_contact", fake_contact)
    monkeypatch.setattr(lead_pipeline, "generate_outreach_email", fake_email)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.db")
    initialize_database(path)
    return path


def test_first_run_saves_evidence_stage_statuses_timing_and_email(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)

    result = lead_pipeline.process_one_company("Example Corp", db)

    company = get_all_companies(db)[0]
    research = get_research_for_company(company["id"], db)
    evidence = json.loads(research["india_evidence"])
    assert evidence[0]["locations"] == ["Pune"]
    assert evidence[0]["page"] == "https://acmecorp.com"

    # The keyword-scan block is sent to the LLM ahead of the page text.
    assert calls.last_llm_input.startswith("KEYWORD SCAN")
    assert "[1] (https://acmecorp.com)" in calls.last_llm_input
    assert PAGE_TEXT in calls.last_llm_input

    statuses = get_stage_statuses(company["id"], db)
    assert {s: statuses[s]["status"] for s in statuses} == {
        "website": "ok", "crawl": "ok", "analysis": "ok", "contact": "ok", "email": "ok",
    }
    assert statuses["crawl"]["seconds"] is not None
    assert result["seconds"] >= 0
    assert company["company_email"] == "info@acmecorp.com"
    assert company["company_email_source"] == "https://acmecorp.com"


def test_second_run_skips_everything_already_done(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    lead_pipeline.process_one_company("Example Corp", db)

    second = lead_pipeline.process_one_company("Example Corp", db)

    assert calls.counts == {"discover": 1, "crawl": 1, "analyze": 1, "contact": 1, "email": 1}
    assert second["stages"]["website_discovery"] == "skipped (found)"
    assert second["stages"]["crawl"] == "skipped (already done)"
    assert second["stages"]["analysis"] == "skipped (already done)"
    assert second["stages"]["contact"] == "skipped (already done)"
    assert second["stages"]["email"] == "skipped (already done)"
    company_id = get_all_companies(db)[0]["id"]
    assert get_outreach_for_company(company_id, db) is not None


def test_force_reruns_every_stage(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    lead_pipeline.process_one_company("Example Corp", db)

    lead_pipeline.process_one_company("Example Corp", db, force=True)

    assert calls.counts == {"discover": 2, "crawl": 2, "analyze": 2, "contact": 2, "email": 2}


def test_retry_after_llm_failure_redoes_only_the_failed_stage_onward(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls, analysis_fails_times=1)

    first = lead_pipeline.process_one_company("Example Corp", db)
    assert first["stages"]["analysis"].startswith("failed:")
    company_id = get_all_companies(db)[0]["id"]
    statuses = get_stage_statuses(company_id, db)
    assert statuses["analysis"]["status"] == "failed"
    assert "503" in statuses["analysis"]["message"]
    assert "contact" not in statuses

    second = lead_pipeline.process_one_company("Example Corp", db)

    # No second search and no second crawl - only the AI steps ran.
    assert calls.counts["discover"] == 1
    assert calls.counts["crawl"] == 1
    assert calls.counts["analyze"] == 2
    assert second["stages"]["crawl"] == "skipped (already done)"
    assert second["stages"]["analysis"] == "success"
    assert second["stages"]["email"] == "drafted"
    # The retry reused the saved evidence and text for the LLM input.
    assert calls.last_llm_input.startswith("KEYWORD SCAN")
    assert get_research_for_company(company_id, db)["research_status"] == "analyzed"


def test_contact_failure_is_stored_and_retried_alone(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    state = {"fail": True}

    def flaky_contact(name, text):
        calls.counts["contact"] += 1
        if state["fail"]:
            raise RuntimeError("503 busy")
        return {"status": "found", "name": "Jane Doe", "title": "VP Engineering", "email": None, "linkedin_url": None, "source": "x"}

    monkeypatch.setattr(lead_pipeline, "find_contact", flaky_contact)

    lead_pipeline.process_one_company("Example Corp", db)
    company_id = get_all_companies(db)[0]["id"]
    assert get_stage_statuses(company_id, db)["contact"]["status"] == "failed"

    state["fail"] = False
    second = lead_pipeline.process_one_company("Example Corp", db)

    assert second["stages"]["contact"] == "found"
    assert second["stages"]["analysis"] == "skipped (already done)"
    assert second["stages"]["email"] == "skipped (already done)"
    assert calls.counts["analyze"] == 1 and calls.counts["email"] == 1


def test_website_override_skips_search_and_redoes_everything(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    lead_pipeline.process_one_company("Example Corp", db)

    crawled_urls = []
    original_crawl = lead_pipeline.crawl_company_website

    def recording_crawl(url):
        crawled_urls.append(url)
        return original_crawl(url)

    monkeypatch.setattr(lead_pipeline, "crawl_company_website", recording_crawl)

    result = lead_pipeline.process_one_company("Example Corp", db, website_override="right-site.com/")

    assert calls.counts["discover"] == 1  # the search was not run again
    assert crawled_urls == ["https://right-site.com"]
    assert result["stages"]["website_discovery"] == "manual"
    company = get_all_companies(db)[0]
    assert company["official_website"] == "https://right-site.com"
    assert company["website_status"] == "manual"
    assert calls.counts["analyze"] == 2 and calls.counts["email"] == 2


def test_thin_content_is_flagged_and_skips_the_ai(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "MIN_CONTENT_CHARS", 500)

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["crawl"] == "thin_content"
    assert "analysis" not in result["stages"]
    assert calls.counts["analyze"] == 0
    company_id = get_all_companies(db)[0]["id"]
    assert get_research_for_company(company_id, db)["research_status"] == "thin_content"
    crawl_status = get_stage_statuses(company_id, db)["crawl"]
    assert crawl_status["status"] == "failed"
    assert "JavaScript" in crawl_status["message"]
    # The company email found on the thin page is still saved.
    assert get_all_companies(db)[0]["company_email"] == "info@acmecorp.com"


def test_failed_crawl_stores_no_evidence_so_dashboard_can_tell(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(
        lead_pipeline, "crawl_company_website",
        lambda url: {"pages_researched": [], "pages": [], "text_length": 0, "combined_text": "",
                     "crawl_status": "failed: http_error_403", "emails_found": [], "email_sources": {}},
    )

    result = lead_pipeline.process_one_company("Example Corp", db)

    company_id = get_all_companies(db)[0]["id"]
    assert result["stages"]["crawl"] == "failed: http_error_403"
    assert get_research_for_company(company_id, db)["india_evidence"] is None
    assert get_stage_statuses(company_id, db)["crawl"]["message"] == "failed: http_error_403"


def test_regenerate_email_adds_a_new_draft(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    lead_pipeline.process_one_company("Example Corp", db)
    company_id = get_all_companies(db)[0]["id"]

    seen = {}

    def fake_email(**kwargs):
        seen.update(kwargs)
        return {"subject": "New subject", "body": "New body"}

    monkeypatch.setattr(lead_pipeline, "generate_outreach_email", fake_email)

    draft = lead_pipeline.regenerate_email(company_id, "Example Corp", db)

    assert draft["subject"] == "New subject"
    assert get_outreach_for_company(company_id, db)["subject"] == "New subject"
    assert seen["research_summary"] == "Example Corp builds equipment."
    assert seen["contact_name"] is None


def test_regenerate_email_needs_finished_research(db):
    company_id = lead_pipeline.insert_company("Empty Co", "empty co", db)
    with pytest.raises(ValueError):
        lead_pipeline.regenerate_email(company_id, "Empty Co", db)


def test_summarize_batch_counts_each_outcome():
    results = [
        {"stages": {"website_discovery": "found", "crawl": "success", "analysis": "success",
                    "contact": "found", "email": "drafted"}, "seconds": 10.0},
        {"stages": {"website_discovery": "found_unverified", "crawl": "thin_content"}, "seconds": 2.5},
        {"stages": {"website_discovery": "not_found"}, "seconds": 1.0},
        {"stages": {"website_discovery": "found", "crawl": "failed: http_error_403"}, "seconds": 3.0},
        {"stages": {"website_discovery": "found", "crawl": "success", "analysis": "failed: 503"}, "seconds": 4.0},
        {"stages": {}, "error": "boom", "seconds": 0.5},
    ]

    summary = lead_pipeline.summarize_batch(results)

    assert summary == {
        "companies": 6,
        "website_found": 3,
        "website_unverified": 1,
        "website_missing": 1,
        "crawl_ok": 2,
        "crawl_thin": 1,
        "crawl_failed": 1,
        "analysis_ok": 1,
        "analysis_failed": 1,
        "contacts_found": 1,
        "emails_drafted": 1,
        "unexpected_errors": 1,
        "seconds": 21.0,
    }


def test_log_batch_summary_returns_counts(caplog):
    with caplog.at_level("INFO"):
        summary = lead_pipeline.log_batch_summary([{"stages": {"website_discovery": "found"}, "seconds": 1.0}])
    assert summary["companies"] == 1
    assert any("Batch finished: 1 companies" in record.message for record in caplog.records)


# --- Tavily Extract fallback -----------------------------------------------------

LONG_TEXT = "Acme builds industrial equipment. Our engineering center in Pune supports global teams. " * 10


def _extract_crawl(text=LONG_TEXT):
    return {
        "pages_researched": ["https://acmecorp.com", "https://acmecorp.com/locations"],
        "pages": [
            {"url": "https://acmecorp.com", "text": text},
            {"url": "https://acmecorp.com/locations", "text": "Our office is in Pune."},
        ],
        "text_length": len(text) + len("Our office is in Pune."),
        "combined_text": text,
        "crawl_status": "success",
        "emails_found": ["info@acmecorp.com"],
        "email_sources": {"info@acmecorp.com": "https://acmecorp.com"},
    }


BLOCKED_CRAWL = {
    "pages_researched": [], "pages": [], "text_length": 0, "combined_text": "",
    "crawl_status": "failed: http_error_403", "emails_found": [], "email_sources": {},
}


def test_extract_fallback_rescues_a_blocked_site(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)
    monkeypatch.setattr(lead_pipeline, "crawl_company_website", lambda url: BLOCKED_CRAWL)
    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", lambda url: _extract_crawl())

    result = lead_pipeline.process_one_company("Example Corp", db)

    company_id = get_all_companies(db)[0]["id"]
    assert result["stages"]["extract_fallback"] == "used"
    assert result["stages"]["crawl"] == "success"
    assert result["stages"]["analysis"] == "success"
    assert calls.counts["analyze"] == 1
    status = get_stage_statuses(company_id, db)["crawl"]
    assert status["status"] == "ok"
    assert "Tavily Extract" in status["message"]
    # The keyword scan ran on the extracted pages.
    evidence = json.loads(get_research_for_company(company_id, db)["india_evidence"])
    assert evidence[0]["locations"] == ["Pune"]
    assert get_all_companies(db)[0]["company_email"] == "info@acmecorp.com"


def test_extract_fallback_rescues_a_thin_site(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)
    monkeypatch.setattr(lead_pipeline.settings, "MIN_CONTENT_CHARS", 500)
    # _patch_stages' normal crawl returns only a short page, so it is "thin".
    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", lambda url: _extract_crawl())

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["extract_fallback"] == "used"
    assert result["stages"]["crawl"] == "success"
    assert calls.counts["analyze"] == 1


def test_extract_fallback_is_off_by_default(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline, "crawl_company_website", lambda url: BLOCKED_CRAWL)

    def must_not_be_called(url):
        raise AssertionError("Tavily Extract should not run when the setting is off")

    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", must_not_be_called)

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["crawl"] == "failed: http_error_403"
    assert "extract_fallback" not in result["stages"]


def test_extract_fallback_not_used_when_the_normal_crawl_is_fine(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)

    def must_not_be_called(url):
        raise AssertionError("normal crawl was fine")

    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", must_not_be_called)

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["crawl"] == "success"
    assert "extract_fallback" not in result["stages"]


def test_extract_fallback_that_finds_nothing_keeps_the_original_result(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)
    monkeypatch.setattr(lead_pipeline, "crawl_company_website", lambda url: BLOCKED_CRAWL)
    monkeypatch.setattr(
        lead_pipeline, "crawl_with_extract",
        lambda url: {**BLOCKED_CRAWL, "crawl_status": "failed: extract_error: no credits left"},
    )

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["extract_fallback"] == "no better content"
    assert result["stages"]["crawl"] == "failed: http_error_403"
    assert calls.counts["analyze"] == 0


def test_thin_site_stays_flagged_if_extract_does_not_help_either(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)
    monkeypatch.setattr(lead_pipeline.settings, "MIN_CONTENT_CHARS", 500)
    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", lambda url: {**BLOCKED_CRAWL, "crawl_status": "failed: extract_no_content"})

    result = lead_pipeline.process_one_company("Example Corp", db)

    company_id = get_all_companies(db)[0]["id"]
    assert result["stages"]["crawl"] == "thin_content"
    assert "Tavily Extract was tried too" in get_stage_statuses(company_id, db)["crawl"]["message"]


# --- Company profile -------------------------------------------------------------

from database.models import get_export_rows  # noqa: E402  (used by the test below)


def test_profile_is_saved_by_the_pipeline_and_flattened_in_the_export(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    initialize_database(db)
    calls = Calls()
    _patch_stages(monkeypatch, calls)

    profile = {"industry": "Pumps", "industry_source": "https://acmecorp.com/about", "size": "900 employees",
               "size_source": None, "sites": "12 countries", "sites_source": "https://acmecorp.com"}
    original = lead_pipeline.analyze_company_website

    def analyze_with_profile(name, text):
        return {**original(name, text), "company_profile": profile}

    monkeypatch.setattr(lead_pipeline, "analyze_company_website", analyze_with_profile)

    lead_pipeline.process_one_company("Example Corp", db)

    company_id = get_all_companies(db)[0]["id"]
    saved = json.loads(get_research_for_company(company_id, db)["company_profile"])
    assert saved == profile

    export = get_export_rows(db)[0]
    assert export["industry"] == "Pumps"
    assert export["size_stated"] == "900 employees"
    assert export["sites_stated"] == "12 countries"
    assert "company_profile_json" not in export


# --- robots.txt and the pipeline ----------------------------------------------------

THIN_CRAWL_WITH_ROBOTS_SKIPS = {
    "pages_researched": ["https://acmecorp.com"],
    "pages": [{"url": "https://acmecorp.com", "text": "short"}],
    "text_length": 5,
    "combined_text": "short",
    "crawl_status": "success",
    "emails_found": [],
    "email_sources": {},
    "skipped_by_robots": ["https://acmecorp.com/locations"],
}


def test_pages_skipped_by_robots_are_mentioned_in_the_crawl_message(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    crawl = {**_extract_crawl(), "skipped_by_robots": ["https://acmecorp.com/careers"]}
    monkeypatch.setattr(lead_pipeline, "crawl_company_website", lambda url: crawl)

    lead_pipeline.process_one_company("Example Corp", db)

    company_id = get_all_companies(db)[0]["id"]
    status = get_stage_statuses(company_id, db)["crawl"]
    assert status["status"] == "ok"
    assert "1 page(s) skipped because of robots.txt" in status["message"]


def test_extract_fallback_never_reads_pages_that_robots_txt_excluded(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)
    monkeypatch.setattr(lead_pipeline.settings, "MIN_CONTENT_CHARS", 500)
    monkeypatch.setattr(lead_pipeline, "crawl_company_website", lambda url: THIN_CRAWL_WITH_ROBOTS_SKIPS)

    def must_not_be_called(url):
        raise AssertionError("a third party must not fetch pages robots.txt excluded")

    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", must_not_be_called)

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["crawl"] == "thin_content"
    assert "extract_fallback" not in result["stages"]


def test_a_site_that_blocks_us_in_robots_txt_is_not_sent_to_the_extract_fallback(db, monkeypatch):
    calls = Calls()
    _patch_stages(monkeypatch, calls)
    monkeypatch.setattr(lead_pipeline.settings, "TAVILY_EXTRACT_FALLBACK", True)
    monkeypatch.setattr(
        lead_pipeline, "crawl_company_website",
        lambda url: {**BLOCKED_CRAWL, "crawl_status": "failed: robots_txt", "skipped_by_robots": []},
    )

    def must_not_be_called(url):
        raise AssertionError("robots.txt blocks are respected, not worked around")

    monkeypatch.setattr(lead_pipeline, "crawl_with_extract", must_not_be_called)

    result = lead_pipeline.process_one_company("Example Corp", db)

    assert result["stages"]["crawl"] == "failed: robots_txt"
    assert calls.counts["analyze"] == 0