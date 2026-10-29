"""
Tests for scraper/content_parser.py

Run with:  pytest tests/test_content_parser.py -v
"""

from scraper.content_parser import extract_links, extract_readable_text, is_same_domain


def test_extract_readable_text_removes_script_and_style():
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <script>alert('hello');</script>
        <p>Welcome to Example Corp.</p>
      </body>
    </html>
    """
    text = extract_readable_text(html)

    assert "Welcome to Example Corp." in text
    assert "alert" not in text
    assert "color: red" not in text


def test_extract_readable_text_collapses_whitespace():
    html = "<html><body>Hello   \n\n   World</body></html>"
    text = extract_readable_text(html)
    assert text == "Hello World"


def test_extract_links_resolves_relative_urls():
    html = '<a href="/about-us">About</a>'
    links = extract_links(html, "https://example.com")
    assert links == ["https://example.com/about-us"]


def test_extract_links_keeps_absolute_urls():
    html = '<a href="https://other.com/page">Other</a>'
    links = extract_links(html, "https://example.com")
    assert links == ["https://other.com/page"]


def test_extract_links_skips_anchors_mailto_and_tel():
    html = """
    <a href="#section">Jump</a>
    <a href="mailto:info@example.com">Email us</a>
    <a href="tel:+1234567890">Call us</a>
    <a href="/real-page">Real page</a>
    """
    links = extract_links(html, "https://example.com")
    assert links == ["https://example.com/real-page"]


def test_extract_links_skips_empty_href():
    html = '<a href="">Empty</a><a href="/page">Page</a>'
    links = extract_links(html, "https://example.com")
    assert links == ["https://example.com/page"]


def test_is_same_domain_true_for_matching_domain():
    assert is_same_domain("https://example.com/about", "https://example.com") is True


def test_is_same_domain_false_for_different_domain():
    assert is_same_domain("https://linkedin.com/company/example", "https://example.com") is False


def test_is_same_domain_ignores_scheme_and_path():
    assert is_same_domain("http://example.com/careers", "https://example.com/") is True
