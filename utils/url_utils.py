"""
Small, dependency-free helpers for working with URLs.

Why this file exists:
Several parts of the project need to answer simple questions about a URL:
what domain is it on? Is it one of the third-party sites (LinkedIn,
Wikipedia, news outlets, etc.) we want to avoid picking as a company's
"official website"? Centralizing this logic here means we maintain one
list and one set of rules, instead of scattering them across the project.

No network calls happen in this file - just string/URL parsing - which
is what makes it easy to test without mocking anything.
"""

import re
from urllib.parse import urlparse

# Domains that are almost never a company's OWN official website, even
# though they frequently show up at the top of search results for a
# company name. When picking an "official website" for a company, we
# skip any result whose domain matches one of these.
#
# This list is a heuristic and will need tuning over time - that's
# expected and fine. Add to it as you notice bad results.
BLOCKED_DOMAINS = {
    "cacompanyregistry.com",
    "connexy.com",
    "cuinsight.com",
    "globalrecognitionawards.org",
    "textranch.com",
    "cbiinsights.com",
    "theleague.coop",
    "fortune.com",
    "apple.com",
    "pinterest.com",
    "tradekey.com",
    "bebee.com",
    "linkedin.com",
    "rocketreach.co",
    "leadiq.com",
    "lnkd.in",      
    "wikipedia.org",
    "crunchbase.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "bloomberg.com",
    "indeed.com",
    "glassdoor.com",
    "zoominfo.com",
    "pitchbook.com",
    "owler.com",
    "reuters.com",
    "forbes.com",
    "wsj.com",
    "cnbc.com",
    "yellowpages.com",
    "bbb.org",
    "dnb.com",
    "manta.com",
    "craft.co",
    "tracxn.com",
    "github.com",
}


def get_domain(url: str) -> str:
    """
    Extract the bare domain from a URL, without "www." and without any
    path or query string.

    Example:
        "https://www.honeywell.com/us/en/about" -> "honeywell.com"
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[len("www."):]
    return domain


def is_blocked_domain(url: str) -> bool:
    """
    Return True if this URL's domain is a known third-party site
    (social media, business directory, news outlet, etc.) rather than
    a company's own website.

    We check both an exact match ("linkedin.com") and a subdomain match
    ("in.linkedin.com" ends with ".linkedin.com"), since sites often use
    country/region subdomains.
    """
    domain = get_domain(url)
    return any(
        domain == blocked or domain.endswith("." + blocked)
        for blocked in BLOCKED_DOMAINS
    )


def is_valid_url(url: str) -> bool:
    """
    Basic sanity check: does this look like a real, fetchable http(s)
    URL? This catches things like empty strings, "mailto:" links, or
    malformed values before we try to use them.
    """
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_url(url: str) -> str:
    """
    Add a scheme if missing, and strip a trailing slash, so URLs coming
    from different sources are stored and compared consistently.

    Example: "honeywell.com/" -> "https://honeywell.com"
    """
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    if url.endswith("/"):
        url = url[:-1]
    return url


# Words that appear in company names but not in their web addresses.
LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "llp", "plc", "gmbh", "ag", "sa", "pvt", "private",
    "pte", "bv", "nv", "sarl",
}


def domain_matches_company(company_name: str, url: str) -> bool:
    """
    Check whether a URL's domain looks like it belongs to the company,
    e.g. "Rockwell Automation" -> rockwellautomation.com.

    This is a heuristic. A False result does not mean the site is wrong
    (Tata Consultancy Services uses tcs.com); it only means the domain
    doesn't resemble the name.
    """
    all_tokens = re.findall(r"[a-z0-9]+", company_name.lower())
    # Drop words like "Inc" / "Ltd"; if that leaves nothing, keep them.
    tokens = [t for t in all_tokens if t not in LEGAL_SUFFIXES] or all_tokens
    if not tokens:
        return False

    domain = get_domain(url)
    label = domain.split(".")[0]  # "honeywell" from "honeywell.com"
    squashed = domain.replace(".", "").replace("-", "")
    compact = "".join(tokens)
    full = "".join(all_tokens)
    first = tokens[0]

    # Very short names ("GE", "3M", "PMI") match too easily by accident,
    # so they must equal the whole domain label.
    if len(compact) < 4:
        return label in (compact, full)

    return (
        compact in squashed
        or (len(first) >= 4 and first in squashed)
        or (len(first) >= 3 and label.startswith(first))
    )


def url_key(url: str) -> str:
    """
    A version of a URL used only to decide whether two URLs point to the
    same page. These all produce the same key:
        https://example.com
        https://example.com/
        https://Example.com/#top
    Different query strings stay different pages.
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query}"


def get_site_root(url: str) -> str:
    """
    Reduce any URL to its site's root, e.g.
    "https://www.honeywell.com/us/en/about-us" -> "https://www.honeywell.com"
    Returns the URL unchanged if it doesn't look like a full URL.
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"