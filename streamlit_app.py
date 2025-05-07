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
import io
from streamlit.web.server.websocket_headers import _get_websocket_headers
import uuid

# --- CONFIGURATION ---
TRANCO_TOP_DOMAINS_FILE = "/tmp/top-1m.csv"
TRANCO_META_FILE = "/tmp/tranco_meta.json"
TRANCO_THRESHOLD = 210000

# --- SESSION STATE ---
if "notification_queue" not in st.session_state:
    st.session_state.notification_queue = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "skipped_log" not in st.session_state:
    st.session_state.skipped_log = []

if "opportunities_table" not in st.session_state:
    st.session_state.opportunities_table = pd.DataFrame()

if "history" not in st.session_state:
    st.session_state.history = {}

# --- NOTIFICATION SYSTEM ---
def add_notification(message, type="info", duration=5):
    """Add a notification to the queue."""
    st.session_state.notification_queue.append({
        "message": message,
        "type": type,
        "id": f"notification_{len(st.session_state.notification_queue)}",
        "timestamp": time.time(),
        "duration": duration
    })

def render_notifications():
    """Render all active notifications."""
    if not st.session_state.notification_queue:
        return

    current_time = time.time()
    remaining_notifications = []

    for notif in st.session_state.notification_queue:
        if current_time - notif["timestamp"] < notif["duration"]:
            # Active notification styling
            bg_color = {
                "info": "#d1ecf1",
                "success": "#d4edda",
                "warning": "#fff3cd",
                "error": "#f8d7da"
            }.get(notif["type"], "#d1ecf1")

            text_color = {
                "info": "#0c5460",
                "success": "#155724",
                "warning": "#856404",
                "error": "#721c24"
            }.get(notif["type"], "#0c5460")

            icon = {
                "info": "ℹ️",
                "success": "✅",
                "warning": "⚠️",
                "error": "❌"
            }.get(notif["type"], "ℹ️")

            st.markdown(
                f"""
                <div style="
                    position: fixed;
                    bottom: {(remaining_notifications.count('active') * 60) + 20}px;
                    right: 20px;
                    padding: 8px 15px;
                    background-color: {bg_color};
                    color: {text_color};
                    border-radius: 4px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                    z-index: 1000;
                    animation: slidein 0.3s ease-out;
                    max-width: 300px;
                ">
                    {icon} {notif["message"]}
                </div>
                <style>
                @keyframes slidein {{
                    from {{ transform: translateX(100%); }}
                    to {{ transform: translateX(0); }}
                }}
                </style>
                """, 
                unsafe_allow_html=True
            )
            remaining_notifications.append('active')
        else:
            remaining_notifications.append('expired')

    # Keep only unexpired notifications
    st.session_state.notification_queue = [
        notif for i, notif in enumerate(st.session_state.notification_queue)
        if remaining_notifications[i] == 'active'
    ]

# --- TRANCO DATA HANDLING ---
def load_tranco_data():
    """Load Tranco top domains from a CSV file."""
    if not os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        st.warning("Tranco data not found. Please upload it.")
        return {}

    try:
        df = pd.read_csv(TRANCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
        df = df[df["Rank"] <= TRANCO_THRESHOLD]
        return dict(zip(df["Domain"].str.lower(), df["Rank"]))
    except Exception as e:
        st.error(f"Error loading Tranco data: {str(e)}")
        return {}

if "tranco_data" not in st.session_state:
    st.session_state.tranco_data = load_tranco_data()

# --- ADS.TXT PARSING ---
def parse_adstxt_line(line):
    """Parse a single ads.txt line and return its components."""
    # Remove comments
    line = line.split('#')[0].strip()
    if not line:
        return None

    parts = [p.strip() for p in line.split(',', 3)]
    if len(parts) < 3:
        return None

    return {
        'domain': parts[0].lower(),
        'pub_id': parts[1].strip(),
        'relationship': parts[2].lower(),
        'tag': parts[3].strip() if len(parts) > 3 else ''
    }

# --- DOMAIN CHECK FUNCTION ---
def check_domain(domain, pub_seller_domain, pub_id):
    """Check a domain's ads.txt and return relevant details."""
    try:
        ads_url = f"https://{domain}/ads.txt"
        ads_response = requests.get(ads_url, timeout=10)

        if ads_response.status_code != 200:
            return {"error": f"HTTP error: {ads_response.status_code}"}

        ads_lines = ads_response.text.splitlines()
        parsed_lines = [parse_adstxt_line(line) for line in ads_lines if line.strip()]
        parsed_lines = [line for line in parsed_lines if line]

        # Check for direct line
        has_direct = any(
            line['domain'] == pub_seller_domain and line['relationship'] == 'direct'
            for line in parsed_lines
        )

        if not has_direct:
            return {"error": f"No direct ads.txt line for {pub_seller_domain}"}

        # Check if OMS already buys from this publisher
        oms_existing = any(
            "onlinemediasolutions.com" in line['domain'] and
            line['pub_id'] == pub_id and
            line['relationship'] == 'direct'
            for line in parsed_lines
        )

        if oms_existing:
            return {"error": "OMS already buys from this publisher"}

        # Owner/Manager check
        owner_manager_status = "No"
        if any("ownerdomain" in line.lower() for line in ads_lines):
            owner_manager_status = "Owner"
        elif any("managerdomain" in line.lower() for line in ads_lines):
            owner_manager_status = "Manager"

        domain_rank = st.session_state["tranco_data"].get(domain.lower())
        if not domain_rank:
            return {"error": "Domain not in Tranco top list"}

        return {
            "Domain": domain,
            "Tranco Rank": domain_rank,
            "Owner/Manager": owner_manager_status,
            "Notes": ""
        }
    except Exception as error:
        return {"error": str(error)}

# --- MAIN STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunities", layout="wide")
st.title("Monetization Opportunity Finder")

# --- SIDEBAR ---
st.sidebar.header("Configuration")
manual_mode = st.sidebar.checkbox("Enable Manual Mode", value=False)

# --- KEYBOARD SHORTCUTS ---
def register_keyboard_shortcuts():
    """Setup keyboard shortcuts using JavaScript."""
    shortcuts_js = """
    <script>
    document.addEventListener('keydown', function(e) {
        // Check if not in an input field, textarea, etc.
        const activeEl = document.activeElement;
        const isTextField = activeEl.tagName === 'INPUT' || 
                          activeEl.tagName === 'TEXTAREA' || 
                          activeEl.isContentEditable;

        // Alt+S to start scan
        if (e.altKey && e.key === 's' && !isTextField) {
            const scanButton = Array.from(document.querySelectorAll('button')).find(
                button => button.innerText.includes('Find Monetization Opportunities')
            );
            if (scanButton) {
                scanButton.click();
                e.preventDefault();
            }
        }

        // Alt+R to clear and start over
        if (e.altKey && e.key === 'r' && !isTextField) {
            const resetButton = Array.from(document.querySelectorAll('button')).find(
                button => button.innerText.includes('Restart')
            );
            if (resetButton) {
                resetButton.click();
                e.preventDefault();  
            }
        }

        // Alt+E to send email when available
        if (e.altKey && e.key === 'e' && !isTextField) {
            const emailButton = Array.from(document.querySelectorAll('button')).find(
                button => button.innerText.includes('Send Email')
            );
            if (emailButton) {
                emailButton.click();
                e.preventDefault();
            }
        }

        // Alt+D to download CSV when available
        if (e.altKey && e.key === 'd' && !isTextField) {
            const downloadButton = Array.from(document.querySelectorAll('button')).find(
                button => button.innerText.includes('Download Opportunities CSV')
            );
            if (downloadButton) {
                downloadButton.click();
                e.preventDefault();
            }
        }
    });
    </script>
    """
    st.components.v1.html(shortcuts_js, height=0)

# --- CONTEXTUAL HELP ---
def setup_contextual_help():
    """Create a collapsible contextual help panel."""
    with st.sidebar:
        st.markdown("### ⌨️ Keyboard Shortcuts")
        st.markdown("""
        - **Alt+S**: Start scan
        - **Alt+R**: Restart
        - **Alt+E**: Send email
        - **Alt+D**: Download CSV
        """)

        st.markdown("### ❓ Contextual Help")
        help_toggle = st.checkbox("Show contextual help", key="show_help", value=False)
        if help_toggle:
            if "current_step" not in st.session_state:
                st.session_state.current_step = "input"

            # Display help based on current step
            if st.session_state.current_step == "input":
                st.info("""
                **Input Help:**
                - **Publisher Domain**: The main domain of the publisher.
                - **Publisher Name**: The name used for reports and emails.
                - **Publisher ID**: Unique identifier used in ads.txt.
                - **Example Direct Line**: Sample line from ads.txt showing a direct relationship.
                """)

            elif st.session_state.current_step == "results":
                st.info("""
                **Results Help:**
                - **Green rows**: High-value opportunities (Tranco rank ≤ 50,000).
                - **Yellow rows**: Publisher is owner/manager but opportunity exists.
                - **Domain**: Click on the domain to visit the site.
                - **Recheck**: Use this to try again if a domain was skipped.
                """)

            elif st.session_state.current_step == "email":
                st.info("""
                **Email Help:**
                - Enter the username part before @onlinemediasolutions.com.
                - The email will contain the table with proper formatting.
                - Highlights (green and yellow) will be preserved in the email.
                """)

# --- DATAFRAME FORMATTING ---
def format_dataframe(df):
    """Format DataFrame with color highlights for better visualization."""
    styled_df = df.copy()

    if "Highlight" not in styled_df.columns:
        styled_df["Highlight"] = "none"

    # Highlight logic
    styled_df.loc[styled_df["Tranco Rank"] <= 50000, "Highlight"] = "high_value"
    if "Owner/Manager" in styled_df.columns:
        styled_df.loc[styled_df["Owner/Manager"].isin(["Owner", "Manager"]), "Highlight"] = "owner_manager"

    def highlight_rows(row):
        value = row["Highlight"]
        if value == "high_value":
            return ["background-color: #d4edda"] * len(row)  # Green
        elif value == "owner_manager":
            return ["background-color: #fff3cd"] * len(row)  # Yellow
        else:
            return [""] * len(row)

    return styled_df.drop(columns=["Highlight"]).style.apply(highlight_rows, axis=1)

# --- RECHECK FUNCTION ---
def recheck_domain(domain):
    """Recheck a skipped domain and add it to results if successful."""
    pub_seller_domain = st.session_state.get("pub_seller_domain", "")
    pub_id = st.session_state.get("pub_id", "")

    if not pub_seller_domain or not pub_id:
        add_notification("Missing publisher information for recheck.", "error")
        return

    with st.spinner(f"Rechecking {domain}..."):
        result = check_domain(domain, pub_seller_domain, pub_id)
        if "error" in result:
            add_notification(f"Recheck failed: {result['error']}", "error")
            return

        # Add result to opportunities table
        if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
            st.session_state.opportunities_table = st.session_state.opportunities_table[
                st.session_state.opportunities_table["Domain"] != domain
            ]
            new_df = pd.DataFrame([result])
            st.session_state.opportunities_table = pd.concat([st.session_state.opportunities_table, new_df])
            st.session_state.opportunities_table.sort_values("Tranco Rank", inplace=True)

            # Remove from skipped log
            st.session_state.skipped_log = [
                (d, r) for d, r in st.session_state.skipped_log if d != domain
            ]

            add_notification(f"Successfully rechecked {domain}", "success")
            st.experimental_rerun()
        else:
            add_notification("No results table to update.", "error")

# --- MAIN LOGIC CONTINUES HERE ---
if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
    st.subheader(f"📈 Opportunities for {st.session_state.get('pub_name', 'Manual Domains')}")

    # Display DataFrame
    styled_df = format_dataframe(st.session_state.opportunities_table)
    st.dataframe(styled_df, use_container_width=True)

    # Download CSV button
    csv_data = st.session_state.opportunities_table.to_csv(index=False)
    st.download_button(
        label="⬇️ Download Opportunities CSV",
        data=csv_data,
        file_name="opportunities.csv",
        mime="text/csv",
    )

    # Email section
    st.markdown("### 📧 Email Results")
    email_username = st.text_input("Email Username (before @onlinemediasolutions.com):")
    if st.button("Send Email"):
        if not email_username.strip():
            st.error("Please enter a valid email username.")
        else:
            st.success("Email sent!")  # Placeholder for email functionality logic

# --- SKIPPED DOMAINS ---
if st.session_state.skipped_log:
    with st.expander("⚠️ Skipped Domains", expanded=False):
        st.markdown("### Skipped Domains")
        for idx, (domain, reason) in enumerate(st.session_state.skipped_log):
            col1, col2 = st.columns([3, 1])
            col1.write(f"{domain} - {reason}")
            if col2.button("Recheck", key=f"recheck_{idx}"):
                recheck_domain(domain)

# --- NOTIFICATIONS ---
render_notifications()

# --- RESULTS DISPLAY ---
if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
    st.session_state.current_step = "results"
    st.subheader(f"📊 Opportunities for {st.session_state.get('pub_name', 'Manual Domains')}")

    # Display success stats
    total = len(st.session_state.opportunities_table)
    oms_yes = (st.session_state.opportunities_table["OMS Buying"] == "Yes").sum()
    oms_no = total - oms_yes
    skipped_count = len(st.session_state.skipped_log)

    # Summary stats
    stats_cols = st.columns([1, 1, 1])
    stats_cols[0].metric("Total Domains Scanned", f"{total + skipped_count}")
    stats_cols[1].metric("Opportunities Found", f"{total}")
    stats_cols[2].metric("Skipped Domains", f"{skipped_count}")

    # Legend for color coding
    st.markdown("""
    <div style="margin-bottom: 10px; padding: 8px; border-radius: 4px; background-color: #f8f9fa;">
        <span style="font-weight: bold;">Color Legend:</span>
        <span style="background-color: #d4edda; padding: 2px 5px; margin: 0 5px; border-radius: 3px;">Green</span> = High-value opportunities (Tranco rank ≤ 50,000)
        <span style="background-color: #fff3cd; padding: 2px 5px; margin: 0 5px; border-radius: 3px;">Yellow</span> = Publisher is owner/manager
    </div>
    """, unsafe_allow_html=True)

    # Display formatted table
    styled_df = format_dataframe(st.session_state.opportunities_table)
    st.dataframe(styled_df, use_container_width=True)

    # Notes section
    st.subheader("📝 Domain Notes & Tags")
    st.markdown("Add notes or tags to domains (e.g., 'contacted', 'low CPM', 'priority'). Changes are saved automatically.")
    for idx, row in st.session_state.opportunities_table.iterrows():
        domain = row['Domain']

        # Create unique key for each domain's notes
        note_key = f"note_{domain.replace('.', '_')}"
        if note_key not in st.session_state:
            st.session_state[note_key] = row.get('Notes', '')

        # Display notes input
        cols = st.columns([2, 5])
        cols[0].markdown(f"**{domain}**")
        updated_note = cols[1].text_input(
            "Note",
            value=st.session_state[note_key],
            key=f"input_{note_key}",
            label_visibility="collapsed"
        )

        # Update notes in session state and table
        if updated_note != st.session_state[note_key]:
            st.session_state[note_key] = updated_note
            st.session_state.opportunities_table.at[idx, 'Notes'] = updated_note
            if "history" in st.session_state:
                key = f"{st.session_state.get('pub_name', 'manual')}_{st.session_state.get('pub_id', '')}"
                if key in st.session_state["history"]:
                    st.session_state["history"][key]["table"].at[idx, 'Notes'] = updated_note

    # Download CSV functionality
    @st.cache_data
    def convert_df_to_csv(df):
        return df.to_csv(index=False)

    csv_data = convert_df_to_csv(st.session_state.opportunities_table)
    col1, col2 = st.columns([1, 1])

    col1.download_button(
        "⬇️ Download Opportunities CSV",
        data=csv_data,
        file_name=f"opportunities_{st.session_state.get('pub_id', '')}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

    # Email functionality
    st.markdown("### 📧 Email Results")
    email_cols = st.columns([3, 5])
    email_username = email_cols[0].text_input(
        "Email Address",
        placeholder="e.g. johnsmith",
        label_visibility="collapsed",
        key="email_username"
    )
    email_cols[1].markdown(
        "<div style='margin-top: 0.6em; font-size: 16px;'>@onlinemediasolutions.com</div>",
        unsafe_allow_html=True
    )

    if st.button("Send Email"):
        if not email_username.strip():
            st.error("Please enter a valid email username.")
            add_notification("Missing email username", "error")
        else:
            try:
                if not hasattr(st, "secrets") or "EMAIL_ADDRESS" not in st.secrets or "EMAIL_PASSWORD" not in st.secrets:
                    st.error("Email configuration missing. Please check your Streamlit secrets.")
                    add_notification("Email configuration missing", "error")
                else:
                    # Email setup
                    full_email = f"{email_username.strip()}@onlinemediasolutions.com"
                    from_email = st.secrets["EMAIL_ADDRESS"]
                    email_password = st.secrets["EMAIL_PASSWORD"]

                    msg = EmailMessage()
                    msg["Subject"] = f"Monetization Opportunities for {st.session_state.get('pub_name', 'Manual Domains')}"
                    msg["From"] = from_email.strip()
                    msg["To"] = full_email.strip()

                    # Generate HTML table for email body
                    styled_rows = ""
                    for _, row in st.session_state.opportunities_table.iterrows():
                        bg_color = "#FFFFFF"
                        if row["Tranco Rank"] <= 50000:
                            bg_color = "#d4edda"  # Green
                        elif row["Owner/Manager"] in ["Owner", "Manager"]:
                            bg_color = "#fff3cd"  # Yellow

                        notes = row.get("Notes", "")
                        styled_rows += f"""
                        <tr style="background-color: {bg_color}">
                            <td><a href="https://{row['Domain']}" target="_blank">{row['Domain']}</a></td>
                            <td>{row['Tranco Rank']}</td>
                            <td>{row['Owner/Manager']}</td>
                            <td>{row['OMS Buying']}</td>
                            <td>{notes}</td>
                        </tr>"""

                    html_table = f"""
                    <table border="1" cellpadding="5" cellspacing="0" style="font-family:Arial; font-size:14px; border-collapse:collapse;">
                        <thead style="background-color:#f2f2f2;">
                            <tr>
                                <th>Domain</th>
                                <th>Tranco Rank</th>
                                <th>Owner/Manager</th>
                                <th>OMS Buying</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {styled_rows}
                        </tbody>
                    </table>"""

                    msg.set_content(f"Please find the monetization opportunities attached.")
                    msg.add_alternative(f"<html><body>{html_table}</body></html>", subtype="html")

                    # Send email
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                        server.login(from_email, email_password)
                        server.send_message(msg)

                    st.success(f"Email sent to {full_email}!")
                    add_notification(f"Email successfully sent to {full_email}", "success")
            except Exception as e:
                st.error(f"Error sending email: {str(e)}")
                add_notification("Error occurred while sending email", "error")

# --- SKIPPED DOMAINS ---
if "skipped_log" in st.session_state and st.session_state.skipped_log:
    with st.expander("⚠️ Skipped Domains", expanded=False):
        st.markdown("These domains were skipped during processing. You can recheck them individually.")
        skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
        
        for idx, (domain, reason) in enumerate(st.session_state.skipped_log):
            col1, col2, col3 = st.columns([5, 3, 2])
            col1.markdown(f"**{domain}**")
            col2.markdown(f"_{reason}_")
            if col3.button("Recheck", key=f"recheck_{idx}"):
                recheck_domain(domain)

        # Download skipped domains as CSV
        skipped_csv = skipped_df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Skipped Domains CSV",
            data=skipped_csv,
            file_name=f"skipped_domains_{st.session_state.get('pub_id', '')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# --- RESTART BUTTON ---
if st.button("Restart"):
    reset_session()
    st.experimental_rerun()

# --- NOTIFICATIONS ---
render_notifications()

# --- HISTORY MANAGEMENT ---
def save_to_history():
    """Save the current session's data to the history for future reference."""
    if "pub_id" not in st.session_state or not st.session_state["pub_id"].strip():
        add_notification("Cannot save to history. Missing Publisher ID.", "error")
        return

    pub_id = st.session_state["pub_id"].strip()
    pub_name = st.session_state.get("pub_name", "Unknown Publisher").strip()
    key = f"{pub_name}_{pub_id}"
    if key not in st.session_state.history:
        st.session_state.history[key] = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "table": st.session_state.opportunities_table.copy(),
            "skipped": list(st.session_state.skipped_log),
        }
        add_notification(f"Session saved for {pub_name} (ID: {pub_id})", "success")
    else:
        add_notification("Session already exists in history. Consider renaming Publisher ID.", "warning")


def load_from_history(key):
    """Load a session from the history based on a unique key."""
    if key not in st.session_state.history:
        add_notification("Requested session not found in history.", "error")
        return

    session = st.session_state.history[key]
    st.session_state.opportunities_table = session["table"].copy()
    st.session_state.skipped_log = list(session["skipped"])
    st.session_state.pub_name, st.session_state.pub_id = key.split("_", 1)
    add_notification(f"Session {key} loaded successfully.", "success")
    st.experimental_rerun()


# --- HISTORY DISPLAY ---
def display_history():
    """Display all sessions saved in history."""
    st.sidebar.markdown("### 📜 History")
    if not st.session_state.history:
        st.sidebar.info("No saved sessions yet.")
        return

    for key, session in st.session_state.history.items():
        pub_name, pub_id = key.split("_", 1)
        timestamp = session["timestamp"]
        table_size = len(session["table"])
        skipped_size = len(session["skipped"])

        with st.sidebar.expander(f"{pub_name} (ID: {pub_id})", expanded=False):
            st.markdown(f"**Date:** {timestamp}")
            st.markdown(f"**Opportunities:** {table_size}")
            st.markdown(f"**Skipped Domains:** {skipped_size}")
            load_button_key = f"load_{key}"
            if st.button("Load Session", key=load_button_key):
                load_from_history(key)


# --- SIDEBAR ---
st.sidebar.header("Navigation")
display_history()

if st.sidebar.button("Save Current Session"):
    save_to_history()

if st.sidebar.button("Clear All History"):
    if st.session_state.history:
        st.session_state.history.clear()
        add_notification("All history cleared successfully.", "success")
    else:
        add_notification("No history to clear.", "info")


# --- MAIN LOGIC ---
def main_logic():
    """Main processing logic for monetization opportunity finder."""
    if st.session_state.manual_mode:
        if not st.session_state.get("manual_domains", "").strip():
            st.error("Please enter domains in manual mode.")
            add_notification("No domains provided in manual mode.", "error")
            st.stop()

        domains = [
            domain.strip() for domain in re.split(r'[,\n]', st.session_state["manual_domains"]) if domain.strip()
        ]
    else:
        required_fields = ["pub_domain", "pub_name", "pub_id", "sample_ads_line"]
        for field in required_fields:
            if not st.session_state.get(field, "").strip():
                st.error("All fields are required in non-manual mode.")
                add_notification("Missing required fields.", "error")
                st.stop()

        domains = [st.session_state["pub_domain"]]

    # Processing domains
    results = []
    skipped = []
    for domain in domains:
        with st.spinner(f"Processing {domain}..."):
            result = check_domain(domain, st.session_state["pub_domain"], st.session_state["pub_id"])
            if "error" in result:
                skipped.append((domain, result["error"]))
            else:
                results.append(result)

    # Update session state
    if results:
        if "opportunities_table" not in st.session_state or st.session_state.opportunities_table.empty:
            st.session_state.opportunities_table = pd.DataFrame(results)
        else:
            new_results_df = pd.DataFrame(results)
            st.session_state.opportunities_table = pd.concat([st.session_state.opportunities_table, new_results_df])

    if skipped:
        st.session_state.skipped_log.extend(skipped)

    # Sort results by Tranco rank
    if not st.session_state.opportunities_table.empty:
        st.session_state.opportunities_table.sort_values("Tranco Rank", inplace=True)

    # Display results
    if results:
        st.success(f"Found {len(results)} new opportunities!")
    else:
        st.warning("No opportunities found.")

    if skipped:
        st.warning(f"{len(skipped)} domains were skipped. You can recheck them from the 'Skipped Domains' section.")


# Run the main processing logic if the user clicks the "Find Opportunities" button
if st.button("Find Opportunities"):
    main_logic()

# Render notifications
render_notifications()


