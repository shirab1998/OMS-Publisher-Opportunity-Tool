import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
import os
import re
import json
import smtplib
from email.message import EmailMessage
import unicodedata

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

@st.cache_data
def load_tranco_top_domains():
    if not os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        return {}
    df = pd.read_csv(TRANCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
    df = df[df["Rank"] <= TRANCO_THRESHOLD]
    return dict(zip(df["Domain"].str.lower(), df["Rank"]))

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("\U0001F4A1 Publisher Monetization Opportunity Finder")

# --- SIDEBAR ---
with st.sidebar:
    st.header("\U0001F310 Tranco List")

    tranco_meta = get_tranco_meta()
    tranco_exists = os.path.exists(TRANCO_TOP_DOMAINS_FILE)
    update_triggered = st.session_state.get("show_tranco_input", False)

    if tranco_exists and tranco_meta:
        last_updated = datetime.fromisoformat(tranco_meta["timestamp"])
        st.markdown(f"**Last Tranco update:** {last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
        if is_recent(tranco_meta["timestamp"]):
            st.success("✅ The Tranco file is up to date.")
        if st.button("Update Tranco File", key="update_tranco_file_btn"):
            st.session_state["show_tranco_input"] = True
            st.rerun()
    elif not tranco_exists:
        st.markdown("**❌ No Tranco list available**")
        update_triggered = True

    if update_triggered:
        st.markdown("[Tranco link](https://tranco-list.eu)")
        st.markdown("**Add latest Tranco list URL:**")
        custom_url = st.text_input("", placeholder="https://tranco-list.eu/list/XXXXX/1000000", key="tranco_url")
        if st.button("Save Tranco List", key="save_tranco_list_btn"):
            match = re.search(r"/list/([A-Z0-9]{5})/", custom_url)
            if not match:
                st.error("❌ Invalid URL. Please paste a correct Tranco list URL.")
            else:
                tranco_id = match.group(1)
                download_url = f"https://tranco-list.eu/download/{tranco_id}/full"
                try:
                    response = requests.get(download_url)
                    if response.status_code == 200:
                        with open(TRANCO_TOP_DOMAINS_FILE, "wb") as f:
                            f.write(response.content)
                        save_tranco_meta(tranco_id)
                        st.success(f"✅ Tranco list updated successfully (ID: {tranco_id})")
                        st.session_state["show_tranco_input"] = False
                        st.rerun()
                    else:
                        st.error(f"Download failed: HTTP {response.status_code}")
                except Exception as e:
                    st.error(f"Error fetching Tranco list: {e}")

# --- LOAD RANKINGS ---
tranco_rankings = load_tranco_top_domains()

# --- PUBLISHER FORM ---
st.markdown("### 📝 Enter Publisher Details")
pub_domain = st.text_input("Publisher Domain", placeholder="example.com", key="pub_domain_input")
pub_name = st.text_input("Publisher Name", placeholder="connatix.com", key="pub_name_input")
pub_id = st.text_input("Publisher ID", placeholder="1536788745730056", key="pub_id_input")
sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT", key="sample_direct_line_input")
st.markdown("Or paste domains manually (if sellers.json not found):")
manual_domains_input = st.text_area("Manual Domains (comma or newline separated)", height=100, key="manual_domains_input")

# --- MONETIZATION CHECK ---
if st.button("🔍 Find Monetization Opportunities"):
    st.session_state["pub_domain"] = pub_domain
    st.session_state["pub_name"] = pub_name
    st.session_state["pub_id"] = pub_id
    st.session_state["sample_direct_line"] = sample_direct_line

    if not all([pub_domain, pub_name, pub_id, sample_direct_line]):
        st.error("Please fill out all fields!")
    else:
        with st.spinner("🔎 Checking domains..."):
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
                    domains = set()
                else:
                    domains = {
                        s.get("domain").lower() for s in sellers_data.get("sellers", [])
                        if s.get("domain") and s.get("domain").lower() != pub_domain.lower()
                    }

                if not domains and manual_domains_input:
                    manual_lines = re.split(r'[\n,]+', manual_domains_input)
                    domains = {d.strip().lower() for d in manual_lines if d.strip()}

                results = []
                progress = st.progress(0)
                progress_text = st.empty()
                for idx, domain in enumerate(domains, start=1):
                    try:
                        ads_url = f"https://{domain}/ads.txt"
                        ads_response = requests.get(ads_url, timeout=10)
                        ads_lines = ads_response.text.splitlines()

                        has_direct = any(line.strip().lower().startswith(pub_name.lower()) and "direct" in line.lower() for line in ads_lines)
                        if not has_direct:
                            st.session_state.skipped_log.append((domain, f"No {pub_name} direct line"))
                            continue

                        rank = tranco_rankings.get(domain.lower())
                        if rank is None:
                            st.session_state.skipped_log.append((domain, "Missing Tranco Rank"))
                            continue

                        if any("onlinemediasolutions.com" in line.lower() and pub_id in line and ("direct" in line.lower() or "reseller" in line.lower()) for line in ads_lines):
                            st.session_state.skipped_log.append((domain, "OMS is already buying from this publisher"))
                            continue

                        is_oms_buyer = any("onlinemediasolutions.com" in line.lower() and pub_id not in line and "direct" in line.lower() for line in ads_lines)

                        results.append({
                            "Domain": domain,
                            "Tranco Rank": rank,
                            "OMS Buying": "Yes" if is_oms_buyer else "No"
                        })
                        time.sleep(0.1)

                    except Exception as e:
                        st.session_state.skipped_log.append((domain, f"Request error: {e}"))
                    progress.progress(idx / len(domains))
                    progress_text.text(f"Checking domain {idx}/{len(domains)}: {domain}")
                if results:
                     df_results = pd.DataFrame(results)
                     if "Tranco Rank" in df_results.columns:
                        df_results.sort_values("Tranco Rank", inplace=True)
                    st.session_state.opportunities_table = df_results
                    st.success("✅ Analysis complete")
                    st.balloons()
                else:
                    st.warning("No valid monetization opportunities found.")


            except Exception as e:
                st.error(f"Error while processing: {e}")


# --- RESULTS DISPLAY ---
if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
    st.subheader(f"📈 Opportunities for {pub_name} ({pub_id})")
    total = len(st.session_state.opportunities_table)
    oms_yes = (st.session_state.opportunities_table["OMS Buying"] == "Yes").sum()
    oms_no = total - oms_yes
    skipped = len(st.session_state.skipped_log)
    st.markdown(f"📊 **{total + skipped} domains scanned** | ✅ {total} opportunities found | ⛔ {skipped} skipped")

    styled_df = st.session_state.opportunities_table.copy()
    styled_df["Highlight"] = styled_df["Tranco Rank"] <= 50000
    styled_df_display = styled_df.drop(columns=["Highlight"])
    st.dataframe(
        styled_df_display.style.apply(
            lambda x: ["background-color: #d4edda" if v else "" for v in styled_df["Highlight"]],
            axis=0
        ),
        use_container_width=True
    )

    csv_data = st.session_state.opportunities_table.to_csv(index=False)
    st.download_button("⬇️ Download Opportunities CSV", data=csv_data, file_name=f"opportunities_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

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
            st.info("✅ Want to analyze another publisher? Update the fields above or refresh the page.")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

# --- START OVER BUTTON ---
if st.button("🔁 Start Over"):
    history_backup = st.session_state.get("history", {}).copy()
    for key in list(st.session_state.keys()):
        if key != "history":
            del st.session_state[key]
    st.session_state["history"] = history_backup
    st.rerun()

# --- SKIPPED DOMAINS REPORT ---
if st.session_state.get("skipped_log"):
    with st.expander("⛔ Skipped Domains", expanded=False):
        st.subheader("⛔ Skipped Domains")
        skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
        st.dataframe(skipped_df, use_container_width=True)
        skipped_csv = skipped_df.to_csv(index=False)
        st.download_button("⬇️ Download Skipped Domains CSV", data=skipped_csv, file_name="skipped_domains.csv", mime="text/csv")
