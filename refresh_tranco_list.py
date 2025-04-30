# refresh_tranco_list.py
import requests

def download_tranco_csv(output_file="top-1m.csv"):
    try:
        url = "https://tranco-list.eu/top-1m.csv"
        response = requests.get(url)
        response.raise_for_status()
        with open(output_file, "wb") as f:
            f.write(response.content)
        print(f"✅ Saved Tranco list to {output_file}")
    except Exception as e:
        print(f"❌ Failed to download Tranco list: {e}")

if __name__ == "__main__":
    download_tranco_csv()

