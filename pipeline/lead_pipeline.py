"""
Orchestrates the full lead-generation pipeline for one or many
companies: website discovery -> crawling -> India evidence scan -> AI
analysis -> contact discovery -> email drafting, saving results to the
database at every step.

Why this file exists:
Every individual stage already exists as its own tested module. This
file calls them in order, in plain readable code. It also remembers how
each stage finished (the stage_status table), so a re-run skips finished
work and retries only the stage that failed - for example, a Gemini
"busy" error costs one retried LLM call, not a whole re-crawl.
"""

import json
import time

from ai.email_generator import generate_outreach_email
from ai.website_analyzer import analyze_company_website
from config import settings
from contacts.contact_finder import find_company_email, find_contact
from database.models import (
    get_company_by_normalized_name,
    get_contact_for_company,
    get_outreach_for_company,
    get_research_for_company,
    get_stage_statuses,
    insert_company,
    insert_contact,
    insert_outreach,
    insert_research,
    set_stage_status,
    update_company_email,
    update_company_website,
    update_research_analysis,
)
from scraper.company_extractor import normalize_for_deduplication
from scraper.india_evidence import find_india_evidence, format_evidence_for_prompt
from scraper.website_crawler import crawl_company_website, crawl_with_extract
from scraper.website_discovery import find_official_website
from utils.logger import get_logger
from utils.url_utils import normalize_url

logger = get_logger(__name__)


def _completed_stages(company_id: int, db_path: str | None) -> set[str]:
    """Names of the stages that finished successfully on an earlier run."""
    rows = get_stage_statuses(company_id, db_path)
    return {stage for stage, row in rows.items() if row["status"] == "ok"}


def _needs_extract_fallback(crawl: dict) -> bool:
    """True if the normal crawl was blocked (HTTP 403) or returned too little text."""
    if crawl.get("skipped_by_robots"):
        # The site asked crawlers to skip some pages; don't have a third
        # party fetch them instead.
        return False
    status = crawl["crawl_status"]
    if status.startswith("failed: http_error_403"):
        return True
    text_length = crawl.get("text_length", len(crawl["combined_text"]))
    return status == "success" and text_length < settings.MIN_CONTENT_CHARS


def _record_stage(
    company_id: int,
    name: str,
    stage: str,
    status: str,
    message: str | None,
    started: float,
    db_path: str | None,
) -> None:
    """Save how a stage finished (and how long it took) and log it."""
    seconds = round(time.perf_counter() - started, 2)
    set_stage_status(company_id, stage, status, message, seconds, db_path)
    detail = f" - {message}" if message else ""
    logger.info(f"[{name}] {stage}: {status}{detail} ({seconds}s)")


def process_one_company(
    name: str,
    db_path: str | None = None,
    website_override: str | None = None,
    force: bool = False,
) -> dict:
    """
    Run every pipeline stage for one company and return a summary
    dictionary describing what happened at each step, e.g.:

        {
            "company_name": "Honeywell",
            "stages": {
                "company": "created",
                "website_discovery": "found",
                "crawl": "success",
                "analysis": "success",
                "contact": "not_found",
                "email": "drafted",
            },
            "seconds": 41.2,
        }

    Stages that finished on an earlier run are skipped (shown as
    "skipped (already done)") unless force=True. Giving website_override
    uses that URL instead of searching, and redoes everything after it.

    This function never raises - any unexpected error is caught, logged,
    and reported in the summary's "error" key, so a batch of many
    companies can keep going even if one company hits a surprise.
    """
    summary: dict = {"company_name": name, "stages": {}}
    started_at = time.perf_counter()

    try:
        # --- Stage 1: store the company ---------------------------------
        normalized_name = normalize_for_deduplication(name)
        company_id = insert_company(name, normalized_name, db_path)

        if company_id is None:
            summary["stages"]["company"] = "already_exists"
            existing = get_company_by_normalized_name(normalized_name, db_path)
            company_id = existing["id"] if existing else None
            if company_id is None:
                summary["error"] = "could not find or create a company row"
                return summary
        else:
            summary["stages"]["company"] = "created"

        logger.info(f"[{name}] processing started (company_id={company_id})")
        company_row = get_company_by_normalized_name(normalized_name, db_path)

        # A manually chosen website makes everything after it out of date.
        if website_override:
            force = True
        done = set() if force else _completed_stages(company_id, db_path)

        # --- Stage 2: website discovery ----------------------------------
        started = time.perf_counter()
        website_skipped = False

        if website_override:
            discovery = {
                "official_website": normalize_url(website_override),
                "website_status": "manual",
            }
        elif "website" in done and company_row["official_website"]:
            website_skipped = True
            discovery = {
                "official_website": company_row["official_website"],
                "website_status": company_row["website_status"],
            }
        else:
            discovery = find_official_website(name)

        if website_skipped:
            summary["stages"]["website_discovery"] = f"skipped ({discovery['website_status']})"
        else:
            update_company_website(company_id, discovery["official_website"], discovery["website_status"], db_path)
            summary["stages"]["website_discovery"] = discovery["website_status"]
            website_found = bool(discovery["official_website"])
            _record_stage(
                company_id, name, "website",
                "ok" if website_found else "failed",
                None if website_found else discovery["website_status"],
                started, db_path,
            )

        if not discovery["official_website"]:
            return summary  # nothing further to research without a website

        # --- Stage 3: crawl the website + scan for India mentions ---------
        research = get_research_for_company(company_id, db_path)
        crawl_skipped = "crawl" in done and research is not None and bool(research["website_text"])

        if crawl_skipped:
            # Reuse the text and evidence saved by the earlier crawl.
            research_id = research["id"]
            website_text = research["website_text"]
            evidence = json.loads(research["india_evidence"] or "[]")
            summary["stages"]["crawl"] = "skipped (already done)"
        else:
            started = time.perf_counter()
            crawl = crawl_company_website(discovery["official_website"])

            # Optional fallback for sites that block the crawler or build
            # their pages with JavaScript: fetch them through Tavily Extract.
            extract_note = None
            extract_tried = False
            if settings.TAVILY_EXTRACT_FALLBACK and _needs_extract_fallback(crawl):
                extract_tried = True
                original_length = crawl.get("text_length", len(crawl["combined_text"]))
                fallback = crawl_with_extract(discovery["official_website"])
                if fallback["crawl_status"] == "success" and fallback["text_length"] > original_length:
                    crawl = fallback
                    extract_note = (
                        "text fetched through Tavily Extract because the normal "
                        "crawl was blocked or returned too little"
                    )
                    summary["stages"]["extract_fallback"] = "used"
                else:
                    summary["stages"]["extract_fallback"] = "no better content"

            pages = crawl.get("pages", [])
            website_text = crawl["combined_text"]
            text_length = crawl.get("text_length", len(website_text))
            evidence = find_india_evidence(pages)

            crawl_status = crawl["crawl_status"]
            crawl_message = extract_note
            if crawl_status == "success" and text_length < settings.MIN_CONTENT_CHARS:
                # Almost no text: usually a JavaScript-built site. Flag it
                # instead of letting the AI "analyze" nothing.
                crawl_status = "thin_content"
                crawl_message = (
                    f"only {text_length} characters of text found; "
                    "the site may rely on JavaScript"
                    + (" (Tavily Extract was tried too)" if extract_tried else "")
                )
            elif crawl_status != "success":
                crawl_message = crawl_status

            robots_skipped = crawl.get("skipped_by_robots", [])
            if robots_skipped:
                crawl_message = (
                    f"{crawl_message or ''} ({len(robots_skipped)} page(s) skipped because of robots.txt)"
                ).strip()

            research_id = insert_research(
                company_id,
                crawl["pages_researched"],
                website_text,
                crawl_status,
                db_path=db_path,
                india_evidence=evidence if pages else None,
            )
            summary["stages"]["crawl"] = crawl_status

            # Company contact email (plain Python, no LLM)
            company_email = find_company_email(
                crawl.get("emails_found", []), discovery["official_website"]
            )
            email_source = crawl.get("email_sources", {}).get(company_email) if company_email else None
            if company_email:
                # Only overwrite when something was found, so a later failed
                # crawl can't erase an email saved by an earlier run.
                update_company_email(
                    company_id, company_email, company_email_source=email_source, db_path=db_path
                )
            summary["stages"]["company_email"] = "found" if company_email else "not_found"
            logger.info(
                f"[{name}] company email: {company_email or 'not found'}"
                + (f" (found on {email_source})" if email_source else "")
            )

            _record_stage(
                company_id, name, "crawl",
                "ok" if crawl_status == "success" else "failed",
                crawl_message, started, db_path,
            )
            if crawl_status != "success":
                return summary  # nothing trustworthy to analyze

        # --- Stage 4: AI analysis (India/GCC evidence + summary) -----------
        analysis_skipped = crawl_skipped and "analysis" in done

        if analysis_skipped:
            analysis = {
                "india_presence_status": research["india_presence_status"],
                "india_gcc_evidence": research["india_gcc_evidence"],
                "research_summary": research["research_summary"],
                "qualification_notes": research["qualification_notes"],
            }
            summary["stages"]["analysis"] = "skipped (already done)"
        else:
            started = time.perf_counter()
            # The keyword-scan results go first so the model can cite the
            # pages they came from.
            llm_input = format_evidence_for_prompt(evidence) + "\n\n" + website_text
            try:
                analysis = analyze_company_website(name, llm_input)
                update_research_analysis(
                    research_id,
                    india_presence_status=analysis["india_presence_status"],
                    india_gcc_evidence=analysis["india_gcc_evidence"],
                    research_summary=analysis["research_summary"],
                    qualification_notes=analysis["qualification_notes"],
                    research_status="analyzed",
                    db_path=db_path,
                    company_profile=analysis.get("company_profile"),
                )
                summary["stages"]["analysis"] = "success"
                _record_stage(company_id, name, "analysis", "ok", None, started, db_path)
            except Exception as error:
                logger.error(f"[{name}] analysis failed: {error}")
                update_research_analysis(
                    research_id,
                    india_presence_status=None,
                    india_gcc_evidence=None,
                    research_summary=None,
                    qualification_notes=None,
                    research_status=f"llm_error: {error}",
                    db_path=db_path,
                )
                summary["stages"]["analysis"] = f"failed: {error}"
                _record_stage(company_id, name, "analysis", "failed", str(error), started, db_path)
                return summary  # can't draft a personalized email without analysis

        # --- Stage 5: contact discovery --------------------------------------
        contact = {"name": None, "title": None}
        saved_contact = get_contact_for_company(company_id, db_path) if "contact" in done else None

        if saved_contact is not None:
            contact = {"name": saved_contact["name"], "title": saved_contact["title"]}
            summary["stages"]["contact"] = "skipped (already done)"
        else:
            started = time.perf_counter()
            try:
                contact = find_contact(name, website_text)
                insert_contact(
                    company_id,
                    contact.get("name"),
                    contact.get("title"),
                    contact.get("email"),
                    contact.get("linkedin_url"),
                    contact.get("source"),
                    contact["status"],
                    db_path,
                )
                summary["stages"]["contact"] = contact["status"]
                _record_stage(company_id, name, "contact", "ok", None, started, db_path)
            except Exception as error:
                logger.error(f"[{name}] contact discovery failed: {error}")
                summary["stages"]["contact"] = f"failed: {error}"
                _record_stage(company_id, name, "contact", "failed", str(error), started, db_path)

        # --- Stage 6: email draft generation ------------------------------------
        if "email" in done and get_outreach_for_company(company_id, db_path) is not None:
            summary["stages"]["email"] = "skipped (already done)"
        else:
            started = time.perf_counter()
            try:
                email_draft = generate_outreach_email(
                    company_name=name,
                    research_summary=analysis["research_summary"],
                    india_gcc_evidence=analysis["india_gcc_evidence"],
                    qualification_notes=analysis["qualification_notes"],
                    contact_name=contact.get("name"),
                    contact_title=contact.get("title"),
                )
                insert_outreach(company_id, email_draft["subject"], email_draft["body"], db_path=db_path)
                summary["stages"]["email"] = "drafted"
                _record_stage(company_id, name, "email", "ok", None, started, db_path)
            except Exception as error:
                logger.error(f"[{name}] email generation failed: {error}")
                summary["stages"]["email"] = f"failed: {error}"
                _record_stage(company_id, name, "email", "failed", str(error), started, db_path)

        return summary

    except Exception as error:
        # Last-resort safety net: something unexpected happened that none
        # of the per-stage try/except blocks above caught. We log it and
        # record it, but we do NOT let it crash the whole batch.
        logger.exception(f"[{name}] unexpected error")
        summary["error"] = str(error)
        return summary

    finally:
        # Runs on every return path, so the summary always has a duration.
        summary["seconds"] = round(time.perf_counter() - started_at, 1)
        logger.info(f"[{name}] finished in {summary['seconds']}s")


def regenerate_email(company_id: int, company_name: str, db_path: str | None = None) -> dict:
    """
    Draft a fresh outreach email for a company from its saved research
    and contact, and save it as a new draft (older drafts are kept).
    Used by the dashboard's "Regenerate" button. Raises ValueError if
    the company has no completed research yet.
    """
    research = get_research_for_company(company_id, db_path)
    if research is None or not research["research_summary"]:
        raise ValueError("No completed research for this company yet - run the analysis first.")

    contact = get_contact_for_company(company_id, db_path)
    found = contact is not None and contact["status"] == "found"

    draft = generate_outreach_email(
        company_name=company_name,
        research_summary=research["research_summary"],
        india_gcc_evidence=research["india_gcc_evidence"],
        qualification_notes=research["qualification_notes"],
        contact_name=contact["name"] if found else None,
        contact_title=contact["title"] if found else None,
    )
    insert_outreach(company_id, draft["subject"], draft["body"], db_path=db_path)
    set_stage_status(company_id, "email", "ok", db_path=db_path)
    return draft


def summarize_batch(results: list[dict]) -> dict:
    """
    Count how a batch of process_one_company() results turned out. Pure
    function (no database or logging), so it is easy to test.
    """

    def count(stage: str, matches) -> int:
        return sum(1 for result in results if matches(result["stages"].get(stage, "")))

    return {
        "companies": len(results),
        "website_found": count("website_discovery", lambda s: s in ("found", "manual")),
        "website_unverified": count("website_discovery", lambda s: s == "found_unverified"),
        "website_missing": count("website_discovery", lambda s: s == "not_found" or s.startswith("error")),
        "crawl_ok": count("crawl", lambda s: s == "success"),
        "crawl_thin": count("crawl", lambda s: s == "thin_content"),
        "crawl_failed": count("crawl", lambda s: s.startswith("failed")),
        "analysis_ok": count("analysis", lambda s: s == "success"),
        "analysis_failed": count("analysis", lambda s: s.startswith("failed")),
        "contacts_found": count("contact", lambda s: s == "found"),
        "emails_drafted": count("email", lambda s: s == "drafted"),
        "unexpected_errors": sum(1 for result in results if "error" in result),
        "seconds": round(sum(result.get("seconds", 0) for result in results), 1),
    }


def log_batch_summary(results: list[dict]) -> dict:
    """Log a one-line summary of a finished batch and return the counts."""
    s = summarize_batch(results)
    logger.info(
        f"Batch finished: {s['companies']} companies in {s['seconds']}s | "
        f"websites found {s['website_found']}, unverified {s['website_unverified']}, "
        f"missing {s['website_missing']} | "
        f"crawl ok {s['crawl_ok']}, thin {s['crawl_thin']}, failed {s['crawl_failed']} | "
        f"analysis ok {s['analysis_ok']}, failed {s['analysis_failed']} | "
        f"contacts found {s['contacts_found']}, emails drafted {s['emails_drafted']} | "
        f"unexpected errors {s['unexpected_errors']}"
    )
    return s


def process_many_companies(names: list[str], db_path: str | None = None) -> list[dict]:
    """
    Run process_one_company() for a list of companies, one at a time,
    and return a list of summaries - one per company, in the same
    order. One company's failure never stops the others from being
    processed. A batch summary is logged at the end.
    """
    results = []
    for name in names:
        result = process_one_company(name, db_path)
        results.append(result)
    log_batch_summary(results)
    return results