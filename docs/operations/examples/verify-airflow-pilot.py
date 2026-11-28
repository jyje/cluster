#!/usr/bin/env python3
"""End-to-end check of the Airflow pilot user. Prints no password and no token.

Usage: python3 docs/operations/examples/verify-airflow-pilot.py
Needs kubectl with the context in KUBE_CONTEXT (default: microk8s).
Expected last line: failures: 0
"""
import base64, json, os, subprocess, time, urllib.error, urllib.request

BASE = "https://airflow.app.jyje.online"
DAG = "pilot_portability"
pw = base64.b64decode(subprocess.check_output(
    ["kubectl", "--context", os.environ.get("KUBE_CONTEXT", "microk8s"), "-n", "airflow", "get", "secret", "airflow-pilot",
     "-o", "jsonpath={.data.password}"])).decode()

def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}

status, data = call("POST", "/auth/token", body={"username": "pilot", "password": pw})
token = data.get("access_token")
print("token:", status, "received" if token else "NOT received")
if not token:
    raise SystemExit(1)
fails = 0
def expect(name, got, want):
    global fails
    ok = got in want
    fails += not ok
    print(("ok  " if ok else "FAIL"), name, "->", got)

s, d = call("GET", "/api/v2/dags", token)
expect("list dags", s, {200}); print("     visible:", [x["dag_id"] for x in d.get("dags", [])])
run = f"pilot-check-{int(time.time())}"
s, _ = call("POST", f"/api/v2/dags/{DAG}/dagRuns", token,
            {"dag_run_id": run, "logical_date": None, "conf": {"items": 100, "shards": 1}})
expect("trigger run", s, {200, 201})
state = None
for _ in range(60):
    _, d = call("GET", f"/api/v2/dags/{DAG}/dagRuns/{run}", token)
    state = d.get("state")
    if state in ("success", "failed"):
        break
    time.sleep(6)
expect("run state", state, {"success"})
s, d = call("GET", f"/api/v2/dags/{DAG}/dagRuns/{run}/taskInstances/total/xcomEntries/return_value", token)
expect("read xcom", s, {200}); expect("xcom value", str(d.get("value")), {"328350"})
for name, path in [("connections", "/api/v2/connections"), ("variables", "/api/v2/variables"),
                   ("configuration", "/api/v2/config")]:
    s, _ = call("GET", path, token)
    expect(f"denied: {name}", s, {403})
print("failures:", fails)
