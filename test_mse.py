import requests
from datetime import datetime, timezone

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://mse.mn/news",
}

r = requests.get(
    "https://mse.mn/api/news",
    params={
        "lang":    "mn",
        "orderby": "DESC",
        "page":    1,
        "perPage": 15,
        "sdate":   "2000-01-01",
        "edate":   datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    },
    headers=headers,
    timeout=10
)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")