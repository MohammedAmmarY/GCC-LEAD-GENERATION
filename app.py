"""
Streamlit dashboard for the GCC lead-generation system.

Why this file exists:
This file is intentionally just a UI layer. It calls functions from
database/models.py and pipeline/lead_pipeline.py and displays the
results - it contains no scraping, AI, or business logic of its own.

Run with:
    streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

from database.database import initialize_database
from database.models import (
    get_all_companies,
    get_company_overview,
    get_contact_for_company,
    get_export_rows,
    get_outreach_for_company,
    get_research_for_company,
    get_stage_statuses,
    update_outreach,
)
from pipeline.lead_pipeline import log_batch_summary, process_one_company, regenerate_email
from scraper.company_extractor import extract_companies_from_text
from utils.overview import (
    INDIA_LABEL_OPTIONS,
    SORT_OPTIONS,
    VIEW_OPTIONS,
    attention_reasons,
    filter_and_sort,
    india_label,
)
from utils.url_utils import is_valid_url, normalize_url

STAGE_ORDER = ["website", "crawl", "analysis", "contact", "email"]
STAGE_LABELS = {
    "website": "Find website",
    "crawl": "Crawl pages",
    "analysis": "AI analysis",
    "contact": "Find contact",
    "email": "Draft email",
}


def explain_crawl_status(research_status: str) -> str | None:
    """Plain-language hint for a research problem, or None if all is well."""
    if research_status.startswith("failed: http_error_403"):
        return (
            "The site blocked the crawler (HTTP 403). Try again later, research this company by hand, "
            "or set TAVILY_EXTRACT_FALLBACK=true in .env to try Tavily Extract."
        )
    if research_status.startswith("failed: http_error_404"):
        return "The page was not found (HTTP 404). The website address may be wrong - use the correction box below."
    if research_status.startswith("failed: timeout"):
        return "The site was too slow to respond."
    if research_status.startswith("failed: connection_error"):
        return "The site could not be reached. It may not exist, or the address may be wrong."
    if research_status.startswith("failed: robots_txt"):
        return (
            "The site's robots.txt asks automated tools not to read its home page, so the crawler "
            "skipped it. Research this company by hand. (You can change this with RESPECT_ROBOTS_TXT in .env.)"
        )
    if research_status.startswith("failed:"):
        return "The crawl failed, so there is nothing to analyze."
    if research_status == "thin_content":
        return (
            "Very little text was found. The site may build its pages with JavaScript, "
            "so the AI step was skipped instead of analyzing almost nothing. "
            "You can set TAVILY_EXTRACT_FALLBACK=true in .env to try Tavily Extract."
        )
    if research_status.startswith("llm_error"):
        return "The crawl worked but the AI step failed. Use 'Retry failed steps' below - finished steps are skipped."
    return None


def clean_website_input(text: str) -> str | None:
    """Turn what the user typed into a usable website address, or None if it isn't one."""
    if not text.strip():
        return None
    candidate = normalize_url(text)
    if " " in candidate or "." not in candidate or not is_valid_url(candidate):
        return None
    return candidate


def show_company_profile(profile: dict) -> None:
    """Show industry, size and number of sites as stated on the site, each with its source page."""
    fields = [("Industry", "industry"), ("Size", "size"), ("Countries / sites", "sites")]

    if not any(profile.get(key) for _, key in fields):
        st.caption("The crawled pages did not state an industry, size or number of sites.")
        return

    for label, key in fields:
        value = profile.get(key)
        if value:
            st.write(f"**{label}:** {value}")
            source = profile.get(f"{key}_source")
            st.caption(f"Source page: {source}" if source else "Source page not given")
        else:
            st.write(f"**{label}:** not stated")


def show_india_evidence(research) -> None:
    """Show the passages the keyword scan found (facts), each with its source page."""
    raw = research["india_evidence"]
    if raw is None:
        st.caption("No keyword scan is saved for this research record. Re-run the company to scan it.")
        return

    evidence = json.loads(raw)
    if not evidence:
        st.write("No India-related passages were found on the crawled pages.")
        return

    for item in evidence:
        center = f" - center wording: {', '.join(item['center_terms'])}" if item["center_terms"] else ""
        st.markdown(f"**{', '.join(item['locations'])}**{center}")
        st.text(item["text"])
        st.caption(f"Source page: {item['page']}")


st.set_page_config(page_title="GCC Lead Generator", layout="wide")

initialize_database()

st.title("GCC Lead Generator")
st.caption(
    "Finds companies that may be candidates for an India GCC / engineering "
    "capability center. All outreach emails require human review - nothing "
    "is ever sent automatically."
)

# Messages saved just before a page refresh, so they survive the refresh.
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

# --- 1. Input ----------------------------------------------------------------

st.header("1. Input companies")

raw_text = st.text_area(
    "Paste company names, one per line",
    height=150,
    placeholder="Honeywell\nCaterpillar\nEmerson\nRockwell Automation",
)

force_rerun = st.checkbox(
    "Re-run steps that already finished",
    value=False,
    help="Off: finished steps are skipped and only failed or missing ones run. On: everything is redone.",
)

if st.button("Start processing", type="primary"):
    company_names = extract_companies_from_text(raw_text)

    if not company_names:
        st.warning("No company names found in the text above.")
    else:
        progress_bar = st.progress(0, text="Starting...")
        results = []

        for index, company_name in enumerate(company_names):
            progress_bar.progress(
                index / len(company_names),
                text=f"Processing {company_name} ({index + 1}/{len(company_names)})",
            )
            results.append(process_one_company(company_name, force=force_rerun))

        progress_bar.progress(1.0, text="Done")
        batch = log_batch_summary(results)
        st.success(f"Processed {batch['companies']} companies in {batch['seconds']} seconds.")
        st.write(
            f"Websites found {batch['website_found']} "
            f"(unverified {batch['website_unverified']}, missing {batch['website_missing']}) | "
            f"Crawl ok {batch['crawl_ok']}, thin {batch['crawl_thin']}, failed {batch['crawl_failed']} | "
            f"AI analysis ok {batch['analysis_ok']}, failed {batch['analysis_failed']} | "
            f"Contacts found {batch['contacts_found']} | Emails drafted {batch['emails_drafted']}"
        )
        with st.expander("Show detailed results"):
            st.json(results)

st.divider()

# --- 2. Companies table ----------------------------------------------------------

st.header("2. Companies")

companies = get_all_companies()

if not companies:
    st.info("No companies yet. Paste some names above and click 'Start processing'.")
else:
    companies_df = pd.DataFrame([dict(row) for row in companies])
    overview_rows = get_company_overview()
    overview_by_id = {row["id"]: row for row in overview_rows}

    # Quick counts
    metric_cols = st.columns(3)
    metric_cols[0].metric("Companies", len(overview_rows))
    metric_cols[1].metric("Need attention", sum(1 for row in overview_rows if attention_reasons(row)))
    metric_cols[2].metric(
        "Drafts waiting for review",
        sum(1 for row in overview_rows if row["email_review_status"] == "pending_review"),
    )

    # Filters and sorting
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        view = st.selectbox("Show", VIEW_OPTIONS)
    with filter_col2:
        india_filter = st.multiselect(
            "India evidence", INDIA_LABEL_OPTIONS, help="Leave empty to show every status."
        )
    with filter_col3:
        sort_by = st.selectbox("Sort by", SORT_OPTIONS)

    visible_rows = filter_and_sort(overview_rows, view, india_filter, sort_by)

    if visible_rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "id": row["id"],
                        "Company": row["name"],
                        "Website": row["official_website"],
                        "Website status": row["website_status"],
                        "Research": (row["research_status"] or "")[:40],
                        "India evidence": india_label(row),
                        "Email draft": row["email_review_status"] or "",
                        "Needs attention": "; ".join(attention_reasons(row)),
                    }
                    for row in visible_rows
                ]
            ),
            hide_index=True,
        )
    else:
        st.info("No companies match these filters.")

    # --- 3. Company details --------------------------------------------------------

    st.header("3. Company details")

    selected_id = None
    if visible_rows:
        selected_id = st.selectbox(
            "Select a company to review",
            options=[row["id"] for row in visible_rows],
            format_func=lambda company_id: overview_by_id[company_id]["name"],
        )

    if selected_id:
        company_row = companies_df.loc[companies_df["id"] == selected_id].iloc[0]
        company_name = company_row["name"]
        research = get_research_for_company(selected_id)
        contact = get_contact_for_company(selected_id)
        outreach = get_outreach_for_company(selected_id)

        # Website, with a way to correct it
        website = company_row["official_website"] if pd.notna(company_row["official_website"]) else None
        st.write(f"**Website:** {website or 'none found'}  ({company_row['website_status']})")
        if company_row["website_status"] == "found_unverified":
            st.warning("This website was not matched to the company name. Please check it is the right one.")

        reasons = attention_reasons(overview_by_id[selected_id])
        if reasons:
            st.warning("Needs attention: " + "; ".join(reasons))

        with st.expander("Wrong website? Enter the correct one and re-run"):
            typed_url = st.text_input(
                "Correct website address",
                key=f"override_url_{selected_id}",
                placeholder="https://www.company.com",
            )
            if st.button("Save website and re-run", key=f"override_button_{selected_id}"):
                new_website = clean_website_input(typed_url)
                if new_website is None:
                    st.error("Please enter a valid website address, like https://www.company.com")
                else:
                    with st.spinner(f"Re-running {company_name} with {new_website} ..."):
                        process_one_company(company_name, website_override=new_website)
                    st.session_state["flash"] = f"Re-ran {company_name} using {new_website}."
                    st.rerun()

        # What happened at each step, with errors
        statuses = get_stage_statuses(selected_id)
        if statuses:
            st.subheader("Pipeline steps")
            status_rows = [
                {
                    "Step": STAGE_LABELS[stage],
                    "Result": statuses[stage]["status"],
                    "Seconds": statuses[stage]["seconds"],
                    "Message": statuses[stage]["message"] or "",
                }
                for stage in STAGE_ORDER
                if stage in statuses
            ]
            st.dataframe(pd.DataFrame(status_rows), hide_index=True)

        retry_col, rerun_col = st.columns(2)
        with retry_col:
            if st.button("Retry failed steps", key=f"retry_{selected_id}"):
                with st.spinner(f"Retrying {company_name} ..."):
                    process_one_company(company_name)
                st.session_state["flash"] = f"Retried {company_name}. Finished steps were skipped."
                st.rerun()
        with rerun_col:
            if st.button("Re-run everything", key=f"force_{selected_id}"):
                with st.spinner(f"Re-running {company_name} ..."):
                    process_one_company(company_name, force=True)
                st.session_state["flash"] = f"Re-ran every step for {company_name}."
                st.rerun()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Research")
            if research:
                st.write(f"**Crawl/research status:** {research['research_status']}")
                hint = explain_crawl_status(research["research_status"])
                if hint:
                    st.warning(hint)

                pages_crawled = json.loads(research["pages_researched"] or "[]")
                with st.expander(f"Pages crawled ({len(pages_crawled)})"):
                    if pages_crawled:
                        for page_url in pages_crawled:
                            st.markdown(f"- {page_url}")
                    else:
                        st.write("No pages were crawled.")

                raw_profile = research["company_profile"]
                if raw_profile is None:
                    st.caption("No company profile is saved for this research record. Re-run the company to get one.")
                else:
                    show_company_profile(json.loads(raw_profile))

                st.markdown("**India-related passages found on the site** (keyword scan - facts, with source page)")
                show_india_evidence(research)

                st.markdown("**AI analysis** (interpretation - check it against the passages above)")
                st.write(f"**India presence status:** {research['india_presence_status'] or 'Not yet analyzed'}")
                st.write("**India/GCC evidence:**")
                st.write(research["india_gcc_evidence"] or "Not yet analyzed.")
                st.write("**Research summary:**")
                st.write(research["research_summary"] or "Not yet analyzed.")
                st.write("**Qualification notes (heuristic - not a verified score):**")
                st.write(research["qualification_notes"] or "Not yet analyzed.")
            else:
                st.write("No research yet for this company.")

        with col2:
            st.subheader("Contact")

            company_email = company_row["company_email"]
            email_source = company_row["company_email_source"]
            if pd.notna(company_email):
                st.write(f"**Company email (found on website):** {company_email}")
                if pd.notna(email_source):
                    st.caption(f"Found on page: {email_source}")
                else:
                    st.caption("Source page not recorded. Re-run this company to record it.")
            else:
                st.write("**Company email (found on website):** Not found")

            if contact and contact["status"] == "found":
                st.write(f"**Name:** {contact['name']}")
                st.write(f"**Title:** {contact['title']}")
                st.write(f"**Source:** {contact['source']}")
                st.write(f"**Email:** {contact['email'] or 'Not publicly available'}")
            else:
                st.write("Contact not found.")

        st.subheader("Outreach email (human review required)")

        if outreach:
            edited_subject = st.text_input(
                "Subject", value=outreach["subject"], key=f"subject_{outreach['id']}"
            )
            edited_body = st.text_area(
                "Email body", value=outreach["email_body"], height=250, key=f"body_{outreach['id']}"
            )
            st.write(f"**Review status:** {outreach['review_status']}")

            with st.expander("Facts this draft is based on (check every claim)"):
                if research:
                    st.write(f"**Research summary:** {research['research_summary']}")
                    st.write(f"**India/GCC evidence (AI):** {research['india_gcc_evidence']}")
                    st.write(f"**Qualification notes:** {research['qualification_notes']}")
                    st.markdown("**Passages found on the site:**")
                    show_india_evidence(research)
                if contact and contact["status"] == "found":
                    st.write(f"**Contact addressed:** {contact['name']} ({contact['title']})")
                else:
                    st.write("**Contact addressed:** none (neutral greeting)")

            btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
            with btn_col1:
                if st.button("Save edits", key=f"save_{outreach['id']}"):
                    update_outreach(outreach["id"], edited_subject, edited_body, outreach["review_status"])
                    st.success("Saved.")
            with btn_col2:
                if st.button("Approve", key=f"approve_{outreach['id']}"):
                    update_outreach(outreach["id"], edited_subject, edited_body, "approved")
                    st.success("Marked as approved. This tool does NOT send emails - approval just records your decision.")
            with btn_col3:
                if st.button("Reject", key=f"reject_{outreach['id']}"):
                    update_outreach(outreach["id"], edited_subject, edited_body, "rejected")
                    st.info("Marked as rejected.")
            with btn_col4:
                if st.button("Regenerate draft", key=f"regenerate_{outreach['id']}"):
                    error_message = None
                    try:
                        with st.spinner("Writing a new draft..."):
                            regenerate_email(selected_id, company_name)
                    except Exception as error:
                        error_message = str(error)

                    # st.rerun() is called outside the try block on purpose.
                    if error_message:
                        st.error(f"Could not regenerate the draft: {error_message}")
                    else:
                        st.session_state["flash"] = "New draft created. Your previous draft is kept in the database."
                        st.rerun()
        else:
            st.write("No email draft yet for this company.")

    st.divider()

    # --- 4. Export ---------------------------------------------------------------

    st.header("4. Export")

    export_rows = get_export_rows()
    if export_rows:
        export_df = pd.DataFrame(export_rows)
        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download all results as CSV",
            data=csv_bytes,
            file_name="gcc_leads_export.csv",
            mime="text/csv",
        )
    else:
        st.write("Nothing to export yet.")