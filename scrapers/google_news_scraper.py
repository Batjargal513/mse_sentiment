"""
MSE Sentiment — Google News Scraper
Searches Google News for MSE-related content using English-only queries.
English-only = zero Russian contamination (Russian uses same Cyrillic as Mongolian).
Runs every 60 minutes.
"""

import time
import requests
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from config.settings import MAX_ARTICLE_CHARS, GOOGLE_NEWS_QUERIES
from db.supabase import save_article, log_scrape
from utils.date_utils import extract_date_from_soup, parse_date

SOURCE_NAME = "google_news"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Russian domains to block (extra safety net) ───────────────────────────────
BLOCKED_DOMAINS = {
    "rg.ru", "ria.ru", "tass.ru", "interfax.ru", "kommersant.ru",
    "vedomosti.ru", "fontanka.ru", "kp.ru", "mk.ru", "iz.ru",
    "lenta.ru", "gazeta.ru", "novayagazeta.ru", "meduza.io",
    "sibreal.org", "altapress.ru", "amic.ru", "bankiros.ru",
    "ngs22.ru", "gornovosti.ru", "kyrgyzstan.org", "akipress.com",
    "kabar.kg", "24.kg", "vb.kg",
}


def is_blocked_domain(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return any(domain == bd or domain.endswith("." + bd) for bd in BLOCKED_DOMAINS)
    except Exception:
        return False


def detect_language(text: str) -> str:
    """English-only queries should return English articles — default to 'en'."""
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    # If somehow a Cyrillic article slips through, detect Mongolian vs Russian
    if cyrillic > len(text) * 0.2:
        mongolian_only = set("өүӨҮ")
        russian_only   = set("ёъыьэюяЁЪЫЬЭЮЯ")
        mn_hits = sum(1 for c in text if c in mongolian_only)
        ru_hits = sum(1 for c in text if c in russian_only)
        if ru_hits > 2 and mn_hits == 0:
            return "ru"  # will be skipped
        return "mn"
    return "en"


def scrape_with_gnews(query: str) -> list[dict]:
    try:
        from gnews import GNews
        gn = GNews(language="en", country="MN", max_results=10)
        results = gn.get_news(query)
        articles = []
        for item in results:
            pub = item.get("published date") or item.get("published") or ""
            published_at = parse_date(str(pub)) if pub else None
            articles.append({
                "title":        item.get("title", ""),
                "url":          item.get("url", ""),
                "content":      item.get("description", "") or item.get("content", ""),
                "published_at": published_at,
            })
        return articles
    except ImportError:
        return []
    except Exception as e:
        print(f"  [gnews] error for '{query}': {e}")
        return []


def scrape_with_rss(query: str) -> list[dict]:
    try:
        import feedparser
        from urllib.parse import quote
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=MN&ceid=MN:en"
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        parsed = feedparser.parse(resp.content)
        articles = []
        for entry in parsed.entries[:10]:
            pub_parsed = getattr(entry, "published_parsed", None)
            published_at = None
            if pub_parsed:
                try:
                    import time as _t
                    dt = datetime.fromtimestamp(_t.mktime(pub_parsed), tz=timezone.utc)
                    published_at = dt.isoformat()
                except Exception:
                    pass
            articles.append({
                "title":        getattr(entry, "title",   "") or "",
                "url":          getattr(entry, "link",    "") or "",
                "content":      getattr(entry, "summary", "") or "",
                "published_at": published_at,
            })
        return articles
    except Exception as e:
        print(f"  [RSS] error for '{query}': {e}")
        return []


def fetch_article_text(url: str) -> tuple[str, str | None]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        published_at = extract_date_from_soup(soup)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        for selector in ["article", ".article-body", ".post-content", ".entry-content", "main"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)[:MAX_ARTICLE_CHARS], published_at
        return " ".join(p.get_text(strip=True) for p in soup.find_all("p"))[:MAX_ARTICLE_CHARS], published_at
    except Exception:
        return "", None


def scrape_query(query: str) -> tuple[int, int]:
    # Try gnews first, fall back to RSS
    articles = scrape_with_gnews(query)
    if not articles:
        articles = scrape_with_rss(query)
    if not articles:
        return 0, 0

    saved = skipped = 0

    for art in articles:
        title        = art["title"]
        url          = art["url"]
        content      = art["content"]
        published_at = art.get("published_at")

        if not title:
            continue

        # Block known Russian domains
        if is_blocked_domain(url):
            skipped += 1
            continue

        # Fetch full text if content is thin
        if len(content) < 100 and url:
            full_text, pub = fetch_article_text(url)
            content = full_text or content
            if not published_at:
                published_at = pub
            time.sleep(0.5)

        # Skip Russian articles that slipped through
        lang = detect_language(f"{title} {content}")
        if lang == "ru":
            skipped += 1
            print(f"  ✗ [RU] {title[:60]}")
            continue

        article_id = save_article(
            source       = SOURCE_NAME,
            source_type  = "aggregator",
            title        = title,
            content      = content or title,
            url          = url,
            language     = lang,
            published_at = published_at,
        )
        if article_id:
            saved += 1
            print(f"  ✓ [{lang}] {title[:70]}")

    if skipped:
        print(f"  ✗ Skipped {skipped} non-relevant articles")

    return len(articles), saved


def scrape_google_news():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  Google News — {now}")
    print(f"  Queries: {len(GOOGLE_NEWS_QUERIES)} (English-only)")

    total_found = total_saved = 0

    for query in GOOGLE_NEWS_QUERIES:
        found, saved = scrape_query(query)
        total_found += found
        total_saved += saved
        if found:
            print(f"  '{query}': {found} found, {saved} saved")
        time.sleep(3)  # be polite

    print(f"\n  Google News: {total_found} total, {total_saved} new saved")
    log_scrape(SOURCE_NAME, "success", total_found, total_saved)
    return total_found, total_saved


if __name__ == "__main__":
    print("\nGoogle News Scraper — English-only mode")
    print(f"Queries ({len(GOOGLE_NEWS_QUERIES)}):")
    for q in GOOGLE_NEWS_QUERIES:
        print(f"  · {q}")

    try:
        import gnews
    except ImportError:
        print("\nInstalling gnews...")
        import subprocess
        subprocess.run(["pip", "install", "gnews", "--quiet"], check=True)

    print("\nRunning first scrape...")
    scrape_google_news()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(scrape_google_news, trigger="interval", minutes=60)
    print("\nGoogle News scraper live. Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nStopped.")