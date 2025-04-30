# publisher_opportunity_finder.py
import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
from email.message import EmailMessage
import smtplib
import os

# --- SIMILARWEB SETTINGS ---
SIMILARWEB_API_KEY = st.secrets.get("similarweb_key", "YOUR_DEFAULT_KEY")
SIMILARWEB_BASE_URL = "https://api.similarweb.com/v1/website/"
TIER1_COUNTRIES = ["us", "gb", "ca", "au", "de"]

# --- STREAMLIT INTERFACE ---
st.title("Publisher Monetization Opportunity Finder")

pub_domain = st.text_input("Publisher Domain (e.g., example.com)")
pub_name = st.text_input("Publisher Name (e.g., connatix.com)")
pub_id = st.text_input("Publisher ID (e.g., 1536788745730056)")
sample_direct_line = st.text_input("Sample Direct Line (e.g., connatix.com, 12345, DIRECT)")

# --- SESSION STATE SETUP ---
st.session_state.setdefault("result_text", "")
st.session_state.setdefault("results_ready", False)
st.session_state.setdefault("skipped_log", [])

# --- UTILITY: CALL SIMILARWEB API ---
def call_sw_api(endpoint: str, domain: str, params: dict = None):
    url = f"{SIMILARWEB_BASE_URL}{domain}/{endpoint}"
    default_params = {"api_key": SIMILARWEB_API_KEY}
    if params:
        default_params.update(params)
    try:
        response = requests.get(url, params=default_params, timeout=10)
        if not response.ok:
            return None, f"HTTP {response.status_code}: {response.text}"
        return response.json(), None
    except Exception as e:
        return None, str(e)

# --- MAIN LOGIC ---
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

                best_traffic, good_traffic = [], []

                for domain in domains:
                    st.write(f"🔍 Checking domain: {domain}")
                    ads_url = f"https://{domain}/ads.txt"
                    try:
                        ads_response = requests.get(ads_url, timeout=10)
                        ads_lines = ads_response.text.lower().splitlines()

                        has_direct = any(
                            line.strip().startswith(pub_name.lower()) and "direct" in line
                            for line in ads_lines
                        )
                        if not has_direct:
                            st.write(f"❌ Skipped: No direct line for {pub_name}")
                            st.session_state.skipped_log.append((domain, "No direct line"))
                            continue

                        oms_lines = [
                            line for line in ads_lines
                            if "onlinemediasolutions.com" in line and "direct" in line
                        ]

                        classified = None
                        for line in oms_lines:
                            parts = [p.strip() for p in line.split(",")]
                            if len(parts) >= 4 and parts[0] == "onlinemediasolutions.com":
                                classified = "Skip" if parts[1] == pub_id else "Best"
                                break

                        if classified == "Skip":
                            st.write("⛔ Skipped: Already buying from this publisher via OMS")
                            st.session_state.skipped_log.append((domain, "Already buying via OMS"))
                            continue

                        traffic_json, traffic_err = call_sw_api("traffic-sources/overview", domain)
                        geo_json, geo_err = call_sw_api("traffic-sources/geo-distribution", domain)

                        if traffic_err:
                            st.write(f"⚠️ SW Traffic Error: {traffic_err}")
                            st.session_state.skipped_log.append((domain, f"SW traffic error: {traffic_err}"))
                            continue
                        if geo_err:
                            st.write(f"⚠️ SW Geo Error: {geo_err}")
                            st.session_state.skipped_log.append((domain, f"SW geo error: {geo_err}"))
                            continue

                        total_visits = traffic_json.get("visits", 0)
                        geo_data = geo_json.get("country_distribution", [])

                        tier1_visits = sum(
                            c.get("visits", 0)
                            for c in geo_data if c.get("country", "").lower() in TIER1_COUNTRIES
                        )

                        st.write(f"🌍 Traffic: {total_visits:,} total | {tier1_visits:,} Tier1")

                        if tier1_visits >= 500_000:
                            record = {
                                "Domain": domain,
                                "Total Visits": total_visits,
                                "Tier1 Visits": tier1_visits,
                                "Traffic Category": classified or "Good"
                            }
                            (best_traffic if classified == "Best" else good_traffic).append(record)
                        else:
                            st.write("⚠️ Skipped: Not enough Tier1 traffic")
                            st.session_state.skipped_log.append((domain, "Not enough Tier1 traffic"))

                        time.sleep(1)

                    except Exception as e:
                        st.write(f"❌ Error checking {domain}: {e}")
                        st.session_state.skipped_log.append((domain, f"Request error: {e}"))

                best_traffic.sort(key=lambda x: x["Tier1 Visits"], reverse=True)
                good_traffic.sort(key=lambda x: x["Tier1 Visits"], reverse=True)

                st.success("Done!")
                st.subheader(f"{pub_name} ({pub_id}) Opportunities:")

                result_lines = [f"{pub_name} ({pub_id}) Opportunities:\n"]
                count = 1
                for row in best_traffic + good_traffic:
                    label = "Best Traffic" if row in best_traffic else "Good Traffic"
                    line = f"{count}. {row['Domain']} (Tier1 Visits: {row['Tier1 Visits']:,}) [{label}]"
                    st.write(line)
                    result_lines.append(line)
                    count += 1

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