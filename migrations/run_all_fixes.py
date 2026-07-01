#!/usr/bin/env python3
"""
MSE Sentiment — Run All Fixes in Order
=======================================
Run this from your project root:

  PYTHONPATH=. python3 migrations/run_all_fixes.py

Order:
  1. Fix AARD false positives     (~1,799 rows deleted)
  2. Remove duplicate scores      (~593 rows deleted)
  3. Rebuild sentiment_history    (707 rows rebuilt correctly)

After this script:
  4. Copy fix4_patched_sentiment_processor.py → sentiment_processor.py
  5. Run fix5_supabase_sql.sql in Supabase SQL editor
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run():
    print("\n" + "=" * 60)
    print("  MSE Sentiment — Full Accuracy Fix")
    print("=" * 60)
    print("""
  This will:
    Fix 1 — Delete ~1,799 false-positive AARD score rows
    Fix 2 — Delete ~593 duplicate score rows
    Fix 3 — Rebuild all 707 history rows correctly

  Prerequisites:
    • .env file with SUPABASE_URL and SUPABASE_KEY
    • PYTHONPATH=. (run from project root)

  Estimated time: 3–5 minutes (Supabase API rate limits)
    """)

    go = input("  Start? (yes/no): ")
    if go.strip().lower() != "yes":
        print("  Aborted.")
        return

    print("\n\n── FIX 1: AARD False Positives ──────────────────────────")
    from migrations.fix1_aard_false_positives import run as fix1
    fix1()

    print("\n\n── FIX 2: Duplicate Scores ──────────────────────────────")
    from migrations.fix2_dedup_scores import run as fix2
    fix2()

    print("\n\n── FIX 3: Rebuild History ───────────────────────────────")
    from migrations.fix3_rebuild_history import run as fix3
    fix3()

    print("\n\n" + "=" * 60)
    print("  ✅ Data fixes complete!")
    print("=" * 60)
    print("""
  Next steps:
  ─────────────────────────────────────────────────────────
  4. Replace your processor:
       cp fixes/fix4_patched_sentiment_processor.py sentiment_processor.py

  5. Run SQL in Supabase SQL editor:
       fixes/fix5_supabase_sql.sql
       (adds UNIQUE constraint, indexes, channel column)

  6. Verify in Supabase:
       SELECT ticker, COUNT(*) as scores,
              ROUND(AVG(score)::numeric,3) as avg_score
       FROM sentiment_scores
       GROUP BY ticker ORDER BY scores DESC;

  Expected after fixes:
    • AARD drops from ~1920 to ~120 scores
    • No duplicate (article_id, ticker) pairs
    • history article_count matches actual score rows
    • Score distribution shows values between -0.4 and -0.2
  ─────────────────────────────────────────────────────────
    """)

if __name__ == "__main__":
    run()
