import streamlit as st
import requests
import pandas as pd
import re
import time

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

if st.button("Find Opportunities"):
    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner('Processing...'):
            try:
                # Step 1: Pull sellers.json
                sellers_url = f"https://{pub_domain}/sellers.json"
                sellers_response = requests.get(sellers_url, timeout=10)
                sellers_data = sellers_response.json()

                domains = set()
                for seller in sellers_data.get("sellers", []):
                    domain_name = seller.get("domain")
                    if domain_name and domain_name.lower() != pub_domain.lower():
                        domains.add(domain_name.lower())

                st.write(f"Found {len(domains)} domains to check.")

                # Step 2: Direct Line pattern
                direct_pattern = re.compile(
                    rf"^{re.escape(pub_name)}\s*,\s*[^,]+\s*,\s*direct(\s*,\s*[^,]+)?$",
                    re.IGNORECASE
                )

                oms_pattern = re.compile(
                    r"^onlinemediasolutions\.com\s*,\s*([^,]+)\s*,\s*direct\s*,\s*b3868b187e4b6402$",
                    re.IGNORECASE
                )

                best_traffic = []
                good_traffic = []

                for domain in domains:
                    ads_url = f"https://{domain}/ads.txt"
                    try:
                        ads_response = requests.get(ads_url, timeout=10)
                        ads_lines = ads_response.text.lower().splitlines()

                        has_direct = any(direct_pattern.match(line.strip()) for line in ads_lines)
                        if not has_direct:
                            continue

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
                            continue
                        elif classified == "Best":
                            traffic_category = "Best"
                        else:
                            traffic_category = "Good"

                        # Step 3: Pull SimilarWeb Traffic only now
                        traffic_url = f"{SIMILARWEB_BASE_URL}{domain}/traffic-sources/overview?api_key={SIMILARWEB_API_KEY}&country=world"
                        geo_url = f"{SIMILARWEB_BASE_URL}{domain}/traffic-sources/geo-distribution?api_key={SIMILARWEB_API_KEY}"

                        traffic_response = requests.get(traffic_url, timeout=10)
                        geo_response = requests.get(geo_url, timeout=10)

                        total_visits = traffic_response.json().get("visits", 0)
                        geo_data = geo_response.json().get("country_distribution", [])

                        tier1_visits = sum([
                            c.get("visits", 0)
                            for c in geo_data if c.get("country", "").lower() in TIER1_COUNTRIES
                        ])

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

                        time.sleep(1)

                    except Exception:
                        continue

                best_traffic = sorted(best_traffic, key=lambda x: x["Tier1 Visits"], reverse=True)
                good_traffic = sorted(good_traffic, key=lambda x: x["Tier1 Visits"], reverse=True)

                st.success("Done!")
                st.subheader(f"{pub_name} ({pub_id}) Opportunities:")

                count = 1
                for row in best_traffic:
                    st.write(f"{count}. {row['Domain']} (Tier1 Visits: {row['Tier1 Visits']:,}) [Best Traffic]")
                    count += 1
                for row in good_traffic:
                    st.write(f"{count}. {row['Domain']} (Tier1 Visits: {row['Tier1 Visits']:,}) [Good Traffic]")
                    count += 1

            except Exception as e:
                st.error(f"An error occurred: {e}")
