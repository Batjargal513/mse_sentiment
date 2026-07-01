"""
Tests for utils.date_utils — date parsing used by every scraper to populate
articles.published_at.
"""

from datetime import datetime, timezone

from utils.date_utils import parse_date, parse_relative_date


# ── Absolute formats ──────────────────────────────────────────────────────────

def test_iso_date():
    assert parse_date("2026-04-22").startswith("2026-04-22")


def test_iso_datetime_with_tz():
    out = parse_date("2026-04-22T14:30:00+00:00")
    assert out.startswith("2026-04-22")


def test_mongolian_dotted_date():
    # 22.04.2026 → 22 April 2026
    assert parse_date("22.04.2026").startswith("2026-04-22")


def test_english_long_date():
    assert parse_date("April 22, 2026").startswith("2026-04-22")


def test_date_embedded_in_text():
    # Last-resort regex extraction
    assert parse_date("Published on 2026-04-22 by editor").startswith("2026-04-22")


# ── Unparseable input ─────────────────────────────────────────────────────────

def test_empty_returns_none():
    assert parse_date("") is None


def test_garbage_returns_none():
    assert parse_date("not a date at all") is None


# ── Relative dates (Mongolian + English) ──────────────────────────────────────

def test_english_days_ago():
    out = parse_relative_date("3 days ago")
    assert out is not None
    parsed = datetime.fromisoformat(out)
    delta_days = (datetime.now(timezone.utc) - parsed).days
    assert 2 <= delta_days <= 3


def test_mongolian_days_ago():
    # "2 өдрийн өмнө" = "2 days ago"
    out = parse_relative_date("2 өдрийн өмнө")
    assert out is not None
    parsed = datetime.fromisoformat(out)
    delta_days = (datetime.now(timezone.utc) - parsed).days
    assert 1 <= delta_days <= 2


def test_today_keyword():
    assert parse_relative_date("өнөөдөр").startswith(
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )


def test_non_relative_returns_none():
    assert parse_relative_date("2026-04-22") is None
