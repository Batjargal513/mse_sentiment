"""
MSE Sentiment — FRC Scraper
Scrapes regulatory news from the Financial Regulatory Commission (frc.mn).

API endpoint: https://www.frc.mn:5001/api/news?menuid=18&site=main&lang=mn&page=N
Falls back to HTML scraping if the API port is unreachable (common outside MN).
Runs every 60 minutes.
"""

import time
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from config.settings import MAX_ARTICLE_CHARS
from db.supabase import save_article, log_scrape
from utils.date_utils import parse_date, extract_date_from_soup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCE_NAME  = "frc"
API_BASE     = "https://www.frc.mn:5001/api/news"
HTML_BASE    = "https://frc.mn/mn/post/18"
DETAIL_BASE  = "https://frc.mn/mn/post"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/html, */*",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
    "Referer":         "https://frc.mn",
    "Origin":          "https://frc.mn",
}


def fetch_via_api(page: int = 0) -> list[dict]:
    try:
        r = requests.get(
            API_BASE,
            params={"menuid": 18, "site": "main", "lang": "mn", "page": page},
            headers=HEADERS,
            timeout=12,
            verify=False,
        )
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data") or data.get("items") or data.get("news") or []
        else:
            items = []

        print(f"  [FRC] API returned {len(items)} items")

        articles = []
        for item in items:
            title   = (item.get("subject") or item.get("title") or item.get("Title") or item.get("name") or "").strip()
            url_id  = item.get("iDs") or item.get("id") or item.get("Id") or item.get("newsId") or ""
            url     = item.get("url") or item.get("link") or (f"{DETAIL_BASE}/{url_id}" if url_id else "")
            raw_content = item.get("info") or item.get("body") or item.get("content") or item.get("description") or ""
            content = BeautifulSoup(raw_content, "html.parser").get_text(separator=" ", strip=True) if raw_content else ""
            raw_date = item.get("publishedAt") or item.get("date") or item.get("createdAt") or ""
            published_at = parse_date(str(raw_date)) if raw_date else None

            if title:
                articles.append({
                    "title":        title,
                    "url":          url,
                    "content":      content[:MAX_ARTICLE_CHARS],
                    "published_at": published_at,
                })
        return articles

    except requests.exceptions.ConnectionError:
        print("  [FRC] API port :5001 unreachable — switching to HTML fallback")
        return []
    except Exception as e:
        print(f"  [FRC] API error: {e}")
        return []


def fetch_via_html(page: int = 0) -> list[dict]:
    try:
        url = HTML_BASE if page == 0 else f"{HTML_BASE}?page={page}"
        r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = []
        seen = set()

        selectors = [
            "a[href*='/mn/post/']", ".news-list a", ".post-list a",
            "article a", "li a", "h2 a", "h3 a", "h4 a",
        ]

        for sel in selectors:
            links = soup.select(sel)
            if links:
                for a in links:
                    href  = a.get("href", "")
                    title = a.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    full_url = href if href.startswith("http") else f"https://frc.mn{href}"
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    articles.append({"title": title, "url": full_url, "content": "", "published_at": None})
                if articles:
                    break

        return articles

    except Exception as e:
        print(f"  [FRC] HTML fallback error: {e}")
        return []


def fetch_article_body(url: str) -> tuple[str, str | None]:
    if not url:
        return "", None
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        published_at = extract_date_from_soup(soup)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        for sel in ["article", ".article-body", ".post-content",
                    ".entry-content", ".detail-content", ".content", "main"]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator=" ", strip=True)[:MAX_ARTICLE_CHARS], published_at
        paragraphs = soup.find_all("p")
        return " ".join(p.get_text(strip=True) for p in paragraphs)[:MAX_ARTICLE_CHARS], published_at
    except Exception:
        return "", None


def scrape_frc(max_pages: int = 72) -> tuple[int, int]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  FRC scraper — {now}")

    total_found = 0
    total_saved = 0

    for page in range(max_pages):
        print(f"  Page {page}...")

        articles = fetch_via_api(page)
        if not articles:
            articles = fetch_via_html(page)

        if not articles:
            print(f"  No articles on page {page}, stopping.")
            break

        total_found += len(articles)
        page_saved = 0

        for art in articles:
            content      = art["content"]
            published_at = art["published_at"]

            if not content and art["url"]:
                content, pub = fetch_article_body(art["url"])
                if not published_at:
                    published_at = pub
                time.sleep(0.5)

            article_id = save_article(
                source       = SOURCE_NAME,
                source_type  = "regulatory",
                title        = art["title"],
                content      = content or art["title"],
                url          = art["url"],
                language     = "mn",
                published_at = published_at,
            )
            if article_id:
                total_saved += 1
                page_saved  += 1
                print(f"  ✓ {art['title'][:70]}")

        time.sleep(1)

        if page_saved == 0:
            print(f"  No new articles on page {page}, stopping.")
            break

    print(f"\n  FRC: {total_found} found, {total_saved} new saved")
    log_scrape(SOURCE_NAME, "success", total_found, total_saved)
    return total_found, total_saved


if __name__ == "__main__":
    print("\nFRC Scraper")
    print("API   : https://www.frc.mn:5001/api/news (with HTML fallback)")
    print("Schedule: Every 60 minutes\n")

    print("Running first scrape now...")
    scrape_frc()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(scrape_frc, trigger="interval", minutes=60)
    print("\nFRC scraper live. Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nFRC scraper stopped.")