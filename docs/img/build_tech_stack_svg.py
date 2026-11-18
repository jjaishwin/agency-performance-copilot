"""Tech stack slide (16:9) built from the official icon packs the user supplied."""
import base64
IC = "/home/claude/icons_src"
FAB = IC + "/e4c9db1f-Icons/v6.1.0/package/dist/svg/"
PP = IC + "/b6dd382c-Power-Platform-icons-scalable/"
AZ = IC + "/1974a0a9-Azure_Public_Service_Icons_V25/Azure_Public_Service_Icons/Icons/"
DBX = IC + "/fa1bf9d3-Databricks_Asset_Library-selected-assets/"
W, H = 1920, 1080
INK, QUIET, EDGE = "#1F2937", "#5B6675", "#D5DAE1"
out = []
add = out.append
def esc(t): return t.replace("&", "&amp;")
def text(x, y, t, size=15, weight=400, color=INK, anchor="start"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{esc(t)}</text>')
def img(path, x, y, w, h=None):
    h = h or w
    data = base64.b64encode(open(path, "rb").read()).decode()
    add(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml;base64,{data}"/>')

# Reuse the drawn line icons from the architecture diagram for Databricks features (no official per-feature icons).
src = open("/home/claude/diagram/arch_svg.py").read()
start = src.index("def icon(kind, x, y, c):")
end = src.index("def card(")
ns = {"add": add, "LOGOS": False, "SLOTS": False, "OFFICIAL": {}}
exec(src[start:end], ns)
drawn = ns["icon"]

add(f'<rect width="{W}" height="{H}" fill="white"/>')
text(64, 78, "Tech stack: aligned to American's Azure + Databricks platform", 34, 700)
text(64, 114, "Azure Databricks for data and AI · Microsoft Fabric and Power Platform where account managers work · one Entra ID tenant", 17, 400, QUIET)

cols = [
    ("AZURE DATABRICKS", "#D9481C", "#FFF6F1", AZ + "analytics/10787-icon-service-Azure-Databricks.svg", [
        ("layers", "Delta Lake · medallion", "bronze / silver / gold, quarantine, SCD2"),
        ("shield", "Unity Catalog", "row filters, masks, lineage, metric views"),
        ("chat", "Genie Agent", "formerly Genie Space · as code · 15-benchmark gate"),
        ("agents", "Agent Bricks", "Supervisor Agent (legacy) now · CLI next"),
        ("spark", "MLflow 3", "tracing · evaluation · LLM judges"),
        ("app", "Apps · Declarative Automation Bundles", "Deal Desk app · Lakeflow job · one command"),
    ]),
    ("MICROSOFT FABRIC", "#117865", "#F0F8F5", FAB + "fabric_32_color.svg", [
        (FAB + "mirrored_generic_database_32_item.svg", "Mirrored Azure Databricks Catalog", "metadata mirror via shortcuts, no data copy"),
        (FAB + "one_lake_32_color.svg", "OneLake security", "region RLS on the mirror (preview), parity tested"),
        (FAB + "semantic_model_32_item.svg", "Direct Lake on OneLake", "DAX re-implements metric views, reconciled"),
        (FAB + "report_32_item.svg", "Power BI report", "scorecards, share vs QSI, deal what-if"),
        (FAB + "fabric_32_color.svg", "Git integration", "semantic model as TMDL in GitHub"),
    ]),
    ("POWER PLATFORM · M365", "#1F63C6", "#F1F6FD", PP + "Power Platform/PowerPlatform_scalable.svg", [
        (PP + "Power Platform/PowerAutomate_scalable.svg", "Power Automate", "Azure Databricks connector (premium)"),
        (PP + "CopilotStudio_scalable.svg", "Copilot Studio", "Genie tool (MCP, preview toggle) in Teams"),
        (PP + "Power Platform/PowerPlatform_scalable.svg", "Power Platform connector", "Entra sign-in, Unity Catalog permissions apply"),
        (AZ + "identity/10230-icon-service-Users.svg", "Microsoft Entra ID", "one tenant · OBO app · OIDC CI · shared mirror credential"),
    ]),
]
x0, cw, gap, top = 64, 584, 36, 160
for i, (title, acc, fill, hdr, items) in enumerate(cols):
    x = x0 + i * (cw + gap)
    add(f'<rect x="{x}" y="{top}" width="{cw}" height="800" rx="18" fill="{fill}" stroke="{EDGE}" stroke-width="1.5"/>')
    if i != 0:
        img(hdr, x + 26, top + 24, 40)
    tx = x + 80
    if i == 0:
        data = base64.b64encode(open(DBX + "Databricks Logo Primary Lockup/primary-lockup-full-color-rgb.svg", "rb").read()).decode()
        add(f'<image x="{x + 28}" y="{top + 28}" width="190" height="32" preserveAspectRatio="xMinYMid meet" href="data:image/svg+xml;base64,{data}"/>')
        text(x + 228, top + 52, "on Azure", 19, 750, acc)
    else:
        text(tx, top + 52, title, 19, 750, acc)
    for j, (ic, name, desc) in enumerate(items):
        y = top + 92 + j * 116
        add(f'<rect x="{x + 22}" y="{y}" width="{cw - 44}" height="100" rx="12" fill="white" stroke="{EDGE}" stroke-width="1.3"/>')
        if ic.startswith("/"):
            img(ic, x + 44, y + 28, 44)
        else:
            add(f'<g transform="translate({x + 44},{y + 28}) scale(1.45)">')
            drawn(ic, 0, 0, acc)
            add("</g>")
        text(x + 108, y + 46, name, 19, 650)
        text(x + 108, y + 72, desc, 15, 400, QUIET)
text(64, 1010, "Also: Python, PySpark, SQL, DAX, GitHub Actions. Synthetic data for demonstration. Product icons are the vendors' official icon sets, used to identify the products.", 15, 400, QUIET)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       f'font-family="Inter, Helvetica, Arial, sans-serif">' + "".join(out) + "</svg>")
open("/home/claude/diagram/agency_copilot_tech_stack.svg", "w").write(svg)
print("ok")
