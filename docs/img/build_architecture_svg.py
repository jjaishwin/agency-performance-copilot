"""Detailed architecture diagram for the Agency Performance Copilot (16:9 slide)."""
W, H = 1920, 1080
INK, QUIET, EDGE = "#1F2937", "#5B6675", "#A3ADB9"
DBX_FILL, DBX_EDGE, DBX_ACC = "#FFF6F1", "#F2B8A0", "#D9481C"      # Databricks area
MS_FILL, MS_EDGE, MS_ACC = "#F1F6FD", "#A9C6EC", "#1F63C6"          # Microsoft area
OPS_FILL, OPS_EDGE = "#F4F5F7", "#C5CBD3"
UC_FILL = "#FDE8DD"
GATE = "#0F766E"

out = []
def add(s): out.append(s)

def esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def text(x, y, t, size=15, weight=400, color=INK, anchor="start"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{esc(t)}</text>')

def rect(x, y, w, h, fill="white", stroke=EDGE, sw=1.4, r=10, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

# ---------- icons (drawn, 30x30 box at x,y) ----------
import os, base64
SLOTS = os.environ.get("SLOTS") == "1"
LOGOS = os.environ.get("LOGOS") == "1"
IC = "/home/claude/icons_src"
FAB = IC + "/e4c9db1f-Icons/v6.1.0/package/dist/svg/"
PP = IC + "/b6dd382c-Power-Platform-icons-scalable/"
AZ = IC + "/1974a0a9-Azure_Public_Service_Icons_V25/Azure_Public_Service_Icons/Icons/"
DBX = IC + "/fa1bf9d3-Databricks_Asset_Library-selected-assets/"
OFFICIAL = {
    "mirror": FAB + "mirrored_generic_database_32_item.svg",
    "lake": FAB + "one_lake_32_color.svg",
    "model": FAB + "semantic_model_32_item.svg",
    "chart_pbi": FAB + "report_32_item.svg",
    "flow": PP + "Power Platform/PowerAutomate_scalable.svg",
    "bot": PP + "CopilotStudio_scalable.svg",
    "package": DBX + "Databricks Symbol/databricks-symbol-color.svg",
}
def logo(path, x, y, size):
    data = base64.b64encode(open(path, "rb").read()).decode()
    add(f'<image x="{x}" y="{y}" width="{size}" height="{size}" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml;base64,{data}"/>')
def icon(kind, x, y, c):
    if LOGOS and kind in OFFICIAL:
        logo(OFFICIAL[kind], x - 1, y - 1, 32)
        return
    if kind == "chart_pbi":
        kind = "chart"
    if SLOTS:
        add(f'<rect x="{x-1}" y="{y-1}" width="32" height="32" rx="6" fill="white" stroke="{c}" stroke-width="1.4" stroke-dasharray="3 3"/>')
        return
    s = f'stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    g = f'<g transform="translate({x},{y})">'
    if kind == "db":
        g += f'<ellipse cx="15" cy="7" rx="11" ry="4" {s}/><path d="M4 7v16c0 2.2 4.9 4 11 4s11-1.8 11-4V7" {s}/><path d="M4 15c0 2.2 4.9 4 11 4s11-1.8 11-4" {s}/>'
    elif kind == "file":
        g += f'<path d="M7 3h11l6 6v18H7z" {s}/><path d="M18 3v6h6" {s}/><path d="M11 16h9M11 21h9" {s}/>'
    elif kind == "sheet":
        g += f'<rect x="4" y="5" width="22" height="20" rx="2" {s}/><path d="M4 12h22M4 18h22M12 5v20M19 5v20" {s}/>'
    elif kind == "plane":
        g += f'<path d="M3 17l24-10-6 18-6-6-5 5v-7z" {s}/>'
    elif kind == "layers":
        g += f'<path d="M15 4l11 6-11 6-11-6z" {s}/><path d="M4 16l11 6 11-6" {s}/><path d="M4 21l11 6 11-6" {s}/>'
    elif kind == "filter":
        g += f'<path d="M4 6h22l-8.5 10v8l-5 3V16z" {s}/>'
    elif kind == "cube":
        g += f'<path d="M15 3l11 6v12l-11 6-11-6V9z" {s}/><path d="M4 9l11 6 11-6M15 15v12" {s}/>'
    elif kind == "shield":
        g += f'<path d="M15 3l10 4v8c0 6-4.5 10-10 12C9.5 25 5 21 5 15V7z" {s}/><path d="M11 15l3 3 6-6" {s}/>'
    elif kind == "ruler":
        g += f'<rect x="3" y="10" width="24" height="10" rx="2" {s}/><path d="M8 10v4M13 10v5M18 10v4M23 10v5" {s}/>'
    elif kind == "score":
        g += f'<rect x="4" y="4" width="22" height="22" rx="3" {s}/><circle cx="10" cy="11" r="2" fill="{c}"/><circle cx="10" cy="19" r="2" fill="{c}"/><path d="M15 11h7M15 19h7" {s}/>'
    elif kind == "share":
        g += f'<circle cx="8" cy="15" r="3.5" {s}/><circle cx="22" cy="8" r="3.5" {s}/><circle cx="22" cy="22" r="3.5" {s}/><path d="M11 13.5l7.5-4M11 16.5l7.5 4" {s}/>'
    elif kind == "chat":
        g += f'<path d="M4 6h22v14H13l-6 5v-5H4z" {s}/><path d="M10 13h.01M15 13h.01M20 13h.01" stroke="{c}" stroke-width="3.2" stroke-linecap="round"/>'
    elif kind == "agents":
        g += f'<circle cx="15" cy="7" r="3.5" {s}/><circle cx="6" cy="23" r="3.5" {s}/><circle cx="15" cy="23" r="3.5" {s}/><circle cx="24" cy="23" r="3.5" {s}/><path d="M15 10.5v9M13 10l-5 10M17 10l5 10" {s}/>'
    elif kind == "spark":
        g += f'<path d="M15 3l2.5 7.5L25 13l-7.5 2.5L15 23l-2.5-7.5L5 13l7.5-2.5z" {s}/><path d="M24 22l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" {s}/>'
    elif kind == "app":
        g += f'<rect x="3" y="5" width="24" height="20" rx="3" {s}/><path d="M3 10h24" {s}/><circle cx="7" cy="7.5" r=".8" fill="{c}"/><circle cx="10" cy="7.5" r=".8" fill="{c}"/><path d="M8 20l4-5 3 3 5-6" {s}/>'
    elif kind == "gauge":
        g += f'<path d="M4 21a11 11 0 0 1 22 0" {s}/><path d="M15 21l6-7" {s}/><circle cx="15" cy="21" r="1.8" fill="{c}"/>'
    elif kind == "mirror":
        g += f'<rect x="3" y="6" width="10" height="18" rx="2" {s}/><rect x="17" y="6" width="10" height="18" rx="2" {s}/><path d="M13 12h4M15 10l2 2-2 2M17 18h-4M15 16l-2 2 2 2" {s}/>'
    elif kind == "lake":
        g += f'<path d="M3 12c3-3 6-3 9 0s6 3 9 0 4-2 6-1" {s}/><path d="M3 19c3-3 6-3 9 0s6 3 9 0 4-2 6-1" {s}/><path d="M15 3v5" {s}/>'
    elif kind == "model":
        g += f'<rect x="3" y="4" width="10" height="8" rx="1.5" {s}/><rect x="17" y="4" width="10" height="8" rx="1.5" {s}/><rect x="10" y="19" width="10" height="8" rx="1.5" {s}/><path d="M8 12v3h14v-3M15 15v4" {s}/>'
    elif kind == "chart":
        g += f'<path d="M4 26h22" {s}/><rect x="6" y="15" width="4" height="11" rx="1" {s}/><rect x="13" y="9" width="4" height="17" rx="1" {s}/><rect x="20" y="4" width="4" height="22" rx="1" {s}/>'
    elif kind == "flow":
        g += f'<circle cx="7" cy="8" r="3.5" {s}/><rect x="18" y="4" width="8" height="8" rx="1.5" {s}/><rect x="11" y="19" width="8" height="8" rx="1.5" {s}/><path d="M10.5 8h7.5M22 12v3h-7v4" {s}/>'
    elif kind == "bot":
        g += f'<rect x="5" y="9" width="20" height="15" rx="4" {s}/><path d="M15 9V5M12 4h6" {s}/><circle cx="11" cy="16" r="1.6" fill="{c}"/><circle cx="19" cy="16" r="1.6" fill="{c}"/><path d="M11 20.5h8" {s}/>'
    elif kind == "teams":
        g += f'<rect x="4" y="7" width="15" height="16" rx="2.5" {s}/><path d="M8 12h7M11.5 12v7" {s}/><circle cx="23" cy="9" r="3" {s}/><path d="M19 16h7v5a3.5 3.5 0 0 1-7 0" {s}/>'
    elif kind == "users":
        g += f'<circle cx="11" cy="10" r="4" {s}/><path d="M3 25c0-4.5 3.6-8 8-8s8 3.5 8 8" {s}/><circle cx="22" cy="11" r="3" {s}/><path d="M20.5 17.5c3.5 0 6.5 2.8 6.5 6.5" {s}/>'
    elif kind == "git":
        g += f'<circle cx="8" cy="7" r="3" {s}/><circle cx="8" cy="23" r="3" {s}/><circle cx="22" cy="12" r="3" {s}/><path d="M8 10v10M22 15c0 4-6 4-11 7" {s}/>'
    elif kind == "gear":
        g += f'<circle cx="15" cy="15" r="4" {s}/><path d="M15 3v4M15 23v4M3 15h4M23 15h4M6.5 6.5l2.8 2.8M20.7 20.7l2.8 2.8M6.5 23.5l2.8-2.8M20.7 9.3l2.8-2.8" {s}/>'
    elif kind == "package":
        g += f'<path d="M4 9l11-5 11 5v12l-11 5-11-5z" {s}/><path d="M4 9l11 5 11-5M15 14v12M9.5 6.5l11 5" {s}/>'
    elif kind == "check":
        g += f'<circle cx="15" cy="15" r="11" {s}/><path d="M10 15l3.5 3.5L20 12" {s}/>'
    elif kind == "key":
        g += f'<circle cx="10" cy="15" r="5" {s}/><path d="M15 15h11M22 15v4M26 15v3" {s}/>'
    g += "</g>"
    add(g)

def card(x, y, w, h, ic, title, sub=None, c=INK, fill="white", stroke=EDGE, sub2=None, dash=None):
    rect(x, y, w, h, fill=fill, stroke=stroke, dash=dash)
    icon(ic, x + 12, y + (h - 30) / 2 if not sub2 else y + 12, c)
    tx = x + 52
    if sub2:
        text(tx, y + 25, title, 15.5, 650)
        text(tx, y + 45, sub, 12.5, 400, QUIET)
        text(tx, y + 62, sub2, 12.5, 400, QUIET)
    elif sub:
        text(tx, y + h / 2 - 3, title, 15.5, 650)
        text(tx, y + h / 2 + 15, sub, 12.5, 400, QUIET)
    else:
        text(tx, y + h / 2 + 5, title, 15.5, 650)

def arrow(pts, color=EDGE, sw=1.8, dash=None):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" marker-end="url(#ah{color[1:]})"{da}/>')

def badge(x, y, n, color=INK):
    add(f'<circle cx="{x}" cy="{y}" r="12" fill="{color}"/>')
    text(x, y + 5, str(n), 13, 700, "white", "middle")

markers = set()
def marker(color):
    markers.add(color)

# ---------- canvas ----------
add(f'<rect width="{W}" height="{H}" fill="white"/>')
text(48, 58, "Agency Performance Copilot: architecture", 30, 700)
text(48, 88, "Synthetic airline corporate and agency sales data · Azure Databricks + Microsoft Fabric + Power Platform · one Microsoft Entra ID tenant", 16, 400, QUIET)

# ---------- 1. sources ----------
SX, SY, SW = 40, 135, 220
rect(SX - 10, SY - 10, SW + 20, 700, fill="#FAFAFB", stroke=OPS_EDGE, r=14)
text(SX + 4, SY + 18, "SOURCES (synthetic)", 13, 700, QUIET)
srcs = [("plane", "Bookings feed", "CSV · 267K tickets"),
        ("file", "Agency snapshots", "parent TMC changes"),
        ("file", "Accounts & contracts", "Managed + SMB · targets"),
        ("db", "Markets & QSI", "fair share by carrier"),
        ("sheet", "Legacy Excel", "incentive targets")]
for i, (ic, t, s) in enumerate(srcs):
    card(SX, SY + 36 + i * 126, SW, 104, ic, t, s, c=QUIET)

# ---------- 2. Azure Databricks ----------
DX, DY, DW, DH = 300, 125, 840, 710
rect(DX, DY, DW, DH, fill=DBX_FILL, stroke=DBX_EDGE, sw=1.8, r=16)
hx = DX + 22
if LOGOS:
    logo(AZ + "analytics/10787-icon-service-Azure-Databricks.svg", hx, DY + 14, 28)
    hx += 38
text(hx, DY + 34, "AZURE DATABRICKS (Premium)", 15, 750, DBX_ACC)
text(hx + 240, DY + 34, "serverless · Delta Lake · Unity Catalog · Lakeflow Jobs (Workflows)", 13.5, 400, QUIET)

# medallion
my = DY + 56
cw = 248
med = [("layers", "Bronze", "raw as landed", "+ source file & ingest time"),
       ("filter", "Silver", "types · dedupe · DQ checks", "quarantine with reasons · SCD2"),
       ("cube", "Gold", "account×market×month", "agency×month · facts · dims")]
for i, (ic, t, s, s2) in enumerate(med):
    card(DX + 22 + i * (cw + 34), my, cw, 84, ic, t, s, c=DBX_ACC, sub2=s2)
for i in range(2):
    x1 = DX + 22 + (i + 1) * cw + i * 34
    arrow([(x1 + 3, my + 42), (x1 + 31, my + 42)], DBX_ACC); marker(DBX_ACC)

# Unity Catalog band
uy = my + 104
rect(DX + 22, uy, DW - 44, 52, fill=UC_FILL, stroke=DBX_EDGE)
icon("shield", DX + 36, uy + 11, DBX_ACC)
text(DX + 76, uy + 24, "Unity Catalog governance", 15.5, 700)
text(DX + 76, uy + 42, "comments + tags · region row filter · PNR column mask · lineage · grants · volumes", 12.5, 400, QUIET)

# products
py = uy + 72
pw = 248
prods = [("ruler", "Metric views", "share · fair share (QSI)", "attainment · NDC · incentive ROI"),
         ("score", "Scorecards & scenarios", "agency Green/Amber/Red", "account risk · QSI + 0/5/10/15"),
         ("share", "fabric_share schema", "tables for mirroring", "no row filters, no contact IDs")]
for i, (ic, t, s, s2) in enumerate(prods):
    card(DX + 22 + i * (pw + 34), py, pw, 84, ic, t, s, c=DBX_ACC, sub2=s2)

# AI layer
ay = py + 112
text(DX + 22, ay - 10, "AI LAYER", 12.5, 700, QUIET)
aw = 248
ai = [("chat", "Genie Agent", "formerly Genie Space · as code", "15 benchmarks · release gate"),
      ("agents", "Sales Copilot agent", "Agent Bricks · Genie + UC tools", "Supervisor (legacy) → CLI next"),
      ("spark", "Brief agent", "LLM + governed tool", "MLflow tracing + evaluation")]
for i, (ic, t, s, s2) in enumerate(ai):
    card(DX + 22 + i * (aw + 34), ay, aw, 84, ic, t, s, c=DBX_ACC, sub2=s2)

# apps / monitoring
oy = ay + 104
card(DX + 22, oy, 395, 66, "app", "Deal Desk (Databricks App)", "what-if · Ask Genie · runs as the signed-in user", c=DBX_ACC)
card(DX + 22 + 395 + 34, oy, 367, 66, "gauge", "Monitoring (AI/BI dashboard)", "benchmark accuracy · DQ failures · health", c=DBX_ACC)
wy = oy + 86
card(DX + 22, wy, 395, 66, "spark", "MLflow 3", "traces · evaluations · LLM judges · runs", c=DBX_ACC)
card(DX + 22 + 395 + 34, wy, 367, 66, "db", "Serverless SQL warehouse", "serves Genie, the app and Power Automate", c=DBX_ACC)

# internal arrows (gold -> UC -> products -> AI)
gx = DX + 22 + 2 * (cw + 34) + cw / 2
arrow([(gx, my + 84), (gx, uy - 2)], DBX_ACC)
for i in range(3):
    cx = DX + 22 + i * (pw + 34) + pw / 2
    arrow([(cx, uy + 52), (cx, py - 2)], DBX_ACC)
arrow([(DX + 22 + pw / 2, py + 84), (DX + 22 + pw / 2, ay - 2)], DBX_ACC)                    # metric views -> Genie
arrow([(DX + 22 + pw + 34 + pw / 2, py + 84), (DX + 22 + pw + 34 + pw / 2, ay - 2)], DBX_ACC)  # scorecards -> supervisor
arrow([(DX + 22 + aw + 2, ay + 42), (DX + 22 + aw + 32, ay + 42)], DBX_ACC)                  # genie -> supervisor (subagent)

# ---------- 3. Microsoft ----------
MX, MY, MW, MH = 1180, 125, 470, 710
rect(MX, MY, MW, MH, fill=MS_FILL, stroke=MS_EDGE, sw=1.8, r=16)
mhx = MX + 22
if LOGOS:
    logo(FAB + "fabric_32_color.svg", mhx, MY + 14, 28)
    logo(PP + "Power Platform/PowerPlatform_scalable.svg", mhx + 34, MY + 14, 28)
    mhx += 72
text(mhx, MY + 34, "MICROSOFT FABRIC · POWER PLATFORM · M365", 15, 750, MS_ACC)
cw2 = MW - 44
ms = [("mirror", "Mirrored Azure Databricks Catalog", "reads fabric_share in place: no copy"),
      ("lake", "OneLake + OneLake security", "region RLS roles (preview on mirror) · parity test"),
      ("model", "Direct Lake on OneLake model", "DAX re-implements metric views · TMDL in Git"),
      ("chart_pbi", "Power BI report", "scorecards · share vs QSI · deal what-if"),
      ]
ys = [MY + 56, MY + 148, MY + 240, MY + 332, MY + 460, MY + 460]
for (ic, t, s), y in zip(ms, ys):
    card(MX + 22, y, cw2, 72, ic, t, s, c=MS_ACC)
hw = (cw2 - 16) / 2
card(MX + 22, ys[4], hw, 96, "flow", "Power Automate", "Azure Databricks conn.", c=MS_ACC, sub2="premium · monthly")
card(MX + 22 + hw + 16, ys[5], hw, 96, "bot", "Copilot Studio", "Genie tool (MCP)", c=MS_ACC, sub2="Managed MCP preview")
for a, b in [(0, 1), (1, 2), (2, 3)]:
    arrow([(MX + 22 + cw2 / 2, ys[a] + 72), (MX + 22 + cw2 / 2, ys[b] - 2)], MS_ACC)
TY = MY + 600
card(MX + 22, TY, cw2, 64, "teams", "Microsoft Teams", "scorecard posts · agent chat", c=MS_ACC)
arrow([(MX + 22 + hw / 2, ys[4] + 96), (MX + 22 + hw / 2, TY - 2)], MS_ACC)
arrow([(MX + 22 + hw + 16 + hw / 2, ys[5] + 96), (MX + 22 + hw + 16 + hw / 2, TY - 2)], MS_ACC)

# ---------- cross-platform arrows ----------
sh_x = DX + 22 + 2 * (pw + 34) + pw
arrow([(sh_x + 2, py + 42), (DX + DW + 8, py + 42), (DX + DW + 8, ys[0] + 36), (MX + 20, ys[0] + 36)], INK, 2.2)     # fabric_share -> mirror
arrow([(DX + 22 + 395 + 34 + 367 + 2, wy + 33), (DX + DW + 22, wy + 33), (DX + DW + 22, ys[4] + 48), (MX + 20, ys[4] + 48)], INK, 2.2)  # SQL warehouse -> Power Automate
gen_x = DX + 22 + aw / 2
cop_x = MX + 22 + hw + 16 + hw / 2
gq_x = DX + 22 + aw - 40
arrow([(gq_x, ay + 84), (gq_x, ay + 94), (DX + DW + 36, ay + 94), (DX + DW + 36, ys[4] - 16), (cop_x, ys[4] - 16), (cop_x, ys[5] - 2)], INK, 2.2)  # Genie -> Copilot Studio
# sources -> bronze
for i in range(5):
    yy = SY + 36 + i * 126 + 52
    add(f'<path d="M{SX+SW},{yy} C{SX+SW+22},{yy} {SX+SW+14},{my+42} {DX+20},{my+42}" fill="none" stroke="{EDGE}" stroke-width="1.5"/>')
marker(EDGE); marker(INK); marker(MS_ACC); marker(DBX_ACC)
add(f'<path d="M{DX+8},{my+42} L{DX+20},{my+42}" fill="none" stroke="{EDGE}" stroke-width="1.5" marker-end="url(#ah{EDGE[1:]})"/>')

# ---------- 4. users ----------
UX = 1690
rect(UX, 125, 190, 710, fill="#FAFAFB", stroke=OPS_EDGE, r=16)
text(UX + 18, 159, "WHO USES IT", 13, 700, QUIET)
users = [("users", "Account managers", ["pre-call prep in Teams", "deal what-if", "Ask Genie"]),
         ("chart", "Sales leaders", ["program scorecards", "share vs fair share", "incentive ROI"]),
         ("shield", "Data & AI team", ["benchmarks", "monitoring", "agent cards · CI/CD"])]
for i, (ic, t, lines) in enumerate(users):
    y = 185 + i * 205
    rect(UX + 14, y, 162, 180, fill="white", stroke=EDGE)
    icon(ic, UX + 28, y + 14, INK)
    text(UX + 28, y + 70, t, 15, 650)
    for j, l in enumerate(lines):
        text(UX + 28, y + 98 + j * 22, "· " + l, 12.5, 400, QUIET)
arrow([(MX + MW + 2, TY + 32), (UX - 4, TY + 32)], MS_ACC, 2.2)
arrow([(MX + MW + 2, ys[3] + 36), (UX - 4, ys[3] + 36)], MS_ACC, 2.2)


# ---------- 5. DevOps lane ----------
LY = 870
rect(30, LY, 1850, 160, fill=OPS_FILL, stroke=OPS_EDGE, r=16)
text(52, LY + 32, "DEVOPS, EVALUATION & IDENTITY", 13, 700, QUIET)
lane = [("git", "GitHub repo", "notebooks · Genie spec · app", "dashboard JSON · TMDL"),
        ("gear", "GitHub Actions", "OIDC, no PAT · spec check", "deploy on merge to main"),
        ("package", "Declarative Automation Bundle", "Lakeflow job: 12 notebook tasks", "Deal Desk app + user scopes"),
        ("check", "Quality gates", "Genie: 15 benchmarks ≥ 90% in CI", "brief + routing evals (by hand)"),
        ("key", "Microsoft Entra ID", "one tenant · OBO app · OIDC for CI", "one shared credential for the mirror")]
lw = 330
for i, (ic, t, s, s2) in enumerate(lane):
    card(52 + i * (lw + 26), LY + 48, lw, 84, ic, t, s, c=GATE if ic == "check" else INK, sub2=s2)
for i in range(3):
    x1 = 52 + (i + 1) * lw + i * 26
    arrow([(x1 + 3, LY + 90), (x1 + 23, LY + 90)], INK)

# ---------- numbered flow badges ----------
badge(SX + SW + 22, my + 14, 1, DBX_ACC)                       # land
badge(DX + 22 + cw + 17, my + 22, 2, DBX_ACC)                   # clean
badge(gx + 18, my + 98, 3, DBX_ACC)                             # govern
badge(DX + 22 + pw / 2 + 18, py + 98, 4, DBX_ACC)               # define metrics -> AI
badge(DX + DW + 8, ys[0] + 12, 5, INK)                          # mirror
badge(MX + 22 + cw2 / 2 + 18, ys[2] + 84, 6, MS_ACC)            # model/report
badge(cop_x - 60, ys[4] - 16, 7, INK)                          # genie -> copilot
badge(1180 + MW + 20, TY + 8, 8, MS_ACC)                         # users

legend = ["1 land raw files", "2 clean, quarantine, keep history", "3 govern in Unity Catalog", "4 define metrics once; AI answers on them",
          "5 mirror to Fabric (no copy)", "6 Direct Lake model and Power BI", "7 agents and flows in Teams", "8 people act on it"]
lx = 48
for i, l in enumerate(legend):
    n, rest = l.split(" ", 1)
    add(f'<circle cx="{lx+8}" cy="{1058}" r="8" fill="{QUIET}"/>')
    text(lx + 8, 1062, n, 10.5, 700, "white", "middle")
    text(lx + 22, 1062, rest, 12.5, 500, QUIET)
    lx += 22 + len(rest) * 6.9 + 26
text(1880, 1062, "", 12, 400, QUIET, "end")

# ---------- assemble ----------
defs = "<defs>" + "".join(
    f'<marker id="ah{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
    for c in markers | {INK, EDGE, MS_ACC, DBX_ACC}) + "</defs>"
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       f'font-family="Inter, Helvetica, Arial, sans-serif">' + defs + "".join(out) + "</svg>")
open("/home/claude/diagram/agency_copilot_architecture" + ("_logo_slots" if SLOTS else "") + ("_official_icons" if LOGOS else "") + ".svg", "w").write(svg)
print("ok")
