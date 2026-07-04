import os
import sys
import xml.etree.ElementTree as ET

OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT)
from dio import DrawioDoc, vendored, bundled

COLOR = {
    "edge": "#EA580C",
    "workload": "#DB2777",
    "data": "#0891B2",
    "gitops": "#2563EB",
    "platform": "#64748B",
}

GAP = 25
MARGIN = 40

TOP_Y, TOP_H = 60, 150
EDGE_W, CERTS_W = 300, 220

MID_Y, MID_H = 250, 420
# AIOps holds two peer AI workloads side by side: Open WebUI's chain (through
# the shared LiteLLM proxy) and Hermes's chain (straight to GitHub Copilot).
# They're both "AI Workload", not "Hermes bolted onto an Agents box" --
# see conversation notes in docs/diagrams/readme.md.
MESH_W, AIOPS_W, DATA_W, STORAGE_W = 180, 480, 200, 240
AIOPS_HALF = AIOPS_W / 2

BOT_Y, BOT_H = 710, 170
OBS_W, SEC_W, GITOPS_W, OPS_W = 300, 200, 160, 300

mx_mesh = MARGIN
mx_aiops = mx_mesh + MESH_W + GAP
mx_data = mx_aiops + AIOPS_W + GAP
mx_storage = mx_data + DATA_W + GAP
mid_right = mx_storage + STORAGE_W

tx_edge = mx_aiops + (AIOPS_W - EDGE_W) / 2
tx_certs = tx_edge + EDGE_W + GAP

bx_obs = MARGIN
bx_sec = bx_obs + OBS_W + GAP
bx_gitops = bx_sec + SEC_W + GAP
bx_ops = bx_gitops + GITOPS_W + GAP
bot_right = bx_ops + OPS_W

PAGE_W = max(mid_right, bot_right, tx_certs + CERTS_W) + MARGIN
PAGE_H = BOT_Y + BOT_H + 60

doc = DrawioDoc("Logical Architecture", PAGE_W, PAGE_H)

# Enters from the left, at icon height -- entering from directly above would
# cross straight through the box's own title text.
user = doc.next_id()
cell = ET.SubElement(doc.root, "mxCell", id=user, value="User",
                      style="text;html=1;fontSize=14;fontStyle=1;fontColor=#0F172A;align=center;",
                      vertex="1", parent="1")
ET.SubElement(cell, "mxGeometry", x=str(tx_edge - 100), y=str(TOP_Y + 55 + 18), width="80", height="20", **{"as": "geometry"})

# -- Certificates ---------------------------------------------------------
doc.box(tx_certs, TOP_Y, CERTS_W, TOP_H, "certs", COLOR["platform"], "Certificates")
certmgr, lets = doc.icon_row(tx_certs, CERTS_W, TOP_Y + 55, [
    ("icon", bundled("onprem/certificates/cert-manager.png"), "cert-manager", 56, 10),
    ("icon", bundled("onprem/certificates/lets-encrypt.png"), "Let's Encrypt", 56, 10),
])

# -- Edge / Ingress ---------------------------------------------------------
doc.box(tx_edge, TOP_Y, EDGE_W, TOP_H, "edge", COLOR["edge"], "Edge / Ingress")
nginx, metallb = doc.icon_row(tx_edge, EDGE_W, TOP_Y + 55, [
    ("icon", bundled("onprem/network/nginx.png"), "ingress-nginx", 56, 10),
    ("icon", vendored("metallb.png"), "MetalLB (L2)", 56, 10),
])

# -- Service Mesh (disabled) -------------------------------------------------
doc.add_rect(mx_mesh, MID_Y, MESH_W, MID_H,
             f"rounded=1;dashed=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={COLOR['platform']};strokeWidth=2;")
doc.add_text(mx_mesh + 14, MID_Y + 8, MESH_W - 24, 50, "Service Mesh\n(evaluation / disabled)", size=13, color=COLOR["platform"])
istio, = doc.icon_row(mx_mesh, MESH_W, MID_Y + MID_H / 2 - 20, [
    ("icon", bundled("onprem/network/istio.png"), "Istio Ambient", 56, 10),
])

# -- AIOps ------------------------------------------------------------------
# Two peer branches under one AIOps roof: Open WebUI -> LiteLLM -> shared
# backends (left), and Hermes -> GitHub Copilot directly (right). Both are
# AI workloads; Hermes is not a separate "Agents" category.
doc.box(mx_aiops, MID_Y, AIOPS_W, MID_H, "workload", COLOR["workload"], "AIOps")
doc.add_rect(mx_aiops + AIOPS_HALF, MID_Y + 40, 1, MID_H - 60, "fillColor=#E2E8F0;strokeColor=none;")

openwebui, = doc.icon_row(mx_aiops, AIOPS_HALF, MID_Y + 55, [("icon", vendored("open-webui.png"), "Open WebUI", 56, 10)])
litellm, = doc.icon_row(mx_aiops, AIOPS_HALF, MID_Y + 165, [("icon", vendored("litellm.png"), "LiteLLM Proxy", 56, 10)])
ollama, nim, openai = doc.icon_row(mx_aiops, AIOPS_HALF, MID_Y + 285, [
    ("icon", vendored("ollama.png"), "Ollama", 46, 9),
    ("icon", vendored("nvidia.png"), "NVIDIA NIM", 46, 9),
    ("icon", vendored("openai.png"), "OpenAI", 46, 9),
])

# 3 ArgoCD Applications deploy the same hermes-agent-helm chart:
# hermes-agent (git main), hermes-june, hermes-july (pinned OCI releases) --
# see clusters/r4spi/apps/hermes-*.yaml.
hermes, = doc.icon_row(mx_aiops + AIOPS_HALF, AIOPS_HALF, MID_Y + 55, [("icon", vendored("hermes.png"), "Hermes", 56, 10)])
doc.add_text(mx_aiops + AIOPS_HALF + 10, MID_Y + 120, AIOPS_HALF - 20, 18, "3 instances: agent / june / july", size=9, bold=False, color="#64748B", align="center")
discord, copilot = doc.icon_row(mx_aiops + AIOPS_HALF, AIOPS_HALF, MID_Y + 165, [
    ("icon", vendored("discord.png"), "Discord (ext.)", 50, 9),
    ("icon", vendored("githubcopilot.png"), "GitHub Copilot\n(device-flow, ext.)", 50, 9),
])

# -- Stateful Data -----------------------------------------------------------
doc.box(mx_data, MID_Y, DATA_W, MID_H, "data", COLOR["data"], "Stateful Data")
cnpg, qdrant = doc.icon_row(mx_data, DATA_W, MID_Y + MID_H / 2 - 30, [
    ("icon", vendored("cloudnativepg.png"), "CloudNativePG", 56, 10),
    ("icon", bundled("onprem/database/qdrant.png"), "Qdrant", 56, 10),
])

# -- Storage ------------------------------------------------------------
doc.box(mx_storage, MID_Y, STORAGE_W, MID_H, "platform", COLOR["platform"], "Storage")
longhorn, seaweed, nfs = doc.icon_row(mx_storage, STORAGE_W, MID_Y + MID_H / 2 - 30, [
    ("icon", vendored("longhorn.png"), "Longhorn", 50, 9),
    ("icon", vendored("seaweedfs.png"), "SeaweedFS", 50, 9),
    ("mono", "NFS", "NFS (legacy)", COLOR["platform"], 50, 9),
])

# -- Observability ------------------------------------------------------
doc.box(bx_obs, BOT_Y, OBS_W, BOT_H, "platform", COLOR["platform"], "Observability")
grafana, prom, loki, tempo = doc.icon_row(bx_obs, OBS_W, BOT_Y + 55, [
    ("icon", bundled("onprem/monitoring/grafana.png"), "Grafana", 46, 9),
    ("icon", bundled("onprem/monitoring/prometheus.png"), "Prometheus", 46, 9),
    ("icon", vendored("loki.png"), "Loki", 46, 9),
    ("mono", "TE", "Tempo", COLOR["platform"], 46, 9),
])

# -- Secrets --------------------------------------------------------------
doc.box(bx_sec, BOT_Y, SEC_W, BOT_H, "platform", COLOR["platform"], "Secrets")
sealed, infisical = doc.icon_row(bx_sec, SEC_W, BOT_Y + 55, [
    ("mono", "SS", "Sealed Secrets", COLOR["platform"], 56, 10),
    ("icon", vendored("infisical.png"), "Infisical", 56, 10),
])

# -- GitOps ---------------------------------------------------------------
doc.box(bx_gitops, BOT_Y, GITOPS_W, BOT_H, "gitops", COLOR["gitops"], "GitOps")
argocd, = doc.icon_row(bx_gitops, GITOPS_W, BOT_Y + 55, [
    ("icon", bundled("onprem/gitops/argocd.png"), "ArgoCD", 56, 10),
])

# -- Ops Utilities ------------------------------------------------------
doc.box(bx_ops, BOT_Y, OPS_W, BOT_H, "platform", COLOR["platform"], "Ops Utilities")
portainer, homer, n8n, actions = doc.icon_row(bx_ops, OPS_W, BOT_Y + 55, [
    ("icon", vendored("portainer.png"), "Portainer", 46, 9),
    ("icon", vendored("homer.png"), "Homer", 46, 9),
    ("icon", vendored("n8n.png"), "n8n", 46, 9),
    ("icon", bundled("onprem/ci/github-actions.png"), "Actions Runner", 46, 9),
])

# ---------------------------------------------------------------------------
# primary request / data flow
doc.add_edge(user, nginx, color=COLOR["edge"])
doc.add_edge(nginx, openwebui, color=COLOR["workload"])
doc.add_edge(openwebui, litellm, color=COLOR["workload"], label="LLM request")
doc.add_edge(litellm, ollama, color=COLOR["workload"])
doc.add_edge(litellm, nim, color=COLOR["workload"])
doc.add_edge(litellm, openai, color=COLOR["workload"])
doc.add_edge(hermes, discord, color=COLOR["workload"])
doc.add_edge(hermes, copilot, color=COLOR["workload"])

# control / secondary interaction
doc.add_edge(certmgr, lets, color=COLOR["platform"], dashed=True)
doc.add_edge(certmgr, nginx, color=COLOR["platform"], dashed=True, label="issues certs")
# Routed explicitly down the AIOps box's right margin, then left through the
# gap between tiers -- edgeStyle=orthogonalEdgeStyle (the default) ignores
# manual waypoints entirely and recomputes its own path, which cuts straight
# through the Ollama/NIM/OpenAI row on the way to Secrets. add_edge() drops
# the computed edgeStyle whenever waypoints are given, so these points are
# honored as literal turns.
_hermes_cy = MID_Y + 55 + 28
_sealed_cx = bx_sec + 35 + 28
_gap_y = MID_Y + MID_H + 20
doc.add_edge(hermes, sealed, color=COLOR["platform"], dashed=True, label="hermes-agent-creds",
             exit_side="right", entry_side="top",
             waypoints=[(mx_aiops + AIOPS_W + 12, _hermes_cy),
                        (mx_aiops + AIOPS_W + 12, _gap_y),
                        (_sealed_cx, _gap_y)])

# Legend
ly = PAGE_H - 40
doc.add_rect(MARGIN, ly, 18, 3, "fillColor=#334155;strokeColor=none;")
doc.add_text(MARGIN + 26, ly - 10, 220, 20, "request / data flow", size=11, bold=False)
doc.add_rect(MARGIN + 240, ly, 18, 3, "fillColor=#64748B;strokeColor=none;dashed=1;")
doc.add_text(MARGIN + 266, ly - 10, 260, 20, "control / secondary interaction", size=11, bold=False)

doc.write(os.path.join(OUT, "logical-architecture.drawio"))
