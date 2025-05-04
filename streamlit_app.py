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

# --- CONFIGURATION ---
TRANCO_TOP_DOMAINS_FILE = "/tmp/top-1m.csv"
TRANCO_THRESHOLD = 210000

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("\U0001F4A1 Publisher Monetization Opportunity Finder")

# --- SIDEBAR ---
with st.sidebar:
    st.header("\U0001F310 Tranco List")
    if os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        last_updated = datetime.fromtimestamp(os.path.getmtime(TRANCO_TOP_DOMAINS_FILE))
        st.success(f"Last updated: {last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("Tranco list not available")

# --- FUNCTION TO FETCH TRANCO LIST ---
def fetch_latest_tranco(output_file):
    try:
        homepage = requests.get("https://tranco-list.eu")
        match = re.search(r'href=\"/list/([A-Z0-9]{5})\"', homepage.text)
        if not match:
            st.error("Could not extract latest Tranco list ID from homepage.")
            return False

        list_id = match.group(1)
        download_url = f"https://tranco-list.eu/download/{list_id}/full"
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

# --- INPUT SECTION ---
if "opportunities_table" not in st.session_state or st.session_state.opportunities_table.empty:
    st.markdown("### \U0001F4DD Enter Publisher Details")
    pub_domain = st.text_input("Publisher Domain", placeholder="example.com")
    pub_name = st.text_input("Publisher Name", placeholder="connatix.com")
    pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
    sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT")
else:
    pub_domain = st.session_state.get("pub_domain", "")
    pub_name = st.session_state.get("pub_name", "")
    pub_id = st.session_state.get("pub_id", "")
    sample_direct_line = st.session_state.get("sample_direct_line", "")

st.session_state.setdefault("result_text", "")
st.session_state.setdefault("results_ready", False)
st.session_state.setdefault("skipped_log", [])
st.session_state.setdefault("opportunities_table", pd.DataFrame())

@st.cache_data
def load_tranco_top_domains():
    if not os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        return {}
    df = pd.read_csv(TRANCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
    df = df[df["Rank"] <= TRANCO_THRESHOLD]
    return dict(zip(df["Domain"].str.lower(), df["Rank"]))

tranco_rankings = load_tranco_top_domains()

# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("\U0001F50D Find Monetization Opportunities"):
    st.session_state["pub_domain"] = pub_domain
    st.session_state["pub_name"] = pub_name
    st.session_state["pub_id"] = pub_id
    st.session_state["sample_direct_line"] = sample_direct_line

    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner("\U0001F50E Checking domains..."):
            try:
                st.session_state.skipped_log = []
                sellers_url = f"https://{pub_domain}/sellers.json"
                try:
                    sellers_response = requests.get(sellers_url, timeout=10)
                    sellers_data = sellers_response.json()
                except Exception:
                    st.error(f"Invalid sellers.json at {sellers_url}")
                    sellers_data = {}

                if "sellers" not in sellers_data:
                    st.warning(f"No 'sellers' field in sellers.json for {pub_domain}")
                else:
                    domains = {
                        s.get("domain").lower() for s in sellers_data.get("sellers", [])
                        if s.get("domain") and s.get("domain").lower() != pub_domain.lower()
                    }
                    results = []
                    progress = st.progress(0)
                    for idx, domain in enumerate(domains, start=1):
                        ads_url = f"https://{domain}/ads.txt"
                        try:
                            ads_response = requests.get(ads_url, timeout=10)
                            ads_lines = ads_response.text.splitlines()

                            has_direct = any(line.strip().lower().startswith(pub_name.lower()) and "direct" in line.lower() for line in ads_lines)
                            if not has_direct:
                                st.session_state.skipped_log.append((domain, f"No {pub_name} direct line"))
                                continue

                            if domain.lower() not in tranco_rankings:
                                st.session_state.skipped_log.append((domain, "Not in Tranco top list"))
                                continue

                            is_oms_buyer = any("onlinemediasolutions.com" in line.lower() and pub_id not in line and "direct" in line.lower() for line in ads_lines)

                            rank = tranco_rankings[domain.lower()]
                            results.append({
                                "Domain": domain,
                                "Tranco Rank": rank,
                                "OMS Buying": "Yes" if is_oms_buyer else "No"
                            })
                            time.sleep(0.1)
                        except Exception as e:
                            st.session_state.skipped_log.append((domain, f"Request error: {e}"))
                        progress.progress(idx / len(domains))

                    df_results = pd.DataFrame(results)
                    df_results.sort_values("Tranco Rank", inplace=True)
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

# --- EMAIL SECTION ---
def sanitize_header(text):
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r'[^ -~]', '', text)
    text = text.strip().replace("\r", "").replace("\n", "")
    return text

st.markdown("### 📧 Email This List")
st.markdown("<label>Email Address</label>", unsafe_allow_html=True)
email_cols = st.columns([3, 5])
email_local_part = email_cols[0].text_input("", placeholder="e.g. shirab", label_visibility="collapsed")
email_cols[1].markdown("<div style='margin-top: 0.6em; font-size: 16px;'>@onlinemediasolutions.com</div>", unsafe_allow_html=True)

if st.button("Send Email"):
    if not email_local_part.strip():
        st.error("Please enter a valid username before sending the email.")
    else:
        try:
            full_email = f"{email_local_part.strip()}@onlinemediasolutions.com"
            from_email = st.secrets["EMAIL_ADDRESS"]
            email_password = st.secrets["EMAIL_PASSWORD"]

            subject_name = sanitize_header(pub_name or "Unknown Publisher")
            subject_id = sanitize_header(pub_id or "NoID")
            msg = EmailMessage()
            msg["Subject"] = f"{subject_name} ({subject_id}) opportunities"
            msg["From"] = from_email.strip()
            msg["To"] = full_email.strip()
            html_table = st.session_state.opportunities_table.to_html(index=False, border=1, justify='center', classes='styled-table')
            body = f"""
<html>
  <head>
    <style>
      * {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; }}
      .styled-table {{
        border-collapse: collapse;
        margin: 10px 0;
        font-size: 14px;
        min-width: 400px;
        border: 1px solid #ddd;
      }}
      .styled-table th, .styled-table td {{
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
      }}
      .styled-table th {{
        background-color: #f2f2f2;
        font-weight: bold;
      }}
    </style>
  </head>
  <body>
    <p>Hi there!</p>
    <p>Here is the list of opportunities for <strong>{pub_name}</strong> ({pub_id}):</p>
    {html_table}
    <p>Warm regards,<br/>Automation bot</p>
  </body>
</html>
"""
            msg.set_content("This email requires an HTML-capable email client.")
            msg.add_alternative(body, subtype="html")

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(from_email, email_password)
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
