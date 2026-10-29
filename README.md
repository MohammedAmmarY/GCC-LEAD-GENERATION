# GCC Lead Generator

A Python tool that helps identify companies that may be candidates for
setting up an India GCC (Global Capability Center) / engineering
capability center, and drafts personalized outreach emails for **human
review**. It never sends emails automatically.

## What it does

Given a list of company names, for each one it:

1. Finds the company's official website (via Tavily search, filtering
   out LinkedIn/Wikipedia/news/directory results).
2. Crawls the homepage plus a handful of relevant pages (About, Careers,
   Locations, etc.).
3. Uses Google's Gemini API to look for evidence of an existing
   India presence/GCC on the website, and produce a factual summary.
4. Attempts to find a named contact (only if one is explicitly written
   on the site - never guessed).
5. Drafts a personalized outreach email.
6. Stores everything in a local SQLite database.
7. Shows it all in a Streamlit dashboard, where a human reviews,
   edits, approves/rejects, and can export results to CSV.

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env        # on Windows; use `cp` on Mac/Linux
```

Edit `.env` and add your real keys:

```
GEMINI_API_KEY=your-gemini-key-here
TAVILY_API_KEY=your-tavily-key-here
```

## Running it

**Dashboard (the main way to use this):**

```bash
streamlit run app.py
```

Paste company names (one per line) into the text box, click "Start
processing", and review results as they appear.

**Command-line demo script** (useful for quick testing without the UI):

```bash
python try_pipeline.py
```

**Tests** (no API keys needed - every network/LLM call is faked):

```bash
pytest tests/ -v
```

## Project structure

```
app.py                     - Streamlit dashboard (UI only, no business logic)
try_pipeline.py            - small script for trying the pipeline from the command line

config/settings.py         - all configuration (reads .env, holds defaults)

database/
  database.py              - SQLite connection + schema
  models.py                - all SQL lives here as plain functions

scraper/
  company_extractor.py     - cleans/dedupes a pasted list of company names
  search_provider.py       - the ONLY file that knows about Tavily
  website_discovery.py     - picks a real company site from search results
  website_crawler.py       - fetches homepage + relevant pages, handles errors
  content_parser.py        - HTML -> readable text, link extraction

ai/
  llm_service.py           - the ONLY file that calls the Gemini API
  website_analyzer.py      - India/GCC evidence detection + summary
  email_generator.py       - drafts outreach emails

contacts/
  contact_finder.py        - extracts a named contact IF one is on the site

pipeline/
  lead_pipeline.py         - runs all stages for one/many companies,
                              with per-stage and per-company error handling

utils/
  logger.py                - console + file logging
  url_utils.py              - domain/URL helpers (blocklist, validation)

tests/                     - one test file per module above
data/                      - leads.db lives here (git-ignored)
logs/                      - app.log lives here (git-ignored)
```

## Design notes

- **No ORM.** Every SQL query is a plain string in `database/models.py`
  you can read directly.
- **One file per external service.** `search_provider.py` is the only
  file that mentions Tavily; `llm_service.py` is the only file that
  calls the LLM provider. Swapping either later means changing one
  file, not the whole codebase.
- **Every stage is independently testable.** Tests fake the network/LLM
  calls via `monkeypatch`, so `pytest tests/` runs in under 2 seconds
  with no API keys and no internet connection required.
- **Fact vs. inference.** The `india_presence_status` field only records
  what the LLM found stated on the website; `qualification_notes` is
  explicitly labeled `[Heuristic]` to keep opinion separate from
  evidence. Neither is a verified score - both are starting points for
  a human to evaluate.
- **Nothing sends automatically.** Every outreach email starts as
  `review_status = "pending_review"` and only changes when a human
  clicks Approve/Reject in the dashboard. There is no send functionality
  anywhere in this codebase.
- **One company's failure never stops a batch.** Every stage records a
  status string rather than raising uncaught exceptions up to the
  batch loop - see `pipeline/lead_pipeline.py`.

## Known limitations (by design, for this first version)

- Website discovery is a heuristic (skip known non-company domains, take
  the first plausible result) - it can occasionally pick a wrong site,
  especially for small or ambiguously-named companies.
- Contact discovery only looks at text already crawled from the
  company's own site - no LinkedIn scraping, no paid data providers, no
  guessed email addresses.
- Qualification is a plain heuristic label from the LLM, not a
  scientifically validated score.
- Designed for manual, on-demand runs of 10-50 companies - no
  scheduling, background workers, or queueing.

## Troubleshooting

- `RuntimeError: TAVILY_API_KEY is not set` / `GEMINI_API_KEY is not
  set` - make sure `.env` (not `.env.example`) exists in the project
  root with real keys filled in.
- A company stuck at `website_status: not_found` - the search didn't
  return a result outside the blocklist in `utils/url_utils.py`; try a
  more specific company name, or add/remove domains from
  `BLOCKED_DOMAINS` if you notice a pattern.
- Streamlit dashboard shows stale data after a manual DB edit - refresh
  the browser tab; Streamlit re-reads the database on each interaction
  but caches the page between reruns.
