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
TRONCO_TOP_DOMAINS_FILE = "/tmp/top-1m.csv"
TRONCO_THRESHOLD = 300000

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("💡 Publisher Monetization Opportunity Finder")

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
            st.success(f"✅ Downloaded Tranco list (ID: {list_id})")
            return True
        else:
            st.error(f"Failed to download Tranco CSV: HTTP {response.status_code}")
            return False
    except Exception as e:
        st.error(f"Error downloading Tranco list: {e}")
        return False

if "tranco_list_downloaded" not in st.session_state:
    st.session_state.tranco_list_downloaded = os.path.exists(TRONCO_TOP_DOMAINS_FILE)

# --- TRANCO UPDATE SECTION ---
tranco_col = st.container()
with tranco_col:
    st.markdown("### 🔄 Tranco List Update")
    if os.path.exists(TRONCO_TOP_DOMAINS_FILE):
        last_updated = datetime.fromtimestamp(os.path.getmtime(TRONCO_TOP_DOMAINS_FILE))
        delta = datetime.now() - last_updated
        st.caption(f"📅 Tranco list last updated: {last_updated.strftime('%Y-%m-%d %H:%M:%S')}")

        if delta.days >= 7:
            if st.toggle("⚠️ Tranco list is over a week old. Click to open update options"):
                st.markdown("[🌐 Open Tranco Site](https://tranco-list.eu/) to copy latest list ID")
                custom_url = st.text_input("Paste full Tranco download URL")
                if st.button("📥 Download and Save Tranco List"):
                    if custom_url.strip().startswith("https://tranco-list.eu/download/") or custom_url.strip().startswith("https://tranco-list.eu/list/"):
                        try:
                            download_url = custom_url.strip()
                            if "/list/" in download_url:
                            download_url = download_url.replace("/list/", "/download/")
                            list_id_match = re.search(r'/download/([A-Z0-9]{5})/', download_url)
                            if list_id_match:
                                list_id = list_id_match.group(1)
                                st.caption(f"📄 Tranco list ID: {list_id}")
                        response = requests.get(download_url)
                            if response.status_code == 200:
                                with open(TRONCO_TOP_DOMAINS_FILE, "wb") as f:
                                    f.write(response.content)
                                st.session_state.tranco_list_downloaded = True
                                st.success("✅ Tranco list downloaded and saved.")
                            else:
                                st.error(f"Failed to download: HTTP {response.status_code}")
                        except Exception as e:
                            st.error(f"Download error: {e}")
                    else:
                        st.error("❌ Invalid URL. Please paste the full link from tranco-list.eu")
    else:
        st.info("No Tranco list found yet.")
        st.markdown("[🌐 Open Tranco Site](https://tranco-list.eu/)")
        custom_url = st.text_input("Paste full Tranco download URL")
        if st.button("📥 Download and Save Tranco List"):
            if custom_url.strip().startswith("https://tranco-list.eu/download/"):
                try:
                    response = requests.get(custom_url.strip())
                    if response.status_code == 200:
                        with open(TRONCO_TOP_DOMAINS_FILE, "wb") as f:
                            f.write(response.content)
                        st.session_state.tranco_list_downloaded = True
                        st.success("✅ Tranco list downloaded and saved.")
                    else:
                        st.error(f"Failed to download: HTTP {response.status_code}")
                except Exception as e:
                    st.error(f"Download error: {e}")
            else:
                st.error("❌ Invalid URL. Please paste the full link from tranco-list.eu")

# --- INPUT SECTION ---
with st.expander("📝 Enter Publisher Details"):
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
def load_tronco_top_domains():
    try:
        df = pd.read_csv(TRONCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
        df = df[df["Rank"] <= TRONCO_THRESHOLD]
        return dict(zip(df["Domain"].str.lower(), df["Rank"]))
    except Exception as e:
        st.error(f"Failed to load Tranco list: {e}")
        return {}

tronco_rankings = load_tronco_top_domains()

# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("🔍 Find Monetization Opportunities"):
    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner("🔎 Checking domains..."):
            try:
                st.session_state.skipped_log = []
                sellers_url = f"https://{pub_domain}/sellers.json"
                sellers_response = requests.get(sellers_url, timeout=10)
                sellers_data = sellers_response.json()
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

                        if domain.lower() not in tronco_rankings:
                            st.session_state.skipped_log.append((domain, "Not in Tranco top list"))
                            continue

                        rank = tronco_rankings[domain.lower()]
                        tag = (
                            f"{rank} on Tranco" if rank <= 1000 else
                            f"Top 10K" if rank <= 10000 else
                            f"Top 50K" if rank <= 50000 else
                            f"Top 100K" if rank <= 100000 else
                            f"Top {(rank + 49999) // 50000 * 50000:,}"
                        )
                        results.append({"#": len(results)+1, "Domain": domain, "Tranco Tag": tag, "Rank": rank})
                        time.sleep(1)
                    except Exception as e:
                        st.session_state.skipped_log.append((domain, f"Request error: {e}"))

                df_results = pd.DataFrame(results)
                df_results.sort_values("Rank", inplace=True)
                st.session_state.opportunities_table = df_results

                st.success("✅ Analysis complete")
            except Exception as e:
                st.error(f"Error while processing: {e}")

# --- RESULTS DISPLAY ---
if not st.session_state.opportunities_table.empty:
    st.subheader(f"📈 Opportunities for {pub_name} ({pub_id})")
    st.dataframe(st.session_state.opportunities_table, use_container_width=True)
    csv_data = st.session_state.opportunities_table.to_csv(index=False)
    st.download_button("⬇️ Download Opportunities CSV", data=csv_data, file_name="opportunities.csv", mime="text/csv")

    st.text_area("✉️ Email Preview", st.session_state.opportunities_table.to_string(index=False), height=200)
    email_to = st.text_input("Send opportunities via email to")
    if st.button("📧 Send Email") and email_to:
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
    st.subheader("❌ Skipped Domains")
    skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
    st.dataframe(skipped_df, use_container_width=True)
    skipped_csv = skipped_df.to_csv(index=False)
    st.download_button("⬇️ Download Skipped Domains CSV", data=skipped_csv, file_name="skipped_domains.csv", mime="text/csv")
