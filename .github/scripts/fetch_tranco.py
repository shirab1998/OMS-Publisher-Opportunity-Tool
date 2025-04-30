import requests
import re

def fetch_latest_tranco():
    page = requests.get("https://tranco-list.eu/recent").text
    match = re.search(r'/list/([A-Z0-9]{5})', page)
    if not match:
        raise Exception("Could not extract list ID")
    list_id = match.group(1)
    url = f"https://tranco-list.eu/download/{list_id}/1000000"
    print(f"Downloading: {url}")
    r = requests.get(url)
    r.raise_for_status()
    with open("top-1m.csv", "wb") as f:
        f.write(r.content)
    print(f"✅ Saved top-1m.csv (List ID: {list_id})")

if __name__ == "__main__":
    fetch_latest_tranco()
