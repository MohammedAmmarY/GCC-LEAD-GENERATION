"""
Plain-Python logic behind the dashboard's company table and filters.

Why this file exists:
Deciding which companies "need attention", and how to filter and sort the
table, is logic - not display. Keeping it here, away from app.py, means it
can be tested without opening a browser.
"""

VIEW_ALL = "All companies"
VIEW_ATTENTION = "Needs attention"
VIEW_DRAFTS = "Drafts waiting for review"
VIEW_OPTIONS = [VIEW_ALL, VIEW_ATTENTION, VIEW_DRAFTS]

SORT_NEWEST = "Newest first"
SORT_NAME = "Name A-Z"
SORT_INDIA = "India evidence (strongest first)"
SORT_OPTIONS = [SORT_NEWEST, SORT_NAME, SORT_INDIA]

# Readable names for the India status values stored in the database, in the
# order they are listed in filters and used for sorting.
INDIA_STATUS_LABELS = {
    "clear_india_gcc_evidence": "Clear GCC evidence",
    "india_operations_no_clear_gcc": "India operations, no clear GCC",
    "insufficient_information": "Insufficient information",
    "no_evidence_found": "No evidence found",
}
NOT_ANALYZED = "Not analyzed"
INDIA_LABEL_OPTIONS = list(INDIA_STATUS_LABELS.values()) + [NOT_ANALYZED]


def india_label(row: dict) -> str:
    """Readable India status for a company row."""
    status = row.get("india_presence_status")
    if not status:
        return NOT_ANALYZED
    return INDIA_STATUS_LABELS.get(status, status)


def attention_reasons(row: dict) -> list[str]:
    """
    Short reasons a company needs a person to look at it (an empty list
    means nothing is wrong). Drafts waiting for review are NOT a problem,
    so they are handled by their own filter instead.
    """
    reasons: list[str] = []

    website_status = row.get("website_status") or ""
    if website_status == "found_unverified":
        reasons.append("website unverified")
    elif website_status in ("pending", "not_found") or website_status.startswith("error"):
        reasons.append("no website")

    research_status = row.get("research_status") or ""
    if research_status == "thin_content":
        reasons.append("thin content")
    elif research_status.startswith("failed"):
        reasons.append("crawl failed")
    elif research_status.startswith("llm_error"):
        reasons.append("AI step failed")

    failed_steps = (row.get("failed_step_names") or "").split(", ")
    if "contact" in failed_steps:
        reasons.append("contact step failed")
    if "email" in failed_steps:
        reasons.append("email step failed")

    return reasons


_INDIA_SORT_ORDER = {status: position for position, status in enumerate(INDIA_STATUS_LABELS)}


def filter_and_sort(
    rows: list[dict],
    view: str = VIEW_ALL,
    india_labels: list[str] | None = None,
    sort_by: str = SORT_NEWEST,
) -> list[dict]:
    """
    Apply the dashboard's view, India-status filter and sort order.
    india_labels is a list of readable labels (see INDIA_LABEL_OPTIONS);
    an empty or missing list means "don't filter by India status".
    """
    selected = []
    for row in rows:
        if view == VIEW_ATTENTION and not attention_reasons(row):
            continue
        if view == VIEW_DRAFTS and row.get("email_review_status") != "pending_review":
            continue
        if india_labels and india_label(row) not in india_labels:
            continue
        selected.append(row)

    # Start from newest first. Python's sort keeps equal items in their
    # existing order, so the other sorts stay newest-first within a group.
    selected.sort(key=lambda row: row["id"], reverse=True)
    if sort_by == SORT_NAME:
        selected.sort(key=lambda row: row["name"].lower())
    elif sort_by == SORT_INDIA:
        selected.sort(key=lambda row: _INDIA_SORT_ORDER.get(row.get("india_presence_status"), len(_INDIA_SORT_ORDER)))
    return selected