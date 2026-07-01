"""
FIX 3 — Rebuild sentiment_history from Scratch
================================================
Problem : Every one of 707 history rows has wrong article_count.
          Worst case: SUU social shows 1 article but has 1,085 actual scores.
          Trend charts and breakdowns are showing fabricated numbers.

What this does:
  1. Reads all sentiment_scores (after fixes 1 & 2)
  2. Joins to articles to get the correct published_at date
  3. Groups by (ticker, date, channel) and recomputes all aggregates
  4. Truncates sentiment_history and re-inserts clean rows

Run AFTER fix1 and fix2:
  PYTHONPATH=. python3 fixes/fix3_rebuild_history.py
"""

from collections import defaultdict
from datetime import datetime, timezone
from db.supabase import get_client


def run():
    db = get_client()
    print("=" * 54)
    print("  Fix 3 — Rebuild sentiment_history")
    print("=" * 54)

    # Step 1: Fetch all scores with article dates
    print("\n  Fetching all scores + article dates...")
    result = db.table("sentiment_scores") \
               .select("ticker, score, channel, article_id, articles(published_at, scraped_at)") \
               .execute()

    rows = result.data or []
    print(f"  Score rows loaded: {len(rows)}")

    # Step 2: Group by (ticker, date, channel)
    by_key: dict[tuple, list[float]] = defaultdict(list)

    skipped = 0
    for row in rows:
        art      = row.get("articles") or {}
        raw_date = art.get("published_at") or art.get("scraped_at")

        if raw_date:
            try:
                date = raw_date[:10]  # "2026-03-15T..." → "2026-03-15"
            except Exception:
                date = datetime.now(timezone.utc).date().isoformat()
        else:
            skipped += 1
            date = datetime.now(timezone.utc).date().isoformat()

        key = (row["ticker"], row.get("channel", "news"), date)
        by_key[key].append(row["score"])

    print(f"  Unique (ticker, channel, date) groups: {len(by_key)}")
    print(f"  Rows with no date (fallback to today): {skipped}")

    # Step 3: Build upsert payload
    def compute_row(ticker, channel, date, scores):
        avg   = round(sum(scores) / len(scores), 4)
        pos   = sum(1 for s in scores if s > 0.2)
        neg   = sum(1 for s in scores if s < -0.2)
        neu   = len(scores) - pos - neg
        label = "positive" if avg > 0.2 else "negative" if avg < -0.2 else "neutral"
        return {
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
        }

    payload = [
        compute_row(ticker, channel, date, scores)
        for (ticker, channel, date), scores in by_key.items()
    ]

    print(f"\n  Rows to write: {len(payload)}")

    confirm = input("\n  Truncate sentiment_history and rebuild? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("  Aborted.")
        return

    # Step 4: Truncate existing history
    print("\n  Clearing old history...")
    # Delete all rows (Supabase doesn't expose TRUNCATE via client)
    db.table("sentiment_history").delete().neq("ticker", "___never___").execute()
    print("  ✅ Old history cleared")

    # Step 5: Insert in batches of 200
    inserted = 0
    batch_size = 200
    for i in range(0, len(payload), batch_size):
        batch = payload[i:i + batch_size]
        db.table("sentiment_history").insert(batch).execute()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(payload)}...")

    print(f"\n  ✅ Rebuilt {inserted} history rows")

    # Step 6: Spot check
    check = db.table("sentiment_history") \
              .select("ticker, date, channel, avg_score, article_count") \
              .eq("ticker", "SUU") \
              .order("date", desc=True) \
              .limit(5) \
              .execute()

    print("\n  Spot check — SUU history (latest 5):")
    for row in check.data or []:
        print(f"    {row['date']} [{row['channel']}] avg={row['avg_score']:+.3f} count={row['article_count']}")

    print("\n  Done. history is now consistent with sentiment_scores.")


if __name__ == "__main__":
    run()
