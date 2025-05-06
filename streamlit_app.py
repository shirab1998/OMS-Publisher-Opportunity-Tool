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

# --- SESSION UTILITIES ---
if "notification_queue" not in st.session_state:
    st.session_state.notification_queue = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# --- NOTIFICATION SYSTEM ---
def add_notification(message, type="info", duration=5):
    """Add a notification to the queue with type (info, success, warning, error)"""
    st.session_state.notification_queue.append({
        "message": message,
        "type": type,
        "id": f"notification_{len(st.session_state.notification_queue)}",
        "timestamp": time.time(),
        "duration": duration
    })

def render_notifications():
    """Render all active notifications"""
    if not st.session_state.notification_queue:
        return
    
    current_time = time.time()
    remaining_notifications = []
    
    for notif in st.session_state.notification_queue:
        if current_time - notif["timestamp"] < notif["duration"]:
            # Still valid notification
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
            # Expired notification
            remaining_notifications.append('expired')
    
    # Only keep unexpired notifications
    st.session_state.notification_queue = [
        notif for i, notif in enumerate(st.session_state.notification_queue)
        if remaining_notifications[i] == 'active'
    ]

# --- KEYBOARD SHORTCUTS ---
def register_keyboard_shortcuts():
    """Setup keyboard shortcuts using JavaScript"""
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
                button => button.innerText.includes('Start Over')
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
        
        // Alt+H to toggle help
        if (e.altKey && e.key === 'h' && !isTextField) {
            const helpToggle = document.getElementById('help-toggle-checkbox');
            if (helpToggle) {
                helpToggle.checked = !helpToggle.checked;
                const event = new Event('change');
                helpToggle.dispatchEvent(event);
                e.preventDefault();
            }
        }
    });
    </script>
    """
    st.components.v1.html(shortcuts_js, height=0)

# --- CONTEXTUAL HELP SYSTEM ---
def setup_contextual_help():
    """Create a collapsible contextual help panel"""
    with st.sidebar:
        st.markdown("### ⌨️ Keyboard Shortcuts")
        st.markdown("""
        - **Alt+S**: Start scan
        - **Alt+R**: Reset/start over
        - **Alt+E**: Send email
        - **Alt+D**: Download CSV
        - **Alt+H**: Toggle help
        """)
        st.markdown("### ❓ Contextual Help")
        help_toggle = st.checkbox("Show contextual help", key="show_help", value=False)
        if help_toggle:
            if "current_step" not in st.session_state:
                st.session_state.current_step = "input"
            
            # Show different help based on current step
            if st.session_state.current_step == "input":
                st.info("""
                **Input Help:**
                - **Publisher Domain**: The main domain of the publisher
                - **Publisher Name**: Name used for reports and emails
                - **Publisher ID**: Unique identifier used in ads.txt
                - **Example Direct Line**: Sample line from ads.txt showing direct relationship
                
                You can also paste domains manually if you don't have a publisher domain with sellers.json.
                
                Press Alt+S to start the scan once you've filled in the fields.
                """)
            elif st.session_state.current_step == "results":
                st.info("""
                **Results Help:**
                - **Green rows**: High-value opportunities (Tranco rank ≤ 50,000)
                - **Yellow rows**: Publisher is owner/manager but opportunity exists
                - **Domain**: Click on domain to visit the site
                - **Recheck**: Use this to try again if a domain was skipped
                
                Use Alt+D to download results as CSV or Alt+E to email them.
                """)
            elif st.session_state.current_step == "email":
                st.info("""
                **Email Help:**
                - Enter just the username part before @onlinemediasolutions.com
                - The email will contain the table with proper formatting
                - Green and yellow highlights will be preserved in the email
                
                Press Alt+E to send the email once you've entered a username.
                """)

# --- TRANCO FUNCTIONS ---
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

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Monetization Opportunity Finder", layout="wide")
st.title("\U0001F4A1 Publisher Monetization Opportunity Finder")

# Setup keyboard shortcuts
register_keyboard_shortcuts()

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
                add_notification("Invalid Tranco URL format", "error")
            else:
                tranco_id = match.group(1)
                download_url = f"https://tranco-list.eu/download/{tranco_id}/full"
                try:
                    with st.spinner("Downloading Tranco list..."):
                        response = requests.get(download_url, timeout=30)
                        if response.status_code == 200:
                            with open(TRANCO_TOP_DOMAINS_FILE, "wb") as f:
                                f.write(response.content)
                            save_tranco_meta(tranco_id)
                            st.success(f"✅ Downloaded Tranco list (ID: {tranco_id})")
                            add_notification(f"Tranco list downloaded successfully (ID: {tranco_id})", "success")
                            st.session_state["show_input"] = False
                            show_input = False
                            # Force reload of tranco data
                            if "tranco_data" in st.session_state:
                                del st.session_state["tranco_data"]
                        else:
                            st.error(f"Failed to download Tranco list: HTTP {response.status_code}")
                            add_notification(f"Failed to download Tranco list: HTTP {response.status_code}", "error")
                except Exception as e:
                    st.error(f"Error downloading Tranco list: {str(e)}")
                    add_notification(f"Error downloading Tranco list", "error")

    st.markdown("---")
    st.subheader("\U0001F553 Recent Publishers")
    if "history" in st.session_state:
        recent_keys = list(reversed(list(st.session_state["history"].keys())))[:10]
        for key in recent_keys:
            entry = st.session_state["history"][key]
            label = f"{entry['name']} ({entry['id']})"
            small_date = f"<div style='font-size: 12px; color: gray;'>Generated: {entry['date']}</div>"
            if st.button(label, key=key):
                st.session_state.current_step = "results"
                st.subheader(f"\U0001F4DC Past Results: {entry['name']} ({entry['id']})")
                st.markdown(small_date, unsafe_allow_html=True)
                styled = entry['table'].copy()
                
                # Apply color formatting based on special columns
                st.dataframe(
                    format_dataframe(styled),
                    use_container_width=True
                )
                add_notification(f"Loaded saved results for {entry['name']}", "info")
                st.stop()

# Setup contextual help
setup_contextual_help()

# --- TRANCO LOADING ---
@st.cache_data(ttl=86400)  # Cache for one day
def load_tranco_top_domains():
    if not os.path.exists(TRANCO_TOP_DOMAINS_FILE):
        return {}
    try:
        df = pd.read_csv(TRANCO_TOP_DOMAINS_FILE, names=["Rank", "Domain"], skiprows=1)
        df = df[df["Rank"] <= TRANCO_THRESHOLD]
        return dict(zip(df["Domain"].str.lower(), df["Rank"]))
    except Exception as e:
        st.error(f"Error reading Tranco CSV: {str(e)}")
        add_notification(f"Error loading Tranco data", "error")
        return {}

tranco_rankings = load_tranco_top_domains()

if tranco_rankings:
    st.info("✅ Tranco list loaded and ready. You can proceed with domain analysis.")
else:
    st.warning("⚠️ No Tranco data available. Please upload a Tranco list before proceeding.")

# --- INPUT SECTION ---
if "opportunities_table" not in st.session_state or st.session_state.opportunities_table.empty:
    st.session_state.current_step = "input"
    st.markdown("### 📝 Enter Publisher Details")

    # Default to empty for state
    pub_domain, pub_name = "", ""
    manual_domains_input = st.text_area("Paste domains manually (comma or newline separated)", height=100)
    is_manual = bool(manual_domains_input.strip())

    if not is_manual:
        pub_domain = st.text_input("Publisher Domain", placeholder="example.com")
        pub_name = st.text_input("Publisher Name", placeholder="Example Media")
    else:
        st.info("Manual mode detected. Only Publisher ID and example ads.txt line are required.")

    pub_id = st.text_input("Publisher ID", placeholder="1536788745730056")
    sample_direct_line = st.text_input("Example ads.txt Direct Line", placeholder="connatix.com, 12345, DIRECT")

else:
    pub_domain = st.session_state.get("pub_domain", "")
    pub_name = st.session_state.get("pub_name", "")
    pub_id = st.session_state.get("pub_id", "")
    sample_direct_line = st.session_state.get("sample_direct_line", "")
    manual_domains_input = st.session_state.get("manual_domains_input", "")

# Parse the sample direct line
pub_seller_domain = ""
if sample_direct_line:
    parts = [p.strip() for p in sample_direct_line.split(',', 3)]
    if len(parts) >= 1:
        pub_seller_domain = parts[0].lower()

# --- DATAFRAME FORMATTING FUNCTION ---
def format_dataframe(df):
    """Format dataframe with colors based on rank and owner/manager status"""
    styled_df = df.copy()
    
    # Create a copy for styling
    if "Highlight" not in styled_df.columns:
        styled_df["Highlight"] = "none"
    
    # Set highlights based on logic
    styled_df.loc[styled_df["Tranco Rank"] <= 50000, "Highlight"] = "high_value"
    
    if "Owner_Manager" in styled_df.columns:
        # Domains where publisher is owner/manager get the yellow highlight
        styled_df.loc[(styled_df["Owner_Manager"] == "Owner") | 
                     (styled_df["Owner_Manager"] == "Manager"), "Highlight"] = "owner_manager"
    
    # Apply formatting
    def highlight_rows(row):
        value = row["Highlight"]
        if value == "high_value":
            return ["background-color: #d4edda"] * len(row)
        elif value == "owner_manager":
            return ["background-color: #fff3cd"] * len(row)
        else:
            return [""] * len(row)
    
    # Drop the highlight column before display
    display_df = styled_df.drop(columns=["Highlight"])
    
    return display_df.style.apply(highlight_rows, axis=1)

# Function to check one domain
def check_single_domain(domain, pub_seller_domain, pub_id):
    result = {}
    try:
        ads_url = f"https://{domain}/ads.txt"
        ads_response = requests.get(ads_url, timeout=10)
        
        if ads_response.status_code != 200:
            return {"error": f"HTTP error: {ads_response.status_code}"}
            
        ads_lines = ads_response.text.splitlines()
        
        # Parse all valid ads.txt lines
        parsed_lines = [parse_adstxt_line(line) for line in ads_lines]
        parsed_lines = [line for line in parsed_lines if line is not None]
        
        # Check if the publisher has a DIRECT relationship in this ads.txt
        has_direct = any(
            line['domain'] == pub_seller_domain and 
            line['relationship'] == 'direct'
            for line in parsed_lines
        )
        
        if not has_direct:
            return {"error": f"No direct line for publisher {pub_seller_domain}"}

        # Check if OMS already has a direct relationship with this publisher's ID
        has_oms_with_pub_id = any(
            "onlinemediasolutions.com" in line['domain'] and 
            pub_id in line['pub_id'] and 
            line['relationship'] == 'direct'
            for line in parsed_lines
        )
        
        if has_oms_with_pub_id:
            return {"error": "OMS is already buying from this publisher"}

        # Check if OMS has any other direct relationship with this publisher
        is_oms_buyer = any(
            "onlinemediasolutions.com" in line['domain'] and 
            pub_id not in line['pub_id'] and 
            line['relationship'] == 'direct'
            for line in parsed_lines
        )

        # Check for ownerdomain and managerdomain tags
        owner_status = "No"
        
        # First look for ownerdomain
        for line in ads_lines:
            line_lower = line.lower()
            if "ownerdomain" in line_lower and pub_seller_domain in line_lower:
                owner_status = "Owner"
                break
        
        # If not found, look for managerdomain
        if owner_status == "No":
            for line in ads_lines:
                line_lower = line.lower()
                if "managerdomain" in line_lower and pub_seller_domain in line_lower:
                    owner_status = "Manager"
                    break
        
        # If neither found, check if one is missing
        if owner_status == "No":
            has_owner = any("ownerdomain" in line.lower() for line in ads_lines)
            has_manager = any("managerdomain" in line.lower() for line in ads_lines)
            
            if not has_owner and has_manager:
                owner_status = "Owner not indicated"
            elif has_owner and not has_manager:
                owner_status = "Manager not indicated"
            elif not has_owner and not has_manager:
                owner_status = "Neither Owner nor Manager indicated"

        # Check Tranco ranking
        domain_key = domain.lower()
        if domain_key not in tranco_rankings:
            return {
                "error": "Not in Tranco top list",
                "owner_status": owner_status  # Return owner status even if not in Tranco
            }

        rank = tranco_rankings[domain_key]
        return {
            "Domain": domain,
            "Tranco Rank": rank,
            "OMS Buying": "Yes" if is_oms_buyer else "No",
            "Owner_Manager": owner_status
        }
		# And add "Notes" field like this:
return {
    "Domain": domain,
    "Tranco Rank": rank,
    "OMS Buying": "Yes" if is_oms_buyer else "No",
    "Owner_Manager": owner_status,
    "Notes": ""  # Add empty Notes field for each domain
}

    except requests.exceptions.RequestException as e:
        return {"error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"error": f"Processing error: {str(e)}"}

# --- MAIN FUNCTIONALITY BUTTON ---
if st.button("🔍 Find Monetization Opportunities", help="Alt+S"):
    st.session_state["pub_domain"] = pub_domain
    st.session_state["pub_name"] = pub_name
    st.session_state["pub_id"] = pub_id
    st.session_state["sample_direct_line"] = sample_direct_line
    st.session_state["manual_domains_input"] = manual_domains_input

    if not pub_id or not sample_direct_line:
        st.error("Publisher ID and Example Direct Line are required.")
        add_notification("Missing required fields", "error")
    elif not pub_seller_domain:
        st.error("Invalid Example Direct Line format. It should contain at least a domain.")
        add_notification("Invalid direct line format", "error")
    else:
        st.session_state.current_step = "processing"
        with st.spinner("🔎 Checking domains..."):
            try:
                st.session_state.skipped_log = []
                results = []
                domains = set()

                # Check if we have manual domains
                if manual_domains_input.strip():
                    manual_lines = re.split(r'[\n,]+', manual_domains_input.strip())
                    domains = {d.strip().lower() for d in manual_lines if d.strip()}
                    add_notification(f"Found {len(domains)} domains from manual input", "info")
                elif pub_domain:
                    # Try sellers.json
                    sellers_url = f"https://{pub_domain}/sellers.json"
                    try:
                        with st.spinner(f"Fetching sellers.json from {pub_domain}..."):
                            sellers_response = requests.get(sellers_url, timeout=15)
                            if sellers_response.status_code == 200:
                                try:
                                    sellers_data = sellers_response.json()
                                    if "sellers" in sellers_data:
                                        domains = {
                                            s.get("domain").lower() for s in sellers_data["sellers"]
                                            if s.get("domain") and isinstance(s.get("domain"), str) and 
                                            s.get("domain").lower() != pub_domain.lower()
                                        }
                                        st.success(f"Found {len(domains)} domains in sellers.json")
                                        add_notification(f"Found {len(domains)} domains in sellers.json", "success")
                                    else:
                                        st.warning("No sellers field in sellers.json. Provide manual domains if needed.")
                                        add_notification("No sellers field found in sellers.json", "warning")
                                except json.JSONDecodeError:
                                    st.error("Invalid JSON in sellers.json response")
                                    add_notification("Invalid JSON in sellers.json", "error")
                            else:
                                st.error(f"Failed to fetch sellers.json: HTTP {sellers_response.status_code}")
                                add_notification(f"Failed to fetch sellers.json: HTTP {sellers_response.status_code}", "error")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error fetching sellers.json: {str(e)}")
                        add_notification("Error fetching sellers.json", "error")
                
                if not domains:
                    st.error("No valid domains found to check.")
                    add_notification("No valid domains found", "error")
                else:
                    progress = st.progress(0)
                    progress_text = st.empty()
                    
                    for idx, domain in enumerate(domains, start=1):
                        try:
                            progress_text.text(f"Checking domain {idx}/{len(domains)} ({(idx/len(domains)*100):.1f}%): {domain}")
                            
                            domain_result = check_single_domain(domain, pub_seller_domain, pub_id)
                            
                            if "error" in domain_result:
                                # Save owner status for skipped domains too
                                owner_status = domain_result.get("owner_status", "Unknown")
                                if owner_status in ["Owner", "Manager"]:
                                    # Keep domains where publisher is owner/manager
                                    if domain.lower() in tranco_rankings:
                                        # Only include if in Tranco despite other errors
                                        results.append({
                                            "Domain": domain,
                                            "Tranco Rank": tranco_rankings[domain.lower()],
                                            "OMS Buying": "No",  # Default since we don't know
                                            "Owner_Manager": owner_status,
                                        })
                                        # Still log the error
                                        st.session_state.skipped_log.append((domain, domain_result["error"] + f" (but kept as {owner_status})"))
                                    else:
                                        st.session_state.skipped_log.append((domain, domain_result["error"] + f" (would be {owner_status})"))
                                else:
                                    st.session_state.skipped_log.append((domain, domain_result["error"]))
                            else:
                                results.append(domain_result)
                            
                            # Small delay to avoid overwhelming servers
                            time.sleep(0.1)

                        except Exception as e:
                            st.session_state.skipped_log.append((domain, f"Unexpected error: {str(e)}"))

                        progress.progress(idx / len(domains))

					if not results:
						st.warning("No monetization opportunities found based on your criteria.")
						add_notification("No opportunities found", "warning")
						st.session_state.current_step = "input"
					else:
						st.session_state.current_step = "results"
						df_results = pd.DataFrame(results)
    
					# Make sure Notes column exists
					if "Notes" not in df_results.columns:
						df_results["Notes"] = ""
        
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
                        add_notification(f"Found {len(results)} opportunities", "success")
                        st.balloons()

            except Exception as e:
                st.error(f"Error while processing: {str(e)}")
                add_notification("Error occurred during processing", "error")
                import traceback
                st.error(traceback.format_exc())
                st.session_state.current_step = "input"
				
				
# --- ONE-CLICK RECHECK FUNCTIONALITY ---
def recheck_domain(domain):
    """Recheck a previously skipped domain and add it to results if successful"""
    if not pub_seller_domain or not pub_id:
        add_notification("Missing publisher information for recheck", "error")
        return
    
    # Save existing notes if any
    existing_notes = ""
    if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
        domain_row = st.session_state.opportunities_table[st.session_state.opportunities_table["Domain"] == domain]
        if not domain_row.empty and 'Notes' in domain_row.columns:
            existing_notes = domain_row.iloc[0]['Notes']
    
    # Then after this section where the result is checked:
    # elif "error" in result:
    #     add_notification(f"Recheck failed: {result['error']}", "error")
    #     return
    
    # Add this to restore notes:
    # Add existing notes back to result
    if "error" not in result:
        result["Notes"] = existing_notes

    
    with st.spinner(f"🔍 Rechecking {domain}..."):
        result = check_single_domain(domain, pub_seller_domain, pub_id)
        
        # Special case: Keep domain if it's an owner/manager even if otherwise would be skipped
        if "error" in result and "owner_status" in result and result["owner_status"] in ["Owner", "Manager"]:
            if domain.lower() in tranco_rankings:
                # Create a valid entry despite other errors
                result = {
                    "Domain": domain,
                    "Tranco Rank": tranco_rankings[domain.lower()],
                    "OMS Buying": "No",  # Default since we don't know
                    "Owner_Manager": result["owner_status"],
                }
                add_notification(f"Added {domain} as {result['Owner_Manager']} despite errors", "warning")
            else:
                add_notification(f"Domain {domain} is {result['owner_status']} but not in Tranco", "warning")
                return
        elif "error" in result:
            add_notification(f"Recheck failed: {result['error']}", "error")
            return
            
        # Add to results
        if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
            # Remove if exists
            st.session_state.opportunities_table = st.session_state.opportunities_table[
                st.session_state.opportunities_table["Domain"] != domain
            ]
            
            # Add new result
            new_df = pd.DataFrame([result])
            st.session_state.opportunities_table = pd.concat([st.session_state.opportunities_table, new_df])
            st.session_state.opportunities_table.sort_values("Tranco Rank", inplace=True)
            
            # Remove from skipped log
            st.session_state.skipped_log = [(d, r) for d, r in st.session_state.skipped_log if d != domain]
            
            # Update history if present
            if "history" in st.session_state:
                key = f"{pub_name or 'manual'}_{pub_id}"
                if key in st.session_state["history"]:
                    st.session_state["history"][key]["table"] = st.session_state.opportunities_table.copy()
                    
            add_notification(f"Successfully rechecked {domain}", "success")
            st.experimental_rerun()
        else:
            add_notification("No results table to update", "error")

# --- RESULTS DISPLAY ---
if "opportunities_table" in st.session_state and not st.session_state.opportunities_table.empty:
    st.session_state.current_step = "results"
    
    st.subheader(f"📈 Opportunities for {pub_name or 'Manual Domains'} ({pub_id})")
    
    # Success stats
    total = len(st.session_state.opportunities_table)
    oms_yes = (st.session_state.opportunities_table["OMS Buying"] == "Yes").sum()
    oms_no = total - oms_yes
    skipped_count = len(st.session_state.skipped_log) if "skipped_log" in st.session_state else 0
    
    # Stats bar with better formatting
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
    
    # Display properly formatted table
    styled_df = format_dataframe(st.session_state.opportunities_table)
    
    # Add clickable domain links through a component
    def make_clickable(val):
        return f'<a href="https://{val}" target="_blank">{val}</a>'
    
    clickable_df = styled_df.copy()
    clickable_df.format({'Domain': make_clickable})
    
    st.dataframe(styled_df, use_container_width=True)
	st.subheader("📝 Domain Notes & Tags")
	st.markdown("Add notes or tags to domains (e.g., 'contacted', 'low CPM', 'priority'). Changes are saved automatically."	)

# Create a container for the notes editor
	notes_container = st.container()	
    
# Create an edit interface for each row
with notes_container:
    for idx, row in st.session_state.opportunities_table.iterrows():
        domain = row['Domain']
        
        # Create unique key for each domain's notes
        note_key = f"note_{domain.replace('.', '_')}"
        
        # Initialize the note in session state if not already there
        if note_key not in st.session_state:
            st.session_state[note_key] = row.get('Notes', '')
            
        # Create a row with domain and note input
        cols = st.columns([2, 5])
        cols[0].markdown(f"**{domain}**")
        
        # When note is changed, update the dataframe
        updated_note = cols[1].text_input(
            "Note", 
            value=st.session_state[note_key],
            key=f"input_{note_key}",
            label_visibility="collapsed"
        )
        
        # Update dataframe when note changes
        if updated_note != st.session_state[note_key]:
            st.session_state[note_key] = updated_note
            st.session_state.opportunities_table.at[idx, 'Notes'] = updated_note
            
            # Also update in history
            if "history" in st.session_state:
                key = f"{pub_name or 'manual'}_{pub_id}"
                if key in st.session_state["history"]:
                    st.session_state["history"][key]["table"].at[idx, 'Notes'] = updated_note
					
					
    # Download CSV button with enhanced formatting
    @st.cache_data
    def convert_df_to_csv_with_formatting(df):
        # Create a copy for CSV formatting
        csv_df = df.copy()
        
        # Add a column for Excel conditional formatting (can be read by Excel)
        csv_df['_highlight'] = 'none'
        csv_df.loc[csv_df['Tranco Rank'] <= 50000, '_highlight'] = 'high_value'
        csv_df.loc[csv_df['Owner_Manager'].isin(['Owner', 'Manager']), '_highlight'] = 'owner_manager'
        
        return csv_df.to_csv(index=False)
    
    csv_data = convert_df_to_csv_with_formatting(st.session_state.opportunities_table)
    col1, col2 = st.columns([1, 1])
    
    # Download CSV button
    col1.download_button(
        "⬇️ Download Opportunities CSV",
        data=csv_data,
        file_name=f"opportunities_{pub_id}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        help="Alt+D"
    )
    
    # Generate a pre-formatted Excel file (optional)
    if col2.button("📊 Generate Excel Report"):
        with st.spinner("Preparing Excel report..."):
            add_notification("Excel report generation not implemented yet", "info")
    
    # Add email function if we have results
    st.markdown("### 📧 Email This List")
    st.markdown("Send the results with proper formatting to a team member:")
    
    email_cols = st.columns([3, 5])
    email_local_part = email_cols[0].text_input(
        "Email Address",
        placeholder="e.g. johnsmith",
        label_visibility="collapsed",
        key="email_username"
    )
    email_cols[1].markdown(
        "<div style='margin-top: 0.6em; font-size: 16px;'>@onlinemediasolutions.com</div>",
        unsafe_allow_html=True
    )
    
	def send_email():
    """Send email with formatted results table"""
    if not email_local_part.strip():
        st.error("Please enter a valid username before sending the email.")
        add_notification("Missing email username", "error")
        return

    try:
        if not hasattr(st, "secrets") or "EMAIL_ADDRESS" not in st.secrets or "EMAIL_PASSWORD" not in st.secrets:
            st.error("Email configuration missing. Please check your Streamlit secrets.")
            add_notification("Email configuration missing", "error")
            return

        full_email = f"{email_local_part.strip()}@onlinemediasolutions.com"
        from_email = st.secrets["EMAIL_ADDRESS"]
        email_password = st.secrets["EMAIL_PASSWORD"]

        def sanitize_header(text):
            text = unicodedata.normalize("NFKD", str(text))
            text = re.sub(r'[^ -~]', '', text)
            return text.strip().replace("\r", "").replace("\n", "")

        subject_name = sanitize_header(pub_name or "Manual Domains")
        subject_id = sanitize_header(pub_id or "NoID")

        msg = EmailMessage()
        msg["Subject"] = f"{subject_name} ({subject_id}) Monetization Opportunities"
        msg["From"] = from_email.strip()
        msg["To"] = full_email.strip()

        # Construct HTML rows
        styled_rows = ""
        for _, row in st.session_state.opportunities_table.iterrows():
            bg_color = "#FFFFFF"
            if row["Tranco Rank"] <= 50000:
                bg_color = "#d4edda"
            elif row["Owner_Manager"] in ["Owner", "Manager"]:
                bg_color = "#fff3cd"

            notes = row.get("Notes", "")
            styled_rows += f"""
                <tr style="background-color: {bg_color}">
                    <td><a href="https://{row['Domain']}" target="_blank">{row['Domain']}</a></td>
                    <td>{row['Tranco Rank']}</td>
                    <td>{row['Owner_Manager']}</td>
                    <td>{row['OMS Buying']}</td>
                    <td>{notes}</td>
                </tr>
            """

        # Construct HTML body
        html_table = f"""
        <html>
          <body style="font-family:Arial; font-size:14px;">
            <p>Hello,</p>
            <p>Here are the monetization opportunities for <strong>{subject_name}</strong> (ID: {subject_id}):</p>
            <p><strong>Legend:</strong><br>
                <span style="background-color: #d4edda; padding: 2px 5px;">Green</span> = High-value opportunities (Tranco rank ≤ 50,000)<br>
                <span style="background-color: #fff3cd; padding: 2px 5px;">Yellow</span> = Publisher is owner/manager
            </p>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
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
            </table>
            <p>Best regards,<br>The OMS Team</p>
          </body>
        </html>
        """

        msg.set_content("This is an HTML email. Please view it in an HTML-compatible email client.")
        msg.add_alternative(html_table, subtype='html')

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(from_email, email_password)
            smtp.send_message(msg)

        st.success(f"📧 Email successfully sent to {full_email}")
        add_notification(f"Email sent to {full_email}", "success")

    except Exception as e:
        st.error(f"Error sending email: {str(e)}")
        add_notification("Email sending failed", "error")

            
            # Complete HTML table
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
            
            # Complete email body
            body = f"""
            <html>
              <body>
                <p>Hello,</p>
                <p>Here are the monetization opportunities for <strong>{subject_name}</strong> (ID: {subject_id}):</p>
                <p><strong>Legend:</strong><br>
                <span style="background-color: #d4edda; padding: 2px 5px;">Green</span> = High-value opportunities (Tranco rank ≤ 50,000)<br>
                <span style="

# --- SKIPPED DOMAINS DISPLAY ---
if "skipped_log" in st.session_state and st.session_state.skipped_log:
    with st.expander("⚠️ Skipped Domains", expanded=False):
        st.markdown("### ⚠️ Skipped Domains")
        st.markdown("These domains were skipped during processing. You can recheck them individually.")
        
        skipped_df = pd.DataFrame(st.session_state.skipped_log, columns=["Domain", "Reason"])
        
        for idx, (domain, reason) in enumerate(st.session_state.skipped_log):
            col1, col2, col3 = st.columns([5, 3, 2])
            col1.markdown(f"**{domain}**")
            col2.markdown(f"_{reason}_")
            if col3.button("Recheck", key=f"recheck_{idx}"):
                recheck_domain(domain)
        
        # Download button for skipped domains
        skipped_csv = skipped_df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Skipped Domains CSV",
            data=skipped_csv,
            file_name=f"skipped_domains_{pub_id}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# --- START OVER BUTTON ---
if st.button("🔄 Start Over", help="Alt+R"):
    # Keep history but clear everything else
    history_backup = st.session_state.get("history", {}).copy()
    tranco_data_backup = st.session_state.get("tranco_data", None)
    
    # Clear session state
    st.session_state.clear()
    
    # Restore history and tranco data
    st.session_state["history"] = history_backup
    if tranco_data_backup is not None:
        st.session_state["tranco_data"] = tranco_data_backup
    
    # Reset current step
    st.session_state.current_step = "input"
    
    # Force reload
    st.experimental_rerun()

# --- DISPLAY NOTIFICATIONS ---
render_notifications()
