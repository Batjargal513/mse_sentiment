"""
MSE Sentiment — Bulk Processor (OpenAI)
Processes backlog of unprocessed articles using GPT-4o-mini.

Run once to clear backlog:
    PYTHONPATH=. python3 bulk_processor.py
"""

import time
import json
import re
from datetime import datetime, timezone
from openai import OpenAI
from config.settings import OPENAI_API_KEY
from db.supabase import get_unprocessed_articles, save_sentiment, update_daily_history, get_client
from sentiment_processor import detect_companies, get_channel, update_todays_history

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL      = "gpt-4o-mini"
BATCH_SIZE = 50


def score_sentiment_openai(text: str, ticker: str, language: str = "mn", channel: str = "news") -> dict | None:
    lang_note    = "The text is in Mongolian (Cyrillic script). Read carefully." if language == "mn" else ""
    channel_note = (
        "Social media post from Mongolian retail investors — capture emotional tone."
        if channel == "social"
        else "Formal news or regulatory announcement — focus on financial implications."
    )

    prompt = f"""You are a financial analyst for the Mongolian Stock Exchange (MSE).
{lang_note}
{channel_note}

Analyze sentiment toward ticker {ticker}. Use the FULL score range, do NOT default to 0.7.

Text: {text[:800]}

Examples:
- Dividend announced → score: 0.8, label: positive
- Stock delisted → score: -0.6, label: negative
- Routine filing → score: 0.0, label: neutral
- Price dropping → score: -0.7, label: negative

Respond ONLY with valid JSON:
{{"score": 0.0, "label": "neutral", "summary": "max 12 words", "confidence": 0.8}}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)

        result = json.loads(raw)
        score  = max(-1.0, min(1.0, float(result.get("score", 0))))
        label  = result.get("label", "neutral")
        if label not in ("positive", "negative", "neutral"):
            label = "neutral"

        return {
            "score":      round(score, 4),
            "label":      label,
            "summary":    str(result.get("summary", ""))[:200],
            "confidence": round(float(result.get("confidence", 0.7)), 2),
        }

    except Exception as e:
        print(f"  [!] OpenAI error for {ticker}: {e}")
        return None


def process_article_bulk(article: dict) -> int:
    article_id  = article["id"]
    content     = article.get("content") or article.get("title") or ""
    title       = article.get("title") or ""
    language    = article.get("language", "mn")
    source      = article.get("source", "unknown")
    source_type = article.get("source_type", "scraper")
    channel     = get_channel(source_type)

    full_text = f"{title} {content}"
    tickers   = detect_companies(full_text)

    if not tickers:
        try:
            get_client().table("articles") \
                .update({"processed": True}) \
                .eq("id", article_id).execute()
        except Exception:
            pass
        return 0

    saved = 0
    for ticker in tickers:
        print(f"  [{channel}] {ticker} ← {source} | {title[:50]}...")
        result = score_sentiment_openai(full_text, ticker, language, channel)

        if result:
            save_sentiment(
                article_id = article_id,
                ticker     = ticker,
                score      = result["score"],
                label      = result["label"],
                summary    = result["summary"],
                confidence = result["confidence"],
                channel    = channel,
            )
            print(f"  → {ticker}: {result['label']} ({result['score']:+.2f}) [{channel}] — {result['summary']}")
            saved += 1

        time.sleep(0.3)   # be gentle with the API

    return saved


def run_bulk():
    print("\n" + "="*54)
    print(f"  Bulk Processor — OpenAI {MODEL}")
    print("="*54)

    total_articles = 0
    total_scores   = 0
    batch_num      = 0

    while True:
        articles = get_unprocessed_articles(limit=BATCH_SIZE)

        if not articles:
            print(f"\n  ✅ All articles processed!")
            print(f"  Total: {total_articles} articles, {total_scores} scores")
            break

        batch_num += 1
        print(f"\n  Batch {batch_num} — {len(articles)} articles")
        print(f"  Running total: {total_articles} processed\n")

        for article in articles:
            scores = process_article_bulk(article)
            total_scores   += scores
            total_articles += 1

        print(f"\n  Batch {batch_num} done — {total_scores} scores so far")

    print("\n  Updating daily history...")
    update_todays_history()
    print("\n  Bulk processing complete! 🎉")


if __name__ == "__main__":
    run_bulk()