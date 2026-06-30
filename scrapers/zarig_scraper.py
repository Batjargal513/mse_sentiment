"""
MSE Sentiment — zarig.mn Scraper
Scrapes news from zarig.mn with pagination.
Pagination format: https://zarig.mn/economy/l:2
Runs every 30 minutes (latest pages only on scheduled runs).
"""

import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from config.settings import MSE_KEYWORDS, MAX_ARTICLE_CHARS
from db.supabase import save_article, log_scrape
from utils.date_utils import extract_date_from_soup

SOURCE_NAME = "zarig.mn"
BASE_URL    = "https://zarig.mn"

# Sections with their base URLs — pagination appends /l:N
SECTIONS = [
    {"name": "economy",  "first": "https://zarig.mn/economy",  "page_url": "https://zarig.mn/economy/l:{page}"},
    {"name": "society",  "first": "https://zarig.mn/society",  "page_url": "https://zarig.mn/society/l:{page}"},
    {"name": "politics", "first": "https://zarig.mn/politics", "page_url": "https://zarig.mn/politics/l:{page}"},
    {"name": "home",     "first": "https://zarig.mn",          "page_url": None},  # no pagination on homepage
]

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
    "Referer":         "https://zarig.mn",
}


def is_relevant(title: str, content: str = "") -> bool:
    text = f"{title} {content}".upper()
    return any(kw.upper() in text for kw in MSE_KEYWORDS)


def detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    return "mn" if cyrillic > len(text) * 0.2 else "en"


def fetch_links(page_url: str) -> list[dict]:
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        articles  = []
        seen_urls = set()
        selectors = ["article a", ".news-item a", ".article a", ".post a", "h2 a", "h3 a", ".title a"]
        for selector in selectors:
            for a in soup.select(selector):
                href  = a.get("href", "")
                title = a.get_text(strip=True)
                if not href or not title or len(title) < 10:
                    continue
                if href.startswith("/"):
                    href = BASE_URL + href
                elif not href.startswith("http"):
                    continue
                if href in seen_urls or BASE_URL not in href:
                    continue
                seen_urls.add(href)
                articles.append({"title": title, "url": href})
        return articles
    except Exception as e:
        print(f"  [!] zarig.mn fetch error ({page_url}): {e}")
        return []


def fetch_article_text(url: str) -> tuple[str, str | None]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        published_at = extract_date_from_soup(soup)
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        for selector in [".article-body", ".post-content", ".entry-content",
                         ".news-detail", "article", ".content", "main"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)[:MAX_ARTICLE_CHARS], published_at
        paragraphs = soup.find_all("p")
        return " ".join(p.get_text(strip=True) for p in paragraphs)[:MAX_ARTICLE_CHARS], published_at
    except Exception:
        return "", None


def scrape_section(section: dict, max_pages: int, seen_urls: set) -> tuple[int, int]:
    name      = section["name"]
    first_url = section["first"]
    page_url  = section.get("page_url")

    found = 0
    saved = 0

    # Page 1 — first/base URL
    links = fetch_links(first_url)
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
            source       = SOURCE_NAME,
            source_type  = "scraper",
            title        = item["title"],
            content      = content or item["title"],
            url          = item["url"],
            language     = language,
            published_at = published_at,
        )
        if article_id:
            saved += 1
            print(f"  ✓ [{name}] {item['title'][:65]}")
        time.sleep(0.5)

    print(f"  [{name}] Page 1: {found} links, {saved} saved")
    time.sleep(1)

    # Pages 2..max_pages
    if not page_url:
        return found, saved

    for page in range(2, max_pages + 1):
        url   = page_url.format(page=page)
        links = fetch_links(url)

        if not links:
            print(f"  [{name}] Page {page}: no links — stopping")
            break

        page_found = 0
        page_saved = 0

        for item in links:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            page_found += 1
            if not is_relevant(item["title"]):
                continue
            content, published_at = fetch_article_text(item["url"])
            language = detect_language(f"{item['title']} {content}")
            article_id = save_article(
                source       = SOURCE_NAME,
                source_type  = "scraper",
                title        = item["title"],
                content      = content or item["title"],
                url          = item["url"],
                language     = language,
                published_at = published_at,
            )
            if article_id:
                page_saved += 1
                print(f"  ✓ [{name}] {item['title'][:65]}")
            time.sleep(0.5)

        found += page_found
        saved += page_saved
        print(f"  [{name}] Page {page}: {page_found} links, {page_saved} saved")
        time.sleep(1)

        if page_saved == 0 and page > 5:
            print(f"  [{name}] No new articles — stopping")
            break

    return found, saved


def scrape_zarig(max_pages: int = 50):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  zarig.mn scraper — {now} (up to {max_pages} pages per section)")

    total_found = 0
    total_saved = 0
    seen_urls   = set()

    for section in SECTIONS:
        found, saved = scrape_section(section, max_pages, seen_urls)
        total_found += found
        total_saved += saved
        time.sleep(2)

    print(f"\n  zarig.mn: {total_found} found, {total_saved} saved")
    log_scrape(SOURCE_NAME, "success", total_found, total_saved)
    return total_found, total_saved


if __name__ == "__main__":
    print("\nzarig.mn Scraper")
    print("Pagination: /economy/l:N, /society/l:N, /politics/l:N")
    print("First run : up to 50 pages per section")
    print("Scheduled : latest 5 pages only\n")

    print("Running full scrape now...")
    scrape_zarig(max_pages=50)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(lambda: scrape_zarig(max_pages=5), trigger="interval", minutes=30)
    print("\nzarig.mn scraper live. Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nzarig.mn scraper stopped.")