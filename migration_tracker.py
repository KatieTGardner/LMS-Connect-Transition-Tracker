import requests
import datetime
import sys
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import timezone, timedelta

# --- 1. CONFIGURATION ---
# Secrets from GitHub Actions
LD_API_TOKEN = sys.argv
GOOGLE_CREDS_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT')

# Your specific Spreadsheet ID (from the URL)
SHEET_ID = "1EtXGPq3cb1vGzbdMs--gibZkRExKmyQab9Yc82uA9Fg" 

PROJECT_KEY = "default"
ENV_KEY = "production"

# Config mapping Tabs to Flags
LMS_CONFIGS = {
    "google": {
        "tab": "[Data] Google Classroom - Districts",
        "flag": "lms-connect-google-classroom-mvp",
        "color": "#34A853", # Google Green
        "title": "Google Classroom"
    },
    "canvas": {
        "tab": "[Data] Canvas - Districts",
        "flag": "lms-connect-canvas-migration", 
        "color": "#E13939",
        "title": "Canvas"
    },
    "schoology": {
        "tab": "[Data] Schoology - Districts",
        "flag": "lms-connect-schoology-migration",
        "color": "#00AEEF",
        "title": "Schoology"
    }
}

# --- 2. AUTHENTICATION & DATA FETCHING ---
def get_google_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def get_ld_enabled_ids(flag_key):
    url = f"https://app.launchdarkly.com/api/v2/flags/{PROJECT_KEY}/{flag_key}"
    headers = {"Authorization": LD_API_TOKEN, "LD-API-Version": "beta"}
    try:
        res = requests.get(url, headers=headers).json()
        env_data = res.get('environments', {}).get(ENV_KEY, {})
        enabled = []
        # Targets
        for t in env_data.get('targets', []):
            if t.get('variation') == 0: enabled.extend(t.get('values', []))
        # Rules
        for rule in env_data.get('rules', []):
            if rule.get('variation') == 0:
                for c in rule.get('clauses', []): enabled.extend(c.get('values', []))
        return list(set([str(i).strip() for i in enabled if i]))
    except Exception as e:
        print(f"Error fetching LD flag {flag_key}: {e}")
        return []

# --- 3. CORE LOGIC ---
client = get_google_client()
doc = client.open_by_key(SHEET_ID)

lms_results = {}
for key, cfg in LMS_CONFIGS.items():
    try:
        worksheet = doc.worksheet(cfg['tab'])
        rows = worksheet.get_all_records() # Uses header row as keys
        ld_enabled = get_ld_enabled_ids(cfg['flag'])
        
        districts = []
        for row in rows:
            raw_id = str(row.get('District Id', '')).strip()
            # Handle prefixing
            prefixed = f"district:{raw_id}" if not raw_id.startswith("district:") else raw_id
            
            is_done = prefixed in ld_enabled
            districts.append({
                "name": row.get('District Name', 'Unknown Name'),
                "csm": row.get('CSM Name', 'Unassigned'),
                "segment": row.get('Segment', 'N/A'),
                "is_done": is_done
            })
            
        done_count = sum(1 for d in districts if d['is_done'])
        lms_results[key] = {
            "data": districts,
            "done": done_count,
            "total": len(districts),
            "percent": int((done_count / len(districts)) * 100) if len(districts) > 0 else 0
        }
    except Exception as e:
        print(f"Error processing {key}: {e}")
        lms_results[key] = {"data": [], "done": 0, "total": 0, "percent": 0}

# --- 4. HTML GENERATION ---
cards_html = ""
tables_html = ""

for key, cfg in LMS_CONFIGS.items():
    res = lms_results[key]
    
    # Card UI
    cards_html += f"""
    <div class="card">
        <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
        <div class="progress-container"><div class="progress-bar" style="background:{cfg['color']}; width:{res['percent']}%"></div></div>
        <div class="stats">{res['percent']}%</div>
        <p><b>{res['done']}</b> of {res['total']} Districts Enabled</p>
    </div>
    """
    
    # Table Rows
    rows_html = ""
    # Sort by Status (Pending first) then by Name
    sorted_districts = sorted(res['data'], key=lambda x: (x['is_done'], x['name']))
    for d in sorted_districts:
        status_class = "status-done" if d['is_done'] else "status-pend"
        status_text = "✅ Done" if d['is_done'] else "⏳ Pending"
        rows_html += f"""
        <tr>
            <td>{d['name']}</td>
            <td>{d['segment']}</td>
            <td>{d['csm']}</td>
            <td class="{status_class}">{status_text}</td>
        </tr>
        """
        
    tables_html += f"""
    <div class="table-container">
        <h3 style="border-left: 5px solid {cfg['color']}; padding-left:10px;">{cfg['title']} Breakdown</h3>
        <table>
            <thead><tr><th>District Name</th><th>Segment</th><th>CSM</th><th>Status</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """

# Timezone
pdt_now = datetime.datetime.now(timezone.utc) - timedelta(hours=7)
timestamp = pdt_now.strftime('%b %d, %Y at %I:%M %p')

# --- HTML GENERATION ---
cards_html = ""
tables_html = ""

for key, cfg in LMS_MAP.items():
    res = lms_results[key]
    
    # Card UI
    cards_html += f"""
    <div class="card">
        <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
        <div class="bar"><div style="background:{cfg['color']}; width:{res['percent']}%"></div></div>
        <div class="stats">{res['percent']}%</div>
        <p><b>{res['done']}</b> of {res['total']} Districts</p>
    </div>
    """
    
    # Table Rows
    rows_html = "".join([f"""
        <tr>
            <td>{d['n']}</td>
            <td>{d['s']}</td>
            <td>{d['c']}</td>
            <td class="{'ok' if d['done'] else 'no'}">{'✅ Done' if d['done'] else '⏳ Pending'}</td>
        </tr>
    """ for d in sorted(res['data'], key=lambda x: x['n'])])

    # The Collapsible "Dropdown" Section
    tables_html += f"""
    <details>
        <summary style="border-left: 5px solid {cfg['color']};">
            <span>{cfg['title']} Detailed Roster</span>
            <span class="summary-stats">{res['done']}/{res['total']}</span>
        </summary>
        <div class="table-content">
            <table>
                <thead>
                    <tr><th>District</th><th>Segment</th><th>CSM</th><th>Status</th></tr>
                </thead>
                <tbody>{rows_html if rows_html else '<tr><td colspan="4">No districts listed in sheet.</td></tr>'}</tbody>
            </table>
        </div>
    </details>
    """

# Final Assembly
ts = (datetime.datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%b %d, %Y at %I:%M %p')

full_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>LMS Transition Tracker</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f4f7f9; padding: 40px; color: #202124; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 40px; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 5px #0001; width: 260px; text-align: center; }}
        .bar {{ background: #eee; height: 10px; border-radius: 5px; margin: 15px 0; overflow: hidden; }}
        .bar div {{ height: 100%; transition: 1s; }}
        .stats {{ font-size: 2.5em; font-weight: bold; }}
        
        /* Accordion Styles */
        details {{ background: white; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 1px 3px #0001; overflow: hidden; max-width: 1000px; margin-left: auto; margin-right: auto; }}
        summary {{ padding: 15px 20px; cursor: pointer; font-weight: 600; display: flex; justify-content: space-between; align-items: center; outline: none; }}
        summary:hover {{ background: #fcfcfc; }}
        .summary-stats {{ background: #f1f3f4; padding: 2px 10px; border-radius: 12px; font-size: 0.8em; color: #5f6368; }}
        
        .table-content {{ padding: 0 20px 20px; border-top: 1px solid #eee; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; text-align: left; }}
        th, td {{ padding: 12px 8px; border-bottom: 1px solid #f1f3f4; }}
        th {{ color: #5f6368; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.5px; }}
        .ok {{ color: #1e8e3e; font-weight: bold; }}
        .no {{ color: #d93025; }}
        
        .timestamp {{ text-align: center; color: #9aa0a6; font-size: 0.8em; margin-top: 50px; }}
    </style>
</head>
<body>
    <h1 style="text-align:center; font-weight:400; margin-bottom:40px;">LMS Connect Transition Hub</h1>
    <div class="container">{cards_html}</div>
    {tables_html}
    <div class="timestamp">Last Sync: {ts} (PT)</div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(full_html)

# Save to the root of the repo
output_path = os.path.join(os.getcwd(), "index.html")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"Build successful. Dashboard generated at {output_path}")
