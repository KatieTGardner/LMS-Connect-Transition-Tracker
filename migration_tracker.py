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

final_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>LMS Transition Tracker</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f8f9fa; color: #202124; padding: 40px; line-height: 1.5; }}
        .header {{ text-align: center; margin-bottom: 40px; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 40px; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 280px; text-align: center; }}
        .progress-container {{ background: #e8eaed; border-radius: 10px; height: 12px; margin: 15px 0; overflow: hidden; }}
        .progress-bar {{ height: 100%; transition: width 1s ease-in-out; }}
        .stats {{ font-size: 2.5em; font-weight: bold; }}
        
        #details {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); display: none; }}
        .table-container {{ margin-bottom: 40px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9em; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e8eaed; }}
        th {{ background: #f1f3f4; font-weight: 600; position: sticky; top: 0; }}
        .status-done {{ color: #1e8e3e; font-weight: bold; }}
        .status-pend {{ color: #d93025; font-weight: bold; }}
        
        .btn {{ display: block; margin: 0 auto 40px; padding: 12px 30px; background: #1a73e8; color: white; border: none; border-radius: 24px; font-weight: 500; cursor: pointer; font-size: 1em; }}
        .timestamp {{ text-align: center; color: #70757a; font-size: 0.8em; margin-top: 40px; }}
    </style>
</head>
<body>
    <div class="header"><h1>LMS Connect Transition Hub</h1></div>
    <div class="container">{cards_html}</div>
    
    <button class="btn" onclick="document.getElementById('details').style.display='block'; this.style.display='none'">View Detailed Roster</button>
    
    <div id="details">{tables_html}</div>
    <div class="timestamp">Last Sync: {timestamp} (PT)</div>
</body>
</html>
"""

# Save to the root of the repo
output_path = os.path.join(os.getcwd(), "index.html")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"Build successful. Dashboard generated at {output_path}")
