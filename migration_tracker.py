import requests
import datetime
import sys
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import timezone, timedelta

# --- CONFIGURATION ---
LD_API_TOKEN = sys.argv
# We'll store the Google JSON in a GitHub Secret
GOOGLE_CREDS_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT') 
SHEET_ID = "YOUR_SPREADSHEET_ID_HERE" # Found in your browser URL

BASE_DIR = os.getcwd()
PROJECT_KEY = "default"
ENV_KEY = "production"

LMS_CONFIGS = {
    "google": {
        "tab": "[Data] Google Classroom - Districts",
        "flag": "lms-connect-google-classroom-mvp",
        "color": "#34A853",
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

# --- AUTHENTICATION ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_CREDS_JSON)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)

def get_ld_enabled_ids(flag_key):
    url = f"https://app.launchdarkly.com/api/v2/flags/{PROJECT_KEY}/{flag_key}"
    headers = {"Authorization": LD_API_TOKEN, "LD-API-Version": "beta"}
    try:
        data = requests.get(url, headers=headers).json()
        env_data = data.get('environments', {}).get(ENV_KEY, {})
        enabled = []
        for t in env_data.get('targets', []):
            if t.get('variation') == 0: enabled.extend(t.get('values', []))
        for rule in env_data.get('rules', []):
            if rule.get('variation') == 0:
                for c in rule.get('clauses', []): enabled.extend(c.get('values', []))
        return list(set([str(i).strip() for i in enabled if i]))
    except:
        return []

# --- PROCESSING ---
lms_results = {}
for key, cfg in LMS_CONFIGS.items():
    worksheet = sheet.worksheet(cfg['tab'])
    rows = worksheet.get_all_records() # Converts headers to dictionary keys
    
    ld_enabled = get_ld_enabled_ids(cfg['flag'])
    
    processed_districts = []
    for row in rows:
        raw_id = str(row['District Id']).strip()
        prefixed_id = f"district:{raw_id}" if not raw_id.startswith("district:") else raw_id
        
        is_done = prefixed_id in ld_enabled
        processed_districts.append({
            "name": row['District Name'],
            "csm": row['CSM Name'],
            "segment": row['Segment'],
            "status": "✅ Done" if is_done else "⏳ Pending",
            "is_done": is_done
        })

    done_count = sum(1 for d in processed_districts if d['is_done'])
    total_count = len(processed_districts)
    
    lms_results[key] = {
        "districts": processed_districts,
        "percent": int((done_count / total_count) * 100) if total_count > 0 else 0,
        "done": done_count,
        "total": total_count
    }

# --- HTML GENERATION ---
cards_html = ""
details_html = ""

for key, cfg in LMS_CONFIGS.items():
    res = lms_results[key]
    cards_html += f"""
    <div class="card">
        <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
        <div class="progress-container"><div class="progress-bar" style="background:{cfg['color']}; width:{res['percent']}%"></div></div>
        <div class="stats">{res['percent']}%</div>
        <p><b>{res['done']}</b> of {res['total']} Districts</p>
    </div>
    """
    
    table_rows = "".join([f"""
        <tr>
            <td>{d['name']}</td>
            <td>{d['segment']}</td>
            <td>{d['csm']}</td>
            <td class="{'status-done' if d['is_done'] else 'status-pend'}">{d['status']}</td>
        </tr>
    """ for d in res['districts']])

    details_html += f"""
    <div class="detail-block">
        <h3 style="color:{cfg['color']}">{cfg['title']} Roster</h3>
        <table>
            <thead><tr><th>District</th><th>Segment</th><th>CSM</th><th>Status</th></tr></thead>
            <tbody>{table_rows}</tbody>
        </table>
    </div>
    """

# (Rest of the HTML/CSS/Timezone logic remains, but with wider table styles)
# ... [Simplified for brevity, ensure you use the previous CSS + Table CSS] ...
