"""
FIX 1 — AARD False Positive Cleanup
=====================================
Problem : "Ард" in COMPANY_MAP matches any Mongolian text with
          "ард түмэн" (people), "ард иргэн" (citizen), "ардчилал" (democracy).
          1,799 of AARD's 1,920 scored rows are false positives.

What this does:
  1. Deletes false-positive AARD rows from sentiment_scores
  2. Removes AARD's corrupted history rows
  3. Patches COMPANY_MAP in sentiment_processor.py

Run: PYTHONPATH=. python3 fixes/fix1_aard_false_positives.py
"""

from db.supabase import get_client

# ── Specific AARD keywords (compound proper nouns only) ───────────────────────
AARD_REAL_KEYWORDS = [
    "AARD",
    "Ард кредит",
    "Ард даатгал",
    "Ард Санхүүгийн Групп",
    "Ард Санхүү",
    "Ard Credit",
    "Ard Financial",
    "Ard Daatgal",
    "ArdCredit",
]


def is_real_aard(title: str, content: str) -> bool:
    text = f"{title or ''} {content or ''}".lower()
    return any(kw.lower() in text for kw in AARD_REAL_KEYWORDS)


def run():
    db = get_client()
    print("=" * 54)
    print("  Fix 1 — AARD False Positive Cleanup")
    print("=" * 54)

    # Step 1: Get all AARD score rows with their articles
    print("\n  Fetching AARD scores + articles...")
    result = db.table("sentiment_scores") \
               .select("id, article_id, articles(title, content)") \
               .eq("ticker", "AARD") \
               .execute()

    all_aard = result.data or []
    print(f"  Total AARD score rows: {len(all_aard)}")

    # Step 2: Identify false positives
    false_ids = []
    real_ids  = []

    for row in all_aard:
        art    = row.get("articles") or {}
        title  = art.get("title", "") or ""
        content = art.get("content", "") or ""
        if is_real_aard(title, content):
            real_ids.append(row["id"])
        else:
            false_ids.append(row["id"])

    print(f"  Real AARD scores to keep : {len(real_ids)}")
    print(f"  False positives to delete: {len(false_ids)}")

    if not false_ids:
        print("  Nothing to delete.")
        return

    confirm = input(f"\n  Delete {len(false_ids)} false-positive AARD rows? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("  Aborted.")
        return

    # Step 3: Delete in batches of 100 (Supabase limit)
    deleted = 0
    batch_size = 100
    for i in range(0, len(false_ids), batch_size):
        batch = false_ids[i:i + batch_size]
        db.table("sentiment_scores").delete().in_("id", batch).execute()
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(false_ids)}...")

    print(f"\n  ✅ Deleted {deleted} false AARD score rows")

    # Step 4: Delete AARD history so it gets rebuilt clean
    print("\n  Removing AARD history rows for rebuild...")
    db.table("sentiment_history").delete().eq("ticker", "AARD").execute()
    print("  ✅ AARD history cleared (will be rebuilt by fix3)")

    print("\n  Done. Now update COMPANY_MAP in sentiment_processor.py:")
    print("""
    \"AARD\": [
        \"AARD\",
        \"Ард кредит\",
        \"Ард даатгал\",
        \"Ард Санхүүгийн Групп\",
        \"Ард Санхүү\",
        \"Ard Credit\",
        \"Ard Financial\",
        \"Ard Daatgal\",
    ],
    """)


if __name__ == "__main__":
    run()
