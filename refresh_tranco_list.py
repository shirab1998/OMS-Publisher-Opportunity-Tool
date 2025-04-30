import requests
import re

def download_latest_tranco_csv(output_file="top-1m.csv"):
    print("🔍 Fetching latest Tranco list ID...")
    index_url = "https://tranco-list.eu"
    html = requests.get(index_url).text

    match = re.search(r"/list/([A-Z0-9]+)", html)
    if not match:
        raise Exception("Could not find the latest Tranco list ID")

    latest_id = match.group(1)
    csv_url = f"https://tranco-list.eu/download/{latest_id}/1000000"

    print(f"⬇️ Downloading CSV from {csv_url} ...")
    response = requests.get(csv_url)
    if response.status_code == 200:
        with open(output_file, "wb") as f:
            f.write(response.content)
        print(f"✅ Downloaded latest Tranco list as {output_file} (ID: {latest_id})")
    else:
        raise Exception(f"Failed to download CSV: HTTP {response.status_code}")

if __name__ == "__main__":
    download_latest_tranco_csv()
