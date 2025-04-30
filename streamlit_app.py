# publisher_opportunity_finder.py
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
st.title("Publisher Monetization Opportunity Finder")

def download_latest_tranco_csv(output_file="/tmp/top-1m.csv"):
    try:
        download_url = "https://tranco-list.eu/download/YX2VG/1000000"
        response = requests.get(download_url)
        if response.status_code == 200:
            with open(output_file, "wb") as f:
                f.write(response.content)
            st.success("✅ Downloaded Tranco list (ID: YX2VG)")
            return True
        else:
            st.error(f"Failed to download Tranco CSV: HTTP {response.status_code}")
            return False
    except Exception as e:
        st.error(f"Error downloading Tranco list: {e}")
        return False

if st.button("🔄 Refresh Tranco List"):
    download_latest_tranco_csv()

if os.path.exists(TRONCO_TOP_DOMAINS_FILE):
    last_updated = datetime.fromtimestamp(os.path.getmtime(TRONCO_TOP_DOMAINS_FILE))
    st.caption(f"📅 Tranco list last updated: {last_updated.strftime('%Y-%m-%d %H:%M:%S')}")

pub_domain = st.text_input("Publisher Domain (e.g., example.com)")
pub_name = st.text_input("Publisher Name (e.g., connatix.com)")
pub_id = st.text_input("Publisher ID (e.g., 1536788745730056)")
sample_direct_line = st.text_input("Sample Direct Line (e.g., connatix.com, 12345, DIRECT)")

st.session_state.setdefault("result_text", "")
st.session_state.setdefault("results_ready", False)
st.session_state.setdefault("skipped_log", [])

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

if st.button("Find Opportunities"):
    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner('Processing...'):
            st.session_state.skipped_log = []
            try:
                sellers_url = f"https://{pub_domain}/sellers.json"
                sellers_response = requests.get(sellers_url, timeout=10)
                sellers_data = sellers_response.json()
                domains = {
                    s.get("domain").lower() for s in sellers_data.get("sellers", [])
                    if s.get("domain") and s.get("domain").lower() != pub_domain.lower()
                }
                st.write(f"Found {len(domains)} domains to check.")

                potential_traffic = []

                for domain in domains:
                    st.write(f"🔍 Checking domain: {domain}")
                    ads_url = f"https://{domain}/ads.txt"
                    try:
                        ads_response = requests.get(ads_url, timeout=10)
                        ads_lines = ads_response.text.splitlines()

                        has_direct = any(
                            line.strip().lower().startswith(pub_name.lower()) and "direct" in line.lower()
                            for line in ads_lines
                        )
                        if not has_direct:
                            reason = f"No {pub_name} direct line on ads.txt"
                            st.write(f"❌ Skipped: {reason}")
                            st.session_state.skipped_log.append((domain, reason))
                            continue

                        already_buying_oms = any(
                            line.strip().lower().startswith("onlinemediasolutions.com") and pub_id.strip() in line and "direct" in line.lower()
                            for line in ads_lines
                        )
                        if already_buying_oms:
                            reason = f"Already buying via OMS with pub_id {pub_id}"
                            st.write(f"⛔ Skipped: {reason}")
                            st.session_state.skipped_log.append((domain, reason))
                            continue

                        if domain.lower() not in tronco_rankings:
                            reason = f"Not in Tranco Top 500K"
                            st.write(f"⚠️ Skipped: {reason}")
                            st.session_state.skipped_log.append((domain, reason))
                            continue

                        rank = tronco_rankings[domain.lower()]
                        potential_traffic.append({"Domain": domain, "Traffic Category": "Potential", "Rank": rank})
                        time.sleep(1)
                    except Exception as e:
                        st.write(f"❌ Error checking {domain}: {e}")
                        st.session_state.skipped_log.append((domain, f"Request error: {e}"))

                potential_traffic.sort(key=lambda x: x["Rank"])

                st.success("Done!")
                st.subheader(f"{pub_name} ({pub_id}) Opportunities:")

                result_lines = [f"{pub_name} ({pub_id}) Opportunities:\n"]
                for idx, row in enumerate(potential_traffic, 1):
                    rank = row["Rank"]
                    if rank <= 1000:
                        tag = f"{rank} on Tranco"
                    elif rank <= 75000:
                        tag = f"{rank:,} on Tranco"
                    elif rank <= 10000:
                        tag = "Top 10K"
                    elif rank <= 50000:
                        tag = "Top 50K"
                    elif rank <= 100000:
                        tag = "Top 100K"
                    else:
                        rounded = ((rank + 49999) // 50000) * 50000
                        tag = f"Top {rounded:,}"

                    line = f"{idx}. {row['Domain']} – {tag} [{row['Traffic Category']}]"
                    st.write(line)
                    result_lines.append(line)

                st.session_state.result_text = "\n".join(result_lines)
                st.session_state.results_ready = True

                if st.session_state.results_ready:
                    st.subheader("📄 Full Result Preview")
                    st.text(st.session_state.result_text)

                    st.download_button(
                        label="📥 Download Results as .txt",
                        data=st.session_state.result_text,
                        file_name=f"{pub_name}_{pub_id}_opportunities.txt",
                        mime="text/plain"
                    )

                st.subheader("📧 Send Results via Email")
                email_to = st.text_input("Enter email address to send to")
                send_button = st.button("Send Email")

                if send_button and email_to:
                    try:
                        EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
                        EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

                        msg = EmailMessage()
                        msg["Subject"] = f"{pub_name} ({pub_id}) Opportunities"
                        msg["From"] = EMAIL_ADDRESS
                        msg["To"] = email_to

                        date_str = datetime.now().strftime("%B %d, %Y %H:%M")
                        body = (
                            f"Hi!

"
                            f"Adding here the {pub_name} ({pub_id}) opportunities generated at {date_str}!

"
                            f"{st.session_state.result_text}

"
                            f"Warm regards,
Your Automation Bot"
                        )
                        msg.set_content(body)

                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                            smtp.send_message(msg)

                        st.success("Email sent successfully!")
                    except Exception as e:
                        st.error(f"Failed to send email: {e}")

                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                            smtp.send_message(msg)

                        st.success("Email sent successfully!")
                    except Exception as e:
                        st.error(f"Failed to send email: {e}")

                if st.session_state.skipped_log:
                    st.subheader("❗ Skipped Domains Report")
                    skipped_table = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
                    st.dataframe(skipped_table)
                    skipped_csv = skipped_table.to_csv(index=False)
                    st.download_button("📥 Download Skipped Domains", data=skipped_csv, file_name="skipped_domains.csv", mime="text/csv")

                st.subheader("📧 Send Results via Email")
                email_to = st.text_input("Enter email address to send to")
                send_button = st.button("Send Email")

                if send_button and email_to:
                    try:
                        EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
                        EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

                        msg = EmailMessage()
                        msg["Subject"] = f"{pub_name} ({pub_id}) Opportunities"
                        msg["From"] = EMAIL_ADDRESS
                        msg["To"] = email_to

                        date_str = datetime.now().strftime("%B %d, %Y %H:%M")
                        msg.set_content(
                            f"Hi!\n\n"
                            f"Adding here the {pub_name} ({pub_id}) opportunities generated at {date_str}!\n\n"
                            f"{st.session_state.result_text}\n\n"
                            f"Warm regards,\nYour Automation Bot"
                        )

                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                            smtp.send_message(msg)

                        st.success("Email sent successfully!")
                    except Exception as e:
                        st.error(f"Failed to send email: {e}")
            except Exception as e:
                st.error(f"An error occurred: {e}")
