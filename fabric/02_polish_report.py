# Fabric notebook: 02_polish_report
# Report formatting as code. Reads the "Agency Performance" report definition (PBIR) through the
# Fabric REST API, applies layout, titles, column names and red/amber/green rules, saves a backup
# copy of the untouched report, then writes the new definition back with updateDefinition.
# Run the cells in order in a Fabric notebook in the same workspace (semantic-link is preinstalled).
# Theme: microsoft/powerbi/agency_copilot_theme.json (imported in the report: Design > Import theme).

# %% 1 · Read the report definition (PBIR parts)
import sempy.fabric as fabric, base64, json, time
c = fabric.FabricRestClient()
ws = fabric.get_workspace_id()
def lro(r):
    if r.status_code == 200:
        return r.json()
    op = r.headers["Location"]
    while True:
        time.sleep(2)
        s = c.get(op).json()
        if s.get("status") in ("Succeeded", "Failed"):
            break
    if s["status"] == "Failed":
        raise Exception(s)
    return c.get(op + "/result").json()
reps = c.get(f"/v1/workspaces/{ws}/reports").json()["value"]
print([r["displayName"] for r in reps])
rep = [r for r in reps if r["displayName"] == "Agency Performance"][0]
d = lro(c.post(f"/v1/workspaces/{ws}/reports/{rep['id']}/getDefinition"))
parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in d["definition"]["parts"]}
print("FORMAT", d["definition"].get("format"))
for k, v in parts.items():
    print("PART", k, len(v))
globals()["PARTS"] = parts
globals()["REP"] = rep
for k, v in parts.items():
    if k.endswith("report.json") or k.endswith("pages.json") or k.endswith("page.json") or k.endswith(".pbir"):
        print("=====", k); print(v[:1500])
seen = set()
for k, v in parts.items():
    if k.endswith("visual.json"):
        j = json.loads(v); t = j.get("visual", {}).get("visualType")
        if t not in seen:
            seen.add(t); print("=====", k, t); print(json.dumps(j)[:1800])

# %% 2 · Inspect: one line per visual
import json
P = PARTS
print(sorted(P))
rj = json.loads(P["definition/report.json"])
print("THEME", json.dumps(rj.get("themeCollection")), "RES", json.dumps(rj.get("resourcePackages")))
print("KEYS", list(rj))
for k in sorted(P):
    if k.endswith("page.json"):
        j = json.loads(P[k]); print("PAGE", k.split("/")[2], j.get("displayName"), j.get("width"), j.get("height"))
    if k.endswith("visual.json"):
        j = json.loads(P[k]); v = j["visual"]; pos = j["position"]
        fields = []
        for well, q in v.get("query", {}).get("queryState", {}).items():
            for pr in q.get("projections", []):
                fields.append(well + ":" + pr.get("queryRef", "") + ("=" + pr["displayName"] if "displayName" in pr else ""))
        print("VIS", k.split("/")[2][:8], k.split("/")[4][:8], v["visualType"], int(pos["x"]), int(pos["y"]), int(pos["width"]), int(pos["height"]), "|", "; ".join(fields), "| objs:", list(v.get("objects", {})), list(v.get("visualContainerObjects", {})), "| filt:", len(j.get("filterConfig", {}).get("filters", [])))

# %% 3 · Polish: 1280x720 pages, grid layout, titles, display names, RAG rules; backup + update
import json, base64, uuid, copy, time
P = copy.deepcopy(PARTS)
ws = fabric.get_workspace_id()
def L(v):
    if isinstance(v, bool): s = "true" if v else "false"
    elif isinstance(v, (int, float)): s = f"{v}D"
    else: s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}
def col(c): return {"solid": {"color": L(c)}}
M = lambda e, p: {"Measure": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}
pages = {}
for k in P:
    if k.endswith("page.json"):
        j = json.loads(P[k]); pages[k.split("/")[2]] = j.get("displayName", "")
def find(page_word, vtype, field=None):
    for k in P:
        if not k.endswith("visual.json"): continue
        pid = k.split("/")[2]
        if page_word.lower() not in pages[pid].lower(): continue
        j = json.loads(P[k])
        if j["visual"]["visualType"] != vtype: continue
        refs = [pr.get("queryRef", "") for q in j["visual"].get("query", {}).get("queryState", {}).values() for pr in q.get("projections", [])]
        if field is None or any(r.endswith(field) for r in refs):
            return k
    print("NOT FOUND", page_word, vtype, field); return None
def edit(k, x=None, y=None, w=None, h=None, title=None, names=None, objects=None):
    if k is None: return
    j = json.loads(P[k]); v = j["visual"]
    if x is not None: j["position"].update({"x": x, "y": y, "width": w, "height": h})
    if title is not None:
        v.setdefault("visualContainerObjects", {})["title"] = [{"properties": {"show": L(True), "text": L(title), "fontSize": L(13), "fontColor": col("#1F2A37")}}]
    for q in v.get("query", {}).get("queryState", {}).values():
        for pr in q.get("projections", []):
            for ref, nm in (names or {}).items():
                if pr.get("queryRef", "").endswith(ref): pr["displayName"] = nm
    for name, val in (objects or {}).items():
        v.setdefault("objects", {})[name] = val
    P[k] = json.dumps(j, indent=2)
def para(runs): return {"textRuns": [{"value": t, "textStyle": s} for t, s in runs]}
def textbox_objects(paras):
    return {"general": [{"properties": {"paragraphs": paras}}]}
def new_textbox(pid, x, y, w, h, paras):
    name = uuid.uuid4().hex[:20]
    j = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.0.0/schema.json",
         "name": name, "position": {"x": x, "y": y, "z": 9000, "width": w, "height": h, "tabOrder": 9000},
         "visual": {"visualType": "textbox", "objects": textbox_objects(paras), "drillFilterOtherVisuals": True}}
    P[f"definition/pages/{pid}/visuals/{name}/visual.json"] = json.dumps(j, indent=2)
H1 = {"fontSize": "20pt", "fontWeight": "bold", "color": "#0B1F33"}
SUB = {"fontSize": "11pt", "color": "#5B6775"}
NOTE = {"fontSize": "11pt", "color": "#3B4754"}
NOTEB = {"fontSize": "11pt", "fontWeight": "bold", "color": "#0B1F33"}
# pages: 1280x720, clean names
for k in list(P):
    if k.endswith("page.json"):
        j = json.loads(P[k]); j["width"], j["height"] = 1280, 720
        if "sales" in j.get("displayName", "").lower(): j["displayName"] = "Sales performance"
        P[k] = json.dumps(j, indent=2)
p1 = [p for p, n in pages.items() if "sales" in n.lower()][0]
p2 = [p for p, n in pages.items() if "what" in n.lower()][0]
pages[p1] = "Sales performance"
# ---- Page 1
tb = find("sales", "textbox")
if tb:
    edit(tb, 16, 8, 1248, 56, objects=textbox_objects([para([("Agency Performance — Sales", H1)]), para([("2026 YTD · AA passenger share vs QSI fair share · contract attainment for managed accounts", SUB)])]))
else:
    new_textbox(p1, 16, 8, 1248, 56, [para([("Agency Performance — Sales", H1)]), para([("2026 YTD · AA passenger share vs QSI fair share · contract attainment for managed accounts", SUB)])])
edit(find("sales", "cardVisual", "Share Gap (pts)"), 16, 72, 406, 110, names={"Share Gap (pts)": "Share gap vs fair share (pts)"})
edit(find("sales", "cardVisual", "At-Risk Accounts"), 437, 72, 406, 110, names={"At-Risk Accounts": "At-risk managed accounts (<90%)"})
edit(find("sales", "cardVisual", "AA Revenue"), 858, 72, 406, 110, names={"AA Revenue": "AA revenue, 2026 YTD"})
LBL = {"labels": [{"properties": {"show": L(True), "fontSize": L(10)}}]}
edit(find("sales", "clusteredBarChart", "region"), 16, 196, 410, 252, title="Share gap vs fair share by region (pts)", objects=LBL)
ref = dict(LBL); ref["y1AxisReferenceLine"] = [{"properties": {"show": L(True), "value": L(0.9), "lineColor": col("#C8102E"), "style": L("dashed"), "displayName": L("At risk below 90%"), "dataLabelShow": L(True)}, "selector": {"id": "1"}}]
edit(find("sales", "clusteredBarChart", "account_manager"), 16, 462, 410, 250, title="Contract attainment by account manager (managed)", objects=ref)
CA = M("account_market_month", "Contract Attainment")
def rag(measure, metadata):
    cases = [
        {"Condition": {"Comparison": {"ComparisonKind": 3, "Left": measure, "Right": {"Literal": {"Value": "0.9D"}}}}, "Value": {"Literal": {"Value": "'#FDE2E1'"}}},
        {"Condition": {"Comparison": {"ComparisonKind": 3, "Left": measure, "Right": {"Literal": {"Value": "1D"}}}}, "Value": {"Literal": {"Value": "'#FFF1D6'"}}},
        {"Condition": {"Comparison": {"ComparisonKind": 2, "Left": measure, "Right": {"Literal": {"Value": "1D"}}}}, "Value": {"Literal": {"Value": "'#E3F4E6'"}}}]
    return [{"properties": {"backColor": {"solid": {"color": {"expr": {"Conditional": {"Cases": cases}}}}}},
             "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": metadata}}]
edit(find("sales", "tableEx"), 442, 196, 822, 516, title="Managed accounts, lowest attainment first",
     names={"account_name": "Account", "risk_status": "Status", "Contract Attainment": "Contract attainment", "Share Gap (pts)": "Share gap (pts)"},
     objects={"values": rag(CA, "account_market_month.Contract Attainment")})
# ---- Page 2
new_textbox(p2, 16, 8, 1248, 56, [para([("Deal What-If", H1)]), para([("Test a contract target (QSI fair share + points) before the negotiation · managed accounts, 2026 YTD", SUB)])])
edit(find("what", "slicer", "target_points"), 16, 72, 300, 200, names={"target_points": "Target: fair share + pts"})
edit(find("what", "slicer", "account_name"), 16, 288, 300, 100, names={"account_name": "Account"})
new_textbox(p2, 16, 404, 300, 308, [
    para([("How to read", NOTEB)]),
    para([("Contract attainment is the deal in force today: AA passengers ÷ contracted passengers in QSI-eligible markets.", NOTE)]),
    para([("Scenario attainment re-prices the target at fair share + the points selected above.", NOTE)]),
    para([("Below 90% is at risk. When the selected points equal the contract (Zhang PLC: +15), both cards match: a built-in check.", NOTE)])])
edit(find("what", "cardVisual", "Contract Attainment"), 332, 72, 300, 120, names={"Contract Attainment": "Contract attainment (deal today)"})
edit(find("what", "cardVisual", "Scenario Attainment"), 648, 72, 300, 120, names={"Scenario Attainment": "Scenario attainment"})
edit(find("what", "cardVisual", "Scenario Passenger Gap"), 964, 72, 300, 120, names={"Scenario Passenger Gap": "Passengers short of target"})
edit(find("what", "tableEx"), 332, 208, 932, 504, title="Markets for the selected account at the tested target",
     names={"market_name": "Market", "Passenger Share": "AA passenger share", "Fair Share (QSI)": "Fair share (QSI)", "Scenario Attainment": "Scenario attainment"},
     objects={"values": rag(M("account_market_month", "Scenario Attainment"), "account_market_month.Scenario Attainment")})
def to_parts(D): return [{"path": k, "payload": base64.b64encode(v.encode("utf-8")).decode(), "payloadType": "InlineBase64"} for k, v in D.items() if not k.endswith(".platform")]
# backup of the untouched report, then update in place
names_now = [r["displayName"] for r in c.get(f"/v1/workspaces/{ws}/reports").json()["value"]]
if "Agency Performance (backup)" not in names_now:
    rb = c.post(f"/v1/workspaces/{ws}/reports", json={"displayName": "Agency Performance (backup)", "definition": {"parts": to_parts(PARTS)}})
    print("backup status", rb.status_code, rb.text[:200])
    if rb.status_code == 202:
        op = rb.headers["Location"]
        while True:
            time.sleep(2); s_ = c.get(op).json()
            if s_.get("status") in ("Succeeded", "Failed"): break
        print("BACKUP", s_.get("status"), json.dumps(s_.get("error"))[:300])
    print("Backup saved: Agency Performance (backup)")
r = c.post(f"/v1/workspaces/{ws}/reports/{REP['id']}/updateDefinition", json={"definition": {"parts": to_parts(P)}})
print("update status", r.status_code, r.text[:300])
if r.status_code == 202:
    op = r.headers["Location"]
    while True:
        time.sleep(2); s_ = c.get(op).json()
        if s_.get("status") in ("Succeeded", "Failed"): break
    print("UPDATE", s_.get("status"), json.dumps(s_.get("error"))[:600])
globals()["POLISHED"] = P
print("Done. Parts:", len(P))

# %% 4 · Layout pass: no auto-subtitles, slicer tiles in one row, market bar chart with 90% line
import json, copy, uuid, base64, time
NOSUB = [{"properties": {"show": L(False)}}]
def nosub(k):
    j = json.loads(P[k]); j["visual"].setdefault("visualContainerObjects", {})["subTitle"] = NOSUB; P[k] = json.dumps(j, indent=2)
reg = find("sales", "clusteredBarChart", "region"); am = find("sales", "clusteredBarChart", "account_manager")
edit(reg, 16, 196, 520, 170); nosub(reg)
edit(am, 16, 378, 520, 334); nosub(am)
edit(find("sales", "tableEx"), 552, 196, 712, 516)
edit(find("what", "slicer", "target_points"), 16, 72, 300, 90)
edit(find("what", "slicer", "account_name"), 16, 174, 300, 80)
for k in P:
    if k.endswith("visual.json") and k.split("/")[2] == p2:
        j = json.loads(P[k])
        if j["visual"]["visualType"] == "textbox" and j["position"]["y"] > 300:
            j["position"].update({"x": 16, "y": 266, "width": 300, "height": 446}); P[k] = json.dumps(j, indent=2)
edit(find("what", "tableEx"), 332, 208, 560, 504)
if not any(k.split("/")[2] == p2 and json.loads(P[k])["visual"]["visualType"] == "clusteredBarChart" for k in P if k.endswith("visual.json")):
    src = json.loads(P[am]); vis = json.dumps(src["visual"]).replace("account_manager", "market_name").replace("Contract Attainment", "Scenario Attainment")
    name = uuid.uuid4().hex[:20]
    nj = {"$schema": src["$schema"], "name": name, "position": {"x": 904, "y": 208, "z": 9100, "width": 360, "height": 504, "tabOrder": 9100}, "visual": json.loads(vis)}
    P[f"definition/pages/{p2}/visuals/{name}/visual.json"] = json.dumps(nj, indent=2)
    edit(f"definition/pages/{p2}/visuals/{name}/visual.json", title="Scenario attainment by market (90% = at risk)")
    print("added market bar chart")
r = c.post(f"/v1/workspaces/{ws}/reports/{REP['id']}/updateDefinition", json={"definition": {"parts": to_parts(P)}})
print("update status", r.status_code, r.text[:300])
if r.status_code == 202:
    op = r.headers["Location"]
    while True:
        time.sleep(2); s_ = c.get(op).json()
        if s_.get("status") in ("Succeeded", "Failed"): break
    print("UPDATE", s_.get("status"), json.dumps(s_.get("error"))[:600])
globals()["POLISHED"] = P

# %% 5 · Final sizing of the two page-1 bar charts
import json, time
edit(find("sales", "clusteredBarChart", "region"), 16, 196, 520, 214)
edit(find("sales", "clusteredBarChart", "account_manager"), 16, 422, 520, 290)
r = c.post(f"/v1/workspaces/{ws}/reports/{REP['id']}/updateDefinition", json={"definition": {"parts": to_parts(P)}})
op = r.headers.get("Location")
while op:
    time.sleep(2); s_ = c.get(op).json()
    if s_.get("status") in ("Succeeded", "Failed"): print("UPDATE", s_.get("status")); break
