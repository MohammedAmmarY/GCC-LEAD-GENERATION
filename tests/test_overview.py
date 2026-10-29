from utils.overview import (
    NOT_ANALYZED,
    SORT_INDIA,
    SORT_NAME,
    SORT_NEWEST,
    VIEW_ALL,
    VIEW_ATTENTION,
    VIEW_DRAFTS,
    attention_reasons,
    filter_and_sort,
    india_label,
)


def _row(id, name, **fields):
    base = {
        "id": id, "name": name, "official_website": "https://x.com", "website_status": "found",
        "research_status": "analyzed", "india_presence_status": "no_evidence_found",
        "email_review_status": None, "failed_steps": 0, "failed_step_names": None,
    }
    base.update(fields)
    return base


def test_a_healthy_company_has_no_attention_reasons():
    assert attention_reasons(_row(1, "Healthy")) == []


def test_attention_reasons_cover_each_problem():
    assert attention_reasons(_row(1, "A", website_status="found_unverified")) == ["website unverified"]
    assert attention_reasons(_row(1, "A", website_status="not_found", research_status=None)) == ["no website"]
    assert attention_reasons(_row(1, "A", website_status="error: boom")) == ["no website"]
    assert attention_reasons(_row(1, "A", research_status="thin_content")) == ["thin content"]
    assert attention_reasons(_row(1, "A", research_status="failed: http_error_403")) == ["crawl failed"]
    assert attention_reasons(_row(1, "A", research_status="llm_error: 503 busy")) == ["AI step failed"]
    assert attention_reasons(_row(1, "A", failed_step_names="contact, email")) == ["contact step failed", "email step failed"]


def test_several_problems_are_all_reported():
    row = _row(1, "A", website_status="found_unverified", research_status="thin_content")
    assert attention_reasons(row) == ["website unverified", "thin content"]


def test_a_draft_waiting_for_review_is_not_a_problem():
    assert attention_reasons(_row(1, "A", email_review_status="pending_review")) == []


def test_india_label_names():
    assert india_label(_row(1, "A", india_presence_status="clear_india_gcc_evidence")) == "Clear GCC evidence"
    assert india_label(_row(1, "A", india_presence_status=None)) == NOT_ANALYZED
    assert india_label(_row(1, "A", india_presence_status="something_new")) == "something_new"


ROWS = [
    _row(1, "Zeta", india_presence_status="no_evidence_found"),
    _row(2, "alpha", india_presence_status="clear_india_gcc_evidence", email_review_status="pending_review"),
    _row(3, "Mid", india_presence_status=None, research_status="thin_content"),
    _row(4, "Beta", india_presence_status="india_operations_no_clear_gcc", website_status="found_unverified",
         email_review_status="approved"),
]


def test_view_filters():
    assert [r["name"] for r in filter_and_sort(ROWS, VIEW_ALL)] == ["Beta", "Mid", "alpha", "Zeta"]
    assert [r["name"] for r in filter_and_sort(ROWS, VIEW_ATTENTION)] == ["Beta", "Mid"]
    assert [r["name"] for r in filter_and_sort(ROWS, VIEW_DRAFTS)] == ["alpha"]


def test_india_status_filter_uses_readable_labels_and_empty_means_all():
    chosen = filter_and_sort(ROWS, india_labels=["Clear GCC evidence", "Not analyzed"])
    assert [r["name"] for r in chosen] == ["Mid", "alpha"]
    assert len(filter_and_sort(ROWS, india_labels=[])) == 4
    assert len(filter_and_sort(ROWS, india_labels=None)) == 4


def test_filters_combine():
    chosen = filter_and_sort(ROWS, VIEW_ATTENTION, ["Not analyzed"])
    assert [r["name"] for r in chosen] == ["Mid"]


def test_sort_orders():
    assert [r["name"] for r in filter_and_sort(ROWS, sort_by=SORT_NEWEST)] == ["Beta", "Mid", "alpha", "Zeta"]
    assert [r["name"] for r in filter_and_sort(ROWS, sort_by=SORT_NAME)] == ["alpha", "Beta", "Mid", "Zeta"]
    # strongest India evidence first, then operations, then none; unanalyzed last
    assert [r["name"] for r in filter_and_sort(ROWS, sort_by=SORT_INDIA)] == ["alpha", "Beta", "Zeta", "Mid"]


def test_filter_and_sort_does_not_change_the_input_list():
    original = list(ROWS)
    filter_and_sort(ROWS, VIEW_ATTENTION, sort_by=SORT_NAME)
    assert ROWS == original