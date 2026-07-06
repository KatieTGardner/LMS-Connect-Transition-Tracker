import requests, datetime, sys, os, json, gspread, re, traceback
from google.oauth2.service_account import Credentials
from datetime import timezone, timedelta

LD_TOKEN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LD_TOKEN", "")
GOOG_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
SHEET_ID = "1EtXGPq3cb1vGzbdMs--gibZkRExKmyQab9Yc82uA9Fg"
PROJECT_KEY = "default"
ENV = "production"
DEBUG_LD = os.environ.get("DEBUG_LD", "false").lower() == "true"

GITHUB_WORKFLOW_URL = "https://github.com/katietgardner/LMS-Connect-Transition-Tracker/actions/workflows/main.yml"

LMS_CONFIGS = {
    "google": {"tab": "[Data] Google Classroom - Districts", "flag": "lms-connect-google-classroom-mvp", "color": "#34A853", "title": "Google Classroom"},
    "canvas": {"tab": "[Data] Canvas - Districts", "flag": "lms-connect-fully-owned-solution-canvas", "color": "#E13939", "title": "Canvas"},
    "schoology": {"tab": "[Data] Schoology - Districts", "flag": "lms-connect-fully-owned-solution-schoology", "color": "#00AEEF", "title": "Schoology"},
}

app_name_map = {
    "5d41ba752769fb0001ae10fa": "Khan Academy",
    "64cbff9e498f330001ce6412": "My Ada Math",
    "64cbf9e498f330001ce6412": "My Ada Math",
    "68a35343a1f1a21425233bcf": "Ellipsis Education",
    "5b2077fb03a826000165c4a1": "ClassHero",
    "607472b92b7bf90001040d41": "Smart Science Education",
    "66b1022e6c74dbaab2f81c82": "Blueprint (PlayVS, formerly Generation Esports)",
    "5501ca28059de501000000bb": "BrainPOP",
    "62b4a8cf26567400018ce321": "Progress Learning",
    "5b4640bc454d4a0001cd154c": "BrainPOP ELL",
    "5b46407f2b1e1d000194b2c1": "BrainPOP Jr.",
    "60076a4160534c000106935d": "BrainPOP Español",
    "60076a803269cb000103882b": "BrainPOP Français",
    "604fb030c8497b000106ef82": "BrainPOP Science (SSO Only)",
    "5b4640e82b1e1d000194b2c2": "BrainPOP Suite",
}

total_targeted_apps = 13


def clean_id_string(raw_str):
    val = str(raw_str or "").strip().lower()
    if val.startswith("app:"):
        val = val.replace("app:", "", 1)
    if val.startswith("district:"):
        val = val.replace("district:", "", 1)
    return val.strip()


def normalize_key_variants(raw_value, type_prefix=None):
    raw = str(raw_value or "").strip().lower()
    clean = clean_id_string(raw)
    variants = {raw, clean}
    if type_prefix and clean:
        variants.add(f"{type_prefix}:{clean}")
    return {v for v in variants if v}


def variation_value(flag_response, variation_index):
    try:
        idx = int(variation_index)
        variations = flag_response.get("variations", [])
        if 0 <= idx < len(variations):
            return variations[idx].get("value")
    except Exception:
        pass
    return None


def add_target_values_to_state(flag_response, state, values, variation_index):
    actual_value = variation_value(flag_response, variation_index)

    for val in values or []:
        raw_val = str(val or "").strip().lower()
        clean_val = clean_id_string(raw_val)
        variants = {raw_val, clean_val}

        if clean_val:
            variants.add(f"app:{clean_val}")
            variants.add(f"district:{clean_val}")

        if actual_value is True:
            state["explicit_true_keys"].update(variants)
        elif actual_value is False:
            state["explicit_false_keys"].update(variants)


def get_ld_environment_state(flag_key):
    url = f"https://app.launchdarkly.com/api/v2/flags/{PROJECT_KEY}/{flag_key}"
    headers = {"Authorization": LD_TOKEN, "Content-Type": "application/json"}

    state = {
        "default_is_on": False,
        "explicit_true_keys": set(),
        "explicit_false_keys": set(),
        "flag_on": False,
        "flag_key": flag_key,
    }

    try:
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code >= 400:
            print(f"LaunchDarkly API error for {flag_key}: {res.status_code} {res.text}")
            return state

        flag_response = res.json()
        env_data = flag_response.get("environments", {}).get(ENV, {})
        state["flag_on"] = bool(env_data.get("on", False))

        if state["flag_on"]:
            default_value = variation_value(flag_response, env_data.get("fallthrough", {}).get("variation"))
        else:
            default_value = variation_value(flag_response, env_data.get("offVariation"))

        state["default_is_on"] = default_value is True

        for target in env_data.get("targets", []) or []:
            add_target_values_to_state(flag_response, state, target.get("values", []), target.get("variation"))

        for target in env_data.get("contextTargets", []) or []:
            add_target_values_to_state(flag_response, state, target.get("values", []), target.get("variation"))

        for rule in env_data.get("rules", []) or []:
            rule_variation = rule.get("variation")

            for clause in rule.get("clauses", []) or []:
                add_target_values_to_state(flag_response, state, clause.get("values", []), rule_variation)

            rollout = rule.get("rollout")
            if rollout:
                variations = rollout.get("variations", []) or []

                true_rollout = any(
                    variation_value(flag_response, v.get("variation")) is True
                    and int(v.get("weight", 0)) >= 100000
                    for v in variations
                )

                false_rollout = any(
                    variation_value(flag_response, v.get("variation")) is False
                    and int(v.get("weight", 0)) >= 100000
                    for v in variations
                )

                for clause in rule.get("clauses", []) or []:
                    for val in clause.get("values", []):
                        if true_rollout:
                            state["explicit_true_keys"].update(normalize_key_variants(val))
                        elif false_rollout:
                            state["explicit_false_keys"].update(normalize_key_variants(val))

        if DEBUG_LD:
            print(f"\n===== PARSED LD STATE: {flag_key} =====")
            print({
                "flag_on": state["flag_on"],
                "default_is_on": state["default_is_on"],
                "explicit_true_count": len(state["explicit_true_keys"]),
                "explicit_false_count": len(state["explicit_false_keys"]),
                "sample_true_keys": sorted(list(state["explicit_true_keys"]))[:20],
            })

    except Exception as e:
        print(f"Error compiling LaunchDarkly state for {flag_key}: {e}")

    return state


def evaluate_key_status(clean_id, type_prefix, ld_state):
    raw_key = clean_id_string(clean_id)
    variants = normalize_key_variants(raw_key, type_prefix)

    if any(v in ld_state["explicit_true_keys"] for v in variants):
        return True
    if any(v in ld_state["explicit_false_keys"] for v in variants):
        return False
    return ld_state["default_is_on"]


def should_skip_district_row(row):
    rid = clean_id_string(row.get("District Id", ""))
    district_name = str(row.get("District Name", "")).strip().lower()

    if not rid or len(rid) < 10:
        return True

    bad_row_markers = [
        "has not used",
        "haven't synced",
        "have never",
        "confirmed by",
        "can be moved",
        "low usage",
        "not used lms connect",
    ]

    return any(marker in district_name for marker in bad_row_markers)


try:
    if not LD_TOKEN:
        raise ValueError("Missing LaunchDarkly token. Pass it as argv[1] or set LD_TOKEN.")
    if not GOOG_JSON:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT environment variable.")

    creds_dict = json.loads(GOOG_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"],
    )
    doc = gspread.authorize(creds).open_by_key(SHEET_ID)

except Exception as e:
    print(f"CRITICAL AUTH ERROR: {e}")
    sys.exit(1)


cards_html, dropdowns_html = "", ""
global_apps_matrix = {}
total_done_districts = 0
total_scope_districts = 0

ld_flags_cache = {key: get_ld_environment_state(cfg["flag"]) for key, cfg in LMS_CONFIGS.items()}

for key, cfg in LMS_CONFIGS.items():
    ld_state = ld_flags_cache[key]

    for app_id in app_name_map.keys():
        clean_app_id = clean_id_string(app_id)

        if evaluate_key_status(clean_app_id, "app", ld_state):
            global_apps_matrix.setdefault(clean_app_id, {"google": False, "canvas": False, "schoology": False})
            global_apps_matrix[clean_app_id][key] = True


for key, cfg in LMS_CONFIGS.items():
    try:
        rows = doc.worksheet(cfg["tab"]).get_all_records()
        ld_state = ld_flags_cache[key]

        districts_data = []
        seen_district_ids = set()

        for r in rows:
            if should_skip_district_row(r):
                continue

            rid = clean_id_string(r.get("District Id", ""))

            if rid in seen_district_ids:
                continue

            seen_district_ids.add(rid)

            raw_apps = str(r.get("Connected Apps", "")).strip()
            app_list = [a.strip() for a in re.split(r",|;|\|", raw_apps) if a.strip()]
            formatted_apps = ", ".join(app_list) if app_list else "None"

            bts_date = str(r.get("BTS Dates", "TBD")).strip() or "TBD"
            is_done = evaluate_key_status(rid, "district", ld_state)

            districts_data.append({
                "id": rid,
                "name": r.get("District Name", r.get("District Id", rid)),
                "segment": r.get("Segment", "N/A"),
                "csm": r.get("CSM Name", "N/A"),
                "apps": formatted_apps,
                "bts": bts_date,
                "done": is_done,
            })

        done_count = sum(1 for d in districts_data if d["done"])
        total = len(districts_data)
        pct = int((done_count / total) * 100) if total > 0 else 0

        total_done_districts += done_count
        total_scope_districts += total

        cards_html += f"""
        <div class="card">
            <h2 style="color:{cfg['color']}">{cfg['title']}</h2>
            <div class="bar"><div style="width:{pct}%;background:{cfg['color']}"></div></div>
            <div class="stats">{pct}%</div>
            <p><b>{done_count}</b> / {total} Districts</p>
        </div>"""

        rows_html = "".join([
            f"""
            <tr>
                <td>
                    <div class="district-info">
                        <span class="d-name">{d['name']}</span>
                        <span class="d-id" onclick="navigator.clipboard.writeText('{d['id']}');alert('ID Copied!');">>ID: {d['id']}</span>
                    </div>
                </td>
                <td>{d['segment']}</td>
                <td>{d['csm']}</td>
                <td class="app-cell">{d['apps']}</td>
                <td class="bts-cell">{d['bts']}</td>
                <td class="{'ok' if d['done'] else 'no'}">{'✅ Done' if d['done'] else '⏳ Pending'}</td>
            </tr>"""
            for d in sorted(districts_data, key=lambda x: str(x["name"]))
        ])

        dropdowns_html += f"""
        <details>
            <summary style="border-left: 5px solid {cfg['color']};">
                <span>{cfg['title']} Detailed Roster</span>
                <span class="sum-count">{done_count} / {total}</span>
            </summary>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>District (Click ID to Copy)</th>
                            <th>Segment</th>
                            <th>CSM</th>
                            <th>Apps</th>
                            <th>BTS Date</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html if rows_html else '<tr><td colspan="6">No data found in sheet.</td></tr>'}</tbody>
                </table>
            </div>
        </details>"""

    except Exception as e:
        print(f"Error generating UI for tab {cfg['tab']}: {e}")
        traceback.print_exc()  # <-- added here


deduped_live_apps = set()

for app_id, states in global_apps_matrix.items():
    if all(states.values()):
        name_match = app_name_map.get(app_id)
        if name_match:
            deduped_live_apps.add(name_match)

live_prod_apps_count = len(deduped_live_apps)
total_targeted_apps = len(set(app_name_map.values()))
app_progress_pct = int((live_prod_apps_count / total_targeted_apps) * 100) if total_targeted_apps > 0 else 0

overall_done = live_prod_apps_count + total_done_districts
overall_total = total_targeted_apps + total_scope_districts
overall_pct = int((overall_done / overall_total) * 100) if overall_total > 0 else 0


overall_progress_block = f"""
<div class="overall-progress-block">
    <div class="overall-label">Overall Project Progress</div>
    <div class="overall-percent">{overall_pct}%</div>
    <div class="overall-bar">
        <div style="width:{overall_pct}%;"></div>
    </div>
    <div class="overall-subtext">
        {overall_done} of {overall_total} total app + district transitions complete
    </div>
</div>
"""


apps_matrix_rows = []
seen_app_names = set()

for app_id, name in sorted(app_name_map.items(), key=lambda x: x):
    if name in seen_app_names:
        continue

    clean_key = clean_id_string(app_id)
    systems = global_apps_matrix.get(clean_key, {"google": False, "canvas": False, "schoology": False})

    if name == "My Ada Math":
        typo_sys = global_apps_matrix.get("64cbf9e498f330001ce6412", {"google": False, "canvas": False, "schoology": False})
        valid_sys = global_apps_matrix.get("64cbff9e498f330001ce6412", {"google": False, "canvas": False, "schoology": False})
        systems = {k: typo_sys[k] or valid_sys[k] for k in systems}

    display_id = "64cbff9e498f330001ce6412" if name == "My Ada Math" else app_id

    display_label = f"""
        {name}
        <br>
        <small style='color:#9aa0a6; font-family:monospace;'>{display_id}</small>
    """

    gc_status = '<span class="ok">✅ Active</span>' if systems["google"] else '<span class="no muted">⏳ Pending</span>'
    canvas_status = '<span class="ok">✅ Active</span>' if systems["canvas"] else '<span class="no muted">⏳ Pending</span>'
    schoology_status = '<span class="ok">✅ Active</span>' if systems["schoology"] else '<span class="no muted">⏳ Pending</span>'

    apps_matrix_rows.append(f"""
        <tr>
            <td class="app-profile">{display_label}</td>
            <td class="center">{gc_status}</td>
            <td class="center">{canvas_status}</td>
            <td class="center">{schoology_status}</td>
        </tr>
    """)

    seen_app_names.add(name)


apps_dropdown_html = f"""
<details class="app-matrix" open>
    <summary>
        <span>📦 App Feature Flags Details</span>
        <span class="sum-count">{live_prod_apps_count} / {total_targeted_apps} Enabled</span>
    </summary>
    <div class="table-wrap app-table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Application Profile / ID</th>
                    <th class="center">Google Classroom</th>
                    <th class="center">Canvas</th>
                    <th class="center">Schoology</th>
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
<div class="summary-block">
    <div class="summary-flex">
        <div>
            <h2>App Migration Status</h2>
            <p>Tracks apps fully migrated across all three LMS platforms (Google Classroom, Canvas, Schoology).</p>
        </div>
        <div class="summary-metrics">
            <div class="metric">
                <span class="metric-value green">{live_prod_apps_count}</span>
                <span class="metric-label">Fully Migrated</span>
            </div>
            <div class="divider"></div>
            <div class="metric">
                <span class="metric-value gray">{total_targeted_apps}</span>
                <span class="metric-label">Total Apps</span>
            </div>
            <div class="divider"></div>
            <div class="pill">{app_progress_pct}% Migrated</div>
        </div>
    </div>
</div>
"""


ts = (datetime.datetime.now(timezone.utc) - timedelta(hours=7)).strftime("%b %d, %Y at %I:%M %p")


final_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LMS Transition Tracker</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f4f7f9;
            padding: 40px;
            color: #202124;
            line-height: 1.5;
        }}

        h1 {{
            text-align: center;
            font-weight: 400;
            margin-bottom: 20px;
        }}

        .dashboard-actions {{
            display: flex;
            justify-content: center;
            gap: 12px;
            margin: 0 0 32px 0;
            flex-wrap: wrap;
        }}

        .action-btn {{
            border: 1px solid #d0d7de;
            background: white;
            color: #24292f;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            font-size: 0.95rem;
            text-decoration: none;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            font-family: inherit;
        }}

        .action-btn:hover {{
            background: #f6f8fa;
            border-color: #afb8c1;
        }}

        .sync-note {{
            text-align: center;
            color: #64748b;
            font-size: 0.8rem;
            margin-top: -20px;
            margin-bottom: 28px;
        }}

        .overall-progress-block {{
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e2e8f0;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
            border-radius: 20px;
            max-width: 1200px;
            margin: 0 auto 32px auto;
            padding: 36px 32px;
            text-align: center;
        }}

        .overall-label {{
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.85rem;
            font-weight: 800;
            margin-bottom: 8px;
        }}

        .overall-percent {{
            color: #0f172a;
            font-size: 5rem;
            line-height: 1;
            font-weight: 900;
            margin-bottom: 20px;
        }}

        .overall-bar {{
            background: #e5e7eb;
            height: 16px;
            border-radius: 999px;
            overflow: hidden;
            max-width: 760px;
            margin: 0 auto 16px auto;
        }}

        .overall-bar div {{
            height: 100%;
            background: #10b981;
            border-radius: 999px;
            transition: width 1s ease;
        }}

        .overall-subtext {{
            color: #475569;
            font-size: 1rem;
            font-weight: 600;
        }}

        .container {{
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
            margin-bottom: 40px;
        }}

        .card {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            width: 260px;
            text-align: center;
            border: 1px solid #e0e0e0;
        }}

        .bar {{
            background: #eee;
            height: 10px;
            border-radius: 5px;
            margin: 15px 0;
            overflow: hidden;
        }}

        .bar div {{
            height: 100%;
            transition: width 1s;
        }}

        .stats {{
            font-size: 2.5em;
            font-weight: bold;
        }}

        details {{
            background: white;
            margin: 0 auto 12px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            max-width: 1300px;
            border: 1px solid #e0e0e0;
        }}

        summary {{
            padding: 15px 20px;
            cursor: pointer;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .sum-count {{
            background: #f1f3f4;
            padding: 2px 12px;
            border-radius: 12px;
            font-size: 0.85em;
        }}

        .table-wrap {{
            padding: 0 20px 20px;
            max-height: 600px;
            overflow-y: auto;
            position: relative;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85em;
            text-align: left;
            min-width: 1000px;
        }}

        thead {{
            position: sticky;
            top: 0;
            background: #f1f3f4;
            z-index: 10;
            box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1);
        }}

        th, td {{
            padding: 12px 10px;
            border-bottom: 1px solid #f1f3f4;
            vertical-align: top;
        }}

        th {{
            color: #5f6368;
            text-transform: uppercase;
            font-size: 0.75em;
            letter-spacing: 0.5px;
        }}

        .center {{ text-align: center; }}

        .district-info {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .d-name {{
            font-weight: 600;
            color: #202124;
        }}

        .d-id {{
            font-family: monospace;
            font-size: 0.8em;
            color: #9aa0a6;
            cursor: pointer;
            display: inline-block;
        }}

        .d-id:hover {{
            color: #1a73e8;
            text-decoration: underline;
        }}

        .app-cell {{
            color: #5f6368;
            font-style: italic;
            max-width: 300px;
            word-wrap: break-word;
        }}

        .bts-cell {{
            font-weight: 500;
            color: #1a73e8;
        }}

        .ok {{
            color: #1e8e3e;
            font-weight: bold;
        }}

        .no {{
            color: #d93025;
            font-weight: bold;
        }}

        .muted {{
            color: #9aa0a6 !important;
        }}

        .ts {{
            text-align: center;
            color: #9aa0a6;
            font-size: 0.8em;
            margin-top: 50px;
        }}

        .summary-block {{
            background: white;
            padding: 24px;
            border-radius: 12px;
            max-width: 1200px;
            margin: 0 auto 32px auto;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border: 1px solid #eef2f5;
        }}

        .summary-flex {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 24px;
            flex-wrap: wrap;
        }}

        .summary-block h2 {{
            margin: 0 0 4px 0;
            color: #1e293b;
            font-size: 1.25rem;
            font-weight: 600;
        }}

        .summary-block p {{
            margin: 0;
            color: #64748b;
            font-size: 0.875rem;
        }}

        .summary-metrics {{
            display: flex;
            gap: 40px;
            align-items: center;
            flex-wrap: wrap;
        }}

        .metric {{ text-align: center; }}

        .metric-value {{
            display: block;
            font-size: 2rem;
            font-weight: 700;
        }}

        .green {{ color: #10b981; }}
        .gray {{ color: #64748b; }}

        .metric-label {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #64748b;
            font-weight: 600;
        }}

        .divider {{
            border-left: 1px solid #e2e8f0;
            height: 40px;
        }}

        .pill {{
            background: #ecfdf5;
            color: #065f46;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 1.1rem;
        }}

        .app-matrix {{ margin-bottom: 24px; }}

        .app-table-wrap {{
            max-height: 500px;
            overflow-y: auto;
            padding: 0 20px 20px;
        }}

        .app-profile {{
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #f1f3f4;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <h1>LMS Connect Transition Hub</h1>

    <div class="dashboard-actions">
        <button onclick="window.location.reload();" class="action-btn">🔄 Refresh Dashboard</button>
        <a href="{GITHUB_WORKFLOW_URL}" target="_blank" class="action-btn">⚡ Run Sync</a>
    </div>

    <div class="sync-note">
        Run Sync opens GitHub Actions. After the workflow completes, come back here and click Refresh Dashboard.
    </div>

    {overall_progress_block}
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

print(f"Dashboard generated successfully. Overall progress: {overall_pct}%. Apps active: {live_prod_apps_count}/{total_targeted_apps}")
