"""
MSE Sentiment — Company Intelligence
Builds the full intelligence profile for one MSE company.
Used by the frontend company pages (APU, SEND etc.)
Also generates a daily AI summary using Groq.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from groq import Groq
from config.settings import GROQ_API_KEY
from db.supabase import get_client, get_sentiment_history

groq_client = Groq(api_key=GROQ_API_KEY)


# ── Build full company intelligence profile ───────────────────────────────────
def get_company_intelligence(ticker: str) -> dict:
    """
    Returns everything needed for a company intelligence page:
    - Current sentiment score + trend
    - 30-day sentiment history
    - Recent articles with scores
    - AI-generated summary (Groq)
    - Sentiment shift alerts
    """
    ticker = ticker.upper()
    db     = get_client()
    today  = datetime.now(timezone.utc).date().isoformat()

    # ── 1. Company info ───────────────────────────────────────────────────────
    company_result = db.table("companies") \
                       .select("*") \
                       .eq("ticker", ticker) \
                       .execute()
    company = company_result.data[0] if company_result.data else {
        "ticker": ticker, "name_en": ticker, "name_mn": ticker, "sector": "Unknown"
    }

    # ── 2. Latest sentiment ───────────────────────────────────────────────────
    history = get_sentiment_history(ticker, days=30)
    latest  = history[0] if history else None

    current_score = latest["avg_score"]   if latest else 0.0
    current_label = latest["dominant_label"] if latest else "neutral"

    # ── 3. Trend — compare last 7 days vs previous 7 days ────────────────────
    trend_direction = "stable"
    if len(history) >= 14:
        recent_avg = sum(h["avg_score"] for h in history[:7])  / 7
        older_avg  = sum(h["avg_score"] for h in history[7:14]) / 7
        diff = recent_avg - older_avg
        if diff > 0.15:
            trend_direction = "improving"
        elif diff < -0.15:
            trend_direction = "declining"

    # ── 4. Recent articles ────────────────────────────────────────────────────
    articles_result = db.table("sentiment_scores") \
                        .select("score, label, summary, scored_at, articles(title, source, url, language)") \
                        .eq("ticker", ticker) \
                        .order("scored_at", desc=True) \
                        .limit(10) \
                        .execute()

    articles = []
    for row in articles_result.data or []:
        art = row.get("articles") or {}
        articles.append({
            "title":     art.get("title", ""),
            "source":    art.get("source", ""),
            "url":       art.get("url", ""),
            "language":  art.get("language", "mn"),
            "score":     row["score"],
            "label":     row["label"],
            "summary":   row["summary"],
            "scored_at": row["scored_at"],
        })

    # ── 5. Sentiment breakdown (last 30 days) ─────────────────────────────────
    total_articles = sum(h["article_count"] for h in history)
    total_positive = sum(h["positive_count"] for h in history)
    total_negative = sum(h["negative_count"] for h in history)
    total_neutral  = sum(h["neutral_count"]  for h in history)

    # ── 6. Recent alerts (big score shifts) ───────────────────────────────────
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    alerts_result = db.table("sentiment_scores") \
                      .select("score, label, summary, scored_at") \
                      .eq("ticker", ticker) \
                      .or_("score.gte.0.7,score.lte.-0.7") \
                      .gte("scored_at", cutoff) \
                      .order("scored_at", desc=True) \
                      .limit(5) \
                      .execute()

    # ── 7. AI summary (Groq — generated once, cached) ────────────────────────
    ai_summary = generate_company_summary(
        ticker    = ticker,
        name      = company.get("name_en", ticker),
        score     = current_score,
        label     = current_label,
        trend     = trend_direction,
        articles  = articles[:5],
        history   = history[:7],
    )

    return {
        "ticker":   ticker,
        "company":  company,
        "sentiment": {
            "current_score": round(current_score, 4),
            "current_label": current_label,
            "trend":         trend_direction,
            "as_of":         today,
        },
        "history":     history,
        "articles":    articles,
        "breakdown": {
            "total_articles": total_articles,
            "positive":       total_positive,
            "negative":       total_negative,
            "neutral":        total_neutral,
        },
        "alerts":      alerts_result.data or [],
        "ai_summary":  ai_summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── AI summary generation ─────────────────────────────────────────────────────
def generate_company_summary(ticker: str, name: str, score: float,
                              label: str, trend: str,
                              articles: list, history: list) -> str:
    """
    Generate a 3-sentence English summary of the company's sentiment situation.
    Uses Groq — cheap model, short output.
    """
    if not articles and not history:
        return f"No recent news coverage found for {ticker}."

    # Build context from recent articles
    headlines = "\n".join(
        f"- {a['title']} ({a['label']}, score: {a['score']:+.2f})"
        for a in articles[:5] if a.get("title")
    )

    avg_7d = round(
        sum(h["avg_score"] for h in history[:7]) / len(history[:7]), 2
    ) if history else 0.0

    prompt = f"""You are a financial analyst writing a brief for {name} ({ticker}) stock.

Current sentiment: {label} (score: {score:+.2f})
7-day trend: {trend}
7-day average score: {avg_7d:+.2f}

Recent headlines:
{headlines or 'No recent headlines'}

Write exactly 3 sentences in English:
1. Current sentiment and what is driving it
2. The trend direction over the past week
3. What investors should watch for

Keep it factual, neutral tone, max 20 words per sentence."""

    try:
        response = groq_client.chat.completions.create(
            model    = "llama3-8b-8192",
            messages = [{"role": "user", "content": prompt}],
            max_tokens  = 150,
            temperature = 0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [!] Summary generation error for {ticker}: {e}")
        return f"{name} ({ticker}) currently shows {label} market sentiment."


# ── Seed companies table ──────────────────────────────────────────────────────
def seed_companies():
    """
    Populate the companies table with MSE Tier 1 stocks.
    Run once after creating the schema.
    """
    companies = [
        {"ticker": "APU",  "name_en": "APU JSC",             "name_mn": "АПУ ХК",           "sector": "Consumer"},
        {"ticker": "SEND", "name_en": "Sendly LLC",           "name_mn": "Сэндли ХХК",        "sector": "Technology"},
        {"ticker": "TDB",  "name_en": "Trade & Development Bank", "name_mn": "ХХБ",         "sector": "Finance"},
        {"ticker": "XAC",  "name_en": "XacBank",              "name_mn": "ХасБанк",          "sector": "Finance"},
        {"ticker": "MIK",  "name_en": "MIK Holdings",         "name_mn": "МИК",              "sector": "Finance"},
        {"ticker": "BDS",  "name_en": "BDSec JSC",            "name_mn": "БДСек",            "sector": "Finance"},
        {"ticker": "GLMT", "name_en": "Golomt Bank",          "name_mn": "Голомт Банк",      "sector": "Finance"},
        {"ticker": "SUU",  "name_en": "Suu JSC",              "name_mn": "Сүү ХК",           "sector": "Consumer"},
        {"ticker": "GOV",  "name_en": "Gobi JSC",             "name_mn": "Говь ХК",          "sector": "Consumer"},
        {"ticker": "INV",  "name_en": "Invescore NBFI",       "name_mn": "Инвескор ББСБ",    "sector": "Finance"},
        {"ticker": "MBW",  "name_en": "Mongol Bicheelt Urguu","name_mn": "Монгол Бичил",     "sector": "Real Estate"},
        {"ticker": "MFC",  "name_en": "Mongolian Finance Corp","name_mn": "МФК",             "sector": "Finance"},
        {"ticker": "MLG",  "name_en": "Mongolian Alt",        "name_mn": "Монголын Алт",     "sector": "Mining"},
        {"ticker": "NEH",  "name_en": "Nekhii JSC",           "name_mn": "Нэхий ХК",        "sector": "Consumer"},
        {"ticker": "SBM",  "name_en": "SBM",                  "name_mn": "СБМ",              "sector": "Finance"},
        {"ticker": "TTL",  "name_en": "TTL JSC",              "name_mn": "ТТЛ ХК",           "sector": "Consumer"},
        {"ticker": "TUM",  "name_en": "Tumen JSC",            "name_mn": "Тумэн ХК",        "sector": "Consumer"},
        {"ticker": "LEND", "name_en": "LendMN",               "name_mn": "Лендмн",           "sector": "Fintech"},
        {"ticker": "AARD", "name_en": "Ard Financial Group",  "name_mn": "Ард Санхүүгийн Групп", "sector": "Finance"},
    ]

    db = get_client()
    for company in companies:
        try:
            db.table("companies").upsert(company, on_conflict="ticker").execute()
            print(f"  ✓ {company['ticker']} — {company['name_en']}")
        except Exception as e:
            print(f"  [!] Error seeding {company['ticker']}: {e}")

    print(f"\n  Seeded {len(companies)} companies.")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "seed":
            print("Seeding companies table...")
            seed_companies()
        else:
            ticker = sys.argv[1].upper()
            print(f"\nBuilding intelligence for {ticker}...\n")
            data = get_company_intelligence(ticker)
            print(f"Company  : {data['company'].get('name_en')}")
            print(f"Sentiment: {data['sentiment']['current_label']} ({data['sentiment']['current_score']:+.4f})")
            print(f"Trend    : {data['sentiment']['trend']}")
            print(f"Articles : {data['breakdown']['total_articles']} in last 30 days")
            print(f"\nAI Summary:\n{data['ai_summary']}")
    else:
        print("Usage:")
        print("  python company_intelligence.py APU    — get APU intelligence")
        print("  python company_intelligence.py seed   — seed companies table")
