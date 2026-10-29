"""
All configuration for the project lives here.

Why this file exists:
Instead of scattering "magic numbers" (timeouts, limits, file paths) and
secrets (API keys) across many files, we keep them in one place. If you
need to change the request timeout or move the database, you only need
to look here.

Secrets (API keys) are NOT stored in this file directly. They live in a
local ".env" file (which is git-ignored) and are loaded at runtime using
python-dotenv. This means the actual key values never get committed to
version control.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# load_dotenv() reads the ".env" file in the project root (if it exists)
# and copies its key=value pairs into the environment variables that
# os.getenv() below can then read. If there is no .env file, this simply
# does nothing (no error) and os.getenv() will return None for missing keys.
load_dotenv()

# --- Paths -------------------------------------------------------------

# Path(__file__) is the path to this settings.py file.
# .resolve().parent.parent walks up two levels: config/ -> project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "leads.db"

# --- Secrets (from .env / environment variables) ------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # "gemini" or "grok"

# --- Non-secret configuration (safe defaults, can still be overridden) --

# How long (seconds) to wait for a web page before giving up.
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))

# How many pages of one company's website we will fetch at most.
MAX_PAGES_PER_WEBSITE = int(os.getenv("MAX_PAGES_PER_WEBSITE", "5"))

# How many characters of website text we will send to the LLM at once.
# LLMs charge/limit by tokens, so we cap this to keep costs and errors down.
MAX_TEXT_CHARS_FOR_LLM = int(os.getenv("MAX_TEXT_CHARS_FOR_LLM", "12000"))

# If a crawled site yields fewer text characters than this, it is flagged
# "thin_content" (often a JavaScript-based site) and the LLM step is
# skipped instead of analyzing almost nothing.
MIN_CONTENT_CHARS = int(os.getenv("MIN_CONTENT_CHARS", "500"))

# Sent with every web request so sites can identify our traffic.
USER_AGENT = os.getenv(
    "USER_AGENT",
    "GCCLeadResearchBot/0.1 (contact: you@example.com)",
)

# When true, a site that blocks the crawler (HTTP 403) or returns almost no
# text is fetched through Tavily Extract instead. This uses Tavily credits.
TAVILY_EXTRACT_FALLBACK = os.getenv("TAVILY_EXTRACT_FALLBACK", "false").strip().lower() == "true"


# --- Polite crawling -------------------------------------------------------

# Seconds to wait between requests to the same website.
CRAWL_DELAY_SECONDS = float(os.getenv("CRAWL_DELAY_SECONDS", "1.0"))

# When true, pages that a site's robots.txt disallows are not fetched.
RESPECT_ROBOTS_TXT = os.getenv("RESPECT_ROBOTS_TXT", "true").strip().lower() == "true"

# --- Who the outreach emails are from ---------------------------------------

SENDER_NAME = os.getenv("SENDER_NAME", "")
SENDER_TITLE = os.getenv("SENDER_TITLE", "")
SENDER_COMPANY = os.getenv("SENDER_COMPANY", "")
# One or two sentences on what your company offers. The email drafts describe
# your offer using only this text, so write what you are happy to claim.
SENDER_OFFER = os.getenv("SENDER_OFFER", "")


def ensure_data_dir_exists() -> None:
    """
    Make sure the folder that will hold the SQLite database file exists.

    Called once when the app starts. mkdir(parents=True, exist_ok=True)
    means: create any missing parent folders, and don't raise an error
    if the folder is already there.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
