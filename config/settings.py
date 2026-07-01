"""
MSE Sentiment — Config
Load all settings from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")      # legacy — no longer used for scoring
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")   # Claude Haiku 4.5 sentiment scoring

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY", "")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_API_ID   = int(os.environ.get("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE    = os.environ.get("TELEGRAM_PHONE", "")

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── Twitter / X ───────────────────────────────────────────────────────────────
# auth_token cookie from a logged-in (throwaway) x.com account — see twitter_scraper.py
X_AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "")

# ── Telegram groups to monitor ────────────────────────────────────────────────
TELEGRAM_GROUPS = [
    "openmindmse",
    "bibbytimes",
]

# ── RSS feeds ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    {"name": "news.mn",      "url": "https://news.mn/rss"},
    {"name": "montsame.mn",  "url": "https://montsame.mn/mn/rss"},
    {"name": "montsame_en",  "url": "https://montsame.mn/en/rss"},
]

# ── Google News search queries (English-only — eliminates Russian contamination)
# Cyrillic queries return mixed Russian/Mongolian results due to shared alphabet
GOOGLE_NEWS_QUERIES = [
    "Mongolia Stock Exchange",
    "MSE Mongolia stock",
    "Mongolia Stock Exchange dividend",
    "Mongolia Stock Exchange investor",
    "Oyu Tolgoi stock",
    "Tavan Tolgoi investment",
    "Mongolia mining stock",
    "Golomt Bank Mongolia",
    "Khan Bank Mongolia",
    "Trade Development Bank Mongolia",
    "Ard Financial Mongolia",
    "Mongolia IPO listing",
    "Mongolia bond market",
]

# ── Twitter/X search queries (social source) ──────────────────────────────────
# Finance-targeted Mongolian queries. Tweets matching these are saved as
# source_type="twitter" (→ 'social' channel); detect_companies maps them to
# tickers later at scoring time.
TWITTER_QUERIES = [
    "хувьцаа", "хувьцааны зах зээл", "ногдол ашиг",
    "МХБ хувьцаа", "Монголын хөрөнгийн бирж",
    "хөрөнгийн бирж", "хөрөнгө оруулалт хувьцаа",
    "хувьцаа арилжаа", "брокер хувьцаа",
    "Оюу толгой хувьцаа", "Оюутолгой ногдол ашиг",
    "Тавантолгой хувьцаа", "ETT хувьцаа",
    "АПУ хувьцаа", "АПУ ХК",
    "Голомт банк хувьцаа", "Хаан банк хувьцаа",
    "Худалдаа хөгжлийн банк хувьцаа",
    "IPO Монгол", "хувьцаа гаргах",
    "from:BloombergTVM",
]

# ── MSE company keywords ──────────────────────────────────────────────────────
# Rules:
#   1. No standalone common Mongolian words (Ард, Говь, Сүү, Мах etc.)
#   2. All Mongolian keywords must be compound proper nouns
#   3. Ticker symbols always included as exact match
MSE_KEYWORDS = [
    # ── General MSE market terms ──────────────────────────────────────────────
    "МХБ", "хувьцаа", "ногдол ашиг", "IPO", "бонд", "bond",
    "stock", "shares", "dividend", "MSE", "bourse", "арилжаа",
    "зах зээл", "хөрөнгийн бирж", "хөрөнгө оруулалт",
    "тендер", "дүрэм", "андеррайтер", "листинг",
    "хаалт", "нээлт", "индекс", "TOP-20", "TOP20",

    # ── Top 20 / high-volume tickers ─────────────────────────────────────────
    "APU", "АПУ",
    "BDS", "BDSec", "БДС",
    "GOV", "Говь ХК", "Gobi JSC",          # FIXED: removed bare "Говь" (= Gobi desert)
    "SUU", "Сүү ХК", "Suu JSC",            # FIXED: removed bare "Suu"/"СУУ" (= milk)
    "TDB", "ТДБ", "Худалдаа хөгжлийн банк",
    "GLMT", "Голомт банк", "Golomt Bank",
    "XAC", "ХАС", "Хас банк", "XacBank",   # XacBank only — NOT Khan Bank (different bank)
    "MIK", "МИК",
    "LEND", "LendMN", "Лендмн",
    "AARD", "Ард кредит", "Ард даатгал",    # FIXED: removed bare "Ард" (= people/citizen)
    "Ард Санхүү", "Ard Credit", "Ard Financial",
    "MFC", "Монос Хүнс",
    "MNP", "МНП",
    "NEH", "Darkhan Nekhii", "Дархан нэхий",
    "TCK", "Talkh Chikher", "Талх чихэр",
    "MMX", "Makhimpecs", "Махимпекс",
    "INV", "Invescore", "Инвескор",
    "TTL", "ТТЛ",
    "TUM", "Тумэн ХК",
    "SBM", "СБМ",
    "MLG", "Монголын Алт",
    "MBW", "Монгол Бичил",
    "SEND", "СЭНДЭ", "Sendly",

    # ── Banks & Financial ─────────────────────────────────────────────────────
    "State Bank", "Төрийн банк", "STB",
    "Bogd Bank", "Богд банк", "BGB",
    "Capital Bank", "Капитал банк",
    "Chinggis Khaan Bank", "Чингис хаан банк",
    "Khas Bank", "Хас банк",
    "Arig Bank", "Ариг банк",
    "Zoos Bank", "Зоос банк",
    "Mandal Daatgal", "Мандал даатгал", "MAN",
    "Ard Daatgal", "Ард даатгал",
    "Mongol Daatgal",

    # ── Mining & Energy ───────────────────────────────────────────────────────
    "Shivee Ovoo", "Шивээ овоо", "SHV",
    "Эрдэнэт үйлдвэр", "Erdenet Mining",   # FIXED: was bare "Эрдэнэт" (= city name too)
    "Oyu Tolgoi", "Оюу толгой",
    "Tavan Tolgoi", "Таван толгой уул",
    "Khailaast", "HST",
    "Mongolrostsvetmet",
    "CUMN", "Зэс үйлдвэр",                 # FIXED: removed bare "Copper"/"Зэс"
    "Altai Gold", "ATA",                    # FIXED: removed bare "Altai"/"Алтай" (= region)
    "Mongol Alt", "ERS",
    "Bayanmod", "BNM",

    # ── Consumer & Food ───────────────────────────────────────────────────────
    "Дархан мах ХК", "HSH",                # FIXED: removed bare "Makh"/"Мах" (= meat)
    "Altan Taria", "Алтан тариа ХК", "ALT",
    "ATR", "GUR", "BYN", "HNG",

    # ── Retail & Trade ────────────────────────────────────────────────────────
    "Central Express", "Централ экспресс", "CEC",
    "Nomin Holdings", "Номин холдинг",      # FIXED: was bare "Nomin"/"Номин"
    "Ard Supermarket",
    "Zoos Goyol", "ZOO",
    "Juulchin", "JUU",

    # ── Telecom & Tech ────────────────────────────────────────────────────────
    "MCH", "Mongoliin Tsakhilgaan",
    "Unitel", "Юнител",
    "Skytel", "Скайтел",
    "MobiCom", "Мобиком",

    # ── Construction & Real Estate ────────────────────────────────────────────
    "Barilga Corporation", "ASA", "USIB", "USB",

    # ── Cashmere & Textile ────────────────────────────────────────────────────
    "Gobi Cashmere", "Говь кашмир",
    "Tuul Cashmere", "TUL",
    "Buligaar", "MBG",
    "Gutal", "GTL",
    "Takhi Ko", "TAH",
    "Eermel", "EER",
    "Monnoos", "MNS",

    # ── Other listed tickers (catch-all) ──────────────────────────────────────
    "BNG", "ZOO", "MIE", "MSC", "NIC", "OHR", "SBB", "SSG",
    "HST", "ULN", "UID", "ERH", "UYN", "CSU", "TLG", "JUU",
    "UBH", "HRD", "MNH", "MSV", "AGA", "ATR", "MZR", "HIE",
    "DRU", "MNS", "BGL", "MIB", "MMH", "TUL", "HMK", "CND",
    "SUL", "SOI", "MBG", "ALT", "KEK", "TVL", "TAH", "MSD",
    "ASA", "USB", "HOR", "CCL", "NUR", "HTR", "URN", "ARZ",
    "JGV", "BNM", "HSH", "HBZ", "NXE", "ERS", "BHG", "NEH",
    "ZES", "BTL", "HVL", "MNG", "MAG", "BND", "LZB", "JGL",
    "GTL", "MSL", "CGC", "BBG", "GUU", "GUR", "SOR", "ULZ",
    "AVT", "URT", "HUV", "ARH", "SVN", "IND", "HLG", "ORL",
    "DLH", "ATA", "HAH", "BYN", "ARI", "MNM", "HML", "BJT",
    "NLH", "ZST", "AYN", "AZA", "DRN", "HRL", "SGT", "TMZ",
    "AHH", "CCA", "HAL", "MSI", "BLA", "DBL", "BAJ", "TAS",
    "JNN", "UNG", "IHN", "SIM", "GNR", "AVH", "CHE", "NSD",
    "SNH", "MTR", "BBH", "ORH", "NDR", "ZAL", "DEE", "AMT",
    "AHR", "JRG", "HHN", "HUJ", "CAD", "SHR", "ETL", "IHU",
    "ALD", "ACL", "JIM", "MAN", "BUK", "TGS", "ZOS", "MTS",
    "ARL", "NOG", "JLT",
]

# Remove duplicates while preserving order
MSE_KEYWORDS = list(dict.fromkeys(MSE_KEYWORDS))

# ── Scraper settings ──────────────────────────────────────────────────────────
RSS_INTERVAL_MINUTES      = 30
TELEGRAM_HISTORY_LIMIT    = 5000
MAX_ARTICLE_CHARS         = 800