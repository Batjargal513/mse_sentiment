"""
MSE Sentiment — New Sources Scraper (verified URL patterns)
============================================================
Sources:
  1. Mongolian Mining Journal  — articles at /a/{id}
  2. Bank of Mongolia          — mongolbank.mn news section
  3. Capital Markets Mongolia  — capitalmarkets.mn

PYTHONPATH=. python3 scrapers/new_sources_scraper.py
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from config.settings import MSE_KEYWORDS
from db.supabase import save_article, log_scrape

try:
    from config.settings import MAX_ARTICLE_CHARS
except ImportError:
    MAX_ARTICLE_CHARS = 3000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
}


def is_relevant(title: str, content: str = "") -> bool:
    text = f"{title} {content}".upper()
    return any(kw.upper() in text for kw in MSE_KEYWORDS)


def detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    return "mn" if cyrillic > len(text) * 0.2 else "en"


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [!] {url}: {e}")
        return None


def fetch_article_text(url: str) -> tuple[str, str | None]:
    soup = fetch_page(url)
    if not soup:
        return "", None
    published_at = None
    for sel in ["time[datetime]", "meta[property='article:published_time']",
                ".date", ".published", ".post-date"]:
        el = soup.select_one(sel)
        if el:
            raw = el.get("datetime") or el.get("content") or el.get_text(strip=True)
            if raw and len(raw) >= 8:
                published_at = raw[:10]
                break
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    for sel in ["article", ".article-body", ".article-content", ".post-content",
                ".entry-content", ".content-body", "main"]:
        el = soup.select_one(sel)
        if el:
            return el.get_text(separator=" ", strip=True)[:MAX_ARTICLE_CHARS], published_at
    return " ".join(p.get_text(strip=True) for p in soup.find_all("p"))[:MAX_ARTICLE_CHARS], published_at


# ── 1. MONGOLIAN MINING JOURNAL ───────────────────────────────────────────────
def scrape_mining_journal(max_pages: int = 5) -> tuple[int, int]:
    """
    Confirmed article URL pattern: /a/{numeric_id}
    e.g. https://www.mongolianminingjournal.com/a/74969
    """
    source = "mongolianminingjournal"
    base   = "https://www.mongolianminingjournal.com"
    print(f"\n{'─'*54}")
    print(f"  Scraping: {source}")

    found = saved = 0
    seen  = set()

    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}/page/{page}"
        soup = fetch_page(url)
        if not soup:
            print(f"  Page {page}: unreachable — stopping")
            break

        links = []
        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 10:
                continue
            if href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                continue
            # Confirmed pattern: /a/{numeric_id}
            if re.search(r'/a/\d+', href) and href not in seen:
                seen.add(href)
                links.append({"title": title, "url": href})

        if not links:
            print(f"  Page {page}: no article links — stopping")
            break

        print(f"  Page {page}: {len(links)} article links")
        page_saved = 0

        for item in links:
            if not is_relevant(item["title"]):
                continue
            found += 1
            content, published_at = fetch_article_text(item["url"])
            lang = detect_language(f"{item['title']} {content}")
            article_id = save_article(
                source="mongolianminingjournal", source_type="news",
                title=item["title"], content=content or item["title"],
                url=item["url"], language=lang, published_at=published_at,
            )
            if article_id:
                saved += 1
                page_saved += 1
                print(f"  ✓ [{lang}] {item['title'][:70]}")
            time.sleep(0.5)

        print(f"  → {page_saved} saved this page")
        time.sleep(2)
        if len(links) > 5 and page_saved == 0:
            print("  All already in DB — stopping")
            break

    print(f"\n  {source}: {found} relevant, {saved} new saved")
    log_scrape(source, "success", found, saved)
    return found, saved


# ── 2. BANK OF MONGOLIA ───────────────────────────────────────────────────────
def scrape_mongolbank() -> tuple[int, int]:
    """
    mongolbank.mn — rate decisions and monetary policy.
    Critical for bank stocks: TDB, GLMT, XAC, STB, BGB.
    All content is relevant — no keyword filter applied.
    """
    source = "mongolbank"
    base   = "https://www.mongolbank.mn"
    print(f"\n{'─'*54}")
    print(f"  Scraping: {source}")

    found = saved = 0
    seen  = set()

    # These category pages contain actual article links (confirmed from page structure)
    # /mn/category/news loads via JS — not scrapeable with BeautifulSoup
    # These static category pages DO have article links:
    section_urls = [
        f"{base}/mn/category/6092",   # Monetary Policy Committee minutes
        f"{base}/mn/category/6082",   # Monetary Policy statements
        f"{base}/mn/category/6086",   # Inflation reports
        f"{base}/mn/category/6079",   # Monetary policy reports
        f"{base}/mn/category/6170",   # Financial stability reports
        f"{base}/mn/category/6154",   # Financial Stability Council minutes
    ]

    reached = False
    for section_url in section_urls:
        soup = fetch_page(section_url)
        if not soup:
            continue
        reached = True
        print(f"  Reached: {section_url}")

        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 10:
                continue
            if href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                continue
            if href in seen or "mongolbank.mn" not in href:
                continue
            # Only save actual article/report links: /mn/r/{id} or /en/r/{id}
            import re as _re
            path = href.replace(base, "")
            if not _re.search(r"/(mn|en)/r/\d+", path):
                continue
            seen.add(href)
            found += 1
            content, published_at = fetch_article_text(href)
            lang = detect_language(f"{title} {content}")
            article_id = save_article(
                source=source, source_type="news",
                title=title, content=content or title,
                url=href, language=lang, published_at=published_at,
            )
            if article_id:
                saved += 1
                print(f"  ✓ [{lang}] {title[:70]}")
            time.sleep(0.5)

        time.sleep(1.5)

    if not reached:
        print(f"  ❌ Could not reach {source} — may need Mongolian IP/VPN")
        log_scrape(source, "failed", 0, 0)
    else:
        print(f"\n  {source}: {found} found, {saved} new saved")
        log_scrape(source, "success", found, saved)

    return found, saved


# ── 3. CAPITAL MARKETS MONGOLIA ───────────────────────────────────────────────
def scrape_capital_markets_mn() -> tuple[int, int]:
    """
    capitalmarkets.mn — professional MSE research and analysis.
    100% relevant — every article is about Mongolian capital markets.
    """
    source = "capitalmarkets.mn"
    base   = "https://capitalmarkets.mn"
    print(f"\n{'─'*54}")
    print(f"  Scraping: {source}")

    found = saved = 0
    seen  = set()

    entry_points = [f"{base}/insight", base, f"{base}/news", f"{base}/research"]

    reached = False
    for entry in entry_points:
        soup = fetch_page(entry)
        if not soup:
            continue
        reached = True

        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 10:
                continue
            if href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                continue
            if href in seen or "capitalmarkets.mn" not in href:
                continue
            if href.rstrip("/") in [base, f"{base}/news", f"{base}/research", f"{base}/markets", f"{base}/insight"]:
                continue
            seen.add(href)
            found += 1
            content, published_at = fetch_article_text(href)
            lang = detect_language(f"{title} {content}")
            article_id = save_article(
                source=source, source_type="news",
                title=title, content=content or title,
                url=href, language=lang, published_at=published_at,
            )
            if article_id:
                saved += 1
                print(f"  ✓ [{lang}] {title[:70]}")
            time.sleep(0.4)

        time.sleep(1.5)

    if not reached:
        print(f"  ❌ Could not reach {source}")
        log_scrape(source, "failed", 0, 0)
    else:
        print(f"\n  {source}: {found} found, {saved} new saved")
        log_scrape(source, "success", found, saved)

    return found, saved


# ── MAIN ──────────────────────────────────────────────────────────────────────
def run_all_new_sources():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*54}")
    print(f"  New Sources Scraper — {now}")
    print(f"{'='*54}")

    results = {}
    for name, fn in [
        ("Mining Journal", lambda: scrape_mining_journal(max_pages=5)),
        ("Mongolbank",     scrape_mongolbank),
        ("Capital Markets", scrape_capital_markets_mn),
    ]:
        f, s = fn()
        results[name] = (f, s)
        time.sleep(3)

    print(f"\n{'='*54}")
    print("  Summary")
    print(f"{'─'*54}")
    for name, (f, s) in results.items():
        status = "✅" if s > 0 else "⚠️ " if f > 0 else "❌"
        print(f"  {status} {name:25s} found={f:4d}  saved={s:4d}")
    print(f"{'='*54}")


if __name__ == "__main__":
    run_all_new_sources()