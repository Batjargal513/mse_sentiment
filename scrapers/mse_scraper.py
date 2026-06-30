"""
MSE Sentiment — MSE Official API Scraper
Uses MSE's internal JSON API directly.
https://mse.mn/api/news?lang=mn&orderby=DESC&page=1&perPage=15&sdate=2000-01-01&edate=today

7,887 total articles across 526 pages.
First run: scrapes all pages for full history.
Subsequent runs: checks only latest pages for new articles.
"""

import os
import time
import requests
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from config.settings import MSE_KEYWORDS
from db.supabase import save_article, log_scrape
from utils.date_utils import parse_date

SOURCE_NAME  = "mse.mn"
API_URL      = "https://mse.mn/api/news"
TOTAL_PAGES  = 526
HISTORY_FLAG = ".mse_history_done"   # created after first full scrape

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Referer":         "https://mse.mn/news",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
}


def fetch_page(page: int) -> list[dict]:
    try:
        r = requests.get(
            API_URL,
            params={
                "lang":    "mn",
                "orderby": "DESC",
                "page":    page,
                "perPage": 15,
                "sdate":   "2000-01-01",
                "edate":   datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            headers=HEADERS,
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        print(f"  [!] MSE API error page {page}: {e}")
        return []


def save_mse_article(item: dict) -> bool:
    title       = item.get("title", "") or ""
    description = item.get("description", "") or ""
    article_id  = item.get("id")

    if not title:
        return False

    url          = f"https://mse.mn/news/{article_id}"
    raw_date     = item.get("date") or item.get("createdAt") or item.get("publishedAt") or item.get("created_at") or ""
    published_at = parse_date(str(raw_date)) if raw_date else None

    article_db_id = save_article(
        source       = SOURCE_NAME,
        source_type  = "official_api",
        title        = title,
        content      = description,
        url          = url,
        language     = "mn",
        published_at = published_at,
    )
    return article_db_id is not None


def scrape_all_pages():
    print(f"\n  MSE full history scrape — {TOTAL_PAGES} pages, ~7,887 articles")
    print("  This will take a few minutes...\n")

    total_found = total_saved = 0

    for page in range(1, TOTAL_PAGES + 1):
        items = fetch_page(page)
        if not items:
            print(f"  Page {page}: empty or error — stopping")
            break

        for item in items:
            total_found += 1
            if save_mse_article(item):
                total_saved += 1

        if page % 10 == 0 or page == 1:
            print(f"  Page {page}/{TOTAL_PAGES} — {total_saved} saved so far")

        time.sleep(0.3)

    print(f"\n  Full scrape done — {total_found} found, {total_saved} saved")
    log_scrape(SOURCE_NAME, "success", total_found, total_saved)

    # Mark full scrape as done
    open(HISTORY_FLAG, "w").close()
    return total_found, total_saved


def scrape_latest(pages: int = 3):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  MSE latest scrape — {now}")

    total_found = total_saved = 0

    for page in range(1, pages + 1):
        items = fetch_page(page)
        for item in items:
            total_found += 1
            if save_mse_article(item):
                total_saved += 1
        time.sleep(0.5)

    print(f"  MSE: {total_found} checked, {total_saved} new saved")
    log_scrape(SOURCE_NAME, "success", total_found, total_saved)
    return total_found, total_saved


if __name__ == "__main__":
    print("\nMSE Official API Scraper")
    print(f"API      : {API_URL}")
    print(f"Total    : ~7,887 articles across {TOTAL_PAGES} pages")
    print("Schedule : Every 60 minutes (latest 3 pages only)\n")

    if os.path.exists(HISTORY_FLAG):
        print("Full history already scraped — running latest only...")
        scrape_latest()
    else:
        print("First run: scraping full history...")
        scrape_all_pages()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(scrape_latest, trigger="interval", minutes=60)
    print("\nMSE scraper live. Checks latest articles every 60 minutes.")
    print("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nMSE scraper stopped.")