"""
MSE Sentiment — Bulk Processor
Processes the backlog of unprocessed articles using the shared Claude scorer.

Run once to clear backlog:
    PYTHONPATH=. python3 bulk_processor.py
"""

import time
from db.supabase import get_unprocessed_articles, save_sentiment, update_daily_history, get_client
from sentiment_processor import (
    detect_companies, get_channel, update_recent_history, score_sentiment, MODEL
)

BATCH_SIZE = 50


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
        result = score_sentiment(full_text, ticker, language, channel)

        if result:
            # Same quality gate as the live processor: drop very low-confidence
            # scores (article barely mentions the ticker) so they don't pollute.
            if result["confidence"] < 0.3:
                print(f"  [skip] {ticker}: confidence too low ({result['confidence']})")
            else:
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

    # Safety: always mark processed so a scoring failure can't make the batch
    # loop re-scan (and re-charge) this article forever.
    try:
        get_client().table("articles") \
            .update({"processed": True}) \
            .eq("id", article_id).execute()
    except Exception:
        pass
    return saved


def run_bulk():
    print("\n" + "="*54)
    print(f"  Bulk Processor — {MODEL}")
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
    # Backlog can span many days — rebuild a wide window so every affected
    # ticker/date/channel bucket gets recomputed, not just the last 2 days.
    update_recent_history(days_back=365)
    print("\n  Bulk processing complete! 🎉")


if __name__ == "__main__":
    run_bulk()