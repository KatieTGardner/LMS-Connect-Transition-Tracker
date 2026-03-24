import requests, datetime, sys, os, json, gspread
from google.oauth2.service_account import Credentials
from datetime import timezone, timedelta

# --- 1. CONFIGURATION ---
LD_TOKEN = sys.argv
GOOG_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
# Double check this ID matches your Google Sheet URL
SHEET_ID = "142A9794u_M87ZqB0fI-y0Ue_k78qP_W5667vC7V7-4U"
ENV = "production"

LMS_CONFIGS = {
    "google": {"tab": "[Data] Google Classroom - Districts", "flag": "lms-connect-google-classroom-mvp", "color": "#34A853", "title": "Google Classroom"},
    "canvas": {"tab": "[Data] Canvas - Districts", "flag": "lms-connect-canvas-migration", "color": "#E13939", "title": "Canvas"},
    "schoology": {"tab": "[Data] Schoology - Districts", "flag": "lms-connect-schoology-migration", "color": "#00AEEF", "title": "Schoology"}
}

def get_ld(flag):
    url = f"https://app.launchdarkly.com/api/v2/flags/default/{flag}"
    # Ensuring the token is passed as a simple string
    headers = {"Authorization": str(LD_TOKEN), "LD-API-Version": "beta"}
    try:
        res = requests.get(url, headers=headers).json()
        env_data = res.get('environments', {}).get(ENV, {})
        vals = []
        for t in env_data.get('targets', []):
            if t.get('variation') == 0: vals.extend(t.get('values', []))
        for r in env_data.get('rules', []):
            if r.get('variation') == 0:
                for c in r.get('clauses', []): vals.extend(c.get('values', []))
        return [str(i).strip() for i in vals]
    except Exception as e:
        print(f"Error fetching LD flag {flag}: {e}")
        return []

# --- 2. AUTH & FETCH ---
try:
    creds_dict = json.loads(GOOG_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    doc = client.open_by_key(SHEET_ID)
except Exception as e:
    print(f"CRITICAL ERROR: Could not open Google Sheet. Check ID and Service Account permissions. {e}")
    sys.exit(1)

cards_html, dropdowns_html = "", ""
for key, cfg in LMS_CONFIGS.items():
    try:
        rows = doc.worksheet(cfg['tab']).get_all_records()
        ld_ids = get_ld(cfg['flag'])
        
        apps_ok = any(i.startswith("app:") for i in ld_ids)
        
        districts_data = []
        for r in rows:
            rid = str(r.get('District Id', '')).strip()
            pre = f"district:{rid}" if not rid.startswith("district:") else rid
            is_done = pre in ld_ids and apps_ok
            districts_data.append({
                "name": r.get('District Name', rid), 
                "segment": r.get('Segment', 'N/A'), 
                "csm": r.get('CSM Name', 'N/A'), 
                "done": is_done
            })
        
        done_count = sum(1 for d in districts_data if d['done'])
        total = len(districts_data)
        pct = int((done_count/total)*100) if total > 0 else 0
        warn = "" if apps_ok or total == 0 else "<div style='color:#d93025;font-size:11px;font-weight:bold;margin-top:5px;'>⚠️ APP GATE CLOSED</div>"
        
        cards_html += f"""
        <div class="card">
            <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
            <div class="bar"><div style="width:{pct}%;background:{cfg['color']}"></div></div>
            <div class="stats">{pct}%</div>
            <p><b>{done_count}</b> / {total} Districts</p>
            {warn}
        </div>"""
        
        rows_html = "".join([f"""
            <tr>
                <td>{d['name']}</td>
                <td>{d['segment']}</td>
                <td>{d['csm']}</td>
                <td class="{'ok' if d['done'] else 'no'}">{'✅ Done' if d['done'] else '⏳ Pending'}</td>
            </tr>""" for d in sorted(districts_data, key=lambda x: x['name'])])
        
        dropdowns_html += f"""
        <details>
            <summary style="border-left: 5px solid {cfg['color']};">
                <span>{cfg['title']} Detailed Roster</span>
                <span class="sum-count">{done_count} / {total}</span>
            </summary>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>District</th><th>Segment</th><th>CSM</th><th>Status</th></tr></thead>
                    <tbody>{rows_html if rows_html else '<tr><td colspan="4">No data found in sheet tab.</td></tr>'}</tbody>
                </table>
            </div>
        </details>"""
    except Exception as e:
        print(f"Error processing tab {cfg['tab']}: {e}")

# --- 3. ASSEMBLY ---
ts = (datetime.datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%b %d, %Y at %I:%M %p')

final_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f4f7f9; padding: 40px; color: #202124; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 40px; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); width: 260px; text-align: center; }}
        .bar {{ background: #eee; height: 10px; border-radius: 5px; margin: 15px 0; overflow: hidden; }}
        .bar div {{ height: 100%; transition: width 1s; }}
        .stats {{ font-size: 2.5em; font-weight: bold; }}
        details {{ background: white; margin: 0 auto 12px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); max-width: 1000px; overflow: hidden; }}
        summary {{ padding: 15px 20px; cursor: pointer; font-weight: 600; display: flex; justify-content: space-between; align-items: center; outline: none; }}
        .sum-count {{ background: #f1f3f4; padding: 2px 12px; border-radius: 12px; font-size: 0.85em; }}
        .table-wrap {{ padding: 0 20px 20px; border-top: 1px solid #eee; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; text-align: left; }}
        th, td {{ padding: 12px 8px; border-bottom: 1px solid #f1f3f4; }}
        .ok {{ color: #1e8e3e; font-weight: bold; }} .no {{ color: #d93025; }}
        .ts {{ text-align: center; color: #9aa0a6; font-size: 0.8em; margin-top: 50px; }}
    </style>
</head>
<body>
    <h1 style="text-align:center; font-weight:400; margin-bottom:40px;">LMS Connect Transition Hub</h1>
    <div class="container">{cards_html}</div>
    {dropdowns_html}
    <div class="ts">Last Sync: {ts} (PT)</div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(final_content)
