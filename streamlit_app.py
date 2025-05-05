import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
import os
import re
import smtplib
from email.message import EmailMessage
import unicodedata
import json

# --- CONFIGURATION ---
TRANCO_TOP_DOMAINS_FILE = "/tmp/top-1m.csv"
TRANCO_META_FILE = "/tmp/tranco_meta.json"
TRANCO_THRESHOLD = 210000

# --- FUNCTIONS FOR TRANCO ---
def get_tranco_meta():
    if os.path.exists(TRANCO_META_FILE):
        with open(TRANCO_META_FILE, "r") as f:
            return json.load(f)
    return None

def save_tranco_meta(tranco_id):
    with open(TRANCO_META_FILE, "w") as f:
        json.dump({
            "id": tranco_id,
            "timestamp": datetime.now().isoformat()
        }, f)

def is_recent(date_str):
    try:
        ts = datetime.fromisoformat(date_str)
        return (datetime.now() - ts).days < 14
    except:
        return False

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("\U0001F4A1 Publisher Monetization Opportunity Finder")

# --- TRANCO LOADING ---
@st.cache_data
def load_tranco_top_domains():
    if not os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        return {}
    try:
        df = pd.read_csv(TRANCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
        df = df[df["Rank"] <= TRANCO_THRESHOLD]
        return dict(zip(df["Domain"].str.lower(), df["Rank"]))
    except Exception as e:
        st.error(f"Error reading Tranco CSV: {e}")
        return {}

tranco_rankings = load_tranco_top_domains()

# --- SIDEBAR ---
with st.sidebar:
    st.header("\U0001F310 Tranco List")
    meta = get_tranco_meta()
    show_input = st.session_state.get("show_input", False)

    if os.path.exists(TRANCO_TOP_DOMAINS_FILE) and meta:
        updated_time = datetime.fromtimestamp(os.path.getmtime(TRANCO_TOP_DOMAINS_FILE)).strftime('%Y-%m-%d %H:%M:%S')
        if is_recent(meta.get("timestamp", "")):
            st.markdown(f"<div style='font-size: 85%; margin-bottom: 0.75em;'><span style='color: green;'>Last updated: {updated_time}</span></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='font-size: 85%; margin-bottom: 0.75em;'><span style='color: orange;'>Last updated: {updated_time} ⬤ Might be outdated</span></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='font-size: 85%; color: red; margin-bottom: 0.75em;'>⚠️ Tranco list not found. Please paste a Tranco list URL below.</div>", unsafe_allow_html=True)
        show_input = True

    if st.button("🔁 Manually Update Tranco List"):
        st.session_state["show_input"] = True
        show_input = True

    if show_input:
        st.markdown("[Visit Tranco list site](https://tranco-list.eu/) to get a link")
        st.text_input("Paste Tranco List URL", key="tranco_url")
        if st.button("\U0001F4E5 Download Tranco List"):
            url = st.session_state.get("tranco_url", "")
            match = re.search(r"/list/([a-zA-Z0-9]{5,})/", url)
            if not match:
                st.error("Invalid Tranco URL format.")
            else:
                tranco_id = match.group(1)
                download_url = f"https://tranco-list.eu/download/{tranco_id}/full"
                try:
                    response = requests.get(download_url)
                    if response.status_code == 200:
                        with open(TRANCO_TOP_DOMAINS_FILE, "wb") as f:
                            f.write(response.content)
                        save_tranco_meta(tranco_id)
                        st.success(f"✅ Downloaded Tranco list (ID: {tranco_id})")
                        st.session_state["show_input"] = False
                        show_input = False
                    else:
                        st.error(f"Failed to download Tranco list: HTTP {response.status_code}")
                except Exception as e:
                    st.error(f"Error downloading Tranco list: {e}")

# --- INPUT SECTION ---
st.markdown("### 📝 Enter Publisher Details")

# Toggle for manual mode
manual_mode = st.checkbox("🔀 Use Manual Domains Instead", value=False)

# Show standard or manual fields based on toggle
if not manual_mode:
    pub_domain = st.text_input("Publisher Domain", placeholder="example.com")
    pub_name = st.text_input("Publisher Name", placeholder="connatix.com")
    manual_domains_input = ""
else:
    st.info("Manual mode active: Paste domains manually. Publisher Domain/Name are hidden.")
    manual_domains_input = st.text_area("Paste domains manually (comma or newline separated)", height=100)
    pub_domain = ""
    pub_name = ""

pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT")

# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("🔍 Find Monetization Opportunities"):
    if not pub_id or not sample_direct_line:
        st.error("Publisher ID and Example Direct Line are required.")
    else:
        with st.spinner("🔎 Checking domains..."):
            skipped_log = []
            results = []
            domains = set()

            if manual_domains_input.strip():
                manual_lines = re.split(r'[\n,]+', manual_domains_input.strip())
                domains = {d.strip().lower() for d in manual_lines if d.strip()}
            else:
                sellers_url = f"https://{pub_domain}/sellers.json"
                try:
                    sellers_response = requests.get(sellers_url, timeout=10)
                    if sellers_response.status_code == 200:
                        try:
                            sellers_data = sellers_response.json()
                            if "sellers" in sellers_data:
                                domains = {
                                    s.get("domain").lower() for s in sellers_data["sellers"]
                                    if s.get("domain") and s.get("domain").lower() != pub_domain.lower()
                                    }
                                        else:
                                            st.warning("No 'sellers' field found in sellers.json.")
    except Exception:
        st.warning("Could not parse sellers.json — fallback to manual or check formatting.")
                    else:
                        st.error(f"Could not fetch sellers.json from {sellers_url} (Status: {sellers_response.status_code})")

                    if "sellers" in sellers_data:
                        domains = {
                            s.get("domain").lower() for s in sellers_data["sellers"]
                            if s.get("domain") and s.get("domain").lower() != pub_domain.lower()
                        }
                    else:
                        st.warning("No sellers field in sellers.json. Provide manual domains if needed.")
                except Exception:
                    st.error(f"Invalid sellers.json at {sellers_url}")

            if not domains:
                st.error("No valid domains found to check.")
            else:
                progress = st.progress(0)
                progress_text = st.empty()
                for idx, domain in enumerate(domains, start=1):
                    try:
                        ads_url = f"https://{domain}/ads.txt"
                        ads_response = requests.get(ads_url, timeout=10)
                        ads_lines = ads_response.text.splitlines()

                        validation_reason = None
                        for line in ads_lines:
                            if sample_direct_line.split(",")[0].strip().lower() in line.lower() and "direct" in line.lower():
                                validation_reason = "direct"
                                break
                            elif f"managerdomain={pub_domain.lower()}" in line.lower():
                                validation_reason = "managerdomain"
                                break

                        if not validation_reason:
                            skipped_log.append((domain, "No valid ads.txt line for publisher"))
                            continue

                        if any(
                            "onlinemediasolutions.com" in line.lower() and pub_id in line and "direct" in line.lower()
                            for line in ads_lines
                        ):
                            skipped_log.append((domain, "OMS is already buying from this publisher"))
                            continue

                        is_oms_buyer = any(
                            "onlinemediasolutions.com" in line.lower() and pub_id not in line and "direct" in line.lower()
                            for line in ads_lines
                        )

                        if domain.lower() not in tranco_rankings:
                            skipped_log.append((domain, "Not in Tranco top list"))
                            continue

                        rank = tranco_rankings[domain.lower()]
                        results.append({
                            "Domain": domain,
                            "Tranco Rank": rank,
                            "OMS Buying": "Yes" if is_oms_buyer else "No",
                            "Validation Reason": validation_reason
                        })
                        time.sleep(0.1)

                    except Exception as e:
                        skipped_log.append((domain, f"Request error: {e}"))

                    progress.progress(idx / len(domains))
                    progress_text.text(f"Checking domain {idx}/{len(domains)}: {domain}")

                df_results = pd.DataFrame(results)
                df_results.sort_values("Tranco Rank", inplace=True)
                st.session_state["opportunities_table"] = df_results
                st.session_state["skipped_log"] = skipped_log

# --- RESULTS DISPLAY ---
st.session_state.setdefault("opportunities_table", pd.DataFrame())

if not st.session_state.opportunities_table.empty:
    styled_df = st.session_state.opportunities_table.copy()

    def highlight(row):
        if row.get("Validation Reason") == "managerdomain":
            return ['background-color: #fff9cc'] * len(row)
        if row.get("Tranco Rank") <= 50000:
            return ['background-color: #d4edda'] * len(row)
        return [''] * len(row)

    st.dataframe(
        styled_df.style.apply(highlight, axis=1),
        use_container_width=True
    )
