# Migrations & one-off fixes (historical)

These scripts were used to patch the database and clean up data **after** the
initial build. They have **already been applied** to the live Supabase project
and are kept here only for history and reproducibility. You do **not** need to
run any of them to set up a fresh project — the canonical schema in
[`db/supabase.py`](../db/supabase.py) (`SCHEMA_SQL`) already includes every
change made here.

| File | What it did |
|---|---|
| `fix1_aard_false_positives.py` | Removed bogus AARD/GOV/SUU scores caused by bare Mongolian words (Ард, Говь, Сүү) matching as tickers. |
| `fix2_dedup_scores.py` | Removed duplicate `(article_id, ticker)` sentiment rows. |
| `fix3_rebuild_history.py` | Rebuilt `sentiment_history` aggregates from scratch. |
| `fix4_patched_sentiment_processor.py` | Snapshot of the patched sentiment processor logic. |
| `fix5_supabase_sql.sql` | SQL: added `channel` / `published_at` columns, unique constraints, and indexes. **Now folded into `SCHEMA_SQL`.** |
| `run_all_fixes.py` | Orchestrator that ran fix1–fix3 in order. |
| `run_all_fixes_paginated.py` | Same as above but paginates through all Supabase rows. |
| `telegram_backfill.py` | Backfilled historical Telegram messages. |

Run from the repo root with `PYTHONPATH=.` if you ever need to re-apply one,
e.g. `PYTHONPATH=. python migrations/fix2_dedup_scores.py`.
