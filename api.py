"""
MSE Sentiment — REST API
FastAPI endpoints exposing sentiment data to clients.

Endpoints:
  GET /companies                    — list all tracked companies
  GET /sentiment/{ticker}           — latest sentiment for one company
  GET /sentiment/{ticker}/history   — sentiment trend (last N days)
  GET /market/overview              — market-wide sentiment summary
  GET /articles/{ticker}            — recent articles mentioning ticker
  GET /alerts                       — recent big sentiment shifts

Run: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone, timedelta
from db.supabase import get_client

app = FastAPI(
    title       = "MSE Sentiment API",
    description = "Mongolia Stock Exchange sentiment intelligence",
    version     = "1.0.0",
)

# Allow NovaNews frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["GET"],
    allow_headers  = ["*"],
)


# ── Helper ────────────────────────────────────────────────────────────────────
def label_to_emoji(label: str) -> str:
    return {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(label, "➡️")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name":    "MSE Sentiment API",
        "version": "1.0.0",
        "docs":    "/docs",
    }


@app.get("/companies")
def list_companies():
    """List all tracked MSE companies."""
    try:
        db = get_client()
        result = db.table("companies") \
                   .select("ticker, name_en, name_mn, sector") \
                   .eq("active", True) \
                   .order("ticker") \
                   .execute()
        return {"companies": result.data, "count": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sentiment/{ticker}")
def get_sentiment(ticker: str):
    """Latest sentiment score for one company."""
    ticker = ticker.upper()
    try:
        db = get_client()

        # Latest daily history
        history = db.table("sentiment_history") \
                    .select("*") \
                    .eq("ticker", ticker) \
                    .order("date", desc=True) \
                    .limit(2) \
                    .execute()

        if not history.data:
            raise HTTPException(status_code=404, detail=f"No sentiment data for {ticker}")

        latest = history.data[0]
        prev   = history.data[1] if len(history.data) > 1 else None

        # Trend direction — guard against None avg_score
        trend = "stable"
        if prev:
            try:
                latest_score = float(latest.get("avg_score") or 0)
                prev_score   = float(prev.get("avg_score") or 0)
                diff = latest_score - prev_score
                if diff > 0.1:
                    trend = "improving"
                elif diff < -0.1:
                    trend = "declining"
            except (TypeError, ValueError):
                trend = "stable"

        # Article count from last 30 days of history (more meaningful than all-time)
        from datetime import timedelta
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        recent_history = db.table("sentiment_history") \
                           .select("article_count") \
                           .eq("ticker", ticker) \
                           .gte("date", thirty_days_ago) \
                           .execute()
        recent_count = sum(r.get("article_count") or 0 for r in recent_history.data or [])

        score = float(latest.get("avg_score") or 0)
        label = latest.get("dominant_label") or "neutral"
        return {
            "ticker":          ticker,
            "date":            latest.get("date", ""),
            "score":           score,
            "label":           label,
            "emoji":           label_to_emoji(label),
            "trend":           trend,
            "article_count":   recent_count,
            "unscored_count":  0,
            "total_articles":  recent_count,
            "breakdown": {
                "positive": int(latest.get("positive_count") or 0),
                "negative": int(latest.get("negative_count") or 0),
                "neutral":  int(latest.get("neutral_count") or 0),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sentiment/{ticker}/history")
def get_sentiment_history(
    ticker: str,
    days: int = Query(default=30, ge=1, le=90)
):
    """Sentiment trend over time for one company."""
    ticker = ticker.upper()
    try:
        db = get_client()
        # Get latest N days (desc), then reverse so chart goes left→right
        # Multiply limit by 2 — each date has both a news and social row
        result = db.table("sentiment_history") \
                   .select("date, avg_score, dominant_label, article_count, channel, positive_count, negative_count, neutral_count") \
                   .eq("ticker", ticker) \
                   .order("date", desc=True) \
                   .limit(days * 2) \
                   .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"No history for {ticker}")
        
        # Reverse to chronological order for chart
        result.data.reverse()

        return {
            "ticker":  ticker,
            "days":    days,
            "history": result.data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market/overview")
def market_overview():
    """Market-wide sentiment summary for today."""
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        db = get_client()
        result = db.table("sentiment_history") \
                   .select("ticker, avg_score, dominant_label, article_count") \
                   .eq("date", today) \
                   .order("avg_score", desc=True) \
                   .execute()

        data = result.data or []

        if not data:
            return {"date": today, "message": "No data yet for today"}

        scores   = [r["avg_score"] for r in data]
        avg      = round(sum(scores) / len(scores), 4)
        positive = sum(1 for r in data if r["dominant_label"] == "positive")
        negative = sum(1 for r in data if r["dominant_label"] == "negative")
        neutral  = len(data) - positive - negative

        market_label = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "neutral"

        return {
            "date":           today,
            "market_score":   avg,
            "market_label":   market_label,
            "market_emoji":   label_to_emoji(market_label),
            "companies_tracked": len(data),
            "breakdown": {
                "positive": positive,
                "negative": negative,
                "neutral":  neutral,
            },
            "top_bullish":  [r for r in data if r["dominant_label"] == "positive"][:3],
            "top_bearish":  sorted(data, key=lambda x: x["avg_score"])[:3],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/articles/{ticker}")
def get_articles(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100)
):
    """Recent articles mentioning a company with their sentiment."""
    ticker = ticker.upper()
    try:
        db = get_client()

        # Single join query: get sentiment scores joined to articles in one call
        # Limit to recent scored articles only — avoids the .in_() URL-length bug
        scores_result = db.table("sentiment_scores") \
                          .select("score, label, summary, scored_at, channel, articles(id, title, source, url, language, published_at, scraped_at)") \
                          .eq("ticker", ticker) \
                          .order("scored_at", desc=True) \
                          .limit(limit) \
                          .execute()

        articles = []
        seen_ids = set()

        for row in scores_result.data or []:
            art = row.get("articles") or {}
            aid = str(art.get("id", ""))
            if not aid or aid in seen_ids:
                continue
            seen_ids.add(aid)
            label = row.get("label") or "neutral"
            pub_date = art.get("published_at") or art.get("scraped_at") or row.get("scored_at")
            articles.append({
                "title":        art.get("title", ""),
                "source":       art.get("source", ""),
                "url":          art.get("url", ""),
                "language":     art.get("language", "mn"),
                "score":        row.get("score"),
                "label":        label,
                "emoji":        label_to_emoji(label),
                "summary":      row.get("summary", ""),
                "published_at": pub_date,
                "channel":      row.get("channel", "news"),
                "scored":       True,
            })

        scored_count = len(articles)

        if not articles:
            raise HTTPException(status_code=404, detail=f"No articles for {ticker}")

        articles.sort(key=lambda x: x.get("published_at") or "", reverse=True)

        return {
            "ticker":         ticker,
            "articles":       articles,
            "count":          len(articles),
            "scored_count":   scored_count,
            "unscored_count": 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts")
def get_alerts(hours: int = Query(default=48, ge=1, le=168)):
    """Recent significant sentiment shifts worth alerting on."""
    try:
        db     = get_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # Fetch recent scores and filter by magnitude in Python
        # (avoids supabase-py .or_() issues with negative numbers)
        result = db.table("sentiment_scores") \
                   .select("ticker, score, label, summary, scored_at, articles(title, source, published_at, scraped_at)") \
                   .gte("scored_at", cutoff) \
                   .order("scored_at", desc=True) \
                   .limit(200) \
                   .execute()

        alerts = []
        for row in [r for r in (result.data or []) if abs(r.get("score") or 0) >= 0.4]:
            article = row.get("articles") or {}
            pub_date = article.get("published_at") or article.get("scraped_at") or row.get("scored_at")
            alerts.append({
                "ticker":     row["ticker"],
                "score":      row["score"],
                "label":      row["label"],
                "summary":    row["summary"],
                "source":     article.get("source", ""),
                "title":      article.get("title", ""),
                "scored_at":  row["scored_at"],
                "published_at": pub_date,
            })

        return {
            "hours":  hours,
            "alerts": alerts,
            "count":  len(alerts),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))