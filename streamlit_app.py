import streamlit as st
import requests
import pandas as pd
import re
import time
from datetime import datetime
from io import StringIO
import smtplib
from email.message import EmailMessage
import os

# --- SIMILARWEB SETTINGS ---
SIMILARWEB_API_KEY = "80c301fd23bb43b0a38aadaa25814ac4"
SIMILARWEB_BASE_URL = "https://api.similarweb.com/v1/website/"
TIER1_COUNTRIES = ["us", "gb", "ca", "au", "de"]

# --- STREAMLIT INTERFACE ---
st.title("Publisher Monetization Opportunity Finder")

pub_domain = st.text_input("Publisher Domain (e.g., example.com)")
pub_name = st.text_input("Publisher Name (e.g., connatix.com)")
pub_id = st.text_input("Publisher ID (e.g., 1536788745730056)")
sample_direct_line = st.text_input("Sample Direct Line (e.g., connatix.com, 12345, DIRECT)")

# Store results in session_state
if "result_text" not in st.session_state:
    st.session_state.result_text = ""
if "results_ready" not in st.session_state:
    st.session_state.results_ready = False

if st.button("Find Opportunities"):
    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner('Processing...'):
            try:
                sellers_url = f"https://{pub_domain}/sellers.json"
                sellers_response = requests.get(sellers_url, timeout=10)
                sellers_data = sellers_response.json()

                domains = set()
                for seller in sellers_data.get("sellers", []):
                    domain_name = seller.get("domain")
                    if domain_name and domain_name.lower() != pub_domain.lower():
                        domains.add(domain_name.lower())

                st.write(f"Found {len(domains)} domains to check.")

                best_traffic = []
                good_traffic = []

                for domain in domains:
                    st.write(f"🔍 Checking domain: {domain}")
                    ads_url = f"https://{domain}/ads.txt"
                    try:
                        ads_response = requests.get(ads_url, timeout=10)
                        ads_lines = ads_response.text.lower().splitlines()

                        has_direct = any(
                            line.strip().lower().startswith(pub_name.lower()) and "direct" in line.lower()
                            for line in ads_lines
                        )
                        if not has_direct:
                            st.write(f"❌ Skipped: No direct line for {pub_name}")
                            continue
                        else:
                            st.write("✅ Found direct line")

                        oms_lines = [line for line in ads_lines if "onlinemediasolutions.com" in line and "direct" in line]

                        classified = None
                        for line in oms_lines:
                            parts = [p.strip() for p in line.split(",")]
                            if len(parts) >= 4 and parts[0] == "onlinemediasolutions.com":
                                if parts[1] == pub_id:
                                    classified = "Skip"
                                    break
                                else:
                                    classified = "Best"

                        if classified == "Skip":
                            st.write("⛔ Skipped: Already buying from this publisher via OMS")
                            continue
                        elif classified == "Best":
                            traffic_category = "Best"
                        else:
                            traffic_category = "Good"

                        try:
                            traffic_response = requests.get(f"{SIMILARWEB_BASE_URL}{domain}/traffic-sources/overview?api_key={SIMILARWEB_API_KEY}&country=world", timeout=10)
                            geo_response = requests.get(f"{SIMILARWEB_BASE_URL}{domain}/traffic-sources/geo-distribution?api_key={SIMILARWEB_API_KEY}", timeout=10)

                            if not traffic_response.ok:
                                st.write(f"⚠️ Skipped: SimilarWeb traffic error for {domain} — HTTP {traffic_response.status_code}")
                                continue
                            if not geo_response.ok:
                                st.write(f"⚠️ Skipped: SimilarWeb geo error for {domain} — HTTP {geo_response.status_code}")
                                continue

                            total_visits = traffic_response.json().get("visits", 0)
                            geo_data = geo_response.json().get("country_distribution", [])

                        except Exception as json_error:
                            st.write(f"⚠️ Skipped: JSON parse error for {domain} — {json_error}")
                            continue

                        tier1_visits = sum([
                            c.get("visits", 0)
                            for c in geo_data if c.get("country", "").lower() in TIER1_COUNTRIES
                        ])

                        st.write(f"🌍 Traffic: {total_visits:,} total | {tier1_visits:,} Tier1")

                        if tier1_visits >= 500_000:
                            record = {
                                "Domain": domain,
                                "Total Visits": total_visits,
                                "Tier1 Visits": tier1_visits,
                                "Traffic Category": traffic_category
                            }
                            if traffic_category == "Best":
                                best_traffic.append(record)
                            else:
                                good_traffic.append(record)
                        else:
                            st.write("⚠️ Skipped: Not enough Tier1 traffic")

                        time.sleep(1)

                    except Exception as e:
                        st.write(f"❌ Error checking {domain}: {e}")
                        continue

                best_traffic = sorted(best_traffic, key=lambda x: x["Tier1 Visits"], reverse=True)
                good_traffic = sorted(good_traffic, key=lambda x: x["Tier1 Visits"], reverse=True)

                st.success("Done!")
                st.subheader(f"{pub_name} ({pub_id}) Opportunities:")

                count = 1
                result_lines = [f"{pub_name} ({pub_id}) Opportunities:\n"]
                for row in best_traffic:
                    line = f"{count}. {row['Domain']} (Tier1 Visits: {row['Tier1 Visits']:,}) [Best Traffic]"
                    st.write(line)
                    result_lines.append(line)
                    count += 1
                for row in good_traffic:
                    line = f"{count}. {row['Domain']} (Tier1 Visits: {row['Tier1 Visits']:,}) [Good Traffic]"
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
                            f"Hi!\n\n"
                            f"Adding here the {pub_name} ({pub_id}) opportunities generated at {date_str}!\n\n"
                            f"{st.session_state.result_text}\n\n"
                            f"Warm regards,\nShira"
                        )
                        msg.set_content(body)

                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                            smtp.send_message(msg)

                        st.success("Email sent successfully!")

                    except Exception as e:
                        st.error(f"Failed to send email: {e}")

            except Exception as e:
                st.error(f"An error occurred: {e}")