import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
from email.message import EmailMessage
import smtplib
import os
import re

# --- CONFIGURATION ---
TRANCO_TOP_DOMAINS_FILE = "/tmp/top-1m.csv"
TRANCO_THRESHOLD = 300000

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("\U0001F4A1 Publisher Monetization Opportunity Finder")

# --- FUNCTION TO FETCH TRANCO LIST ---
def fetch_latest_tranco(output_file):
    try:
        homepage = requests.get("https://tranco-list.eu")
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
            st.success(f"\u2705 Downloaded Tranco list (ID: {list_id})")
            return True
        else:
            st.error(f"Failed to download Tranco CSV: HTTP {response.status_code}")
            return False
    except Exception as e:
        st.error(f"Error downloading Tranco list: {e}")
        return False

if "tranco_list_downloaded" not in st.session_state:
    st.session_state.tranco_list_downloaded = os.path.exists(TRANCO_TOP_DOMAINS_FILE)

# --- TRANCO UPDATE SECTION ---
def auto_fetch_latest_tranco_id():
    try:
        homepage = requests.get("https://tranco-list.eu")
        match = re.search(r'href=\"/list/([A-Z0-9]{5})\"', homepage.text)
        if match:
            return match.group(1)
    except Exception:
        return None

tranco_col = st.container()
with tranco_col:
    st.markdown("### \U0001F501 Tranco List Update")
    if os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        last_updated = datetime.fromtimestamp(os.path.getmtime(TRANCO_TOP_DOMAINS_FILE))
        delta = datetime.now() - last_updated
        st.caption(f"\U0001F4C5 Tranco list last updated: {last_updated.strftime('%Y-%m-%d %H:%M:%S')}")

        if delta.days >= 7:
            if st.toggle("\u26A0\uFE0F Tranco list is over a week old. Click to open update options"):
                st.markdown("[\U0001F310 Open Tranco Site](https://tranco-list.eu/) and copy any list link like:`https://tranco-list.eu/list/ABC12/1000000`")
                st.caption("We'll auto-convert it to the correct download format for you \u2705")
                custom_url = st.text_input("Paste Tranco list link here")
                if st.button("\U0001F4E5 Download and Save Tranco List"):
                    custom_url_clean = custom_url.strip()
                    if custom_url_clean.startswith("https://tranco-list.eu/list/") or custom_url_clean.startswith("https://tranco-list.eu/download/"):
                        try:
                            match = re.search(r"/(list|download)/([A-Z0-9]{5})", custom_url_clean)
                            if match:
                                list_id = match.group(2)
                                download_url = f"https://tranco-list.eu/download/{list_id}/full"
                                st.caption(f"\U0001F4C4 Using Tranco list ID: {list_id}")

                                response = requests.get(download_url)
                                if response.status_code == 200:
                                    with open(TRANCO_TOP_DOMAINS_FILE, "wb") as f:
                                        f.write(response.content)
                                    st.session_state.tranco_list_downloaded = True
                                    st.success("\u2705 Tranco list downloaded and saved.")
                                else:
                                    st.error(f"Failed to download: HTTP {response.status_code}")
                            else:
                                st.error("\u274C Couldn't extract Tranco list ID from the URL.")
                        except Exception as e:
                            st.error(f"Download error: {e}")
                    else:
                        st.error("\u274C Invalid URL. Please paste a link like https://tranco-list.eu/list/ABC12/1000000")
    else:
        st.info("No Tranco list found yet.")
        st.markdown("[\U0001F310 Open Tranco Site](https://tranco-list.eu/)")
        custom_url = st.text_input("Paste full Tranco download URL")
        if st.button("\U0001F4E5 Download and Save Tranco List"):
            if custom_url.strip().startswith("https://tranco-list.eu/list/") or custom_url.strip().startswith("https://tranco-list.eu/download/"):
                try:
                    match = re.search(r"/(list|download)/([A-Z0-9]{5})", custom_url.strip())
                if match:
                    list_id = match.group(2)
                    download_url = f"https://tranco-list.eu/download/{list_id}/full"
                    response = requests.get(download_url)
                    if response.status_code == 200:
                        with open(TRANCO_TOP_DOMAINS_FILE, "wb") as f:
                            f.write(response.content)
                        st.session_state.tranco_list_downloaded = True
                        st.success("\u2705 Tranco list downloaded and saved.")
                    else:
                        st.error(f"Failed to download: HTTP {response.status_code}")
                except Exception as e:
                    st.error(f"Download error: {e}")
            else:
                st.error("\u274C Invalid URL. Please paste the full link from tranco-list.eu")

# --- INPUT SECTION ---
with st.expander("\U0001F4DD Enter Publisher Details"):
    pub_domain = st.text_input("Publisher Domain", placeholder="example.com")
    pub_name = st.text_input("Publisher Name", placeholder="connatix.com")
    pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
    sample_direct_line = st.text_input("Sample Direct Line", placeholder="connatix.com, 12345, DIRECT")

# --- SESSION STATE DEFAULTS ---
st.session_state.setdefault("result_text", "")
st.session_state.setdefault("results_ready", False)
st.session_state.setdefault("skipped_log", [])
st.session_state.setdefault("opportunities_table", pd.DataFrame())

# --- LOAD TRANCO ---
@st.cache_data
def load_tranco_top_domains():
    try:
        df = pd.read_csv(TRANCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
        df = df[df["Rank"] <= TRANCO_THRESHOLD]
        return dict(zip(df["Domain"].str.lower(), df["Rank"]))
    except Exception as e:
        st.error(f"Failed to load Tranco list: {e}")
        return {}

tranco_rankings = load_tranco_top_domains()

# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("\U0001F50D Find Monetization Opportunities"):
    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner("\U0001F50E Checking domains..."):
            try:
                st.session_state.skipped_log = []
                sellers_url = f"https://{pub_domain}/sellers.json"
                sellers_response = requests.get(sellers_url, timeout=10)
                sellers_data = sellers_response.json()

                if "sellers" not in sellers_data:
                    st.warning(f"No 'sellers' field in sellers.json for {pub_domain}")
                else:
                    domains = {
                        s.get("domain").lower() for s in sellers_data.get("sellers", [])
                        if s.get("domain") and s.get("domain").lower() != pub_domain.lower()
                    }
                    results = []
                    for idx, domain in enumerate(domains, start=1):
                        ads_url = f"https://{domain}/ads.txt"
                        try:
                            ads_response = requests.get(ads_url, timeout=10)
                            ads_lines = ads_response.text.splitlines()

                            has_direct = any(line.strip().lower().startswith(pub_name.lower()) and "direct" in line.lower() for line in ads_lines)
                            if not has_direct:
                                st.session_state.skipped_log.append((domain, f"No {pub_name} direct line"))
                                continue

                            if any("onlinemediasolutions.com" in line.lower() and pub_id in line and "direct" in line.lower() for line in ads_lines):
                                st.session_state.skipped_log.append((domain, "Already buying via OMS"))
                                continue

                            if domain.lower() not in tranco_rankings:
                                st.session_state.skipped_log.append((domain, "Not in Tranco top list"))
                                continue

                            rank = tranco_rankings[domain.lower()]
                            tag = (
                                f"{rank} on Tranco" if rank <= 1000 else
                                f"Top 10K" if rank <= 10000 else
                                f"Top 50K" if rank <= 50000 else
                                f"Top 100K" if rank <= 100000 else
                                f"Top {(rank + 49999) // 50000 * 50000:,}"
                            )
                            results.append({"#": len(results)+1, "Domain": domain, "Tranco Tag": tag, "Rank": rank})
                            time.sleep(0.5)
                        except Exception as e:
                            st.session_state.skipped_log.append((domain, f"Request error: {e}"))

                    df_results = pd.DataFrame(results)
                    df_results.sort_values("Rank", inplace=True)
                    st.session_state.opportunities_table = df_results

                    st.success("\u2705 Analysis complete")
            except Exception as e:
                st.error(f"Error while processing: {e}")

# --- RESULTS DISPLAY ---
if not st.session_state.opportunities_table.empty:
    st.subheader(f"\U0001F4C8 Opportunities for {pub_name} ({pub_id})")
    st.dataframe(st.session_state.opportunities_table, use_container_width=True)
    csv_data = st.session_state.opportunities_table.to_csv(index=False)
    st.download_button("\u2B07\uFE0F Download Opportunities CSV", data=csv_data, file_name="opportunities.csv", mime="text/csv")

    st.text_area("\u2709\uFE0F Email Preview", st.session_state.opportunities_table.to_string(index=False), height=200)
    email_to = st.text_input("Send opportunities via email to")
    if st.button("\U0001F4E7 Send Email") and email_to:
        try:
            EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
            EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

            msg = EmailMessage()
            msg["Subject"] = f"{pub_name} ({pub_id}) Monetization Opportunities"
            msg["From"] = EMAIL_ADDRESS
            msg["To"] = email_to
            msg.set_content(st.session_state.opportunities_table.to_string(index=False))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                smtp.send_message(msg)

            st.success("Email sent successfully!")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

# --- SKIPPED DOMAINS REPORT ---
if st.session_state.skipped_log:
    st.subheader("\u274C Skipped Domains")
    skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
    st.dataframe(skipped_df, use_container_width=True)
    skipped_csv = skipped_df.to_csv(index=False)
    st.download_button("\u2B07\uFE0F Download Skipped Domains CSV", data=skipped_csv, file_name="skipped_domains.csv", mime="text/csv")
