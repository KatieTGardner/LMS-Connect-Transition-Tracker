import requests
import datetime
import sys
import os

# --- CONFIGURATION ---
# Step 1: Secure API Key from Argument
if len(sys.argv) > 1:
    API_TOKEN = sys.argv[1]
else:
    print("❌ Error: No API Token provided.")
    sys.exit(1)

# Step 2: Portable Paths (Works on Mac and GitHub)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TARGETS_FILE = os.path.join(BASE_DIR, "targets.txt")
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

PROJECT_KEY = "default"
FLAG_KEY = "lms-connect-fully-owned-setup"
ENV_KEY = "production" 

# 1. Fetch Data from LaunchDarkly
url = f"https://app.launchdarkly.com/api/v2/flags/{PROJECT_KEY}/{FLAG_KEY}"
headers = {"Authorization": API_TOKEN, "LD-API-Version": "beta"}
data = requests.get(url, headers=headers).json()

# 2. Extract Enabled IDs from LD
env_data = data.get('environments', {}).get(ENV_KEY, {})
enabled_ids = []
for t in env_data.get('targets', []):
    if t.get('variation') == 0:
        enabled_ids.extend(t.get('values', []))
for rule in env_data.get('rules', []):
    if rule.get('variation') == 0:
        for clause in rule.get('clauses', []):
            enabled_ids.extend(clause.get('values', []))
enabled_ids = list(set([str(i).strip() for i in enabled_ids if i]))

# 3. Read Master List & Auto-Prefix
MASTER_LIST = []
with open(TARGETS_FILE, "r") as f:
    for line in f:
        clean_id = line.strip().replace(" ", "")
        if clean_id:
            # AUTO-PREFIX: If the ID doesn't start with 'district:', add it
            if not clean_id.startswith("district:"):
                clean_id = f"district:{clean_id}"
            MASTER_LIST.append(clean_id)

completed = [d for d in MASTER_LIST if d in enabled_ids]
pending = [d for d in MASTER_LIST if d not in enabled_ids]

count, total = len(completed), len(MASTER_LIST)
percent = int((count / total) * 100) if total > 0 else 0

# 4. Prepare Lists for HTML (stripping "district:" for a cleaner display)
completed_list_items = "".join([f"<li>{d.replace('district:', '')}</li>" for d in completed])
pending_list_items = "".join([f"<li>{d.replace('district:', '')}</li>" for d in pending])

# 5. Generate Dashboard (Restored 3-Column Layout)
html_content = f"""
<html>
<head>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f0f2f5; margin: 0; padding: 50px; color: #1d1c1d; }}
        .header {{ text-align: center; margin-bottom: 50px; }}
        .container {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 40px; }}
        .card {{ background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); text-align: center; width: 320px; }}
        .card.disabled {{ opacity: 0.6; filter: grayscale(1); }}
        
        .progress-container {{ background: #eee; border-radius: 10px; height: 15px; width: 100%; margin: 20px 0; overflow: hidden; }}
        .progress-bar {{ background: #4285F4; height: 100%; width: {percent}%; transition: width 1s; }}
        
        .google {{ color: #4285F4; }}
        .canvas {{ color: #E13939; }}
        .schoology {{ color: #00AEEF; }}
        
        .btn-details {{ background: #4285F4; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; margin-top: 15px; }}
        
        #details-section {{ display: none; background: white; padding: 40px; border-radius: 15px; max-width: 900px; margin: 0 auto; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
        .columns {{ display: flex; gap: 40px; text-align: left; }}
        .column {{ flex: 1; }}
        h3 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 0; }}
        ul {{ list-style: none; padding: 0; font-family: monospace; font-size: 0.85em; max-height: 400px; overflow-y: auto; background: #fafafa; border-radius: 8px; padding: 10px; }}
        li {{ padding: 6px; border-bottom: 1px solid #eee; }}
        .done {{ color: #1e8e3e; }}
        .todo {{ color: #d93025; }}

        .timestamp {{ font-size: 0.75em; color: #999; margin-top: 40px; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>LMS Connect Migration Dashboard</h1>
    </div>

    <div class="container">
        <div class="card">
            <h2 class="google">Google Classroom</h2>
            <div class="progress-container"><div class="progress-bar"></div></div>
            <div class="stats" style="font-size:1.8em; font-weight:bold;">{percent}%</div>
            <p><b>{count}</b> of {total} Districts Enabled</p>
            <button class="btn-details" onclick="toggleDetails()">View District Lists</button>
        </div>

        <div class="card disabled">
            <h2 class="canvas">Canvas</h2>
            <div class="progress-container"><div class="progress-bar" style="width:0%;"></div></div>
            <div class="stats">0%</div>
            <p>Coming Soon</p>
        </div>

        <div class="card disabled">
            <h2 class="schoology">Schoology</h2>
            <div class="progress-container"><div class="progress-bar" style="width:0%;"></div></div>
            <div class="stats">0%</div>
            <p>Coming Soon</p>
        </div>
    </div>

    <div id="details-section">
        <div class="columns">
            <div class="column">
                <h3 class="done">✅ Transitioned ({count})</h3>
                <ul>{completed_list_items}</ul>
            </div>
            <div class="column">
                <h3 class="todo">⏳ Pending ({len(pending)})</h3>
                <ul>{pending_list_items}</ul>
            </div>
        </div>
        <center><button class="btn-details" style="background:#666; margin-top:20px;" onclick="toggleDetails()">Close Details</button></center>
    </div>

    <div class="timestamp">Last Auto-Update: {datetime.datetime.now().strftime('%I:%M %p')}</div>

    <script>
        function toggleDetails() {{
            var el = document.getElementById("details-section");
            el.style.display = (el.style.display === "none" || el.style.display === "") ? "block" : "none";
            if(el.style.display === "block") el.scrollIntoView({{ behavior: 'smooth' }});
        }}
    </script>
</body>
</html>
"""

with open(OUTPUT_HTML, "w") as f:
    f.write(html_content)

print(f"✅ Success! Dashboard updated at {OUTPUT_HTML}")
