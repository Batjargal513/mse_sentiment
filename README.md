# MSE Sentiment — Mongolia Stock Intelligence

Scrapes Mongolian news, regulatory filings and Telegram groups, runs AI
sentiment analysis on every mention of a Mongolian Stock Exchange (MSE/МХБ)
company, and serves the results through a REST API and dashboard.

The pipeline has four stages:

```
  scrapers  ──▶  articles ──▶  sentiment_processor ──▶  sentiment_scores
 (8 sources)     (Supabase)    (GPT-4o-mini)            + daily history
                                                              │
                                          api.py (FastAPI) ◀──┘ ──▶ dashboard.html
```

## Project structure

```
mse-sentiment/
├── config/
│   └── settings.py             ← all settings + keywords, loaded from .env
├── db/
│   └── supabase.py             ← SCHEMA_SQL + read/write helpers
├── scrapers/
│   ├── mse_scraper.py          ← MSE official JSON API
│   ├── frc_scraper.py          ← Financial Regulatory Commission
│   ├── rss_scraper.py          ← news.mn, montsame.mn
│   ├── ikon_scraper.py         ← ikon.mn
│   ├── zarig_scraper.py        ← zarig.mn
│   ├── google_news_scraper.py  ← Google News (English queries)
│   ├── new_sources_scraper.py  ← Mining Journal, Mongolbank, Capital Markets
│   └── telegram_scraper.py     ← @openmindmse, @bibbytimes (real-time)
├── utils/
│   └── date_utils.py           ← published-date parsing (MN + EN)
├── sentiment_processor.py      ← detects tickers, scores sentiment (Claude Haiku 4.5)
├── bulk_processor.py           ← one-shot backlog processor
├── company_intelligence.py     ← per-company profile + Groq summary, seed companies
├── api.py                      ← FastAPI REST API
├── run_scrapers.py             ← master scheduler for all scrapers
├── dashboard.html              ← static dashboard (calls the API)
├── migrations/                 ← historical one-off DB fixes (already applied)
└── tests/                      ← pytest suite for the pure logic
```

## Setup

**1. Install dependencies** (a virtualenv is recommended)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Create your `.env` file**
```bash
cp .env.example .env
# Fill in your Supabase, Telegram, Anthropic and Groq keys
```

**3. Create the Supabase tables**
- Open your Supabase project → **SQL Editor**
- Print the schema and paste it into the editor, then run it once:
  ```bash
  PYTHONPATH=. python -c "from db.supabase import SCHEMA_SQL; print(SCHEMA_SQL)"
  ```

**4. Get Telegram API credentials**
- Go to https://my.telegram.org → log in with your phone number
- Create an application, then copy `api_id` and `api_hash` into `.env`

## Running the pipeline

All commands run from the repo root. `PYTHONPATH=.` lets the modules import
each other.

**Step 1 — Seed the companies table (run once)**
```bash
PYTHONPATH=. python company_intelligence.py seed
```

**Step 2 — Start the scrapers** (one master process schedules all eight sources)
```bash
PYTHONPATH=. python run_scrapers.py
```
The first run does a full historical scrape; restarts only run sources whose
interval has elapsed. The Telegram listener runs in real time in a background
thread.

**Step 3 — Process sentiment** (scores unprocessed articles every 10 min)
```bash
PYTHONPATH=. python sentiment_processor.py
```
To clear a large backlog in one shot instead:
```bash
PYTHONPATH=. python bulk_processor.py
```

**Step 4 — Start the REST API**
```bash
PYTHONPATH=. uvicorn api:app --host 0.0.0.0 --port 8000
```
Interactive docs: http://localhost:8000/docs

**Dashboard** — open `dashboard.html` in a browser (point it at your API URL).

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /companies` | All tracked MSE companies |
| `GET /sentiment/{ticker}` | Latest sentiment + trend for one stock |
| `GET /sentiment/{ticker}/history?days=30` | Sentiment trend over time |
| `GET /market/overview` | Market-wide sentiment summary for today |
| `GET /articles/{ticker}?limit=20` | Recent articles with scores |
| `GET /alerts?hours=48` | Recent significant sentiment shifts |

## Inspect a single company
```bash
PYTHONPATH=. python company_intelligence.py APU
```

## Database tables

- **`companies`** — MSE company master list (ticker, names, sector)
- **`articles`** — every scraped article/message (deduplicated by URL)
- **`sentiment_scores`** — AI score per company per article (`channel`: news/social)
- **`sentiment_history`** — daily aggregated score per company per channel
- **`scrape_log`** — what ran, when, and how much it found

## How sentiment works

1. Each scraper saves relevant articles to `articles` (keyword pre-filter in
   [`config/settings.py`](config/settings.py)).
2. `sentiment_processor.py` detects which tickers an article mentions
   (`detect_companies`), then asks **Claude Haiku 4.5** (Anthropic) to score
   sentiment (−1.0 bearish … +1.0 bullish) per company.
3. Scores roll up into `sentiment_history` (daily, per news/social channel).
4. `company_intelligence.py` uses **Groq (Llama 3)** to write short English
   summaries for the company pages.

## Tests

The pure logic (ticker detection, date parsing, language detection,
truncation) is covered by a pytest suite — no network or API keys required:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
```

## Notes

- `.env`, `*.session` and the virtualenv are git-ignored — never commit secrets.
- Many sources are Mongolia-geofenced; some scrapers may need a Mongolian IP/VPN.
- See [`migrations/README.md`](migrations/README.md) for the history of DB fixes.
