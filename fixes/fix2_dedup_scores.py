"""
FIX 2 — Remove Duplicate Scores
=================================
Problem : 593 article+ticker combinations have 2 score rows.
          Caused by bulk_processor re-running over already-scored articles.
          Daily averages are inflated — every duplicate counts twice.

What this does:
  1. Finds all (article_id, ticker) pairs with > 1 score row
  2. Keeps the LATEST scored_at, deletes the earlier duplicate
  3. Adds a note about the UNIQUE constraint to add in Supabase

Run: PYTHONPATH=. python3 fixes/fix2_dedup_scores.py
"""

from db.supabase import get_client


def run():
    db = get_client()
    print("=" * 54)
    print("  Fix 2 — Remove Duplicate Scores")
    print("=" * 54)

    # Step 1: Fetch all score rows (id, article_id, ticker, scored_at)
    print("\n  Fetching all sentiment_scores...")
    result = db.table("sentiment_scores") \
               .select("id, article_id, ticker, scored_at") \
               .execute()

    rows = result.data or []
    print(f"  Total rows: {len(rows)}")

    # Step 2: Find duplicates — group by (article_id, ticker), keep latest
    from collections import defaultdict
    groups = defaultdict(list)
    for row in rows:
        key = (row["article_id"], row["ticker"])
        groups[key].append(row)

    ids_to_delete = []
    for key, group_rows in groups.items():
        if len(group_rows) > 1:
            # Sort by scored_at descending — keep first (latest), delete rest
            sorted_rows = sorted(group_rows, key=lambda r: r["scored_at"], reverse=True)
            for duplicate in sorted_rows[1:]:
                ids_to_delete.append(duplicate["id"])

    print(f"  Duplicate score rows to delete: {len(ids_to_delete)}")

    if not ids_to_delete:
        print("  No duplicates found.")
        return

    confirm = input(f"\n  Delete {len(ids_to_delete)} duplicate score rows? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("  Aborted.")
        return

    # Step 3: Delete in batches
    deleted = 0
    batch_size = 100
    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i:i + batch_size]
        db.table("sentiment_scores").delete().in_("id", batch).execute()
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(ids_to_delete)}...")

    print(f"\n  ✅ Removed {deleted} duplicate rows")

    print("""
  ── PREVENT RECURRENCE ───────────────────────────────────
  Run this SQL in Supabase SQL editor to add a unique constraint:

    ALTER TABLE sentiment_scores
    ADD CONSTRAINT uq_article_ticker UNIQUE (article_id, ticker);

  This will block future duplicates at the DB level.
  ─────────────────────────────────────────────────────────
    """)


if __name__ == "__main__":
    run()
