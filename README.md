# GCC Lead Generator

A Python tool that helps find companies that could be candidates for setting up an India GCC (Global Capability Center) or engineering capability center, and drafts personalized outreach emails for a **person to review**. It never sends anything by itself.

## What it does

You paste a list of company names into a dashboard. For each company it:

1. **Finds the official website** with Tavily search, skipping LinkedIn, Wikipedia, news sites and directories, and preferring a site whose address resembles the company name.
2. **Crawls the site politely.** It starts from the real homepage, then reads a few relevant pages (locations, about, careers, contact...), waits between requests and respects `robots.txt`.
3. **Scans for India mentions with plain keyword matching** and saves each passage with the page it came from. This is evidence you can check.
4. **Asks an AI (Gemini or Grok) to analyze the text.** You get an India/GCC status, a short summary, a company profile (industry, size, number of sites, each with its source page) and a note labelled `[Heuristic]`.
5. **Looks for a contact.** It finds a named person only if their name and title are written on the site, and a company email address found on the site, with the page it came from.
6. **Drafts an outreach email** using your sender details, saved as "pending review".
7. **Stores everything locally** in SQLite. You review, edit, approve or reject drafts in the dashboard and export to CSV.

Nothing is ever guessed or invented: no guessed names, no guessed email addresses, and no email is sent automatically.

## What you need

- Python 3.10 or newer
- A [Tavily](https://tavily.com) API key
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey), or an xAI (Grok) key from [console.x.ai](https://console.x.ai)

## Setup

Windows (PowerShell):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Mac/Linux: use `source .venv/bin/activate` and `cp .env.example .env`.

Open `.env` and fill in your keys (see the table below). `.env` is git-ignored, so your keys never get committed.

## Settings (`.env`)

| Setting | Default | What it does |
|---|---|---|
| `GEMINI_API_KEY` | | Needed when `LLM_PROVIDER=gemini` |
| `XAI_API_KEY` | | Needed when `LLM_PROVIDER=grok` |
| `LLM_PROVIDER` | `gemini` | Which AI to use: `gemini` or `grok` |
| `TAVILY_API_KEY` | | Needed for website discovery |
| `SENDER_NAME`, `SENDER_TITLE`, `SENDER_COMPANY` | empty | Who the emails are from. Without them, drafts end with `[Your Name]` |
| `SENDER_OFFER` | empty | One or two sentences on what your company offers. Drafts describe your offer using only this text |
| `MAX_PAGES_PER_WEBSITE` | `5` | Pages read per site, including the homepage |
| `MAX_TEXT_CHARS_FOR_LLM` | `12000` | Text sent to the AI per company, shared fairly between pages |
| `MIN_CONTENT_CHARS` | `500` | Below this, a site is flagged "thin content" and the AI step is skipped |
| `CRAWL_DELAY_SECONDS` | `1.0` | Pause between requests to the same site |
| `RESPECT_ROBOTS_TXT` | `true` | Skip pages a site's robots.txt disallows |
| `TAVILY_EXTRACT_FALLBACK` | `false` | Use Tavily Extract for sites that block the crawler (403) or return almost no text. Uses Tavily credits |
| `REQUEST_TIMEOUT_SECONDS` | `10` | How long to wait for a page |
| `USER_AGENT` | built-in | Sent with every page request |

## Running it

**Dashboard (the main way to use it):**

```
streamlit run app.py
```

**Command line** (edit the company list at the top of the file first):

```
python try_pipeline.py
```

## Using the dashboard

1. **Input.** Paste company names, one per line, and click **Start processing**. Duplicates are removed. Steps that already finished for a company are skipped; tick "Re-run steps that already finished" to redo everything.
2. **Companies.** A table with website status, research status, India evidence, email draft status and a "Needs attention" column. Use the filters (all, needs attention, drafts waiting for review), the India evidence filter and the sort to find what to look at.
3. **Company details.** For the selected company you can see:
   - the website, with a box to enter the correct address and re-run if it is wrong
   - a table of pipeline steps with results, errors and seconds taken, plus **Retry failed steps** and **Re-run everything** buttons
   - the pages crawled, the company profile, the India passages found on the site (facts) and the AI analysis (interpretation)
   - the company email (with its source page) and any named contact
   - the draft email, which you can edit, save, approve, reject or regenerate, with a "Facts this draft is based on" section so you can check every claim
4. **Export.** Download everything as a CSV.

## How a company is processed

Each step is saved as it finishes, so a re-run repeats only the step that failed. For example, a "model is busy" error from Gemini costs one retried AI call, not a new search and crawl. One company failing never stops the others in a batch.

| Step | Possible outcomes |
|---|---|
| Website | `found`, `found_unverified` (no domain matched the name, check it), `manual`, `not_found`, `error` |
| Crawl | `success`, `thin_content`, or `failed: ...` (for example `http_error_403`, `timeout`, `connection_error`, `robots_txt`) |
| AI analysis | India status (below), summary, heuristic note, company profile |
| Contact | `found` or `not_found` |
| Email | drafted, then you decide: approve or reject |

**India status values**

- `clear_india_gcc_evidence`: the site clearly describes an India GCC or capability center.
- `india_operations_no_clear_gcc`: the site shows India offices or operations, but not clearly a GCC.
- `no_evidence_found`: nothing found **on the pages researched**. This is not proof that the company has no India presence.
- `insufficient_information`: not enough text to say.

## Project structure

```
app.py                      Streamlit dashboard (screen only, no business logic)
try_pipeline.py             Run the pipeline from the command line
debug_*.py                  Small scripts for troubleshooting discovery, email finding and Tavily Extract

config/settings.py          All configuration (reads .env, holds defaults)

database/
  database.py               SQLite connection, tables, upgrades for older databases
  models.py                 Every SQL query, as plain functions

scraper/
  company_extractor.py      Cleans and de-duplicates pasted company names
  search_provider.py        The ONLY file that knows about Tavily
  website_discovery.py      Picks the most likely official website
  website_crawler.py        Polite crawling, robots.txt, and the Tavily Extract fallback
  content_parser.py         HTML to text, links, emails, fair text sharing
  india_evidence.py         Keyword scan for India passages

ai/
  llm_service.py            The ONLY file that calls an AI provider (Gemini or Grok), with retries
  website_analyzer.py       India/GCC analysis, summary, company profile
  email_generator.py        Drafts outreach emails

contacts/contact_finder.py  Named contact and company email

pipeline/lead_pipeline.py   Runs the steps, skips finished ones, records timing and errors

utils/
  logger.py                 Console and file logging
  url_utils.py              Blocklist, URL helpers, domain matching
  overview.py               Dashboard filtering and "needs attention" rules

tests/                      Tests for every module
data/                       leads.db (git-ignored)
logs/                       app.log (git-ignored)
```

## Design notes

- **No ORM.** Every SQL query is a plain function in `database/models.py` that you can read.
- **One file per outside service.** Only `search_provider.py` mentions Tavily and only `llm_service.py` calls the AI. Switching providers means changing one file.
- **Facts and interpretation are kept apart.** The keyword scan, the profile sources and the company email show what the site actually says, with the page. The AI analysis is labelled as interpretation.
- **Website text is treated as untrusted.** Prompts tell the AI to treat page text as data and ignore any instructions inside it.
- **Everything is testable without keys.** Tests fake the network and the AI.

## Data and responsible use

- Everything is stored on your computer in `data/leads.db`.
- Company names go to Tavily. Page text goes to the AI provider you chose. With the Extract fallback on, some site addresses also go to Tavily for fetching.
- Emails and phone numbers collected from websites may fall under privacy rules (for example GDPR, or India's DPDP Act). Check with whoever handles compliance before you contact anyone.
- The tool respects `robots.txt` by default. Turning that off is your company's decision.

## Known limitations

- **Input is a pasted list.** Extracting names from a webpage is not built yet.
- **JavaScript-built and blocking sites.** These are flagged. The optional Tavily Extract fallback helps with some of them, but it is not guaranteed to get past a site's bot protection.
- **The keyword scan is English-only.** It uses a list of Indian cities and center-type wording in `scraper/india_evidence.py`. Sites in other languages will give weaker results. Add terms to the list as you find gaps.
- **Contact discovery is basic.** It reads names and titles from the site's own text. There is no LinkedIn lookup, no paid data provider and no confidence score.
- **Qualification is a heuristic note, not a score.** Define your own criteria before relying on it.
- **If the AI provider is busy,** calls are retried a few times, but the tool does not switch providers by itself. Change `LLM_PROVIDER` yourself.
- **The AI can make mistakes.** Check the profile against its source pages, and read every email before it goes anywhere.

## Troubleshooting

| Problem | What to do |
|---|---|
| `... API_KEY is not set` | Check that `.env` (not `.env.example`) is in the project root with real keys |
| Model "no longer available" (404) | Google and xAI retire models. Change the model name near the top of `ai/llm_service.py` to the one named in the error message |
| "Model is busy" (503) | Calls are retried automatically. Use **Retry failed steps** later, or set `LLM_PROVIDER=grok` |
| Crawl shows `http_error_403` | The site blocks automated visits. Try again later, research it by hand, or try `TAVILY_EXTRACT_FALLBACK=true` |
| "Thin content" | The site probably builds its pages with JavaScript. Try the Extract fallback, or research it by hand |
| `found_unverified` or the wrong website | Open the company in the dashboard and use the "Wrong website?" box |
| Crawl shows `robots_txt` | The site asks crawlers to stay away. Research it by hand, or see `RESPECT_ROBOTS_TXT` |
| `pip` can't find `google-genai` | Your Python is probably older than 3.10. Install a newer one and recreate `.venv` |
| `ModuleNotFoundError: No module named 'config'` | Run commands from the project root folder |
| A company email wasn't found | It must appear on a page the crawler fetched, as text or a `mailto:` link. Raise `MAX_PAGES_PER_WEBSITE` to read more pages |

## Tests

```
pytest tests/ -v
```

No API keys or internet connection are needed.