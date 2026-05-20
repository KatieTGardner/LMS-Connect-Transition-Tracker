import requests, datetime, sys, os, json, gspread, re
from google.oauth2.service_account import Credentials
from datetime import timezone, timedelta

# --- 1. CONFIGURATION ---
LD_TOKEN = sys.argv if len(sys.argv) > 1 else "" 
GOOG_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
SHEET_ID = "1EtXGPq3cb1vGzbdMs--gibZkRExKmyQab9Yc82uA9Fg"
ENV = "production"

LMS_CONFIGS = {
    "google": {"tab": "[Data] Google Classroom - Districts", "flag": "lms-connect-google-classroom-mvp", "color": "#34A853", "title": "Google Classroom"},
    "canvas": {"tab": "[Data] Canvas - Districts", "flag": "lms-connect-fully-owned-solution-canvas", "color": "#E13939", "title": "Canvas"},
    "schoology": {"tab": "[Data] Schoology - Districts", "flag": "lms-connect-fully-owned-solution-schoology", "color": "#00AEEF", "title": "Schoology"}
}

# The true production scope mapping parameters (Excludes all test/dev IDs)
app_name_map = {
    "5d41ba752769fb0001ae10fa": "Khan Academy",
    "64cbff9e498f330001ce6412": "My Ada Math",
    "68a35343a1f1a21425233bcf": "Ellipsis Education",
    "5b2077fb03a826000165c4a1": "ClassHero",
    "607472b92b7bf90001040d41": "Smart Science Education",
    "66b1022e6c74dbaab2f81c82": "Blueprint (PlayVS, formerly Generation Esports)",
    "5501ca28059de501000000bb": "BrainPOP",
    "62b4a8cf26567400018ce321": "Progress Learning",
    "63e410a5be04240001a20b02": "Klett World Languages",
    "55d8f1cc71fafb0100005a90": "American Reading Company",
    "5f972d8daa91ed0001504bc0": "Thinking Nation",
    "681d2717cbe25ec8ad378f96": "Open Up Resources",
    "61fd9525b853040001079c9c": "Studies Weekly",
    "5b4640bc454d4a0001cd154c": "BrainPOP ELL",
    "5b46407f2b1e1d000194b2c1": "BrainPOP Jr.",
    "60076a4160534c000106935d": "BrainPOP Español",
    "60076a803269cb000103882b": "BrainPOP Français",
    "604fb030c8497b000106ef82": "BrainPOP Science (SSO Only)",
    "5b4640e82b1e1d000194b2c2": "BrainPOP Suite"
}

def get_ld(flag):
    url = f"https://app.launchdarkly.com/api/v2/flags/default/{flag}"
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
        return [str(i).strip().lower() for i in vals]
    except Exception as e:
        print(f"Error fetching LD flag {flag}: {e}")
        return []

# --- 2. AUTH & FETCH ---
try:
    creds_dict = json.loads(GOOG_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    doc = gspread.authorize(creds).open_by_key(SHEET_ID)
except Exception as e:
    print(f"CRITICAL ERROR: {e}")
    sys.exit(1)

cards_html, dropdowns_html = "", ""
global_apps_matrix = {}
total_targeted_apps = len(app_name_map)

# Loop over configurations to parse specific LaunchDarkly targets
for key, cfg in LMS_CONFIGS.items():
    ld_ids = get_ld(cfg['flag'])
    
    for app_id in app_name_map.keys():
        clean_app_id = app_id.lower().strip()
        # Verify both variations (raw hexadecimal vs string array prefix structure)
        if clean_app_id in ld_ids or f"app:{clean_app_id}" in ld_ids or any(clean_app_id in str(x) for x in ld_ids):
            if clean_app_id not in global_apps_matrix:
                global_apps_matrix[clean_app_id] = {"google": False, "canvas": False, "schoology": False}
            global_apps_matrix[clean_app_id][key] = True

# Loop over district spreadsheet tabs to preserve your deep roster tracking frames
for key, cfg in LMS_CONFIGS.items():
    try:
        rows = doc.worksheet(cfg['tab']).get_all_records()
        ld_ids = get_ld(cfg['flag'])
        apps_ok = any("app:" in str(i) for i in ld_ids)
        
        districts_data = []
        for r in rows:
            rid = str(r.get('District Id', '')).strip()
            pre = f"district:{rid}" if rid and not rid.startswith("district:") else rid
            
            raw_apps = str(r.get('Connected Apps', '')).strip()
            app_list = [a.strip() for a in re.split(',|;|\|', raw_apps) if a.strip()]
            formatted_apps = ", ".join(app_list) if app_list else "None"

            bts_date = str(r.get('BTS Dates', 'TBD')).strip()
            if not bts_date: bts_date = "TBD"
            
            is_done = (pre.lower() in ld_ids or rid.lower() in ld_ids)
            districts_data.append({
                "id": rid, 
                "name": r.get('District Name', rid), 
                "segment": r.get('Segment', 'N/A'), 
                "csm": r.get('CSM Name', 'N/A'), 
                "apps": formatted_apps,
                "bts": bts_date,
                "done": is_done
            })
        
        done_count = sum(1 for d in districts_data if d['done'])
        total = len(districts_data)
        pct = int((done_count/total)*100) if total > 0 else 0
        warn = "" if apps_ok or total == 0 else "<div class='app-warn'>⚠️ APP GATE CLOSED</div>"
        
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
                <td>
                    <div class="district-info">
                        <span class="d-name">{d['name']}</span>
                        <span class="d-id" onclick="navigator.clipboard.writeText('{d['id']}');alert('ID Copied!');">ID: {d['id']}</span>
                    </div>
                </td>
                <td>{d['segment']}</td>
                <td>{d['csm']}</td>
                <td class="app-cell">{d['apps']}</td>
                <td class="bts-cell">{d['bts']}</td>
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
                    <thead><tr><th>District (Click ID to Copy)</th><th>Segment</th><th>CSM</th><th>Apps</th><th>BTS Date</th><th>Status</th></tr></thead>
                    <tbody>{rows_html if rows_html else '<tr><td colspan="6">No data found in sheet.</td></tr>'}</tbody>
                </table>
            </div>
        </details>"""
    except Exception as e:
        print(f"Error on tab {cfg['tab']}: {e}")

live_prod_apps_count = sum(1 for app, states in global_apps_matrix.items() if any(states.values()))
app_progress_pct = int((live_prod_apps_count / total_targeted_apps) * 100) if total_targeted_apps > 0 else 0

# --- 3. HTML ASSEMBLY ---
apps_matrix_rows = []
# Ensure alphabetical sort layout order based on Application descriptive text labels
for app_id, name in sorted(app_name_map.items(), key=lambda x: x):
    clean_key = app_id.lower().strip()
    systems = global_apps_matrix.get(clean_key, {"google": False, "canvas": False, "schoology": False})
    
    display_label = f"{name} <br><small style='color:#9aa0a6; font-family:monospace;'>{app_id}</small>"
    
    gc_status = '<span class="ok">✅ Active</span>' if systems['google'] else '<span class="no" style="color:#9aa0a6;">⏳ Pending</span>'
    canvas_status = '<span class="ok">✅ Active</span>' if systems['canvas'] else '<span class="no" style="color:#9aa0a6;">⏳ Pending</span>'
    schoology_status = '<span class="ok">✅ Active</span>' if systems['schoology'] else '<span class="no" style="color:#9aa0a6;">⏳ Pending</span>'
    
    apps_matrix_rows.append(f"""
        <tr>
            <td style="text-align:left; padding:12px; border-bottom:1px solid #f1f3f4; font-weight:600;">{display_label}</td>
            <td style="text-align:center; padding:12px; border-bottom:1px solid #f1f3f4;">{gc_status}</td>
            <td style="text-align:center; padding:12px; border-bottom:1px solid #f1f3f4;">{canvas_status}</td>
            <td style="text-align:center; padding:12px; border-bottom:1px solid #f1f3f4;">{schoology_status}</td>
        </tr>
    """)

apps_dropdown_html = f"""
<details style="margin-bottom: 24px; background: white; border-radius: 8px; border: 1px solid #e0e0e0;" open>
    <summary style="padding: 15px 20px; cursor: pointer; font-weight: bold; display: flex; justify-content: space-between; align-items: center;">
        <span>📦 Partner Application-Side LMS Matrix (Real-Time Flags)</span>
        <span class="sum-count">{live_prod_apps_count} / {total_targeted_apps} Enabled</span>
    </summary>
    <div class="table-wrap" style="padding: 0 20px 20px; overflow-x: auto;">
        <table style="width:100%; border-collapse: collapse; font-size: 0.85em; text-align: left; min-width: 1000px;">
            <thead>
                <tr style="background:#f1f3f4; color: #5f6368;">
                    <th style="padding:12px; text-align:left;">Application Profile / ID</th>
                    <th style="padding:12px; text-align:center;">Google Classroom</th>
                    <th style="padding:12px; text-align:center;">Canvas</th>
                    <th style="padding:12px; text-align:center;">Schoology</th>
                </tr>
            </thead>
            <tbody>
                {"".join(apps_matrix_rows) if apps_matrix_rows else '<tr><td colspan="4" style="text-align:center; padding:20px;">No application feature flags detected.</td></tr>'}
            </tbody>
        </table>
    </div>
</details>
"""

apps_summary_block = f"""
<div style="background: white; padding: 24px; border-radius: 12px; max-width: 1200px; margin: 0 auto 32px auto; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #eef2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h2 style="margin: 0 0 4px 0; color: #1e293b; font-size: 1.25rem; font-weight: 600;">Partner Applications Migration Status</h2>
            <p style="margin: 0; color: #64748b; font-size: 0.875rem;">Tracks total active applications currently configured across platforms.</p>
        </div>
        <div style="display: flex; gap: 40px; align-items: center;">
            <div style="text-align: center;">
                <span style="display: block; font-size: 2rem; font-weight: 700; color: #10b981;">{live_prod_apps_count}</span>
                <span style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600;">Flags Active</span>
            </div>
            <div style="border-left: 1px solid #e2e8f0; height: 40px;"></div>
            <div style="text-align: center;">
                <span style="display: block; font-size: 2rem; font-weight: 700; color: #64748b;">{total_targeted_apps}</span>
                <span style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600;">Total Scope</span>
            </div>
            <div style="border-left: 1px solid #e2e8f0; height: 40px;"></div>
            <div style="background: #ecfdf5; color: #065f46; padding: 8px 16px; border-radius: 20px; font-weight: 700; font-size: 1.1rem;">
                {app_progress_pct}% Configured
            </div>
        </div>
    </div>
</div>
"""

ts = (datetime.datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%b %d, %Y at %I:%M %p')

final_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LMS Transition Tracker</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; background: #f4f7f9; padding: 40px; color: #202124; line-height: 1.5; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 40px; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); width: 260px; text-align: center; border: 1px solid #e0e0e0; }}
        .bar {{ background: #eee; height: 10px; border-radius: 5px; margin: 15px 0; overflow: hidden; }}
        .bar div {{ height: 100%; transition: width 1s; }}
        .stats {{ font-size: 2.5em; font-weight: bold; }}
        .app-warn {{ color:#d93025; font-size:11px; font-weight:bold; margin-top:5px; }}
        
        details {{ background: white; margin: 0 auto 12px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); max-width: 1300px; border: 1px solid #e0e0e0; }}
        summary {{ padding: 15px 20px; cursor: pointer; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }}
        .sum-count {{ background: #f1f3f4; padding: 2px 12px; border-radius: 12px; font-size: 0.85em; }}
        
        .table-wrap {{ padding: 0 20px 20px; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; text-align: left; min-width: 1000px; }}
        th, td {{ padding: 12px 10px; border-bottom: 1px solid #f1f3f4; vertical-align: top; }}
        th {{ color: #5f6368; text-transform: uppercase; font-size: 0.75em; letter-spacing: 0.5px; }}
        
        .district-info {{ display: flex; flex-direction: column; gap: 4px; }}
        .d-name {{ font-weight: 600; color: #202124; }}
        .d-id {{ font-family: monospace; font-size: 0.8em; color: #9aa0a6; cursor: pointer; display: inline-block; }}
        .d-id:hover {{ color: #1a73e8; text-decoration: underline; }}
        
        .app-cell {{ color: #5f6368; font-style: italic; max-width: 300px; word-wrap: break-word; }}
        .bts-cell {{ font-weight: 500; color: #1a73e8; }}
        .ok {{ color: #1e8e3e; font-weight: bold; }}
        .no {{ color: #d93025; font-weight: bold; }}
        .ts {{ text-align: center; color: #9aa0a6; font-size: 0.8em; margin-top: 50px; }}
    </style>
</head>
<body>
    <h1 style="text-align:center; font-weight:400; margin-bottom:40px;">LMS Connect Transition Hub</h1>
    {apps_summary_block}
    {apps_dropdown_html}
    <div class="container">{cards_html}</div>
    {dropdowns_html}
    <div class="ts">Last Sync: {ts} (PT)</div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(final_content)
