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
        "color": "#4285F4",
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
        with open(path, "r") as f:
            for line in f:
                val = line.strip().replace(" ", "")
                if val:
                    if not val.startswith(prefix): val = f"{prefix}{val}"
                    targets.append(val)
    return targets

# 1. Process Master App List
app_master_list = read_target_file(APP_TARGETS_FILE, "app:")

# 2. Process each LMS with "Double-Gating" Logic
lms_results = {}
for key, cfg in LMS_CONFIGS.items():
    districts_master = read_target_file(cfg['file'], "district:")
    ld_enabled = get_ld_enabled_ids(cfg['flag'])
    
    # Check Apps specifically for THIS LMS flag
    enabled_apps_for_lms = [a for a in app_master_list if a in ld_enabled]
    apps_ready = len(enabled_apps_for_lms) > 0
    
    # A District is ONLY "Complete" if IT is enabled AND at least one App is enabled
    completed_districts = []
    if apps_ready:
        completed_districts = [d for d in districts_master if d in ld_enabled]
    
    pending_districts = [d for d in districts_master if d not in completed_districts]
    
    lms_results[key] = {
        "comp": completed_districts,
        "pend": pending_districts,
        "total": len(districts_master),
        "enabled_apps": enabled_apps_for_lms,
        "apps_ready": apps_ready,
        "percent": int((len(completed_districts) / len(districts_master)) * 100) if len(districts_master) > 0 else 0
    }

# --- HTML GENERATION ---
cards_html = ""
for key, cfg in LMS_CONFIGS.items():
    res = lms_results[key]
    # Warning if no apps are enabled for this LMS
    app_warning = "" if res['apps_ready'] else "<div style='color:red; font-size:0.7em; font-weight:bold;'>⚠️ NO APPS ENABLED</div>"
    
    cards_html += f"""
    <div class="card">
        <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
        <div class="progress-container"><div class="progress-bar" style="background:{cfg['color']}; width:{res['percent']}%"></div></div>
        <div class="stats">{res['percent']}%</div>
        <p><b>{len(res['comp'])}</b> of {res['total']} Districts</p>
        {app_warning}
    </div>
    """

# --- TIMEZONE FIX ---
pdt_now = datetime.datetime.now(timezone.utc) - timedelta(hours=7)
display_time = pdt_now.strftime('%b %d, %Y at %I:%M %p')

final_html = f"""
<html>
<head>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f4f7f9; padding: 40px; text-align: center; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); width: 280px; }}
        .progress-container {{ background: #eee; border-radius: 10px; height: 12px; margin: 15px 0; overflow: hidden; }}
        .progress-bar {{ height: 100%; transition: width 1s; }}
        .stats {{ font-size: 2.2em; font-weight: bold; }}
        .timestamp {{ color: #888; font-size: 0.8em; margin-top: 40px; }}
    </style>
</head>
<body>
    <h1>LMS Connect Transition Hub</h1>
    <div class="container">{cards_html}</div>
    <p class="timestamp">Last Sync: {display_time} (PT)</p>
</body>
</html>
"""

with open(os.path.join(BASE_DIR, "index.html"), "w") as f:
    f.write(final_html)
