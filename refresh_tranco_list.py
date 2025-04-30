import requests
import os

OUTPUT_PATH = "top-1m.csv"

def download_tranco():
    try:
        list_meta = requests.get("https://tranco-list.eu/lists.csv")
        lines = list_meta.text.strip().splitlines()
        if len(lines) < 2:
            raise Exception("No list found in Tranco CSV")

        latest_id = lines[1].split(",")[0]
        csv_url = f"https://tranco-list.eu/download/{latest_id}/1000000"

        print(f"Downloading list ID {latest_id} from {csv_url}")
        response = requests.get(csv_url)
        response.raise_for_status()

        with open(OUTPUT_PATH, "wb") as f:
            f.write(response.content)

        print(f"✅ Downloaded and saved to {OUTPUT_PATH}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    download_tranco()
