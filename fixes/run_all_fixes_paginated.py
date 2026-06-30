"""
MSE Sentiment — Full Fix (Paginated)
======================================
Same as run_all_fixes.py but fetches ALL rows from Supabase
using pagination (1000 rows per page).

Run from project root:
  PYTHONPATH=. python3 fixes/run_all_fixes_paginated.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.supabase import get_client
from datetime import datetime, timezone, timedelta
from collections import defaultdict


# ── Pagination helper ─────────────────────────────────────────────────────────
def fetch_all(db, table, select, filters=None, order_col="id"):
    """Fetch every row from a table using keyset pagination."""
    all_rows = []
    last_id  = None
    page     = 0

    while True:
        q = db.table(table).select(select)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        if last_id:
            q = q.gt(order_col, last_id)
        q = q.order(order_col).limit(1000)

        result = q.execute()
        batch  = result.data or []
        if not batch:
            break

        all_rows.extend(batch)
        last_id = batch[-1][order_col]
        page   += 1
        print(f"    ...page {page}: {len(all_rows)} rows loaded", end="\r")

        if len(batch) < 1000:
            break

    print(f"    Loaded {len(all_rows)} total rows{' ' * 20}")
    return all_rows


# ── AARD keywords ─────────────────────────────────────────────────────────────
AARD_REAL_KEYWORDS = [
    "AARD", "Ард кредит", "Ард даатгал",
    "Ард Санхүүгийн Групп", "Ард Санхүү",
    "Ard Credit", "Ard Financial", "Ard Daatgal",
]

def is_real_aard(title, content):
    text = f"{title or ''} {content or ''}".lower()
    return any(kw.lower() in text for kw in AARD_REAL_KEYWORDS)


# ── Fix 1 ─────────────────────────────────────────────────────────────────────
def fix1_aard(db):
    print("\n── FIX 1: AARD False Positives ──────────────────────────")

    print("  Fetching ALL AARD score rows (paginated)...")
    rows = fetch_all(db, "sentiment_scores",
                     "id, article_id, articles(title, content)",
                     filters={"ticker": "AARD"})
    print(f"  Total AARD rows found: {len(rows)}")

    false_ids = []
    real_ids  = []
    for row in rows:
        art = row.get("articles") or {}
        if is_real_aard(art.get("title",""), art.get("content","")):
            real_ids.append(row["id"])
        else:
            false_ids.append(row["id"])

    print(f"  Real AARD scores to keep : {len(real_ids)}")
    print(f"  False positives to delete: {len(false_ids)}")

    if not false_ids:
        print("  Nothing to delete.")
        return

    confirm = input(f"\n  Delete {len(false_ids)} false AARD rows? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("  Skipped.")
        return

    deleted = 0
    for i in range(0, len(false_ids), 100):
        batch = false_ids[i:i+100]
        db.table("sentiment_scores").delete().in_("id", batch).execute()
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(false_ids)}...", end="\r")

    print(f"\n  ✅ Deleted {deleted} false AARD rows")
    db.table("sentiment_history").delete().eq("ticker", "AARD").execute()
    print("  ✅ AARD history cleared")


# ── Fix 2 ─────────────────────────────────────────────────────────────────────
def fix2_dedup(db):
    print("\n── FIX 2: Duplicate Scores ──────────────────────────────")

    print("  Fetching ALL score rows (paginated)...")
    rows = fetch_all(db, "sentiment_scores", "id, article_id, ticker, scored_at")
    print(f"  Total rows: {len(rows)}")

    groups = defaultdict(list)
    for row in rows:
        groups[(row["article_id"], row["ticker"])].append(row)

    ids_to_delete = []
    for (aid, ticker), group_rows in groups.items():
        if len(group_rows) > 1:
            sorted_rows = sorted(group_rows, key=lambda r: r["scored_at"], reverse=True)
            for dup in sorted_rows[1:]:
                ids_to_delete.append(dup["id"])

    print(f"  Duplicate rows to delete: {len(ids_to_delete)}")

    if not ids_to_delete:
        print("  No duplicates found.")
        return

    confirm = input(f"\n  Delete {len(ids_to_delete)} duplicates? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("  Skipped.")
        return

    deleted = 0
    for i in range(0, len(ids_to_delete), 100):
        batch = ids_to_delete[i:i+100]
        db.table("sentiment_scores").delete().in_("id", batch).execute()
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(ids_to_delete)}...", end="\r")

    print(f"\n  ✅ Removed {deleted} duplicate rows")


# ── Fix 3 ─────────────────────────────────────────────────────────────────────
def fix3_rebuild_history(db):
    print("\n── FIX 3: Rebuild History ───────────────────────────────")

    print("  Fetching ALL scores + article dates (paginated)...")
    rows = fetch_all(db, "sentiment_scores",
                     "id, ticker, score, channel, article_id, articles(published_at, scraped_at)")
    print(f"  Score rows loaded: {len(rows)}")

    by_key = defaultdict(list)
    skipped = 0
    for row in rows:
        art      = row.get("articles") or {}
        raw_date = art.get("published_at") or art.get("scraped_at")
        if raw_date:
            date = raw_date[:10]
        else:
            skipped += 1
            date = datetime.now(timezone.utc).date().isoformat()
        key = (row["ticker"], row.get("channel", "news"), date)
        by_key[key].append(row["score"])

    print(f"  Unique (ticker, channel, date) groups: {len(by_key)}")
    if skipped:
        print(f"  Rows with no date (fallback to today): {skipped}")

    def make_row(ticker, channel, date, scores):
        avg   = round(sum(scores) / len(scores), 4)
        pos   = sum(1 for s in scores if s > 0.2)
        neg   = sum(1 for s in scores if s < -0.2)
        neu   = len(scores) - pos - neg
        label = "positive" if avg > 0.2 else "negative" if avg < -0.2 else "neutral"
        return {
            "ticker": ticker, "date": date, "channel": channel,
            "avg_score": avg, "article_count": len(scores),
            "positive_count": pos, "negative_count": neg,
            "neutral_count": neu, "dominant_label": label,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    payload = [make_row(t, c, d, s) for (t, c, d), s in by_key.items()]

    confirm = input(f"\n  Truncate history and write {len(payload)} rows? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("  Skipped.")
        return

    print("  Clearing old history...")
    db.table("sentiment_history").delete().neq("ticker", "___never___").execute()
    print("  ✅ Cleared")

    inserted = 0
    for i in range(0, len(payload), 200):
        batch = payload[i:i+200]
        db.table("sentiment_history").insert(batch).execute()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(payload)}...", end="\r")

    print(f"\n  ✅ Rebuilt {inserted} history rows")

    # Spot check
    check = db.table("sentiment_history") \
              .select("ticker, date, channel, avg_score, article_count") \
              .eq("ticker", "SUU").order("date", desc=True).limit(3).execute()
    print("\n  Spot check — SUU:")
    for r in check.data or []:
        print(f"    {r['date']} [{r['channel']}] avg={r['avg_score']:+.3f} count={r['article_count']}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print("\n" + "=" * 60)
    print("  MSE Sentiment — Full Accuracy Fix (Paginated)")
    print("=" * 60)
    print("""
  Fetches ALL rows (not just first 1000).
  Previous run deleted 898 AARD rows + 54 duplicates.
  This run will catch the remaining ones.
    """)

    go = input("  Start? (yes/no): ")
    if go.strip().lower() != "yes":
        print("  Aborted.")
        return

    db = get_client()

    only3 = input("  Fix 1 & 2 already ran — skip to Fix 3 only? (yes/no): ")
    if only3.strip().lower() == "yes":
        fix3_rebuild_history(db)
    else:
        fix1_aard(db)
        fix2_dedup(db)
        fix3_rebuild_history(db)

    print("\n\n" + "=" * 60)
    print("  ✅ All fixes complete!")
    print("=" * 60)
    print("""
  Remaining steps:
    4. cp fixes/fix4_patched_sentiment_processor.py sentiment_processor.py
    5. Run fixes/fix5_supabase_sql.sql in Supabase SQL editor
    """)

if __name__ == "__main__":
    run()
