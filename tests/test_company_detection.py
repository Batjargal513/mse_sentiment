"""
Tests for sentiment_processor.detect_companies — the ticker-detection logic.

The important behaviour here is the false-positive prevention: common
Mongolian words (Ард = people, Говь = Gobi desert, Сүү = milk) must NOT be
mistaken for the tickers AARD / GOV / SUU.
"""

from sentiment_processor import detect_companies


# ── Positive matches ──────────────────────────────────────────────────────────

def test_detects_ascii_ticker_with_word_boundary():
    assert "APU" in detect_companies("APU announced a 30% dividend increase")


def test_detects_mongolian_compound_name():
    # "Хас банк" (XacBank) is a keyword for XAC
    assert "XAC" in detect_companies("Хас банк reported strong quarterly earnings")


def test_khan_bank_is_not_xacbank():
    # Khan Bank is a DIFFERENT bank from XacBank — it must not map to ticker XAC
    assert "XAC" not in detect_companies("EBRD invests US$170M in Khan Bank")
    assert "XAC" not in detect_companies("Хаан банк улирлын тайлангаа танилцууллаа")


def test_detects_english_company_name():
    assert "GLMT" in detect_companies("Golomt Bank issued a new bond")


def test_detects_multiple_tickers_in_one_text():
    found = detect_companies("Both APU and Golomt Bank rose today")
    assert "APU" in found
    assert "GLMT" in found


# ── False-positive prevention (the whole point of the keyword cleanup) ─────────

def test_bare_ard_is_not_aard():
    # "Ард түмэн" = "the people" — must not trigger the AARD ticker
    assert "AARD" not in detect_companies("Ард түмэн өнөөдөр чуулганд цугларлаа")


def test_bare_gobi_desert_is_not_gov():
    # "Говь нутаг" = "the Gobi region" — must not trigger GOV
    assert "GOV" not in detect_companies("Манай улсын говь нутгаар аялал хийлээ")


def test_bare_milk_is_not_suu():
    # "сүү" = milk — must not trigger SUU
    assert "SUU" not in detect_companies("Өнөөдөр би сүү уулаа")


def test_ascii_ticker_inside_word_is_not_matched():
    # "APU" embedded in a larger word must not match (word-boundary rule)
    assert "APU" not in detect_companies("The village of SAPUNA is remote")


def test_unrelated_text_returns_nothing():
    assert detect_companies("The weather in Ulaanbaatar is cold today") == []


def test_proper_aard_name_still_matches():
    # The legitimate company reference must still be found
    assert "AARD" in detect_companies("Ард Санхүүгийн Групп released results")
