import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
}

r = requests.get("https://news.mn", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Size: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
links = []
for a in soup.find_all("a", href=True):
    href  = a.get("href", "")
    title = a.get_text(strip=True)
    if len(title) > 15 and href:
        links.append((title, href))

print(f"Links found: {len(links)}")
for title, href in links[:15]:
    print(f"  {title[:60]} -> {href[:60]}")