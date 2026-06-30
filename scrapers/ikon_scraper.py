"""
MSE Sentiment — ikon.mn Scraper
Scrapes business and finance news from ikon.mn
Runs every 30 minutes.
"""

import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from config.settings import MSE_KEYWORDS, MAX_ARTICLE_CHARS
from db.supabase import save_article, log_scrape
from utils.date_utils import extract_date_from_soup

SOURCE_NAME = "ikon.mn"
BASE_URL    = "https://ikon.mn"
NEWS_URL    = "https://ikon.mn"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
    "Referer":         "https://ikon.mn",
    "Cookie":          "_ga=GA1.1.653938253.1765809278; cs=yes; tjsid=59f07d11ba428b125f9c289861626d2f",
}


def is_relevant(title: str, content: str = "") -> bool:
    text = f"{title} {content}".upper()
    return any(kw.upper() in text for kw in MSE_KEYWORDS)


def detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    return "mn" if cyrillic > len(text) * 0.2 else "en"


def fetch_article_links() -> list[dict]:
    try:
        r = requests.get(NEWS_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles  = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 15:
                continue
            if href.startswith("/"):
                href = BASE_URL + href
            elif not href.startswith("http"):
                continue
            if BASE_URL not in href or href in seen_urls:
                continue
            seen_urls.add(href)
            articles.append({"title": title, "url": href})

        return articles

    except Exception as e:
        print(f"  [!] ikon.mn fetch error: {e}")
        return []


def fetch_article_text(url: str) -> tuple[str, str | None]:
    """Returns (text, published_at)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        published_at = extract_date_from_soup(soup)

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        for selector in [".article-body", ".post-content", ".entry-content",
                         ".news-content", "article", ".content", "main"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)[:MAX_ARTICLE_CHARS], published_at

        paragraphs = soup.find_all("p")
        return " ".join(p.get_text(strip=True) for p in paragraphs)[:MAX_ARTICLE_CHARS], published_at

    except Exception:
        return "", None


def scrape_ikon():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  ikon.mn scraper — {now}")

    links = fetch_article_links()
    print(f"  Found {len(links)} article links")

    found = len(links)
    saved = 0

    for item in links:
        title = item["title"]
        url   = item["url"]

        if not is_relevant(title):
            continue

        content, published_at = fetch_article_text(url)
        language = detect_language(f"{title} {content}")

        article_id = save_article(
            source       = SOURCE_NAME,
            source_type  = "scraper",
            title        = title,
            content      = content or title,
            url          = url,
            language     = language,
            published_at = published_at,
        )

        if article_id:
            saved += 1
            print(f"  ✓ {title[:70]}")

        time.sleep(0.8)

    print(f"  ikon.mn: {found} found, {saved} relevant saved")
    log_scrape(SOURCE_NAME, "success", found, saved)
    return found, saved


if __name__ == "__main__":
    print("\nikon.mn Scraper")
    print("Schedule: Every 30 minutes\n")

    print("Running first scrape now...")
    scrape_ikon()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(scrape_ikon, trigger="interval", minutes=30)
    print("\nikon.mn scraper live.")
    print("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nikon.mn scraper stopped.")