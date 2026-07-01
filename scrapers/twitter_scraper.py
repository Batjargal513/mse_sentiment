"""
MSE Sentiment — Twitter/X Scraper (social source)
Pulls Mongolian finance tweets via Scweet and stores them as articles with
source_type="twitter" → automatically tagged as the 'social' channel (same as
Telegram). Company detection happens later, at scoring time (detect_companies).

Ported from the standalone twitter_scraping repo: instead of writing CSV, each
tweet is saved through db.save_article (deduplicated by tweet URL).

Setup:
  pip install scweet
  export X_AUTH_TOKEN="<auth_token cookie from a THROWAWAY x.com account>"
  # Get it: log into x.com → DevTools → Application → Cookies →
  #         https://x.com → copy the `auth_token` value.

Test pull (last 7 days, from repo root):
  PYTHONPATH=. python scrapers/twitter_scraper.py
"""

import time
from datetime import datetime, timezone, timedelta

from config.settings import X_AUTH_TOKEN, TWITTER_QUERIES, MAX_ARTICLE_CHARS
from db.supabase import save_article, log_scrape
from utils.date_utils import parse_date

SOURCE_NAME  = "twitter"
QUERY_SLEEP  = 5     # seconds between queries (stay under X rate limits)


def _get_client():
    """Build a Scweet client lazily so this module imports without scweet installed."""
    if not X_AUTH_TOKEN:
        raise RuntimeError("X_AUTH_TOKEN is not set — add it to your .env")
    from Scweet import Scweet                 # v5.3+ top-level export
    from Scweet.config import ScweetConfig
    cfg = ScweetConfig(
        daily_requests_limit=500,
        daily_tweets_limit=10_000,
        requests_per_min=20,                  # under X's ~30 RPM cap
        min_delay_s=3.0,
    )
    return Scweet(auth_token=X_AUTH_TOKEN, manifest_scrape_on_init=False, config=cfg)


def detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    return "mn" if cyrillic > len(text) * 0.2 else "en"


# ── Defensive field extraction (Scweet's dict keys differ across versions) ─────
def _text(t: dict) -> str:
    return (t.get("text") or t.get("content") or t.get("tweet") or "").strip()


def _tweet_id(t: dict) -> str:
    return str(t.get("tweet_id") or t.get("id") or t.get("id_str") or "")


def _username(t: dict) -> str:
    u = t.get("username") or t.get("user") or t.get("screen_name") or t.get("handle") or ""
    if isinstance(u, dict):
        u = u.get("username") or u.get("screen_name") or ""
    return str(u).lstrip("@")


def _url(t: dict) -> str | None:
    for k in ("url", "tweet_url", "link", "permalink"):
        if t.get(k):
            return t[k]
    tid = _tweet_id(t)
    if tid:
        return f"https://x.com/{_username(t) or 'i'}/status/{tid}"
    return None  # no stable id → can't dedup → skip


def _published_at(t: dict) -> str | None:
    raw = t.get("date") or t.get("created_at") or t.get("timestamp") or t.get("time")
    return parse_date(str(raw)) if raw else None


def scrape_twitter(days_back: int = 7, limit: int = 200) -> tuple[int, int]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  Twitter/X scraper — {now}")
    if not TWITTER_QUERIES:
        print("  No TWITTER_QUERIES configured.")
        return 0, 0

    client = _get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_found = total_saved = 0
    for query in TWITTER_QUERIES:
        try:
            tweets = client.search(
                query=query, since=since, until=until,
                display_type="Latest", limit=limit,
            ) or []
        except Exception as e:
            print(f"  [!] '{query}' error: {type(e).__name__}: {e}")
            time.sleep(QUERY_SLEEP)
            continue

        saved = 0
        for t in tweets:
            text = _text(t)
            if len(text) < 10:
                continue
            url = _url(t)
            if not url:                      # skip tweets we can't dedup
                continue
            total_found += 1
            article_id = save_article(
                source       = SOURCE_NAME,
                source_type  = SOURCE_NAME,  # "twitter" → social channel
                title        = text[:100],
                content      = text[:MAX_ARTICLE_CHARS],
                url          = url,
                language     = detect_language(text),
                published_at = _published_at(t),
            )
            if article_id:
                saved += 1
        total_saved += saved
        print(f"  '{query}': {len(tweets)} tweets, {saved} new saved")
        time.sleep(QUERY_SLEEP)

    print(f"\n  Twitter: {total_found} found, {total_saved} new saved")
    log_scrape(SOURCE_NAME, "success", total_found, total_saved)
    return total_found, total_saved


if __name__ == "__main__":
    print("\nMSE Sentiment — Twitter/X Scraper")
    print("Requires: pip install scweet  +  X_AUTH_TOKEN env var")
    print(f"Queries  : {len(TWITTER_QUERIES)} finance terms\n")
    scrape_twitter(days_back=7)
