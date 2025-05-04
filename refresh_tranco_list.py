def download_latest_tranco_csv(output_file="/tmp/top-1m.csv"):
    try:
        # Get the recent list page
        recent_page = requests.get("https://tranco-list.eu/recent")
        if recent_page.status_code != 200:
            st.error(f"Failed to fetch recent Tranco page: HTTP {recent_page.status_code}")
            return False

        # Extract the first /list/{ID} using regex
        match = re.search(r'/list/([A-Z0-9]{5})', recent_page.text)
        if not match:
            st.error("Could not extract latest Tranco list ID.")
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
