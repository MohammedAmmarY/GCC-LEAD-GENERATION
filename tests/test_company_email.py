from contacts.contact_finder import find_company_email
from scraper.content_parser import extract_emails


def test_extract_emails_finds_mailto_and_visible_text():
    html = '<a href="mailto:Info@Acme.com?subject=Hi">Mail</a><p>Sales: sales@acme.com.</p>'
    assert extract_emails(html) == ["info@acme.com", "sales@acme.com"]


def test_extract_emails_ignores_image_filenames():
    assert extract_emails('<img src="logo@2x.png"> <p>logo@2x.png</p>') == []


def test_find_company_email_prefers_generic_same_domain():
    emails = ["john.smith@acme.com", "sales@other.com", "info@acme.com"]
    assert find_company_email(emails, "https://www.acme.com") == "info@acme.com"


def test_find_company_email_falls_back_to_any_address():
    assert find_company_email(["john.smith@acme.com"], "https://acme.com") == "john.smith@acme.com"


def test_find_company_email_skips_noreply():
    assert find_company_email(["noreply@acme.com"], "https://acme.com") is None


def test_find_company_email_skips_placeholder_domains():
    assert find_company_email(["name@example.com"], "https://acme.com") is None