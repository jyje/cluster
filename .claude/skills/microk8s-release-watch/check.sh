#!/usr/bin/env bash
# Lightweight MicroK8s release check: two read-only HTTP calls, no credentials.
#   1. GitHub releases of canonical/microk8s (one entry per minor release)
#   2. Snap Store channel map (the source that actually gates `snap refresh`)
# Cluster versions come from kubectl when reachable, else pass --current vX.Y.Z.
# Prints versions only. Never prints node names, addresses or credentials.
set -uo pipefail

ARCH=arm64
CONTEXT=microk8s
CURRENT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH=$2; shift 2 ;;
    --context) CONTEXT=$2; shift 2 ;;
    --current) CURRENT=$2; shift 2 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

for tool in curl python3; do
  command -v "$tool" >/dev/null || { echo "need $tool" >&2; exit 2; }
done

# MICROK8S_RELEASES_JSON and MICROK8S_STORE_JSON point to saved responses for offline tests.
if [ -n "${MICROK8S_RELEASES_JSON:-}" ]; then github=$(cat "$MICROK8S_RELEASES_JSON"); else
  github=$(curl -fsS --max-time 15 -H 'Accept: application/vnd.github+json' \
    'https://api.github.com/repos/canonical/microk8s/releases?per_page=5' 2>/dev/null) || github='[]'
fi
if [ -n "${MICROK8S_STORE_JSON:-}" ]; then store=$(cat "$MICROK8S_STORE_JSON"); else
  store=$(curl -fsS --max-time 15 -H 'Snap-Device-Series: 16' \
    'https://api.snapcraft.io/v2/snaps/info/microk8s?fields=version' 2>/dev/null) || store='{}'
fi

if [ -z "$CURRENT" ] && command -v kubectl >/dev/null; then
  CURRENT=$(kubectl --context "$CONTEXT" --request-timeout=10s get nodes \
    -o jsonpath='{range .items[*]}{.status.nodeInfo.kubeletVersion}{"\n"}{end}' 2>/dev/null | sort -V | head -1)
fi

GITHUB="$github" STORE="$store" ARCH="$ARCH" CURRENT="$CURRENT" python3 - <<'PY'
import json, os, re

def ver(text):
    match = re.match(r'v?(\d+)\.(\d+)(?:\.(\d+))?', text or '')
    return tuple(int(part or 0) for part in match.groups()) if match else None

def fmt(v):
    return 'v%d.%d.%d' % v if v else 'unknown'

try: releases = json.loads(os.environ['GITHUB'])
except ValueError: releases = []
try: channels = json.loads(os.environ['STORE']).get('channel-map', [])
except ValueError: channels = []
arch, current = os.environ['ARCH'], ver(os.environ['CURRENT'])

github_minors = sorted({ver(r['tag_name'])[:2] for r in releases
                        if not r.get('prerelease') and ver(r.get('tag_name'))})
stable = {}  # minor -> newest stable version string for this architecture
for entry in channels:
    channel = entry.get('channel', {})
    if channel.get('architecture') != arch or channel.get('risk') != 'stable': continue
    if channel.get('track', '').endswith('-strict') or channel.get('track') == 'latest': continue
    v = ver(entry.get('version'))
    if v: stable[v[:2]] = max(stable.get(v[:2], v), v)

print('MicroK8s release check (%s)' % arch)
if github_minors:
    latest = github_minors[-1]
    published = next((r['published_at'][:10] for r in releases if ver(r['tag_name']) and ver(r['tag_name'])[:2] == latest), '?')
    print('  GitHub latest minor release : v%d.%d (published %s)' % (latest[0], latest[1], published))
else:
    latest = None
    print('  GitHub latest minor release : unavailable')
newest = sorted(stable)[-3:]
for minor in newest: print('  Snap Store stable v%d.%d     : %s' % (minor[0], minor[1], fmt(stable[minor])))
if not stable: print('  Snap Store                  : unavailable')
print('  Cluster (oldest node)       : %s' % fmt(current))

verdict, note = 'UNKNOWN', 'Could not read enough data. Check the network and rerun.'
if current and stable:
    same = stable.get(current[:2])
    newer_minors = [m for m in stable if m > current[:2]]
    if newer_minors:
        verdict, note = 'NEW_MINOR_AVAILABLE', 'Stable track v%d.%d is in the Snap Store. Start the upgrade checklist.' % max(newer_minors)
    elif latest and latest > current[:2]:
        verdict, note = 'NEW_MINOR_ANNOUNCED_NOT_IN_STORE', 'v%d.%d is announced on GitHub but has no stable %s snap yet. Nothing to upgrade.' % (latest[0], latest[1], arch)
    elif same and same > current:
        verdict, note = 'PATCH_AVAILABLE', '%s is the newest stable patch of the current track. The snap refresh schedule applies it.' % fmt(same)
    else:
        verdict, note = 'UP_TO_DATE', 'Nodes run the newest stable patch of the newest track.'
print('VERDICT: %s' % verdict)
print(note)
PY
