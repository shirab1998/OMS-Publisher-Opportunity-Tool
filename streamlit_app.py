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

    st.markdown("---")
    st.subheader("\U0001F553 Recent Publishers")
    if "history" in st.session_state:
        recent_keys = list(reversed(list(st.session_state["history"].keys())))[:10]
        for key in recent_keys:
            entry = st.session_state["history"][key]
            label = f"{entry['name']} ({entry['id']})"
            small_date = f"<div style='font-size: 12px; color: gray;'>Generated: {entry['date']}</div>"
            if st.button(label, key=key):
                st.subheader(f"\U0001F4DC Past Results: {entry['name']} ({entry['id']})")
                st.markdown(small_date, unsafe_allow_html=True)
                styled = entry['table'].copy()
                styled["Highlight"] = styled["Tranco Rank"] <= 50000
                styled_display = styled.drop(columns=["Highlight"])
                st.dataframe(
                    styled_display.style.apply(
                        lambda x: ["background-color: #d4edda" if v else "" for v in styled["Highlight"]],
                        axis=0
                    ),
                    use_container_width=True
                )
                st.stop()

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

st.info("✅ Tranco list loaded and ready. You can proceed with domain analysis.")

# --- INPUT SECTION ---
if "opportunities_table" not in st.session_state or st.session_state.opportunities_table.empty:
    st.markdown("### 📝 Enter Publisher Details")

    # State for manual mode toggle (based on expander)
    if "manual_mode" not in st.session_state:
        st.session_state["manual_mode"] = False

    def toggle_manual_mode():
        st.session_state.manual_mode = not st.session_state.manual_mode

    # Show or hide domain and name based on manual mode state
    if not st.session_state.manual_mode:
        pub_domain = st.text_input("Publisher Domain", placeholder="example.com")
        pub_name = st.text_input("Publisher Name", placeholder="connatix.com")
    else:
        pub_domain = ""
        pub_name = ""
        st.info("Manual mode active: Only Publisher ID and ads.txt line are required.")

    pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
    sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT")

    # Expander for manual domains input — triggers manual mode on expand
    expanded = st.expander("📄 Paste domains manually (click to activate manual mode)", expanded=st.session_state.manual_mode)
    with expanded:
        # When user expands, enter manual mode; when collapsed, exit
        # We assume the toggle happens based on the value being entered or not
        previous_value = st.session_state.get("manual_domains_input", "")
        st.session_state["manual_domains_input"] = st.text_area(
            "Manual Domains (comma or newline separated)",
            value=previous_value,
            height=100
        )
        if not st.session_state.manual_mode and st.session_state["manual_domains_input"]:
            st.session_state.manual_mode = True
        elif st.session_state.manual_mode and not st.session_state["manual_domains_input"]:
            st.session_state.manual_mode = False
else:
    pub_domain = st.session_state.get("pub_domain", "")
    pub_name = st.session_state.get("pub_name", "")
    pub_id = st.session_state.get("pub_id", "")
    sample_direct_line = st.session_state.get("sample_direct_line", "")
    manual_domains_input = st.session_state.get("manual_domains_input", "")

# Session defaults
st.session_state.setdefault("result_text", "")
st.session_state.setdefault("results_ready", False)
st.session_state.setdefault("skipped_log", [])
st.session_state.setdefault("opportunities_table", pd.DataFrame())


# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("🔍 Find Monetization Opportunities"):
    st.session_state["pub_domain"] = pub_domain
    st.session_state["pub_name"] = pub_name
    st.session_state["pub_id"] = pub_id
    st.session_state["sample_direct_line"] = sample_direct_line
    st.session_state["manual_domains_input"] = manual_domains_input

    if not pub_id or not sample_direct_line:
        st.error("Publisher ID and Example Direct Line are required.")
    else:
        with st.spinner("🔎 Checking domains..."):
            try:
                st.session_state.skipped_log = []
                results = []
                domains = set()

                # Check if we have manual domains
                if manual_domains_input.strip():
                    manual_lines = re.split(r'[\n,]+', manual_domains_input.strip())
                    domains = {d.strip().lower() for d in manual_lines if d.strip()}
                else:
                    # Try sellers.json
                    sellers_url = f"https://{pub_domain}/sellers.json"
                    try:
                        sellers_response = requests.get(sellers_url, timeout=10)
                        sellers_data = sellers_response.json()
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

                            has_direct = any(sample_direct_line.split(",")[0].strip().lower() in line.lower() and "direct" in line.lower()
                                             for line in ads_lines)
                            if not has_direct:
                                st.session_state.skipped_log.append((domain, f"No direct line for publisher"))
                                continue

                            if any(
                                "onlinemediasolutions.com" in line.lower() and pub_id in line and "direct" in line.lower()
                                for line in ads_lines
                            ):
                                st.session_state.skipped_log.append((domain, "OMS is already buying from this publisher"))
                                continue

                            is_oms_buyer = any(
                                "onlinemediasolutions.com" in line.lower() and pub_id not in line and "direct" in line.lower()
                                for line in ads_lines
                            )

                            if domain.lower() not in tranco_rankings:
                                st.session_state.skipped_log.append((domain, "Not in Tranco top list"))
                                continue

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
                        progress_text.text(f"Checking domain {idx}/{len(domains)}: {domain}")

                    df_results = pd.DataFrame(results)
                    df_results.sort_values("Tranco Rank", inplace=True)
                    st.session_state.opportunities_table = df_results
                    key = f"{pub_name or 'manual'}_{pub_id}"
                    st.session_state.setdefault("history", {})
                    st.session_state["history"][key] = {
                        "name": pub_name or "Manual Domains",
                        "id": pub_id,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "table": df_results.copy()
                    }
                    st.success("✅ Analysis complete")
                    st.balloons()

            except Exception as e:
                st.error(f"Error while processing: {e}")

# --- RESULTS DISPLAY ---
if not st.session_state.opportunities_table.empty:
    st.subheader(f"📈 Opportunities for {pub_name or 'Manual Domains'} ({pub_id})")
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
    st.download_button(
        "⬇️ Download Opportunities CSV",
        data=csv_data,
        file_name=f"opportunities_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
# --- EMAIL SECTION ---
if not st.session_state.opportunities_table.empty:
    def sanitize_header(text):
        text = unicodedata.normalize("NFKD", text)
        text = re.sub(r'[^ -~]', '', text)
        return text.strip().replace("\r", "").replace("\n", "")

    st.markdown("### 📧 Email This List")
    st.markdown("<label>Email Address</label>", unsafe_allow_html=True)
    email_cols = st.columns([3, 5])
    email_local_part = email_cols[0].text_input(
        "", placeholder="e.g. shirab", label_visibility="collapsed"
    )
    email_cols[1].markdown(
        "<div style='margin-top: 0.6em; font-size: 16px;'>@onlinemediasolutions.com</div>",
        unsafe_allow_html=True
    )

    if st.button("Send Email"):
        if not email_local_part.strip():
            st.error("Please enter a valid username before sending the email.")
        else:
            try:
                full_email = f"{email_local_part.strip()}@onlinemediasolutions.com"
                from_email = st.secrets["EMAIL_ADDRESS"]
                email_password = st.secrets["EMAIL_PASSWORD"]

                subject_name = sanitize_header(pub_name or "Manual Domains")
                subject_id = sanitize_header(pub_id or "NoID")
                msg = EmailMessage()
                msg["Subject"] = f"{subject_name} ({subject_id}) opportunities"
                msg["From"] = from_email.strip()
                msg["To"] = full_email.strip()

                html_table = st.session_state.opportunities_table.to_html(
                    index=False, border=1, justify='center', classes='styled-table'
                )
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
    <p>Here is the list of opportunities for <strong>{subject_name}</strong> ({subject_id}):</p>
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
if st.session_state.skipped_log:
    with st.expander("⛔ Skipped Domains", expanded=False):
        st.subheader("⛔ Skipped Domains")
        skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
        st.dataframe(skipped_df, use_container_width=True)

        skipped_csv = skipped_df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Skipped Domains CSV",
            data=skipped_csv,
            file_name="skipped_domains.csv",
            mime="text/csv"
        )
