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
        return [str(i).strip().lower() for i in vals] # Force lowercase matching tokens
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

# Load the custom application tracker index list cleanly from the local repo file
app_name_map = {}
if os.path.exists("apps_list.txt"):
    with open("apps_list.txt", "r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                parts = line.split(":", 1)
                app_name_map[parts.strip().lower()] = parts.strip()

cards_html, dropdowns_html = "", ""
global_apps_matrix = {}
total_targeted_apps = len(app_name_map) if len(app_name_map) > 0 else 34

# Loop over the structural configurations to pull LaunchDarkly values
for key, cfg in LMS_CONFIGS.items():
    ld_ids = get_ld(cfg['flag'])
    
    # Process the active partner app matrix matches directly against the text file keys
    for app_id in app_name_map.keys():
        # Check if the raw ID string or the modified "app:ID" sequence exists in LaunchDarkly targets
        if app_id in ld_ids or f"app:{app_id}" in ld_ids or any(app_id in str(x) for x in ld_ids):
            if app_id not in global_apps_matrix:
                global_apps_matrix[app_id] = {"google": False, "canvas": False, "schoology": False}
            global_apps_matrix[app_id][key] = True

# Loop over the district tabs to generate high-level metric cards and dropdown rosters
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
for app_id, name in app_name_map.items():
    systems = global_apps_matrix.get(app_id, {"google": False, "canvas": False, "schoology": False})
    
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
