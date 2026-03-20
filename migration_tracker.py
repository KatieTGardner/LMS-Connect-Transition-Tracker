import requests
import datetime
import sys
import os
from datetime import timezone, timedelta

# --- CONFIGURATION ---
if len(sys.argv) > 1:
    API_TOKEN = sys.argv
else:
    print("❌ Error: No API Token provided.")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_KEY = "default"
ENV_KEY = "production"

# Source Files
APP_TARGETS_FILE = "app_targets.txt"
LMS_CONFIGS = {
    "google": {
        "file": "gc_targets.txt",
        "flag": "lms-connect-google-classroom-mvp",
        "color": "#34A853", # Updated to Google Green
        "title": "Google Classroom"
    },
    "canvas": {
        "file": "canvas_targets.txt",
        "flag": "lms-connect-canvas-migration", 
        "color": "#E13939",
        "title": "Canvas"
    },
    "schoology": {
        "file": "schoology_targets.txt",
        "flag": "lms-connect-schoology-migration",
        "color": "#00AEEF",
        "title": "Schoology"
    }
}

def get_ld_enabled_ids(flag_key):
    url = f"https://app.launchdarkly.com/api/v2/flags/{PROJECT_KEY}/{flag_key}"
    headers = {"Authorization": API_TOKEN, "LD-API-Version": "beta"}
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

def read_target_file(filename, prefix):
    path = os.path.join(BASE_DIR, filename)
    targets = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                val = line.strip().replace(" ", "")
                if val:
                    if not val.startswith(prefix): val = f"{prefix}{val}"
                    targets.append(val)
    return targets

# 1. Process Master App List
app_master_list = read_target_file(APP_TARGETS_FILE, "app:")

# 2. Process each LMS
lms_results = {}
for key, cfg in LMS_CONFIGS.items():
    districts_master = read_target_file(cfg['file'], "district:")
    ld_enabled = get_ld_enabled_ids(cfg['flag'])
    
    # Check Apps specifically for this flag
    enabled_apps = [a for a in app_master_list if a in ld_enabled]
    pending_apps = [a for a in app_master_list if a not in ld_enabled]
    apps_ready = len(enabled_apps) > 0
    
    # Logic: Districts only "Done" if App gate is open
    completed_districts = []
    if apps_ready:
        completed_districts = [d for d in districts_master if d in ld_enabled]
    
    pending_districts = [d for d in districts_master if d not in completed_districts]
    
    lms_results[key] = {
        "comp_d": completed_districts,
        "pend_d": pending_districts,
        "comp_a": enabled_apps,
        "pend_a": pending_apps,
        "total_d": len(districts_master),
        "total_a": len(app_master_list),
        "apps_ready": apps_ready,
        "percent": int((len(completed_districts) / len(districts_master)) * 100) if len(districts_master) > 0 else 0
    }

# --- HTML GENERATION ---
cards_html = ""
details_html = ""

for key, cfg in LMS_CONFIGS.items():
    res = lms_results[key]
    warning = "" if res['apps_ready'] else "<div style='color:#d93025; font-size:0.75em; margin-top:5px; font-weight:bold;'>⚠️ APP GATE CLOSED</div>"
    
    # Card UI
    cards_html += f"""
    <div class="card">
        <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
        <div class="progress-container"><div class="progress-bar" style="background:{cfg['color']}; width:{res['percent']}%"></div></div>
        <div class="stats">{res['percent']}%</div>
        <div style="font-size:0.85em; color:#555;">
            🏢 Districts: <b>{len(res['comp_d'])}/{res['total_d']}</b><br>
            📱 Apps: <b>{len(res['comp_a'])}/{res['total_a']}</b>
        </div>
        {warning}
    </div>
    """
    
    # Details UI (Fixed and populated)
    if res['total_d'] > 0 or res['total_a'] > 0:
        def li(items): return "".join([f"<li>{i.split(':')[-1]}</li>" for i in sorted(items)]) if items else "<li>None</li>"
        
        details_html += f"""
        <div class="column">
            <h3 style="border-bottom: 3px solid {cfg['color']}; padding-bottom:5px;">{cfg['title']} Breakdown</h3>
            <p class="section-title">✅ Districts Done ({len(res['comp_d'])})</p><ul>{li(res['comp_d'])}</ul>
            <p class="section-title todo">⏳ Districts Pending ({len(res['pend_d'])})</p><ul>{li(res['pend_d'])}</ul>
            <p class="section-title">✅ Apps Ready ({len(res['comp_a'])})</p><ul>{li(res['comp_a'])}</ul>
            <p class="section-title todo">⚠️ Apps Missing ({len(res['pend_a'])})</p><ul>{li(res['pend_a'])}</ul>
        </div>
        """

pdt_now = datetime.datetime.now(timezone.utc) - timedelta(hours=7)
display_time = pdt_now.strftime('%b %d, %Y at %I:%M %p')

final_html = f"""
<html>
<head>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f8f9fa; padding: 40px; color: #202124; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); width: 260px; text-align: center; }}
        .progress-container {{ background: #e8eaed; border-radius: 10px; height: 10px; margin: 15px 0; overflow: hidden; }}
        .progress-bar {{ height: 100%; transition: width 1s; }}
        .stats {{ font-size: 2.2em; font-weight: bold; margin-bottom: 5px; }}
        #details-section {{ display: none; background: white; padding: 30px; border-radius: 12px; margin: 30px auto; max-width: 1100px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
        .columns {{ display: flex; gap: 25px; flex-wrap: wrap; }}
        .column {{ flex: 1; min-width: 250px; }}
        .section-title {{ font-weight: bold; font-size: 0.85em; margin: 15px 0 5px 0; color: #1e8e3e; }}
        .section-title.todo {{ color: #d93025; }}
        ul {{ background: #f1f3f4; border-radius: 6px; padding: 10px; list-style: none; font-family: monospace; font-size: 0.8em; max-height: 150px; overflow-y: auto; margin: 0; }}
        li {{ padding: 3px 0; border-bottom: 1px solid #e8eaed; }}
        button {{ display: block; margin: 30px auto; padding: 12px 24px; background: #1a73e8; color: white; border: none; border-radius: 24px; font-weight: 500; cursor: pointer; }}
        button:hover {{ background: #1765cc; }}
    </style>
</head>
<body>
    <h1 style="text-align:center; font-weight:400; margin-bottom:40px;">LMS Connect Transition Hub</h1>
    <div class="container">{cards_html}</div>
    <button onclick="document.getElementById('details-section').style.display='block'">View Detailed Breakdown</button>
    <div id="details-section"><div class="columns">{details_html}</div></div>
    <p style="text-align:center; color: #70757a; font-size: 0.8em; margin-top: 40px;">Last Sync: {display_time} (PT)</p>
</body>
</html>
"""

with open(os.path.join(BASE_DIR, "index.html"), "w") as f:
    f.write(final_html)
