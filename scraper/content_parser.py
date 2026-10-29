"""
Extracts readable text and links from raw HTML.

Why this file exists:
Fetching a webpage (website_crawler.py) and making sense of its HTML are
two different jobs. This file only knows how to turn raw HTML into
(a) clean, readable text and (b) a list of links found on the page. It
never touches the network, which is what makes it easy to test with a
plain HTML string - no mocking required.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def extract_readable_text(html: str) -> str:
    """
    Turn raw HTML into plain, readable text.

    We remove <script>, <style>, and <noscript> tags first, because
    BeautifulSoup's get_text() would otherwise include raw JavaScript/CSS
    code in the output - useless (and sometimes huge) text to send to an
    LLM later.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()  # removes the tag and everything inside it

    text = soup.get_text(separator=" ")

    # HTML layout often produces lots of whitespace/newlines in the
    # extracted text. Collapsing every run of whitespace into one space
    # makes the result much more compact and readable.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_links(html: str, base_url: str) -> list[str]:
    """
    Extract every link (<a href="...">) from the page as a full,
    absolute URL.

    HTML links are often relative, e.g. href="/about-us". urljoin()
    combines that with the page's own URL to produce
    "https://example.com/about-us" - without this we couldn't tell
    where a relative link actually points.
    """
    soup = BeautifulSoup(html, "html.parser")

    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()

        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        absolute_url = urljoin(base_url, href)
        links.append(absolute_url)

    return links


def is_same_domain(url: str, base_url: str) -> bool:
    """
    Check whether `url` belongs to the same website as `base_url`.

    Used to make sure crawling stays on the company's own site instead
    of wandering off to partner sites, social media, or ad links found
    on the homepage.
    """
    return urlparse(url).netloc.lower() == urlparse(base_url).netloc.lower()


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IGNORED_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def extract_emails(html: str) -> list[str]:
    """
    Find every email address on a page: both mailto: links and addresses
    written as visible text. Returns lowercase, de-duplicated addresses
    in the order found. Image filenames like "logo@2x.png" are ignored.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []

    # 1. mailto: links (the address may not appear as visible text).
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.lower().startswith("mailto:"):
            address_part = href[len("mailto:"):].split("?")[0]
            found.extend(EMAIL_PATTERN.findall(address_part))

    # 2. Addresses written in the visible page text.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    found.extend(EMAIL_PATTERN.findall(soup.get_text(separator=" ")))

    cleaned: list[str] = []
    for email in found:
        email = email.lower().strip(".")
        if email.endswith(IGNORED_EMAIL_SUFFIXES):
            continue
        if email not in cleaned:
            cleaned.append(email)
    return cleaned


def allocate_text_budget(texts: list[str], total_limit: int) -> list[int]:
    """
    Decide how many characters each text may use so that all of them
    together fit in total_limit. Short pages use only what they need and
    the leftover is shared among the longer pages, so one long page can
    never crowd the others out.
    """
    limits = [0] * len(texts)
    remaining = total_limit
    # Handle the shortest texts first: they take what they need, and
    # whatever is left over is split between the longer ones.
    order = sorted(range(len(texts)), key=lambda index: len(texts[index]))
    for position, index in enumerate(order):
        texts_left = len(texts) - position
        fair_share = remaining // texts_left
        limits[index] = min(len(texts[index]), fair_share)
        remaining -= limits[index]
    return limits


def build_combined_text(pages: list[dict], total_limit: int) -> str:
    """
    Join the text of every crawled page (each labelled with its URL) into
    one block of at most total_limit characters. Pages keep their order,
    so the homepage stays first, but each page gets a fair share of the
    space instead of the first long page using it all.
    """
    if not pages:
        return ""

    headers = [f"--- Page: {page['url']} ---\n" for page in pages]
    separators = 2 * (len(pages) - 1)  # the blank line between pages
    text_budget = max(total_limit - sum(len(header) for header in headers) - separators, 0)

    limits = allocate_text_budget([page["text"] for page in pages], text_budget)

    parts = [
        header + page["text"][:limit]
        for header, page, limit in zip(headers, pages, limits)
    ]
    return "\n\n".join(parts)[:total_limit]