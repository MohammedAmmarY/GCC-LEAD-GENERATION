from scraper.content_parser import allocate_text_budget, build_combined_text


def test_allocate_text_budget_gives_short_pages_what_they_need():
    limits = allocate_text_budget(["a" * 9000, "b" * 500, "c" * 3000, "d" * 200, "e" * 6000], 12000)

    assert limits[3] == 200
    assert limits[1] == 500
    assert limits[2] == 3000
    assert sum(limits) == 12000


def test_allocate_text_budget_never_exceeds_the_total():
    assert sum(allocate_text_budget(["x" * 100, "y" * 100, "z" * 100], 90)) <= 90


def test_build_combined_text_keeps_every_page_and_page_order():
    pages = [
        {"url": "https://example.com", "text": "HOME " * 5000},
        {"url": "https://example.com/locations", "text": "We have an office in Pune."},
    ]

    combined = build_combined_text(pages, 2000)

    assert len(combined) <= 2000
    # The long homepage cannot push the Locations page out.
    assert "We have an office in Pune." in combined
    assert combined.index("https://example.com ---") < combined.index("/locations ---")


def test_build_combined_text_with_no_pages_is_empty():
    assert build_combined_text([], 1000) == ""