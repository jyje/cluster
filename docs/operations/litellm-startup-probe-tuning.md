# LiteLLM Startup Probe Tuning on ARM64 Nodes

## Overview

LiteLLM proxy uses FastAPI + Prisma ORM. On startup, it must:
1. Bind the FastAPI port (fast)
2. Connect to PostgreSQL and run Prisma client initialization (slow)

On resource-constrained ARM64 nodes (e.g. Raspberry Pi), step 2 can take
significantly longer than on x86 or higher-end ARM boards — long enough to
exceed default or naively-tuned startup probe budgets.

| Item | Value |
|------|-------|
| Date | 2026-06-06 |
| Affected app | LiteLLM proxy |
| Helm chart | `ghcr.io/berriai/litellm` |
| Environment | Kubernetes on ARM64 (mixed RPi4 / RPi5 nodes) |

---

## Symptom

Pods kept failing startup probe and restarting (`CrashLoopBackOff`-like cycle
via `failureThreshold` exhaustion) on slower ARM64 nodes, while the same image
started successfully on faster nodes.

During the startup window, inference requests routed to the pod resulted in
**pending / dropped responses** — the port was not yet bound, so TCP connections
were refused.

---

## Root Cause Analysis

### Startup timeline (observed)

```
t=0s    Container starts
t=0-Xs  FastAPI process launches, Prisma initializes DB connection
t=Xs    Port 4000 binds — /health/readiness begins responding
t=Xs+   Startup probe passes, readiness probe takes over
```

`X` varies significantly by hardware:

| Node type | Observed startup time |
|-----------|----------------------|
| RPi5 (ARM Cortex-A76) | ~60–70 s |
| RPi4 (ARM Cortex-A72) | ~130–150 s |

The port stays **closed** (connection refused) for the entire startup window.
A startup probe that fires during this time will see `connection refused`, not
a non-200 HTTP response — meaning `timeoutSeconds` is irrelevant until the port
opens; only `initialDelaySeconds + failureThreshold × periodSeconds` (total
budget) matters.

### Default chart values (insufficient for RPi4)

```yaml
startupProbe:
  path: /health/readiness
  initialDelaySeconds: 0
  periodSeconds: 10
  timeoutSeconds: 1
  failureThreshold: 30     # budget: 0 + 30×10 = 300s  ← OK
```

The default 300 s budget is fine, but `timeoutSeconds: 1` means a slow DB
health response can fail the probe even after the port opens.

### Tightened values that caused failures

An intermediate tuning attempt used aggressive values to reduce detection
latency:

```yaml
startupProbe:
  initialDelaySeconds: 30
  periodSeconds: 5
  timeoutSeconds: 10
  failureThreshold: 18     # budget: 30 + 18×5 = 120s  ← too tight for RPi4
```

RPi4 needed ~146 s → exhausted the 120 s budget → pod killed → restarted.

---

## Solution

Preserve the generous total budget (≥ 300 s), but fix `timeoutSeconds` so slow
DB responses don't cause false failures after the port opens:

```yaml
startupProbe:
  path: /health/readiness
  initialDelaySeconds: 60    # skip first 60s entirely — port won't open anyway
  periodSeconds: 10
  timeoutSeconds: 10         # allow DB health check to respond slowly
  successThreshold: 1
  failureThreshold: 24       # budget: 60 + 24×10 = 300s

readinessProbe:
  path: /health/readiness
  initialDelaySeconds: 0
  periodSeconds: 10
  timeoutSeconds: 5          # raised from 1s — same reason as above
  successThreshold: 1
  failureThreshold: 3
```

### Why `initialDelaySeconds: 60`

Probing during the "port closed" phase wastes failure budget without providing
useful signal. Skipping 60 s means no budget is consumed before the port has
any chance of opening, even on RPi4.

### Rolling update settings

To ensure zero downtime while slow nodes start up:

```yaml
replicaCount: 2

strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0    # never kill old pod until new pod is Ready
    maxSurge: 1          # allow one extra pod during transition

deploymentMinReadySeconds: 15   # extra stabilization after readiness passes
```

`maxUnavailable: 0` is critical: the old pod stays in service for the full
~150 s that a RPi4 needs to become ready.

---

## Validation

A monitoring script is provided at `scripts/validate-litellm.py`. It:

- `kubectl port-forward`s the service locally
- Polls `/health/readiness` every 0.5 s with timestamps
- Watches pod status changes and k8s events in parallel threads
- Optionally fires inference requests every 30 s (pass `--api-key`)
- Prints an availability summary on exit (Ctrl+C)

```bash
# health-only
python3 scripts/validate-litellm.py

# with inference test
python3 scripts/validate-litellm.py --api-key <LITELLM_MASTER_KEY>
```

### Observed rollout with fixed settings

```
09:15:43  litellm-...-txrpx  starts (raspi — RPi4)
09:16:49  startup probe begins (60 s delay elapsed), connection refused
09:18:09  ✅ Ready  (146 s total)

09:18:25  old pod terminates (maxUnavailable=0 held it until new pod was Ready)
09:18:28  litellm-...-jsr2w  starts (raspi — RPi5)
09:19:36  ✅ Ready  (71 s total)

Service health: 100% availability throughout rollout
```

---

## Key Takeaways

1. **Startup budget = `initialDelaySeconds + failureThreshold × periodSeconds`.**
   Reducing `periodSeconds` to "detect faster" eats into the total budget.
   On slow nodes, preserve total budget ≥ longest expected startup time × 1.5.

2. **`timeoutSeconds` matters after the port opens.**
   LiteLLM's `/health/readiness` checks the DB connection; on a loaded cluster
   this can take several seconds. `timeoutSeconds: 1` will cause spurious
   failures even when the app is healthy.

3. **`maxUnavailable: 0` is mandatory when startup is slow.**
   Without it, a rolling update will briefly remove a ready pod before the
   replacement is ready, causing a real outage window.

4. **Different node generations have meaningfully different startup times.**
   Mixed-generation clusters should tune probes for the *slowest* node class.
