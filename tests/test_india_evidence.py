from scraper.india_evidence import find_india_evidence, format_evidence_for_prompt


def _page(text, url="https://example.com/about"):
    return {"url": url, "text": text}


def test_finds_sentence_with_city_and_remembers_the_page():
    pages = [_page("We were founded in 1990. Our engineering center in Pune supports global teams. Contact us today.")]

    evidence = find_india_evidence(pages)

    assert len(evidence) == 1
    assert evidence[0]["page"] == "https://example.com/about"
    assert evidence[0]["locations"] == ["Pune"]
    assert evidence[0]["center_terms"] == ["engineering center"]
    assert "Pune" in evidence[0]["text"]


def test_passages_with_center_wording_come_first():
    pages = [_page("We sell to customers in India. Our global capability center in Hyderabad employs 400 engineers.")]

    evidence = find_india_evidence(pages)

    assert "Hyderabad" in evidence[0]["text"]
    assert evidence[0]["center_terms"] != []
    assert evidence[1]["center_terms"] == []


def test_does_not_match_indiana():
    assert find_india_evidence([_page("Our plant in Indiana makes engine parts.")]) == []


def test_new_delhi_is_one_location():
    evidence = find_india_evidence([_page("Our regional office is in New Delhi.")])
    assert evidence[0]["locations"] == ["New Delhi"]


def test_ignores_country_selector_menus():
    menu = "Select your country Argentina Australia Austria Belgium Brazil Canada China India Indonesia Italy Japan Mexico"
    assert find_india_evidence([_page(menu)]) == []


def test_keeps_a_real_sentence_that_lists_countries():
    text = "Our offices are in Germany, France, Poland, Mexico and India."
    assert len(find_india_evidence([_page(text)])) == 1


def test_removes_duplicate_passages_and_caps_the_count():
    repeated = _page("Our office in Pune is open. " * 5)
    assert len(find_india_evidence([repeated])) == 1

    many = _page(" ".join(f"Office number {i} is in Pune." for i in range(30)))
    assert len(find_india_evidence([many], max_snippets=5)) == 5


def test_long_sentences_are_trimmed_around_the_match():
    text = ("word " * 200) + "our centre in Chennai opened" + (" word" * 200)
    evidence = find_india_evidence([_page(text)])
    assert len(evidence[0]["text"]) <= 310
    assert "Chennai" in evidence[0]["text"]


def test_format_for_prompt_with_and_without_evidence():
    assert "no India-related passages" in format_evidence_for_prompt([])

    block = format_evidence_for_prompt(find_india_evidence([_page("Our office in Pune is open.")]))
    assert "KEYWORD SCAN" in block
    assert "[1] (https://example.com/about) Our office in Pune is open." in block