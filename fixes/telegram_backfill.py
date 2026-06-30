"""
Telegram Backfill — catch up on missed messages
================================================
The real-time listener was down for ~6 days (Apr 22 → Apr 28).
This fetches the last 3000 messages per channel and saves
any that aren't already in the database.

Run while the main telegram_scraper.py is STOPPED:
  Ctrl+C the main scraper first, then:
  PYTHONPATH=. python3 scrapers/telegram_backfill.py
"""

import asyncio
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from config.settings import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    TELEGRAM_GROUPS, MSE_KEYWORDS
)
from db.supabase import save_article, log_scrape

SESSION_FILE = "mse_telegram_session"
BACKFILL_LIMIT = 3000  # enough to cover 6 days on active channels
CUTOFF_DAYS    = 7     # only save messages from last 7 days


def is_relevant(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return False
    text_upper = text.upper()
    return any(kw.upper() in text_upper for kw in MSE_KEYWORDS)


def detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    return "mn" if cyrillic > len(text) * 0.2 else "en"


async def backfill_group(client: TelegramClient, group: str):
    cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
    print(f"\n  Backfilling @{group} (last {CUTOFF_DAYS} days, up to {BACKFILL_LIMIT} msgs)...")

    found = saved = skipped_old = skipped_irrelevant = skipped_dup = 0

    try:
        async for message in client.iter_messages(group, limit=BACKFILL_LIMIT):
            if not message.text:
                continue

            found += 1

            # Stop once we go past the cutoff date
            if message.date and message.date.replace(tzinfo=timezone.utc) < cutoff:
                skipped_old += 1
                if skipped_old == 1:
                    print(f"  Reached cutoff date ({cutoff.date()}) — stopping")
                break

            if not is_relevant(message.text):
                skipped_irrelevant += 1
                continue

            lang         = detect_language(message.text)
            url          = f"tg://{group}/{message.id}"
            published_at = message.date.astimezone(timezone.utc).isoformat()

            article_id = save_article(
                source       = group.lower(),   # normalise case
                source_type  = "telegram",
                title        = message.text[:100],
                content      = message.text,
                url          = url,
                language     = lang,
                published_at = published_at,
            )

            if article_id:
                saved += 1
                print(f"  ✓ [{message.date.strftime('%m-%d %H:%M')}] {message.text[:60]}")
            else:
                skipped_dup += 1  # already in DB

            await asyncio.sleep(0.05)

    except FloodWaitError as e:
        print(f"  [!] Flood wait {e.seconds}s — pausing...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"  [!] Error: {e}")

    print(f"\n  @{group} backfill done:")
    print(f"    Messages checked : {found}")
    print(f"    New saved        : {saved}")
    print(f"    Already in DB    : {skipped_dup}")
    print(f"    Irrelevant       : {skipped_irrelevant}")

    log_scrape(f"telegram:{group}", "success", found, saved)
    return saved


async def run():
    print("\n" + "="*54)
    print("  Telegram Backfill — catching up on missed messages")
    print("="*54)

    async with TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
        if not await client.is_user_authorized():
            print("  [!] Not authorized — run the main scraper first to authenticate")
            return

        print(f"  Connected. Fetching last {CUTOFF_DAYS} days from {len(TELEGRAM_GROUPS)} channels...\n")

        total_saved = 0
        for group in TELEGRAM_GROUPS:
            saved = await backfill_group(client, group)
            total_saved += saved
            await asyncio.sleep(2)

        print(f"\n  ✅ Backfill complete — {total_saved} new articles saved")
        print("  Restart telegram_scraper.py to resume real-time listening")


if __name__ == "__main__":
    asyncio.run(run())
