"""
MSE Sentiment — Date parsing utility
Used by all scrapers to extract published_at from various formats.
"""

import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup


# ── Parse from common string formats ─────────────────────────────────────────

FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",       # ISO 8601 with tz
    "%Y-%m-%dT%H:%M:%SZ",        # ISO 8601 UTC
    "%Y-%m-%dT%H:%M:%S",         # ISO 8601 no tz
    "%Y-%m-%d %H:%M:%S",         # MySQL datetime
    "%Y-%m-%d",                  # date only
    "%d.%m.%Y %H:%M",            # Mongolian common: 22.04.2026 14:30
    "%d.%m.%Y",                  # Mongolian date only: 22.04.2026
    "%d/%m/%Y",
    "%B %d, %Y",                 # April 22, 2026
    "%b %d, %Y",                 # Apr 22, 2026
]

# Mongolian month names → numbers
MN_MONTHS = {
    "1-р сар": 1,  "2-р сар": 2,  "3-р сар": 3,  "4-р сар": 4,
    "5-р сар": 5,  "6-р сар": 6,  "7-р сар": 7,  "8-р сар": 8,
    "9-р сар": 9,  "10-р сар": 10, "11-р сар": 11, "12-р сар": 12,
    "Нэгдүгээр": 1, "Хоёрдугаар": 2, "Гуравдугаар": 3, "Дөрөвдүгээр": 4,
    "Тавдугаар": 5, "Зургадугаар": 6, "Долдугаар": 7, "Наймдугаар": 8,
    "Есдүгээр": 9, "Аравдугаар": 10, "Арван нэгдүгээр": 11, "Арван хоёрдугаар": 12,
}



def parse_relative_date(text: str) -> str | None:
    """
    Parse Mongolian/English relative dates like:
    '3 жилийн өмнө', '2 өдрийн өмнө', '5 цагийн өмнө'
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    t = text.strip().lower()

    patterns = [
        (r"(\d+)\s*жилийн өмнө",          "years"),
        (r"(\d+)\s*жил өмнө",              "years"),
        (r"(\d+)\s*сарын өмнө",            "months"),
        (r"(\d+)\s*долоо хоногийн өмнө",   "weeks"),
        (r"(\d+)\s*өдрийн өмнө",           "days"),
        (r"(\d+)\s*өдөр өмнө",             "days"),
        (r"(\d+)\s*цагийн өмнө",           "hours"),
        (r"(\d+)\s*цаг өмнө",              "hours"),
        (r"(\d+)\s*минутын өмнө",          "minutes"),
        (r"(\d+)\s*years? ago",             "years"),
        (r"(\d+)\s*months? ago",            "months"),
        (r"(\d+)\s*weeks? ago",             "weeks"),
        (r"(\d+)\s*days? ago",              "days"),
        (r"(\d+)\s*hours? ago",             "hours"),
        (r"(\d+)\s*minutes? ago",           "minutes"),
    ]

    for pattern, unit in patterns:
        m = re.search(pattern, t)
        if m:
            n = int(m.group(1))
            if unit == "years":
                try:
                    dt = now.replace(year=now.year - n)
                except ValueError:
                    dt = now.replace(year=now.year - n, day=28)
            elif unit == "months":
                total = now.month - n
                year  = now.year + (total - 1) // 12
                month = ((total - 1) % 12) + 1
                dt = now.replace(year=year, month=month)
            elif unit == "weeks":
                from datetime import timedelta as td
                dt = now - td(weeks=n)
            elif unit == "days":
                from datetime import timedelta as td
                dt = now - td(days=n)
            elif unit == "hours":
                from datetime import timedelta as td
                dt = now - td(hours=n)
            elif unit == "minutes":
                from datetime import timedelta as td
                dt = now - td(minutes=n)
            else:
                continue
            return dt.isoformat()

    from datetime import timedelta as td
    if "өнөөдөр" in t or "today" in t:
        return now.isoformat()
    if "өчигдөр" in t or "yesterday" in t:
        return (now - td(days=1)).isoformat()

    return None

def parse_date(text: str) -> str | None:
    """
    Try to parse a date string into ISO 8601 UTC string.
    Returns None if unparseable.
    """
    if not text:
        return None

    text = text.strip()

    # Try relative dates first ("3 жилийн өмнө", "2 days ago")
    relative = parse_relative_date(text)
    if relative:
        return relative

    # Replace Mongolian month names
    for mn_name, num in MN_MONTHS.items():
        text = text.replace(mn_name, str(num))

    # Try standard formats
    for fmt in FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue

    # Try extracting a date pattern with regex as last resort
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", text)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                          tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    return None


# ── Extract from HTML soup ────────────────────────────────────────────────────

def extract_date_from_soup(soup: BeautifulSoup) -> str | None:
    """
    Try to find a published date in a BeautifulSoup page.
    Checks meta tags, time elements, and common CSS classes.
    """
    # 1. Meta tags (most reliable)
    for prop in ["article:published_time", "og:published_time",
                 "datePublished", "DC.date", "pubdate"]:
        tag = soup.find("meta", attrs={"property": prop}) or \
              soup.find("meta", attrs={"name": prop}) or \
              soup.find("meta", attrs={"itemprop": prop})
        if tag and tag.get("content"):
            result = parse_date(tag["content"])
            if result:
                return result

    # 2. <time> element
    for time_tag in soup.find_all("time"):
        dt = time_tag.get("datetime") or time_tag.get_text(strip=True)
        result = parse_date(dt)
        if result:
            return result

    # 3. Common CSS classes / attributes
    selectors = [
        "[class*='date']", "[class*='time']", "[class*='publish']",
        "[class*='posted']", "[class*='created']", "[itemprop='datePublished']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get("content") or el.get("datetime") or el.get_text(strip=True)
            result = parse_date(text)
            if result:
                return result

    return None


# ── Extract from RSS feed entry ───────────────────────────────────────────────

def extract_date_from_feed_entry(entry) -> str | None:
    """Extract published date from a feedparser entry."""
    import time as time_module

    # feedparser parses dates into time structs
    for field in ["published_parsed", "updated_parsed", "created_parsed"]:
        t = getattr(entry, field, None)
        if t:
            try:
                dt = datetime.fromtimestamp(time_module.mktime(t), tz=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

    # Fallback: raw string fields
    for field in ["published", "updated", "created"]:
        raw = getattr(entry, field, None)
        if raw:
            result = parse_date(raw)
            if result:
                return result

    return None