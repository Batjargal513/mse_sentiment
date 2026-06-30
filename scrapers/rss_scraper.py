"""
MSE Sentiment — News Scraper
Scrapes news.mn and montsame.mn directly.
Loops through pages automatically, stops when no new articles found.
Runs every 30 minutes (only latest 5 pages on scheduled runs).
"""

import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from config.settings import MSE_KEYWORDS, MAX_ARTICLE_CHARS, RSS_INTERVAL_MINUTES
from db.supabase import save_article, log_scrape
from utils.date_utils import extract_date_from_soup

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
}

SOURCES = [
    {
        "name":            "news.mn",
        "base_url":        "https://news.mn",
        "first_url":       "https://news.mn",
        "page_url":        "https://news.mn/r/?page={page}",
        "article_pattern": "/r/",
        "extra_sections":  [],
        "max_pages":       50,
    },
    {
        "name":            "montsame.mn",
        "base_url":        "https://montsame.mn",
        "first_url":       "https://montsame.mn/mn/more/10",
        "page_url":        "https://montsame.mn/mn/more/10?page={page}",
        "article_pattern": "/mn/read/",
        "extra_sections":  [
            "https://montsame.mn/mn/more/16",   # mining
            "https://montsame.mn/mn/more/8",    # mongolian news
        ],
        "max_pages":       50,
    },
]


def is_relevant(title, content=""):
    text = f"{title} {content}".upper()
    return any(kw.upper() in text for kw in MSE_KEYWORDS)


def detect_language(text):
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    return "mn" if cyrillic > len(text) * 0.2 else "en"


def fetch_links(page_url, base_url, article_pattern=None):
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=10)
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
                href = base_url + href
            elif not href.startswith("http"):
                continue
            if article_pattern and article_pattern not in href:
                continue
            if base_url not in href or href in seen_urls:
                continue
            seen_urls.add(href)
            articles.append({"title": title, "url": href})
        return articles
    except Exception as e:
        print(f"  [!] Fetch error {page_url}: {e}")
        return []


def fetch_article_text(url) -> tuple[str, str | None]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        published_at = extract_date_from_soup(soup)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        for selector in ["article", ".article-body", ".post-content", ".content", "main"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)[:MAX_ARTICLE_CHARS], published_at
        return " ".join(p.get_text(strip=True) for p in soup.find_all("p"))[:MAX_ARTICLE_CHARS], published_at
    except Exception:
        return "", None


def process_links(links, name, seen_urls) -> tuple[int, int]:
    found = 0
    saved = 0
    for item in links:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        found += 1
        if not is_relevant(item["title"]):
            continue
        content, published_at = fetch_article_text(item["url"])
        language = detect_language(f"{item['title']} {content}")
        article_id = save_article(
            source       = name,
            source_type  = "scraper",
            title        = item["title"],
            content      = content or item["title"],
            url          = item["url"],
            language     = language,
            published_at = published_at,
        )
        if article_id:
            saved += 1
            print(f"  ✓ {item['title'][:70]}")
        time.sleep(0.3)
    return found, saved


def scrape_source(source, max_pages=None):
    name            = source["name"]
    base_url        = source["base_url"]
    first_url       = source["first_url"]
    page_url_tpl    = source["page_url"]
    article_pattern = source.get("article_pattern")
    extra_sections  = source.get("extra_sections", [])
    if max_pages is None:
        max_pages = source.get("max_pages", 100)

    print(f"\n  Scraping {name} (up to {max_pages} pages)...")

    total_found = 0
    total_saved = 0
    seen_urls   = set()

    # Page 0 — homepage / first URL
    links = fetch_links(first_url, base_url, article_pattern)
    found, saved = process_links(links, name, seen_urls)
    total_found += found
    total_saved += saved
    print(f"  Page 0: {found} links, {saved} saved")
    time.sleep(1)

    # Extra category sections
    for section_url in extra_sections:
        links = fetch_links(section_url, base_url, article_pattern)
        found, saved = process_links(links, name, seen_urls)
        total_found += found
        total_saved += saved
        time.sleep(1)

    # Pages 1 to max_pages — stop as soon as we hit known URLs
    for page in range(1, max_pages + 1):
        url   = page_url_tpl.format(page=page)
        raw_links = fetch_links(url, base_url, article_pattern)

        if not raw_links:
            print(f"  Page {page}: no links — stopping")
            break

        found, saved = process_links(raw_links, name, seen_urls)
        total_found += found
        total_saved += saved
        print(f"  Page {page}: {found} links, {saved} saved")
        time.sleep(1)

        # Stop as soon as a page saves nothing new — news sites are chronological
        # so if nothing on this page is new, older pages won't be either
        if found > 0 and saved == 0:
            break

    print(f"\n  {name}: {total_found} found, {total_saved} saved")
    log_scrape(name, "success", total_found, total_saved)
    return total_found, total_saved


def run_full_scrape():
    """First run — all pages up to max_pages."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*54}\n  News Full Scrape — {now}\n{'='*54}")
    total_found = total_saved = 0
    for source in SOURCES:
        found, saved = scrape_source(source)
        total_found += found
        total_saved += saved
        time.sleep(2)
    print(f"\n  Done — {total_found} total, {total_saved} new saved")


def run_rss_scan():
    """Scheduled run — latest 5 pages only."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*54}\n  News Scraper — {now}\n{'='*54}")
    total_found = total_saved = 0
    for source in SOURCES:
        found, saved = scrape_source(source, max_pages=5)
        total_found += found
        total_saved += saved
        time.sleep(2)
    print(f"\n  Done — {total_found} total, {total_saved} new relevant saved")


if __name__ == "__main__":
    print("\nMSE Sentiment — News Scraper")
    print("First run : full scrape up to 100 pages per source")
    print("Scheduled : latest 5 pages only\n")

    print("Running full scrape now...")
    run_full_scrape()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_rss_scan, trigger="interval", minutes=RSS_INTERVAL_MINUTES)
    print(f"\nNews scraper live. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nStopped.")