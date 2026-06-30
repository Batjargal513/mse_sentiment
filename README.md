# MSE Sentiment — Mongolia Stock Intelligence

Scrapes Mongolian news and Telegram groups, runs AI sentiment analysis,
stores results in Supabase. Part of the NovaNews intelligence platform.

## Project structure

```
mse-sentiment/
├── config/
│   └── settings.py          ← all settings, loaded from .env
├── db/
│   └── supabase.py          ← database schema + read/write helpers
├── scrapers/
│   ├── telegram_scraper.py  ← monitors @openmindmse, @bibbytimes
│   └── rss_scraper.py       ← scrapes news.mn, montsame.mn every 30min
├── .env.example             ← copy to .env and fill in your keys
├── .gitignore               ← protects .env and session files
└── requirements.txt
```

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Create your .env file**
```bash
cp .env.example .env
# Fill in your keys
```

**3. Set up Supabase tables**
- Go to your Supabase project → SQL Editor
- Copy the SQL from `db/supabase.py` (the `SCHEMA_SQL` variable)
- Run it once to create all tables

**4. Get Telegram API credentials**
- Go to https://my.telegram.org
- Log in with your Mongolian phone number
- Create an application
- Copy `api_id` and `api_hash` to your `.env`

## Running

**RSS scraper** (runs every 30 minutes):
```bash
python scrapers/rss_scraper.py
```

**Telegram scraper** (real-time monitoring):
```bash
python scrapers/telegram_scraper.py
# First run will ask for your Telegram verification code
```

## What gets saved

- `articles` table — every relevant article/message
- `sentiment_scores` — AI scores per company per article (built in next step)
- `sentiment_history` — daily aggregated scores per company
- `scrape_log` — track what ran and when

## Running all workers

**Step 1 — Seed companies table (run once)**
```bash
python company_intelligence.py seed
```

**Step 2 — Start RSS scraper**
```bash
python scrapers/rss_scraper.py
```

**Step 3 — Start Telegram scraper**
```bash
python scrapers/telegram_scraper.py
```

**Step 4 — Start sentiment processor**
```bash
python sentiment_processor.py
```

**Step 5 — Start REST API**
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

**API docs available at:** http://localhost:8000/docs

## API endpoints

| Endpoint | Description |
|---|---|
| GET /companies | All tracked MSE companies |
| GET /sentiment/{ticker} | Latest sentiment for one stock |
| GET /sentiment/{ticker}/history | 30-day sentiment trend |
| GET /market/overview | Market-wide sentiment summary |
| GET /articles/{ticker} | Recent articles with scores |
| GET /alerts | Recent big sentiment shifts |

## Test a company
```bash
python company_intelligence.py APU
```
