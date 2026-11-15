#!/usr/bin/env bash
set -euo pipefail

if (( $# < 1 || $# > 2 )); then
  echo "Usage: bash scripts/verify_envoy_udp_poc.sh <context> [previous-ready-pod-uid]" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context=$1
k() { kubectl --context "$context" --request-timeout=10s -n envoy-gateway-system "$@"; }

python3 "$root/scripts/preflight_envoy_udp_pool.py" "$context" --check-gateway

gateway=$(k get gateway factorio -o json)
route=$(k get udproute factorio -o json)

jq -e '
  def current($generation; $type):
    any(.[]?; .type == $type and .status == "True" and .observedGeneration == $generation);
  .metadata.generation as $g |
  (.status.conditions | current($g; "Programmed")) and
  any(.status.listeners[]?; .name == "game" and
      (.attachedRoutes // 0) == 1 and (.conditions | current($g; "Programmed")))
' >/dev/null <<< "$gateway" || { echo "Current Gateway/listener is not programmed." >&2; exit 1; }

jq -e '
  def current($generation; $type):
    any(.[]?; .type == $type and .status == "True" and .observedGeneration == $generation);
  .metadata.generation as $g |
  any(.status.parents[]?; .controllerName == "gateway.envoyproxy.io/gatewayclass-controller" and
      .parentRef.name == "factorio" and .parentRef.sectionName == "game" and
      (.conditions | current($g; "Accepted") and current($g; "ResolvedRefs")))
' >/dev/null <<< "$route" || { echo "Current UDPRoute is not accepted with resolved references." >&2; exit 1; }

address=$(jq -er '[.status.addresses[]? | select(.type == "IPAddress" and (.value | contains(":") | not))] |
  if length == 1 then .[0].value else error("expected one advertised IPv4 address") end' <<< "$gateway")
pod_uid() {
  k get pods -l app.kubernetes.io/name=envoy-udp-echo -o json | jq -er '
    [.items[] | select(.metadata.deletionTimestamp == null and
      any(.status.conditions[]?; .type == "Ready" and .status == "True"))] |
    if length == 1 then .[0].metadata.uid else error("expected exactly one ready echo Pod") end'
}
uid=$(pod_uid)
if [[ -n "${2:-}" && "$uid" == "$2" ]]; then
  echo "Replacement check failed: the previous echo Pod is still serving." >&2
  exit 1
fi

python3 "$root/scripts/probe_envoy_udp_poc.py" "$address"
if [[ "$(pod_uid)" != "$uid" ]]; then
  echo "The echo Pod changed during the probe; repeat the check." >&2
  exit 1
fi
printf 'echo_pod_uid=%s\n' "$uid"
