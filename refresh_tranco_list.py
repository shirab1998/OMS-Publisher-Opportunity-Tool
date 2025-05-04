def download_latest_tranco_csv(output_file="/tmp/top-1m.csv"):
    try:
        # Fetch homepage
        homepage = requests.get("https://tranco-list.eu/")
        if homepage.status_code != 200:
            st.error(f"Failed to fetch Tranco homepage: HTTP {homepage.status_code}")
            return False

        # Extract first list ID from homepage
        match = re.search(r'href=\"/list/([A-Z0-9]{5})\"', homepage.text)
        if not match:
            st.error("Could not extract latest Tranco list ID from homepage.")
            return False

        list_id = match.group(1)
        download_url = f"https://tranco-list.eu/download/{list_id}/1000000"

        response = requests.get(download_url)
        if response.status_code == 200:
            with open(output_file, "wb") as f:
                f.write(response.content)
            st.success(f"✅ Downloaded Tranco list (ID: {list_id})")
            return True
        else:
            st.error(f"Failed to download Tranco CSV: HTTP {response.status_code}")
            return False

    except Exception as e:
        st.error(f"Error downloading Tranco list: {e}")
        return False
