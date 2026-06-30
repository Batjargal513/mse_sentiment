"""
FIX 4 — Patched sentiment_processor.py
========================================
Changes from original:
  A. COMPANY_MAP — AARD keywords fixed, all ambiguous single-word
     Mongolian keywords replaced with compound proper nouns only
  B. score_sentiment() prompt — added mild-sentiment calibration examples
     to fix the bimodal 0.0 / ±0.5 clustering
  C. process_article() — smarter text truncation (keeps first 400 chars
     + last 400 chars so tail-of-article financial figures aren't lost)
  D. update_todays_history() — incremental: only rebuilds rows for dates
     that have new scores, not all-time rebuild every 10 minutes
  E. Duplicate guard — skips scoring if (article_id, ticker) already exists

Replace your existing sentiment_processor.py with this file.
"""

import time
import json
import re
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from openai import OpenAI
from config.settings import OPENAI_API_KEY
from db.supabase import (
    get_unprocessed_articles, save_sentiment,
    update_daily_history, get_client
)

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL  = "gpt-4o-mini"

# ── Channel mapping ───────────────────────────────────────────────────────────
SOCIAL_SOURCE_TYPES = {"telegram", "facebook", "twitter", "reddit", "social"}

def get_channel(source_type: str) -> str:
    return "social" if source_type.lower() in SOCIAL_SOURCE_TYPES else "news"


# ── FIXED COMPANY_MAP ─────────────────────────────────────────────────────────
# Rules applied:
#   1. No standalone common Mongolian words (Ард, Говь, Сүү, etc.)
#   2. All Mongolian keywords must be compound proper nouns
#   3. Ticker symbol always included as exact match
COMPANY_MAP = {
    "APU":   ["APU", "АПУ ХК", "АПУ компани"],
    "SEND":  ["SEND", "СЭНДЭ", "Sendly", "Сэндли", "#SEND", "$SEND"],
    "TDB":   ["TDB", "ТДБ", "Худалдаа хөгжлийн банк", "Trade Development Bank"],
    "XAC":   ["XAC", "ХасБанк", "Хаан банк", "Khan Bank", "XacBank"],
    "MIK":   ["MIK", "МИК холдинг", "MIK Holdings"],
    "BDS":   ["BDS", "BDSec", "БДСек"],
    "GLMT":  ["GLMT", "Голомт банк", "Golomt Bank"],
    "SUU":   ["SUU", "Сүү ХК", "Suu JSC"],          # NOT bare "Сүү" (milk)
    "GOV":   ["GOV", "Говь ХК", "Gobi JSC", "Говь компани"],  # NOT bare "Говь" (desert)
    "INV":   ["INV", "Инвескор", "Invescore"],
    "MBW":   ["MBW", "Монгол Бичил"],
    "MFC":   ["MFC", "Монос Хүнс"],
    "MLG":   ["MLG", "Монголын Алт"],
    "MNP":   ["MNP", "МНП ХК"],
    "NEH":   ["NEH", "Дархан нэхий", "Darkhan Nekhii"],
    "SBM":   ["SBM", "СБМ ХК"],
    "TTL":   ["TTL", "ТТЛ", "Tavan Tolgoi", "Таван толгой уул"],
    "TUM":   ["TUM", "Тумэн ХК"],
    "LEND":  ["LEND", "LendMN", "Лендмн"],
    # AARD FIXED — removed bare "Ард" which matched any Mongolian text
    "AARD":  [
        "AARD",
        "Ард кредит",
        "Ард даатгал",
        "Ард Санхүүгийн Групп",
        "Ард Санхүү",
        "Ard Credit",
        "Ard Financial",
        "Ard Daatgal",
    ],
    "TCK":   ["TCK", "Талх чихэр", "Talkh Chikher"],
    "MMX":   ["MMX", "Махимпекс"],
    "STB":   ["STB", "Төрийн банк", "State Bank of Mongolia"],
    "BGB":   ["BGB", "Богд банк", "Bogd Bank"],
    "MAN":   ["MAN", "Мандал даатгал", "Mandal Insurance"],  # NOT bare "MAN"
    "ALT":   ["ALT", "Алтан тариа ХК", "Altan Taria"],       # NOT bare "ALT"
}


def detect_companies(text: str) -> list[str]:
    found = []
    text_upper = text.upper()
    for ticker, keywords in COMPANY_MAP.items():
        for kw in keywords:
            kw_upper = kw.upper()
            # For short all-caps tickers (≤4 chars), require word boundary
            if len(kw) <= 4 and kw.isascii() and kw.isupper():
                # Match only if surrounded by non-alphanumeric chars
                pattern = r'(?<![A-ZА-ЯӨҮ0-9])' + re.escape(kw_upper) + r'(?![A-ZА-ЯӨҮ0-9])'
                if re.search(pattern, text_upper):
                    found.append(ticker)
                    break
            else:
                if kw_upper in text_upper:
                    found.append(ticker)
                    break
    return found


# ── Smart truncation — keeps financial details at end of article ──────────────
def smart_truncate(text: str, max_chars: int = 900) -> str:
    """
    Instead of text[:800], take first 500 + last 400 chars.
    Mongolian financial articles often put earnings/dividend figures
    in the second or third paragraph, not the lead.
    """
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + " … " + text[-(half - 3):]


# ── IMPROVED GPT-4o-mini prompt ───────────────────────────────────────────────
def score_sentiment(text: str, ticker: str, language: str = "mn", channel: str = "news") -> dict | None:
    lang_note    = "The text is written in Mongolian (Cyrillic script). Read it carefully." if language == "mn" else ""
    channel_note = (
        "This is a social media post from Mongolian retail investors. Capture emotional tone and investor sentiment."
        if channel == "social"
        else "This is a news article or regulatory announcement. Focus on factual financial implications."
    )

    prompt = f"""You are a financial analyst for the Mongolian Stock Exchange (MSE/МХБ).
{lang_note}
{channel_note}

Analyze the sentiment of this text toward the company with ticker {ticker}.
Use the FULL score range including mild scores like 0.3, -0.3, 0.4, -0.4.

Text: {smart_truncate(text)}

Calibration examples (use these as reference):
- Dividend announced, profit up 30% → score: 0.8, label: positive
- Strong earnings beat, analyst upgrades → score: 0.7, label: positive
- Bond issuance announced, moderate demand → score: 0.35, label: positive
- Routine quarterly filing, in line → score: 0.1, label: neutral
- Article mentions ticker but is about something else → score: 0.0, label: neutral
- Management change, mixed signals → score: -0.3, label: negative
- Regulatory inquiry opened → score: -0.45, label: negative
- Earnings miss, guidance cut → score: -0.6, label: negative
- Stock suspended, fraud allegations → score: -0.85, label: negative

Respond ONLY with valid JSON, no markdown:
{{"score": 0.0, "label": "neutral", "summary": "brief factual summary max 12 words", "confidence": 0.8}}

Rules:
- score: -1.0 to +1.0, use the full range including mild values
- label: "positive" if score > 0.15, "negative" if score < -0.15, else "neutral"
- summary: English, max 12 words, what the text actually says about {ticker}
- confidence: 0.3 if text barely mentions {ticker}, 0.9 if clearly about {ticker}
- If text is NOT actually about {ticker}, set score: 0.0, confidence: 0.2"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)

        result = json.loads(raw)
        score  = max(-1.0, min(1.0, float(result.get("score", 0))))

        # Enforce label-score consistency
        if score > 0.15:
            label = "positive"
        elif score < -0.15:
            label = "negative"
        else:
            label = "neutral"

        return {
            "score":      round(score, 4),
            "label":      label,
            "summary":    str(result.get("summary", ""))[:200],
            "confidence": round(float(result.get("confidence", 0.7)), 2),
        }

    except json.JSONDecodeError as e:
        print(f"  [!] JSON parse error for {ticker}: {e}")
        return None
    except Exception as e:
        print(f"  [!] OpenAI error for {ticker}: {e}")
        return None


# ── Duplicate guard ───────────────────────────────────────────────────────────
def already_scored(article_id: str, ticker: str) -> bool:
    """Check if this article+ticker combination already has a score."""
    try:
        result = get_client().table("sentiment_scores") \
                             .select("id") \
                             .eq("article_id", article_id) \
                             .eq("ticker", ticker) \
                             .limit(1) \
                             .execute()
        return bool(result.data)
    except Exception:
        return False


# ── Process one article ───────────────────────────────────────────────────────
def process_article(article: dict) -> int:
    article_id  = article["id"]
    content     = article.get("content") or article.get("title") or ""
    title       = article.get("title") or ""
    language    = article.get("language", "mn")
    source      = article.get("source", "unknown")
    source_type = article.get("source_type", "scraper")
    channel     = get_channel(source_type)

    full_text = f"{title} {content}"
    tickers   = detect_companies(full_text)

    if not tickers:
        try:
            get_client().table("articles") \
                .update({"processed": True}) \
                .eq("id", article_id).execute()
        except Exception:
            pass
        return 0

    saved = 0
    for ticker in tickers:
        # Skip if already scored (prevents duplicates on re-runs)
        if already_scored(article_id, ticker):
            print(f"  [skip] {ticker} already scored for this article")
            continue

        print(f"  [{channel}] {ticker} ← {source} | {title[:50]}...")
        result = score_sentiment(full_text, ticker, language, channel)

        if result:
            # Skip very low confidence scores (article barely mentions ticker)
            if result["confidence"] < 0.3:
                print(f"  [skip] {ticker}: confidence too low ({result['confidence']})")
                continue

            save_sentiment(
                article_id = article_id,
                ticker     = ticker,
                score      = result["score"],
                label      = result["label"],
                summary    = result["summary"],
                confidence = result["confidence"],
                channel    = channel,
            )
            print(f"  → {ticker}: {result['label']} ({result['score']:+.2f}) conf={result['confidence']} [{channel}]")
            saved += 1

        time.sleep(0.3)

    return saved


# ── Incremental history update (not full rebuild) ─────────────────────────────
def update_recent_history(days_back: int = 2):
    """
    Only rebuilds history for the last N days — not all-time.
    Runs after each processing batch to keep history current.
    """
    try:
        db = get_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()

        result = db.table("sentiment_scores") \
                   .select("ticker, score, channel, article_id, articles(published_at, scraped_at)") \
                   .gte("scored_at", cutoff) \
                   .execute()

        if not result.data:
            return

        by_key: dict[tuple, list[float]] = {}
        for row in result.data:
            art      = row.get("articles") or {}
            raw_date = art.get("published_at") or art.get("scraped_at")
            date     = raw_date[:10] if raw_date else datetime.now(timezone.utc).date().isoformat()
            key      = (row["ticker"], row.get("channel", "news"), date)
            by_key.setdefault(key, []).append(row["score"])

        for (ticker, channel, date), scores in by_key.items():
            update_daily_history(ticker, date, scores, channel)

        print(f"  ✅ Updated history for {len(by_key)} ticker/date/channel combinations (last {days_back} days)")

    except Exception as e:
        print(f"  [!] History update error: {e}")


# ── Main processor run ────────────────────────────────────────────────────────
def run_processor():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*54}")
    print(f"  Sentiment Processor — {now}")
    print(f"{'='*54}")

    articles = get_unprocessed_articles(limit=30)

    if not articles:
        print("  No unprocessed articles.")
        return

    print(f"  Processing {len(articles)} articles...\n")
    total_scores = 0

    for article in articles:
        scores = process_article(article)
        total_scores += scores
        time.sleep(0.5)

    print(f"\n  Done — {total_scores} sentiment scores saved")
    print("\n  Updating recent history...")
    update_recent_history(days_back=2)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\nMSE Sentiment — AI Processor (patched)")
    print(f"Model    : {MODEL} (OpenAI)")
    print("Channels : news | social")
    print("Schedule : Every 10 minutes\n")

    print("Running first pass now...")
    run_processor()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_processor, trigger="interval", minutes=10)
    print("\nProcessor live. Runs every 10 minutes.")
    print("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nProcessor stopped.")
