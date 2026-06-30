import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

r = requests.get("https://montsame.mn/mn", headers=headers, timeout=10)
soup = BeautifulSoup(r.text, "html.parser")

links = []
for a in soup.find_all("a", href=True):
    href  = a.get("href", "")
    title = a.get_text(strip=True)
    if len(title) > 15 and "/mn/read/" in href:
        links.append((title, href))

print(f"Article links: {len(links)}")
for title, href in links[:20]:
    print(f"  {title[:80]}")