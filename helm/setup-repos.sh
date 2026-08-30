#!/usr/bin/env bash
# Configure the local `helm repo` list to match the canonical Group | Provider | URL
# table in README.md — the single source of truth for where each vendored chart
# comes from.
#
# Why this exists: `helm repo add` state lives only on the machine that runs it.
# Nothing in this repository enforced it, so a stale or wrong local alias (e.g.
# pointing "sealed-secrets" at a provider URL that later 404s) could silently
# persist for one contributor while README.md already had the correct URL —
# see #85. Running this script is the fix: it reads README.md itself, so the
# table and the actual `helm repo` config can never drift apart again.
#
# Usage:
#   ./helm/setup-repos.sh
#
# Safe to re-run any time (e.g. after pulling a README.md update, or if you
# suspect your local Helm repo config has drifted).

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readme="${script_dir}/README.md"

if [[ ! -f "$readme" ]]; then
  echo "error: $readme not found" >&2
  exit 1
fi

added=0
skipped=0

# Parse table rows of the form "| group | provider | url ... |". Skip the
# header/separator rows, OCI-only providers (no `helm repo add` concept),
# and providers explicitly marked as having no external Helm repo.
while IFS='|' read -r _ _group _provider _rest; do
  provider="$(echo "$_provider" | xargs)"
  rest="$(echo "$_rest" | xargs)"
  # The URL is always the first whitespace-delimited token in the remaining
  # cell; anything after it is a parenthetical note, not part of the URL.
  url="$(echo "$rest" | awk '{print $1}')"

  [[ -z "$provider" || "$provider" == "Provider" || "$provider" == "---"* ]] && continue
  [[ "$provider" == "—" ]] && continue
  [[ "$url" == oci://* ]] && continue
  [[ -z "$url" || "$url" != http* ]] && continue
  # A row can carry a real http(s) URL that isn't actually an installable
  # Helm repo (e.g. a plain GitHub project page for a custom chart wrapper).
  [[ "$rest" == *"no official Helm repo"* || "$rest" == *"no external Helm repo"* || "$rest" == *"custom Helm wrapper"* ]] && continue

  if helm repo add "$provider" "$url" --force-update >/dev/null 2>&1; then
    echo "added:   $provider -> $url"
    added=$((added + 1))
  else
    echo "FAILED:  $provider -> $url" >&2
    skipped=$((skipped + 1))
  fi
done < <(grep -E '^\| ' "$readme")

echo
echo "Configured $added repo(s)."
if [[ "$skipped" -gt 0 ]]; then
  echo "warning: $skipped repo(s) failed to add — check the URLs above" >&2
  exit 1
fi

helm repo update
