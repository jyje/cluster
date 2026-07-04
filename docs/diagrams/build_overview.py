import base64
import os
import xml.etree.ElementTree as ET

REPO = "/Users/jyje/repo/jyje/cluster"
ICONS = os.path.join(REPO, "docs/assets/icons")
OUT = os.path.dirname(os.path.abspath(__file__))

import diagrams
RES = os.path.join(os.path.dirname(os.path.dirname(diagrams.__file__)), "resources")


def data_uri(path):
    # NOTE: mxGraph style strings split on ";", so a standard data URI
    # ("data:image/png;base64,...") corrupts the style. Drop the ";base64"
    # marker -- this is the exact form draw.io itself emits when you embed
    # an image via the GUI, and mxGraph's image loader still treats the
    # payload as base64.
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png,{b64}"


def vendored(name):
    return data_uri(os.path.join(ICONS, name))


def bundled(rel):
    return data_uri(os.path.join(RES, rel))


COLOR = {
    "infra": "#475569",
    "network": "#EA580C",
    "ai": "#DB2777",
    "gitops": "#2563EB",
}

# ---- layout constants (computed up front so page size is known before we
# create the mxGraphModel / background) --------------------------------
COL_TOP, COL_H = 60, 610
COL_W = 300
ROW_GAP = 20
GAP = 30
X0 = 40
X1 = X0 + COL_W + GAP
X2 = X1 + COL_W + GAP
X3 = X2 + COL_W + GAP
PAGE_W = X3 + COL_W + 40
PAGE_H = 720
ROW = [COL_TOP + 50, COL_TOP + 190, COL_TOP + 330, COL_TOP + 470]

# ---------------------------------------------------------------------------
mxfile = ET.Element("mxfile", host="app.diagrams.net")
diagram = ET.SubElement(mxfile, "diagram", name="System Overview", id="overview")
model = ET.SubElement(
    diagram, "mxGraphModel",
    dx="1600", dy="900", grid="0", gridSize="10", guides="1", tooltips="1",
    connect="1", arrows="1", fold="1", page="1", pageScale="1",
    pageWidth=str(PAGE_W), pageHeight=str(PAGE_H), math="0", shadow="0",
)
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", id="0")
ET.SubElement(root, "mxCell", id="1", parent="0")

_id = 1


def next_id():
    global _id
    _id += 1
    return f"n{_id}"


def add_rect(x, y, w, h, style, value=""):
    cid = next_id()
    cell = ET.SubElement(root, "mxCell", id=cid, value=value, style=style,
                          vertex="1", parent="1")
    ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h),
                  **{"as": "geometry"})
    return cid


def add_text(x, y, w, h, text, size=20, color="#1F2937", bold=True, align="left"):
    style = (f"text;html=1;fontSize={size};fontStyle={1 if bold else 0};"
             f"fontColor={color};align={align};verticalAlign=middle;")
    return add_rect(x, y, w, h, style, text)


def add_icon(x, y, uri, label, size=60, fontsize=11):
    style = (
        "shape=image;html=1;imageAspect=1;verticalLabelPosition=bottom;"
        "verticalAlign=top;labelBackgroundColor=none;"
        f"fontSize={fontsize};fontStyle=1;fontColor=#1F2937;"
        f"image={uri};"
    )
    return add_rect(x, y, size, size, style, label)


def add_edge(src, dst, color="#334155", dashed=False, dotted=False, label=""):
    style = f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor={color};strokeWidth=2;endArrow=block;endFill=1;fontSize=11;fontColor=#334155;"
    if dotted:
        style += "dashed=1;dashPattern=1 3;endArrow=open;"
    elif dashed:
        style += "dashed=1;"
    cid = next_id()
    cell = ET.SubElement(root, "mxCell", id=cid, value=label, style=style,
                          edge="1", parent="1", source=src, target=dst)
    ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
    return cid


def column(x, key, title):
    add_rect(x, COL_TOP, COL_W, COL_H, f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={COLOR[key]};strokeWidth=2;")
    add_text(x + 16, COL_TOP + 10, COL_W - 30, 34, title, size=19, color=COLOR[key])
    return x


def icon_row(col_x, y, items):
    """Lay out one or more icons as a single row, centered as a *group*
    within the column -- avoids the classic mistake of anchoring every row
    to the column's left edge, which leaves single-icon rows stranded with
    a wall of dead space to their right."""
    total = sum(size for _, _, size, _ in items) + ROW_GAP * (len(items) - 1)
    x = col_x + (COL_W - total) / 2
    ids = []
    for uri, label, size, fontsize in items:
        ids.append(add_icon(x, y, uri, label, size=size, fontsize=fontsize))
        x += size + ROW_GAP
    return ids


# ---------------------------------------------------------------------------
# Full-bleed light background: readable regardless of the surrounding page's
# light/dark theme (GitHub in particular). Must be added first (bottom of
# z-order). No title/description baked in here -- the README heading right
# above this image already carries that, so duplicating it here just ate
# vertical space and (at "auto" SVG theme) rendered as near-invisible
# low-contrast text on GitHub's dark background.
add_rect(0, 0, PAGE_W, PAGE_H, "fillColor=#F7F8FA;strokeColor=none;")

# -- Column 1: Infra --------------------------------------------------------
column(X0, "infra", "1. Infra (Hardware)")
raspi, = icon_row(X0, ROW[0], [(bundled("generic/os/raspbian.png"), "4x Raspberry Pi (ARM64)", 60, 11)])
gpu, = icon_row(X0, ROW[1], [(bundled("generic/os/ubuntu.png"), "1x GPU node (AMD64)", 60, 11)])
router, = icon_row(X0, ROW[2], [(bundled("generic/network/router.png"), "cluster-router (L2, 10.0.0.1)", 60, 11)])
firewall, = icon_row(X0, ROW[3], [(bundled("generic/network/firewall.png"), "home-router + firewall", 60, 11)])

# -- Column 2: Network -------------------------------------------------------
column(X1, "network", "2. Network Layer")
nginx, = icon_row(X1, ROW[0], [(bundled("onprem/network/nginx.png"), "ingress-nginx (hostNetwork DS)", 60, 11)])
certmgr, = icon_row(X1, ROW[1], [(bundled("onprem/certificates/cert-manager.png"), "cert-manager + Let's Encrypt", 60, 11)])
metallb, = icon_row(X1, ROW[2], [(vendored("metallb.png"), "MetalLB (L2 pool)", 60, 11)])
istio, = icon_row(X1, ROW[3], [(bundled("onprem/network/istio.png"), "Istio Ambient (disabled)", 60, 11)])

# -- Column 3: AI Workload ----------------------------------------------------
# Open WebUI and Hermes are peer AI workloads (row 0) -- Hermes isn't a
# separate "agent" bolted on, it just doesn't route through LiteLLM.
column(X2, "ai", "3. AI Workload (AIOps)")
openwebui, hermes = icon_row(X2, ROW[0], [
    (vendored("open-webui.png"), "Open WebUI", 50, 10),
    (vendored("hermes.png"), "Hermes", 50, 10),
])
litellm, = icon_row(X2, ROW[1], [(vendored("litellm.png"), "LiteLLM Proxy", 60, 11)])
ollama, nim, openai = icon_row(X2, ROW[2], [
    (vendored("ollama.png"), "Ollama", 50, 10),
    (vendored("nvidia.png"), "NVIDIA NIM", 50, 10),
    (vendored("openai.png"), "OpenAI", 50, 10),
])
qdrant, cnpg = icon_row(X2, ROW[3], [
    (bundled("onprem/database/qdrant.png"), "Qdrant", 56, 11),
    (vendored("cloudnativepg.png"), "CloudNativePG", 56, 11),
])

# -- Column 4: GitOps & Platform ---------------------------------------------
column(X3, "gitops", "4. GitOps & Platform")
argocd, = icon_row(X3, ROW[0], [(bundled("onprem/gitops/argocd.png"), "ArgoCD", 60, 11)])
add_text(X3 + 14, ROW[1] - 6, COL_W - 28, 70,
         "Reconciles L0 Bootstrap &#8594; L1 Root app-of-apps<br>"
         "&#8594; L2 Applications &#8594; L3 Helm charts<br>"
         "&#8594; L4 extraResources. Detail: delivery-pipeline.png",
         size=11, bold=False, color="#475569")
grafana, infisical, portainer = icon_row(X3, ROW[2], [
    (bundled("onprem/monitoring/grafana.png"), "Observability", 50, 10),
    (vendored("infisical.png"), "Secrets", 50, 10),
    (vendored("portainer.png"), "Ops Utilities", 50, 10),
])

# entry point: User enters at the network edge (the hardware layer is the
# physical substrate everything else runs on -- see hardware-architecture.png
# for how it wires to the router/firewall -- so it has no inbound arrow here)
user = next_id()
cell = ET.SubElement(root, "mxCell", id=user, value="User", style="text;html=1;fontSize=14;fontStyle=1;fontColor=#0F172A;align=center;", vertex="1", parent="1")
ET.SubElement(cell, "mxGeometry", x=str(X1 + COL_W / 2 - 40), y=str(COL_TOP - 40), width="80", height="20", **{"as": "geometry"})

# ---------------------------------------------------------------------------
# primary request / data flow (solid)
add_edge(user, nginx, color=COLOR["network"])
add_edge(nginx, openwebui, color=COLOR["ai"])
add_edge(openwebui, litellm, color=COLOR["ai"], label="LLM request")
add_edge(litellm, ollama, color=COLOR["ai"])
add_edge(litellm, nim, color=COLOR["ai"])
add_edge(litellm, openai, color=COLOR["ai"])

# control / secondary interaction (dashed). openwebui->qdrant and
# litellm->cnpg are deliberately NOT drawn here: openwebui/litellm sit
# dead-center of a 300px column with the Ollama/NIM/OpenAI row directly
# beneath them, so any orthogonal route to Qdrant/CloudNativePG cuts
# straight through the NVIDIA NIM icon. This overview already places
# Qdrant/CloudNativePG in the same column to show they're part of the AI
# workload; the exact call graph is what logical-architecture.png is for.
add_edge(certmgr, nginx, color="#64748B", dashed=True, label="issues certs")

# GitOps reconciles everything (dotted, long-haul) -- hardware is physical,
# so it is deliberately excluded from ArgoCD's reconcile targets
for target in (nginx, certmgr, openwebui, grafana):
    add_edge(argocd, target, color="#94A3B8", dotted=True)

# ---------------------------------------------------------------------------
# Legend
ly = PAGE_H - 40
add_rect(40, ly, 18, 3, "fillColor=#334155;strokeColor=none;")
add_text(66, ly - 10, 220, 20, "request / data flow", size=11, bold=False)
add_rect(280, ly, 18, 3, "fillColor=#64748B;strokeColor=none;dashed=1;")
add_text(306, ly - 10, 220, 20, "control / secondary interaction", size=11, bold=False)
add_rect(560, ly, 18, 3, "fillColor=#94A3B8;strokeColor=none;dashed=1;")
add_text(586, ly - 10, 260, 20, "reconciled by ArgoCD (GitOps)", size=11, bold=False)

tree = ET.ElementTree(mxfile)
ET.indent(tree, space="  ")
out_path = os.path.join(OUT, "system-overview.drawio")
tree.write(out_path, encoding="utf-8", xml_declaration=True)
print("wrote", out_path)
