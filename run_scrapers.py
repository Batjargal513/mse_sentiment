"""
MSE Sentiment — Master Runner
Tracks last run times — smart restart behavior.

On restart:
- First run ever → full historical scrape
- Subsequent restarts → only runs scrapers that are due based on interval
- Scrapers that ran recently → skipped until interval passes

Usage: PYTHONPATH=. python3 run_scrapers.py
"""

import time
import asyncio
import threading
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from scrapers.new_sources_scraper import run_all_new_sources

from run_state import is_due, mark_done, is_first_run, mark_first_run_done

from scrapers.rss_scraper         import run_full_scrape, run_rss_scan
from scrapers.ikon_scraper        import scrape_ikon
from scrapers.zarig_scraper       import scrape_zarig
from scrapers.google_news_scraper import scrape_google_news
from scrapers.frc_scraper         import scrape_frc
from scrapers.mse_scraper         import scrape_all_pages, scrape_latest as scrape_mse_latest

# Scraper intervals in minutes
INTERVALS = {
    "mse":    60,
    "frc":    60,
    "rss":    30,
    "ikon":   30,
    "zarig":  30,
    "google": 60,
}


def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def run_with_tracking(name: str, fn):
    """Run a scraper and mark it done with timestamp."""
    print(f"\n  ▶ {name}")
    try:
        fn()
        mark_done(name)
    except Exception as e:
        print(f"  [!] {name} error: {e}")


def run_first_time():
    """Full historical scrape — only on very first run ever."""
    print(f"\n{'='*54}")
    print(f"  FIRST RUN — Full historical scrape — {now_str()}")
    print(f"{'='*54}\n")

    run_with_tracking("mse",    scrape_all_pages)
    run_with_tracking("frc",    lambda: scrape_frc(max_pages=50))
    run_with_tracking("rss",    run_full_scrape)
    run_with_tracking("ikon",   scrape_ikon)
    run_with_tracking("zarig",  lambda: scrape_zarig(max_pages=100))
    run_with_tracking("google", scrape_google_news)

    mark_first_run_done()
    print(f"\n  ✅ First run complete — {now_str()}\n")


def run_due_scrapers():
    """On restart — only run scrapers that are due."""
    print(f"\n{'='*54}")
    print(f"  Checking due scrapers — {now_str()}")
    print(f"{'='*54}\n")

    if is_due("mse", INTERVALS["mse"]):
        run_with_tracking("mse", lambda: scrape_mse_latest(pages=3))

    if is_due("frc", INTERVALS["frc"]):
        run_with_tracking("frc", lambda: scrape_frc(max_pages=2))

    if is_due("rss", INTERVALS["rss"]):
        run_with_tracking("rss", run_rss_scan)

    if is_due("ikon", INTERVALS["ikon"]):
        run_with_tracking("ikon", scrape_ikon)

    if is_due("zarig", INTERVALS["zarig"]):
        run_with_tracking("zarig", lambda: scrape_zarig(max_pages=5))

    if is_due("google", INTERVALS["google"]):
        run_with_tracking("google", scrape_google_news)


# ── Scheduled job wrappers ────────────────────────────────────────────────────

def job_mse():
    run_with_tracking("mse", lambda: scrape_mse_latest(pages=3))

def job_frc():
    run_with_tracking("frc", lambda: scrape_frc(max_pages=2))

def job_rss():
    run_with_tracking("rss", run_rss_scan)

def job_ikon():
    run_with_tracking("ikon", scrape_ikon)

def job_zarig():
    run_with_tracking("zarig", lambda: scrape_zarig(max_pages=5))

def job_google():
    run_with_tracking("google", scrape_google_news)


def run_telegram_in_thread():
    from scrapers.telegram_scraper import run as telegram_run
    while True:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print("  [TG] Starting Telegram listener...")
            loop.run_until_complete(telegram_run())
        except Exception as e:
            print(f"  [!] Telegram error: {e} — restarting in 30s")
            time.sleep(30)
        finally:
            loop.close()


if __name__ == "__main__":
    print("\nMSE Sentiment — Master Scraper Runner")
    print("="*54)
    print("Sources:")
    print("  • MSE Official API  — every 60 min")
    print("  • FRC Regulatory    — every 60 min")
    print("  • news.mn           — every 30 min")
    print("  • montsame.mn       — every 30 min")
    print("  • ikon.mn           — every 30 min")
    print("  • zarig.mn          — every 30 min")
    print("  • Google News       — every 60 min")
    print("  • Telegram          — real-time listener")
    print("="*54)

    # Start Telegram
    print("\nStarting Telegram listener...")
    tg_thread = threading.Thread(target=run_telegram_in_thread, daemon=True)
    tg_thread.start()
    time.sleep(3)

    # First run ever vs smart restart
    if is_first_run():
        print("\n  First run detected — full historical scrape starting...\n")
        run_first_time()
    else:
        print("\n  Resuming — checking which scrapers are due...\n")
        run_due_scrapers()

    # Schedule all jobs — APScheduler tracks next run from now
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(job_mse,    "interval", minutes=60, id="mse")
    scheduler.add_job(job_frc,    "interval", minutes=60, id="frc")
    scheduler.add_job(job_rss,    "interval", minutes=30, id="rss")
    scheduler.add_job(job_ikon,   "interval", minutes=30, id="ikon")
    scheduler.add_job(job_zarig,  "interval", minutes=30, id="zarig")
    scheduler.add_job(job_google, "interval", minutes=60, id="google")
    scheduler.add_job(run_all_new_sources, trigger="interval", minutes=60)

    scheduler.start()
    print("\nAll scrapers scheduled and running.")
    print("Telegram listening in real-time.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(60)
            print(f"  [{now_str()}] Pipeline running...")
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("\nAll scrapers stopped.")