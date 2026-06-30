import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Cookie": "_ga=GA1.1.653938253.1765809278; cs=yes; tjsid=59f07d11ba428b125f9c289861626d2f",
}

r = requests.get("https://ikon.mn", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Size: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
links = [(a.get_text(strip=True), a.get("href","")) for a in soup.find_all("a", href=True) if len(a.get_text(strip=True)) > 15]
print(f"Links found: {len(links)}")
for text, href in links[:10]:
    print(f"  {text[:60]} -> {href[:60]}")