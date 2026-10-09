#!/usr/bin/env bash
# Weekly watcher: compare the declared MicroK8s track with the Snap Store and, when a
# newer stable track exists, open or update one pull request that proposes it.
# It records the approved target only. It never touches the cluster.
#
# Environment: LEDGER (default clusters/r4spi/microk8s-track.yaml), ISSUE (tracking
# issue, default 158), DRY_RUN=1 to print the actions instead of running them.
# Needs: gh (authenticated), git, curl, python3. Run from the repository root.
set -euo pipefail

LEDGER=${LEDGER:-clusters/r4spi/microk8s-track.yaml}
ISSUE=${ISSUE:-158}
BRANCH=automation/microk8s-track
DRY_RUN=${DRY_RUN:-0}
HERE=$(cd "$(dirname "$0")" && pwd)

run() { if [ "$DRY_RUN" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }

track=$(sed -n 's/^track:[[:space:]]*"\{0,1\}\([0-9][0-9.]*\)"\{0,1\}[[:space:]]*$/\1/p' "$LEDGER" | head -1)
[ -n "$track" ] || { echo "no track found in $LEDGER" >&2; exit 2; }

report=$("$HERE/check.sh" --track "$track")
echo "$report"
verdict=$(sed -n 's/^VERDICT: //p' <<<"$report")
next=$(sed -n 's/^NEXT_TRACK: //p' <<<"$report")

case "$verdict" in
  UP_TO_DATE|PATCH_AVAILABLE) echo "Nothing to do."; exit 0 ;;
  UNKNOWN) echo "Could not decide. Failing so the run is visible." >&2; exit 1 ;;
  NEW_MINOR_ANNOUNCED_NOT_IN_STORE)
    marker="<!-- microk8s-watch: announced $next -->"
    if gh issue view "$ISSUE" --json comments -q '.comments[].body' | grep -qF "$marker"; then
      echo "Already noted v$next on issue #$ISSUE."; exit 0
    fi
    body="$marker
MicroK8s v$next is announced on GitHub but has no stable snap for the cluster architecture yet. Nothing to upgrade. The weekly check will open a pull request when the track appears in the Snap Store."
    run gh issue comment "$ISSUE" --body "$body"
    exit 0 ;;
  NEW_MINOR_AVAILABLE) ;;
  *) echo "unexpected verdict: $verdict" >&2; exit 1 ;;
esac

# NEW_MINOR_AVAILABLE: propose the track in one pull request.
title="🔭 chore(microk8s): propose MicroK8s track $next"
body=$(cat <<BODY
## What

The Snap Store now has a stable MicroK8s **$next** track for the cluster architecture. The recorded track is **$track**. This pull request proposes recording **$next**.

## Merging means approval

\`$LEDGER\` is a ledger. Merging it **does not upgrade anything**. It records that the upgrade to $next is approved. The nodes are upgraded one at a time by hand afterward, and nothing here drains or restarts a node.

## Before the upgrade

Follow the checklist in the \`microk8s-release-watch\` skill and the upgrade issue #$ISSUE:

- [ ] Read the final Kubernetes and MicroK8s $next release notes (removed APIs, changed defaults, removed addons)
- [ ] Re-run the read-only checks recorded in #$ISSUE
- [ ] Check chart and operator compatibility for the platform components
- [ ] All Applications Synced and Healthy, all nodes Ready, fresh private backup, maintenance window agreed
- [ ] Independent cooling recovery ready for the node that drives the shared fan
- [ ] Upgrade one node at a time (drain, refresh, uncordon, verify) and re-verify strict TLS and pifanctl

## Check output

\`\`\`text
$report
\`\`\`

Opened by the weekly \`microk8s track watch\` workflow. Closing this pull request without merging keeps the recorded track.
BODY
)

existing=$(gh pr list --head "$BRANCH" --state open --json number -q '.[0].number // empty')
run git config user.name "github-actions[bot]"
run git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
run git switch -C "$BRANCH"
if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] set track: \"$next\" in $LEDGER"
else
  sed -i.bak "s/^track:.*/track: \"$next\"/" "$LEDGER" && rm -f "$LEDGER.bak"
fi
run git add "$LEDGER"
run git commit -m "🔭 chore(microk8s): propose MicroK8s track $next"
run git push --force-with-lease origin "$BRANCH"
if [ -n "$existing" ]; then
  run gh pr edit "$existing" --title "$title" --body "$body"
else
  run gh pr create --base main --head "$BRANCH" --title "$title" --body "$body"
fi
