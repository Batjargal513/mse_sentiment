"""
MSE Sentiment — Database (Supabase)
Table setup + all read/write helpers.

First-time setup: copy the SCHEMA_SQL string below into the Supabase SQL
editor and run it once to create every table, constraint and index.

    python -c "from db.supabase import SCHEMA_SQL; print(SCHEMA_SQL)"
"""

from supabase import create_client, Client
from datetime import datetime, timezone
from config.settings import SUPABASE_URL, SUPABASE_KEY

# ── Client ────────────────────────────────────────────────────────────────────
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── SQL schema (run once in Supabase SQL editor) ──────────────────────────────
# This is the single source of truth for the database. Running it on a fresh
# Supabase project produces a schema that matches exactly what the code reads and
# writes. (The historical patches in migrations/ are already folded in here.)
SCHEMA_SQL = """
-- 1. MSE companies master list
CREATE TABLE IF NOT EXISTS companies (
    ticker      TEXT PRIMARY KEY,
    name_en     TEXT,
    name_mn     TEXT,
    sector      TEXT,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Raw scraped articles
CREATE TABLE IF NOT EXISTS articles (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source       TEXT NOT NULL,          -- 'news.mn', 'openmindmse' etc.
    source_type  TEXT NOT NULL,          -- 'scraper', 'telegram', 'official_api' ...
    title        TEXT,
    content      TEXT,
    url          TEXT UNIQUE,
    language     TEXT DEFAULT 'mn',      -- 'mn' or 'en'
    raw_text     TEXT,
    published_at TIMESTAMPTZ,            -- original publish date (when known)
    scraped_at   TIMESTAMPTZ DEFAULT NOW(),
    processed    BOOLEAN DEFAULT FALSE
);

-- 3. Sentiment scores per article per company
CREATE TABLE IF NOT EXISTS sentiment_scores (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id    UUID REFERENCES articles(id) ON DELETE CASCADE,
    ticker        TEXT REFERENCES companies(ticker),
    score         FLOAT,               -- -1.0 (bearish) to 1.0 (bullish)
    label         TEXT,               -- 'positive', 'negative', 'neutral'
    summary       TEXT,               -- one sentence AI summary
    confidence    FLOAT,              -- 0.0 to 1.0
    channel       TEXT DEFAULT 'news', -- 'news' or 'social'
    scored_at     TIMESTAMPTZ DEFAULT NOW(),
    -- One score per (article, company) — lets the processor skip re-scoring
    CONSTRAINT uq_article_ticker UNIQUE (article_id, ticker)
);

-- 4. Daily aggregated sentiment per company + channel (time series)
CREATE TABLE IF NOT EXISTS sentiment_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT REFERENCES companies(ticker),
    date            DATE NOT NULL,
    channel         TEXT DEFAULT 'news', -- 'news' or 'social'
    avg_score       FLOAT,
    article_count   INTEGER,
    positive_count  INTEGER,
    negative_count  INTEGER,
    neutral_count   INTEGER,
    dominant_label  TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_history_ticker_date_channel UNIQUE (ticker, date, channel)
);

-- 5. Scrape log (track what ran and when)
CREATE TABLE IF NOT EXISTS scrape_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      TEXT NOT NULL,
    status      TEXT NOT NULL,         -- 'success', 'error'
    articles_found    INTEGER DEFAULT 0,
    articles_relevant INTEGER DEFAULT 0,
    error_msg   TEXT,
    ran_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_articles_source        ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_processed     ON articles(processed);
CREATE INDEX IF NOT EXISTS idx_articles_published_at  ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_scores_ticker          ON sentiment_scores(ticker);
CREATE INDEX IF NOT EXISTS idx_scores_scored_at       ON sentiment_scores(scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_scores_ticker_scored   ON sentiment_scores(ticker, scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_scores_channel         ON sentiment_scores(channel);
CREATE INDEX IF NOT EXISTS idx_history_ticker_date    ON sentiment_history(ticker, date);
"""


# ── Write helpers ─────────────────────────────────────────────────────────────
def save_article(source: str, source_type: str, title: str,
                 content: str, url: str = None, language: str = "mn",
                 published_at: str = None) -> str | None:
    """Save a scraped article. Returns article id or None if duplicate."""
    try:
        db = get_client()

        # Check for duplicate URL before inserting (avoids 409 spam)
        if url:
            existing = db.table("articles").select("id").eq("url", url).limit(1).execute()
            if existing.data:
                return None  # Already exists, skip silently

        row = {
            "source":      source,
            "source_type": source_type,
            "title":       title,
            "content":     content,        # full content, no truncation
            "url":         url,
            "language":    language,
            "raw_text":    content,
            "processed":   False,
        }
        if published_at:
            row["published_at"] = published_at
        result = db.table("articles").insert(row).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return None
        print(f"[DB] save_article error: {e}")
        return None


def save_sentiment(article_id: str, ticker: str, score: float,
                   label: str, summary: str, confidence: float = 0.8,
                   channel: str = "news"):
    """Save AI sentiment result for one company mention."""
    try:
        db = get_client()
        db.table("sentiment_scores").insert({
            "article_id": article_id,
            "ticker":     ticker,
            "score":      score,
            "label":      label,
            "summary":    summary,
            "confidence": confidence,
            "channel":    channel,   # 'news' or 'social'
        }).execute()
        # Mark article as processed
        db.table("articles").update({"processed": True}) \
          .eq("id", article_id).execute()
    except Exception as e:
        print(f"[DB] save_sentiment error: {e}")


def update_daily_history(ticker: str, date: str, scores: list[float], channel: str = "news"):
    """Upsert daily aggregated sentiment for a ticker + channel."""
    if not scores:
        return
    avg   = round(sum(scores) / len(scores), 4)
    pos   = sum(1 for s in scores if s > 0.2)
    neg   = sum(1 for s in scores if s < -0.2)
    neu   = len(scores) - pos - neg
    label = "positive" if avg > 0.2 else "negative" if avg < -0.2 else "neutral"
    try:
        db = get_client()
        db.table("sentiment_history").upsert({
            "ticker":         ticker,
            "date":           date,
            "channel":        channel,
            "avg_score":      avg,
            "article_count":  len(scores),
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count":  neu,
            "dominant_label": label,
            "updated_at":     datetime.now(timezone.utc).isoformat(),
        }, on_conflict="ticker,date,channel").execute()
    except Exception as e:
        print(f"[DB] update_daily_history error: {e}")


def log_scrape(source: str, status: str, found: int = 0,
               relevant: int = 0, error: str = None):
    try:
        db = get_client()
        db.table("scrape_log").insert({
            "source":             source,
            "status":             status,
            "articles_found":     found,
            "articles_relevant":  relevant,
            "error_msg":          error,
        }).execute()
    except Exception as e:
        print(f"[DB] log_scrape error: {e}")


# ── Read helpers ──────────────────────────────────────────────────────────────
def get_unprocessed_articles(limit: int = 50) -> list:
    try:
        db = get_client()
        result = db.table("articles") \
                   .select("*") \
                   .eq("processed", False) \
                   .limit(limit) \
                   .execute()
        return result.data or []
    except Exception as e:
        print(f"[DB] get_unprocessed error: {e}")
        return []


def get_sentiment_history(ticker: str, days: int = 30) -> list:
    try:
        db = get_client()
        result = db.table("sentiment_history") \
                   .select("*") \
                   .eq("ticker", ticker) \
                   .order("date", desc=True) \
                   .limit(days) \
                   .execute()
        return result.data or []
    except Exception as e:
        print(f"[DB] get_history error: {e}")
        return []


def get_company_latest_sentiment(ticker: str) -> dict | None:
    try:
        db = get_client()
        result = db.table("sentiment_history") \
                   .select("*") \
                   .eq("ticker", ticker) \
                   .order("date", desc=True) \
                   .limit(1) \
                   .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[DB] get_latest error: {e}")
        return None