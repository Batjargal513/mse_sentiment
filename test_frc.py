import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://frc.mn",
    "Origin": "https://frc.mn",
}

r = requests.get(
    "https://www.frc.mn:5001/api/news",
    params={
        "menuid": 18,
        "site":   "main",
        "lang":   "mn",
        "page":   0,
    },
    headers=headers,
    timeout=10,
    verify=False  # bypass SSL
)

print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")