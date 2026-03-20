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

# Configuration for 3 LMS types, each with two source files
LMS_CONFIGS = {
    "google": {
        "districts_file": "gc_targets.txt",
        "apps_file": "gc_apps.txt",
        "flag": "lms-connect-fully-owned-setup",
        "color": "#4285F4",
        "title": "Google Classroom"
    },
    "canvas": {
        "districts_file": "canvas_targets.txt",
        "apps_file": "canvas_apps.txt",
        "flag": "lms-connect-canvas-migration", 
        "color": "#E13939",
        "title": "Canvas"
    },
    "schoology": {
        "districts_file": "schoology_targets.txt",
        "apps_file": "schoology_apps.txt",
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

def process_file(filename, prefix, enabled_ids):
    path = os.path.join(BASE_DIR, filename)
    master = []
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                val = line.strip().replace(" ", "")
                if val:
                    if not val.startswith(prefix): val = f"{prefix}{val}"
                    master.append(val)
    
    comp = [i for i in master if i in enabled_ids]
    pend = [i for i in master if i not in enabled_ids]
    return {"all": master, "comp": comp, "pend": pend}

# Process all data
results = {}
for key, cfg in LMS_CONFIGS.items():
    enabled = get_ld_enabled_ids(cfg['flag'])
    
    districts = process_file(cfg['districts_file'], "district:", enabled)
    apps = process_file(cfg['apps_file'], "app:", enabled)
    
    total_targets = len(districts['all']) + len(apps['all'])
    total_comp = len(districts['comp']) + len(apps['comp'])
    
    results[key] = {
        "districts": districts,
        "apps": apps,
        "percent": int((total_comp / total_targets) * 100) if total_targets > 0 else 0,
        "total": total_targets,
        "count": total_comp
    }

# --- HTML GENERATION ---
cards_html = ""
details_html = ""

for key, cfg in LMS_CONFIGS.items():
    res = results[key]
    cards_html += f"""
    <div class="card">
        <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
        <div class="progress-container"><div class="progress-bar" style="background:{cfg['color']}; width:{res['percent']}%"></div></div>
        <div class="stats">{res['percent']}%</div>
        <div style="font-size: 0.9em; margin-top: 10px;">
            <div>🏢 Districts: <b>{len(res['districts']['comp'])}/{len(res['districts']['all'])}</b></div>
            <div>📱 Apps: <b>{len(res['apps']['comp'])}/{len(res['apps']['all'])}</b></div>
        </div>
    </div>
    """
    
    if res['total'] > 0:
        def format_list(items): return "".join([f"<li>{i.split(':')[-1]}</li>" for i in sorted(items)])
        
        details_html += f"""
        <div class="column">
            <h3 style="border-bottom: 3px solid {cfg['color']}">{cfg['title']}</h3>
            <p><b>Districts Pending:</b></p><ul>{format_list(res['districts']['pend'])}</ul>
            <p><b>Apps Pending:</b></p><ul>{format_list(res['apps']['pend'])}</ul>
        </div>
        """

pdt_now = datetime.datetime.now(timezone.utc) - timedelta(hours=7)
display_time = pdt_now.strftime('%b %d, %Y at %I:%M %p')

final_html = f"""
<html>
<head>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f4f7f9; padding: 40px; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; }}
        .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); width: 280px; text-align: center; }}
        .progress-container {{ background: #eee; border-radius: 10px; height: 12px; margin: 15px 0; overflow: hidden; }}
        .progress-bar {{ height: 100%; transition: width 1s; }}
        .stats {{ font-size: 2em; font-weight: bold; }}
        #details {{ display: none; background: white; padding: 30px; border-radius: 12px; margin-top: 30px; }}
        .columns {{ display: flex; gap: 20px; }}
        .column {{ flex: 1; }}
        ul {{ background: #f9f9f9; border: 1px solid #eee; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 0.8em; max-height: 200px; overflow-y: auto; list-style: none; }}
        button {{ display: block; margin: 30px auto; padding: 12px 24px; background: #4285F4; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; }}
    </style>
</head>
<body>
    <h1 style="text-align:center">LMS Connect Migration Hub</h1>
    <div class="container">{cards_html}</div>
    <button onclick="document.getElementById('details').style.display='flex'">View Detailed Breakdown</button>
    <div id="details" class="columns">{details_html}</div>
    <p style="text-align:center; color: #888; font-size: 0.8em; margin-top: 40px;">Last Sync: {display_time} (PT)</p>
</body>
</html>
"""

with open(os.path.join(BASE_DIR, "index.html"), "w") as f:
    f.write(final_html)
