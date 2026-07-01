"""
Tests for smaller pure helpers: smart_truncate, get_channel, and the
Cyrillic-ratio language detector used by the scrapers.
"""

from sentiment_processor import smart_truncate, get_channel
from scrapers.rss_scraper import detect_language


# ── smart_truncate ────────────────────────────────────────────────────────────

def test_short_text_is_unchanged():
    text = "Short article body."
    assert smart_truncate(text, max_chars=900) == text


def test_long_text_keeps_head_and_tail():
    head = "A" * 600
    tail = "Z" * 600
    text = head + tail
    out = smart_truncate(text, max_chars=400)
    # Should be shorter than original and keep both ends (financials often at end)
    assert len(out) < len(text)
    assert out.startswith("A")
    assert out.endswith("Z")
    assert " … " in out


# ── get_channel ───────────────────────────────────────────────────────────────

def test_telegram_is_social_channel():
    assert get_channel("telegram") == "social"


def test_news_sources_are_news_channel():
    assert get_channel("scraper") == "news"
    assert get_channel("official_api") == "news"
    assert get_channel("regulatory") == "news"


def test_channel_is_case_insensitive():
    assert get_channel("Telegram") == "social"


# ── detect_language ───────────────────────────────────────────────────────────

def test_cyrillic_text_is_mongolian():
    assert detect_language("Энэ бол монгол хэл дээрх текст юм") == "mn"


def test_latin_text_is_english():
    assert detect_language("This is an English news article") == "en"
