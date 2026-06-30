-- ============================================================
-- FIX 5 — Supabase SQL patches
-- Run these in the Supabase SQL editor in order
-- ============================================================


-- ── 1. Add UNIQUE constraint to prevent duplicate scoring ─────────────────────
-- Run AFTER fix2_dedup_scores.py has removed existing duplicates
ALTER TABLE sentiment_scores
ADD CONSTRAINT uq_article_ticker UNIQUE (article_id, ticker);


-- ── 2. Add channel column to sentiment_history if missing ─────────────────────
-- (The schema SQL defined UNIQUE(ticker,date,channel) but may not have
--  added the column if you ran an older migration)
ALTER TABLE sentiment_history
ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT 'news';

-- Update the UNIQUE constraint to include channel
ALTER TABLE sentiment_history
DROP CONSTRAINT IF EXISTS sentiment_history_ticker_date_key;

ALTER TABLE sentiment_history
ADD CONSTRAINT uq_history_ticker_date_channel UNIQUE (ticker, date, channel);


-- ── 3. Missing indexes for query performance ──────────────────────────────────
-- These are used by /alerts and /articles endpoints
CREATE INDEX IF NOT EXISTS idx_scores_scored_at
ON sentiment_scores(scored_at DESC);

CREATE INDEX IF NOT EXISTS idx_scores_ticker_scored_at
ON sentiment_scores(ticker, scored_at DESC);

CREATE INDEX IF NOT EXISTS idx_scores_channel
ON sentiment_scores(channel);

CREATE INDEX IF NOT EXISTS idx_articles_published_at
ON articles(published_at DESC);


-- ── 4. Add published_at column to articles if missing ────────────────────────
ALTER TABLE articles
ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;


-- ── 5. Quick data health check — run after all fixes ─────────────────────────
-- Check score distribution
SELECT
    ticker,
    COUNT(*) as total,
    ROUND(AVG(score)::numeric, 3) as avg_score,
    SUM(CASE WHEN score = 0.0 THEN 1 ELSE 0 END) as zero_count,
    ROUND(100.0 * SUM(CASE WHEN score = 0.0 THEN 1 ELSE 0 END) / COUNT(*), 1) as pct_zero
FROM sentiment_scores
GROUP BY ticker
ORDER BY total DESC;

-- Check history vs actual score counts
SELECT
    h.ticker,
    h.date,
    h.channel,
    h.article_count as history_count,
    COUNT(s.id) as actual_count,
    h.article_count - COUNT(s.id) as drift
FROM sentiment_history h
LEFT JOIN sentiment_scores s
    ON s.ticker = h.ticker
    AND s.channel = h.channel
    AND DATE(s.articles.published_at) = h.date
GROUP BY h.ticker, h.date, h.channel, h.article_count
HAVING ABS(h.article_count - COUNT(s.id)) > 0
ORDER BY ABS(h.article_count - COUNT(s.id)) DESC
LIMIT 20;
