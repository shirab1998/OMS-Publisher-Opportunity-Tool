# Streamlit Ads Analysis Tool - Updated

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

# --- RETRY LOGIC FOR NETWORK REQUESTS ---
import requests
from requests.exceptions import RequestException

def fetch_sellers_json(url, retries=3):
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise HTTP errors
            return response.json()
        except RequestException as e:
            if attempt < retries - 1:
                time.sleep(2)  # Wait before retrying
            else:
                raise e  # Raise the exception after final attempt
                
# --- DOMAIN NORMALIZATION ---
import tldextract

def normalize_domain(domain):
    extracted = tldextract.extract(domain)
    if not extracted.domain or not extracted.suffix:
        return None  # Invalid domain
    return f"{extracted.domain}.{extracted.suffix}".lower()   
    
# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("\U0001F4A1 Publisher Monetization Opportunity Finder")

# --- NOTIFICATION AREA ---
notification = st.empty()

# --- CONTEXTUAL HELP IN SIDEBAR ---
with st.sidebar:
    with st.expander("\u2753 Help & Tips", expanded=False):
        st.markdown("""
        - Paste a Tranco list URL from [Tranco](https://tranco-list.eu/) if needed.
        - You can enter publisher info manually or via sellers.json.
        - Add comments to each result for later use.
        - Skipped domains can be rechecked individually.
        - 'Start Over' clears everything.
        """)
        
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
        st.session_state.clear()
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
# --- SIDEBAR: HELP & TIPS ---
with st.sidebar:
    with st.expander("💡 Help & Tips", expanded=False):
        st.markdown("""
        - Paste a Tranco list URL from [Tranco](https://tranco-list.eu/) if needed.
        - You can enter publisher info manually or via sellers.json.
        - Add comments to each result for later use.
        - Skipped domains can be rechecked individually.
        - 'Start Over' clears everything.
        """)


# --- INPUT SECTION ---
st.markdown("### 📝 Enter Publisher Details")

manual_mode = st.sidebar.checkbox("Enable Manual Mode")
if manual_mode:
    st.info("Manual mode detected. Only Publisher ID and example ads.txt line are required.")
    pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
    sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT")
    pub_domain, pub_name, manual_domains_input = "", "", ""
else:
    pub_domain = st.text_input("Publisher Domain", placeholder="example.com")
    pub_name = st.text_input("Publisher Name", placeholder="connatix.com")
    pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
    sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT")
    manual_domains_input = st.text_area("Paste domains manually (comma or newline separated)", height=100)

# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("🔍 Find Monetization Opportunities"):
    # Store inputs in session state
    st.session_state["pub_domain"] = pub_domain
    st.session_state["pub_name"] = pub_name
    st.session_state["pub_id"] = pub_id
    st.session_state["sample_direct_line"] = sample_direct_line
    st.session_state["manual_domains_input"] = manual_domains_input

    # Input validation
    if not pub_id or not sample_direct_line:
        st.error("Publisher ID and Example Direct Line are required.")
    else:
        with st.spinner("🔎 Checking domains..."):
            try:
                # Initialize variables
                st.session_state.skipped_log = []  # Reset skipped log
                results = []
                domains = set()

                # Handle manual input
                if manual_domains_input.strip():
                    manual_lines = re.split(r'[\n,]+', manual_domains_input.strip())
                    domains = {d.strip().lower() for d in manual_lines if d.strip()}
                else:
                    # Fetch and validate sellers.json
                    try:
                        sellers_url = f"https://{pub_domain}/sellers.json"
                        sellers_data = fetch_sellers_json(sellers_url)
                        if "sellers" not in sellers_data or not isinstance(sellers_data["sellers"], list):
                            st.error(f"Invalid sellers.json structure at {sellers_url}")
                            st.session_state.skipped_log.append((sellers_url, "Invalid sellers.json structure"))
                        else:
                            domains = {
                                normalize_domain(s.get("domain")) for s in sellers_data["sellers"]
                                if s.get("domain") and normalize_domain(s.get("domain")) != normalize_domain(pub_domain)
                            }
                            domains = {d for d in domains if d}  # Remove invalid domains
                    except Exception as e:
                        st.error(f"Error fetching or parsing sellers.json: {e}")
                        st.session_state.skipped_log.append((sellers_url, f"Error fetching or parsing sellers.json: {e}"))

                # Log skipped domains if no valid domains found
                if not domains:
                    st.error("No valid domains found to check.")
                    st.session_state.skipped_log.append((pub_domain, "No valid domains found"))
                else:
                    progress = st.progress(0)
                    progress_text = st.empty()

                    # Process each domain
                    for idx, domain in enumerate(domains, start=1):
                        try:
                            ads_url = f"https://{domain}/ads.txt"
                            ads_response = requests.get(ads_url, timeout=10)
                            ads_lines = ads_response.text.splitlines()

                            # Check for direct lines
                            has_direct = any(
                                sample_direct_line.split(",")[0].strip().lower() in line.lower()
                                and "direct" in line.lower()
                                for line in ads_lines
                            )
                            if not has_direct:
                                st.session_state.skipped_log.append((domain, "No direct line for publisher"))
                                continue

                            # Check if OMS is already buying
                            if any(
                                "onlinemediasolutions.com" in line.lower() and pub_id in line and "direct" in line.lower()
                                for line in ads_lines
                            ):
                                st.session_state.skipped_log.append((domain, "OMS is already buying from this publisher"))
                                continue

                            # Check if OMS is another buyer
                            is_oms_buyer = any(
                                "onlinemediasolutions.com" in line.lower() and pub_id not in line and "direct" in line.lower()
                                for line in ads_lines
                            )

                            # Add valid results
                            row = {
                                "Domain": domain,
                                "OMS Buying": "Yes" if is_oms_buyer else "No",
                                "Comment": ""  # Inline comment box placeholder
                            }
                            results.append(row)

                            # Update progress
                            progress.progress(idx / len(domains))
                            progress_text.text(f"Checking domain {idx}/{len(domains)}: {domain}")

                        except Exception as e:
                            st.session_state.skipped_log.append((domain, f"Request error: {e}"))

                    # Convert results to DataFrame and store in session state
                    df_results = pd.DataFrame(results)

                    # Add inline comment boxes
                    for i, row in df_results.iterrows():
                        key = f"comment_{i}"
                        df_results.at[i, "Comment"] = st.text_input(
                            f"Comment for {row['Domain']}",
                            value=row["Comment"],
                            key=key
                        )

                    st.session_state.opportunities_table = df_results

                    # Display results
                    st.dataframe(df_results, use_container_width=True)

                    # Log completion
                    st.success("✅ Analysis complete")
                    st.balloons()
###
            except Exception as e:
                st.error(f"Error while processing: {e}")

            # --- Owner/Manager Detection ---
            try:
                owner_role = "no"  # Default to "no" if neither owner nor manager is found
                pub_domain_lower = pub_domain.lower()  # Convert publisher domain to lowercase
                found_owner = any("ownerdomain" in l.lower() for l in ads_lines)  # Check for "ownerdomain"
                found_manager = any("managerdomain" in l.lower() for l in ads_lines)  # Check for "managerdomain"

                # Iterate through ads.txt lines to match owner/manager roles
                for l in ads_lines:
                    line_lower = l.lower()
                    if "ownerdomain" in line_lower and pub_domain_lower in line_lower:
                        owner_role = "owner"  # Found the publisher as an owner
                        break
                    elif "managerdomain" in line_lower and pub_domain_lower in line_lower:
                        owner_role = "manager"  # Found the publisher as a manager
                        break
                else:
                    # If neither owner nor manager is explicitly matched, check indirect cases
                    if found_owner and not found_manager:
                        owner_role = "managerdomain not indicated"
                    elif found_manager and not found_owner:
                        owner_role = "ownerdomain not indicated"

                # Append the results row
                row = {
                    "Domain": domain,
                    "Tranco Rank": tranco_rankings.get(domain.lower(), "N/A"),
                    "Owner/Manager": owner_role,
                    "OMS Buying": "Yes" if is_oms_buyer else "No",
                    "Comment": ""
                }
                results.append(row)
                time.sleep(0.1)  # Short delay to avoid overloading requests

            except Exception as e:
                st.session_state.skipped_log.append((domain, f"Request error during Owner/Manager detection: {e}"))

            # Update progress
            progress.progress(idx / len(domains))
            progress_text.text(f"Checking domain {idx}/{len(domains)}: {domain} ({round(100 * idx / len(domains))}%)")

        # Convert results to DataFrame and sort by Tranco Rank
        df_results = pd.DataFrame(results)
        df_results.sort_values("Tranco Rank", inplace=True)
        st.session_state.opportunities_table = df_results

        # Save analysis to session history
        key = f"{pub_name or 'manual'}_{pub_id}"
        st.session_state.setdefault("history", {})
        st.session_state["history"][key] = {
            "name": pub_name or "Manual Domains",
            "id": pub_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "table": df_results.copy()
        }

        # Success message and completion
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

    # Create a copy for editing
    edited_table = st.session_state.opportunities_table.copy()

    # Add comment boxes inline with table rows
    for i in range(len(edited_table)):
        key = f"comment_{i}"
        edited_table.at[i, "Comment"] = st.text_input(
            label=f"Comment for {edited_table.at[i, 'Domain']}",
            value=edited_table.at[i, "Comment"],
            key=key
        )

    st.session_state.opportunities_table = edited_table  # Update with comments

    # Define row highlights
    def highlight_row(row):
        if row["Tranco Rank"] <= 50000:
            return ['background-color: #d4edda'] * len(row)  # green
        elif row["Owner/Manager"] in ["owner", "manager"]:
            return ['background-color: #fff8dc'] * len(row)  # muted yellow
        else:
            return [''] * len(row)

    styled_df = edited_table.copy()
    st.dataframe(
        styled_df.style.apply(highlight_row, axis=1),
        use_container_width=True
    )

    # Download CSV button
    csv_data = edited_table.to_csv(index=False)
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

                # Prepare colored HTML table
                styled_rows = ""
                for _, row in st.session_state.opportunities_table.iterrows():
                    style = ""
                    if row["Tranco Rank"] <= 50000:
                        style = ' style="background-color:#d4edda;"'
                    elif row["Owner/Manager"] in ["owner", "manager"]:
                        style = ' style="background-color:#fff8dc;"'
                    styled_rows += f"""
<tr{style}>
  <td>{row['Domain']}</td>
  <td>{row['Tranco Rank']}</td>
  <td>{row['Owner/Manager']}</td>
  <td>{row['OMS Buying']}</td>
  <td>{row['Comment']}</td>
</tr>"""

                html_table = f"""
<table border="1" cellpadding="5" cellspacing="0" style="font-family:Arial; font-size:14px; border-collapse:collapse;">
  <thead style="background-color:#f2f2f2;">
    <tr>
      <th>Domain</th>
      <th>Tranco Rank</th>
      <th>Owner/Manager</th>
      <th>OMS Buying</th>
      <th>Comment</th>
    </tr>
  </thead>
  <tbody>
    {styled_rows}
  </tbody>
</table>"""

                body = f"""
<html>
  <body>
    <p>Hi there!</p>
    <p>Here is the list of opportunities for <strong>{subject_name}</strong> ({subject_id}):</p>
    {html_table}
    <p>Warm regards,<br/>Automation bot</p>
  </body>
</html>"""

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
    st.session_state.clear()  # Clear all session state
    st.experimental_rerun()  # Restart the app

# --- SKIPPED DOMAINS REPORT ---
st.session_state.setdefault("skipped_log", [])

if st.session_state.skipped_log:
    with st.expander("⛔ Skipped Domains", expanded=False):
        st.subheader("⛔ Skipped Domains")
        skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])

        recheck_container = st.container()

        def recheck_domain(domain):
            try:
                ads_url = f"https://{domain}/ads.txt"
                ads_response = requests.get(ads_url, timeout=10)
                ads_lines = ads_response.text.splitlines()

                has_direct = any(
                    sample_direct_line.split(",")[0].strip().lower() in line.lower()
                    and "direct" in line.lower()
                    for line in ads_lines
                )
                if not has_direct:
                    notification.warning(f"{domain}: still no direct line")
                    return

                is_oms_buyer = any(
                    "onlinemediasolutions.com" in line.lower() and pub_id not in line and "direct" in line.lower()
                    for line in ads_lines
                )

                pub_domain_lower = pub_domain.lower()
                owner_role = "no"
                found_owner = any("ownerdomain" in l.lower() for l in ads_lines)
                found_manager = any("managerdomain" in l.lower() for l in ads_lines)
                for l in ads_lines:
                    line_lower = l.lower()
                    if "ownerdomain" in line_lower and pub_domain_lower in line_lower:
                        owner_role = "owner"
                        break
                    elif "managerdomain" in line_lower and pub_domain_lower in line_lower:
                        owner_role = "manager"
                        break
                else:
                    if found_owner and not found_manager:
                        owner_role = "managerdomain not indicated"
                    elif found_manager and not found_owner:
                        owner_role = "ownerdomain not indicated"

                rank = tranco_rankings.get(domain.lower())
                if not rank:
                    notification.warning(f"{domain}: still not in Tranco")
                    return

                new_row = {
                    "Domain": domain,
                    "Tranco Rank": rank,
                    "Owner/Manager": owner_role,
                    "OMS Buying": "Yes" if is_oms_buyer else "No",
                    "Comment": ""
                }

                st.session_state.opportunities_table = pd.concat([
                    st.session_state.opportunities_table,
                    pd.DataFrame([new_row])
                ], ignore_index=True)
                notification.success(f"{domain}: added to table!")
                st.session_state.skipped_log = [
                    x for x in st.session_state.skipped_log if x[0] != domain
                ]
            except Exception as e:
                notification.error(f"Error rechecking {domain}: {e}")

        for idx, row in skipped_df.iterrows():
            col1, col2 = recheck_container.columns([4, 1])
            col1.markdown(f"**{row['Domain']}** — {row['Reason']}")
            if col2.button("Recheck", key=f"recheck_{idx}"):
                recheck_domain(row["Domain"])

        # Download button for skipped domains
        skipped_csv = skipped_df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Skipped Domains CSV",
            data=skipped_csv,
            file_name="skipped_domains.csv",
            mime="text/csv"
        )
