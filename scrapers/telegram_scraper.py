"""
MSE Sentiment — Telegram Scraper
Monitors @openmindmse and @bibbytimes.
Fetches history on first run only, then listens for new messages in real time.
Pre-filters with keywords before anything touches the AI pipeline.
"""

import os
import asyncio
from datetime import datetime, timezone
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from config.settings import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    TELEGRAM_GROUPS, MSE_KEYWORDS, TELEGRAM_HISTORY_LIMIT
)
from db.supabase import save_article, log_scrape

SESSION_FILE  = "mse_telegram_session"
HISTORY_FLAG  = ".telegram_history_done"   # created after first history fetch


def is_relevant(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return False
    text_upper = text.upper()
    return any(kw.upper() in text_upper for kw in MSE_KEYWORDS)


def detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    return "mn" if cyrillic > len(text) * 0.2 else "en"


def process_message(group: str, message_id: int, text: str, date: datetime):
    if not is_relevant(text):
        return False
    language     = detect_language(text)
    url          = f"tg://{group}/{message_id}"
    published_at = date.astimezone(timezone.utc).isoformat() if date else None
    article_id   = save_article(
        source       = group,
        source_type  = "telegram",
        title        = text[:100],
        content      = text,
        url          = url,
        language     = language,
        published_at = published_at,
    )
    if article_id:
        print(f"  [TG] Saved: {group} | {text[:60]}...")
        return True
    return False


async def fetch_history(client: TelegramClient, group: str):
    print(f"\n  Fetching history from @{group}...")
    found = saved = 0
    try:
        async for message in client.iter_messages(group, limit=TELEGRAM_HISTORY_LIMIT):
            if message.text:
                found += 1
                if process_message(group, message.id, message.text, message.date):
                    saved += 1
                await asyncio.sleep(0.05)
        print(f"  @{group} history: {found} messages, {saved} relevant saved")
        log_scrape(f"telegram:{group}", "success", found, saved)
    except FloodWaitError as e:
        print(f"  [!] Flood wait {e.seconds}s for @{group}")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"  [!] Error fetching @{group}: {e}")


def setup_realtime_listener(client: TelegramClient):
    @client.on(events.NewMessage(chats=TELEGRAM_GROUPS))
    async def handler(event):
        if not event.message.text:
            return
        chat  = await event.get_chat()
        group = getattr(chat, 'username', str(chat.id)) or str(chat.id)
        text  = event.message.text
        if is_relevant(text):
            process_message(group, event.message.id, text, event.message.date)
    print(f"\n  Real-time listener active for: {', '.join('@' + g for g in TELEGRAM_GROUPS)}")


async def run():
    print("\n" + "="*54)
    print("  MSE Sentiment — Telegram Scraper")
    print("="*54)
    print(f"  Groups  : {', '.join('@' + g for g in TELEGRAM_GROUPS)}")

    async with TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
        if not await client.is_user_authorized():
            await client.send_code_request(TELEGRAM_PHONE)
            code = input("Enter Telegram verification code: ")
            await client.sign_in(TELEGRAM_PHONE, code)

        print("  Connected to Telegram\n")

        if os.path.exists(HISTORY_FLAG):
            print("  History already fetched — jumping to real-time listener")
        else:
            print("  First run — fetching history...")
            for group in TELEGRAM_GROUPS:
                await fetch_history(client, group)
                await asyncio.sleep(2)
            open(HISTORY_FLAG, "w").close()
            print("\n  History done — won't re-fetch on restart")

        setup_realtime_listener(client)
        print("\n  Listening for new messages... (Ctrl+C to stop)")
        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(run())