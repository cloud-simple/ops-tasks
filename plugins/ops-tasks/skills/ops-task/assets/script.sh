#!/usr/bin/env bash
# Purpose:    <what the helper does, in one line>
# Usage:      NN-verb-object.sh [--apply]    <dry run without --apply; drop --apply for read-only helpers>
#             NN-verb-object.sh --test       run the offline self-tests (no infrastructure access)
# Effect:     <read-only | changes: what it changes; dry run unless --apply>
# Runs on:    <where it runs, for example the operator's workstation or a jump host>
# Connection: <ID from PLAN.md "## Connections", for example "vc (repo .env)">
# Exit:       0 done, 1 a check or action failed, 2 wrong arguments, wrong target or failed precondition,
#             124 a call hit its time limit (when the helper passes that code on).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"

APPLY=0
[[ $# -le 1 ]] || { echo "Too many arguments: use one of --apply, --test" >&2; exit 2; }
case "${1:-}" in
  --test) exec python3 "$REPO/tasks/lib/stubtest.py" "$0" ;;   # before any setup or credentials
  --apply) APPLY=1 ;;
  "") ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac

TIMEOUT="${OPS_TIMEOUT:-60}"   # seconds per call, used by with_timeout
# shellcheck source=../../lib/with_timeout.sh
source "$REPO/tasks/lib/with_timeout.sh"

# Uncomment only if the Connections entry of this helper names the repo .env:
# shellcheck disable=SC1090
# source "${OPS_ENV_FILE:-$REPO/.env}"

# Target: before any call, check that this helper talks to the system named for it in
# PLAN.md "## Connections". Compare exactly, never as a substring, and never print the
# rejected value: it can hold credentials. Pick the check that fits, delete the others:
#   URL:                 parse the host, then compare it, for example
#                        [[ "${API_URL:-}" =~ ^https://([A-Za-z0-9.-]+)(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$ ]] &&
#                        [[ "$(printf '%s' "${BASH_REMATCH[1]}" | tr 'A-Z' 'a-z')" == "<host name>" ]]
#   SSH host:            [[ "${TARGET_HOST:-}" == "<host name>" ]]
#   Kubernetes context:  [[ "$(kubectl config current-context)" == "<context name>" ]]
target_ok() {
  false   # replace with one of the checks above
}
target_ok || { echo "Wrong target: see the Connections entry in PLAN.md" >&2; exit 2; }

# Wrap every network tool the helper calls, so each call has a time limit and no stdin (it could
# swallow a typed secret or a loop's list). Keep only what you need,
# and give each wrapped tool a stub in scripts/tests/<helper>.json.
# g()   { with_timeout govc "$@" </dev/null; }                               # VMware vSphere
# k()   { with_timeout kubectl --request-timeout=30s "$@" </dev/null; }
#       # Kubernetes: --request-timeout limits each API request; with_timeout caps the whole command
#       # (several requests, watches, credential plugins).
# api() { curl -sS --fail --connect-timeout 10 --max-time 30 "$@"; }         # HTTP API; curl has its own limits
# rsh() { with_timeout ssh -n -o BatchMode=yes -o ConnectTimeout=10 "$@"; }  # remote shell; -n: no stdin

# 1. Check the precondition (read-only). Exit 2 with the reason when it fails.
# 2. Show the exact target and action. Never print credentials.
echo "Target: <object>. Action: <what --apply would do>."
if ((APPLY == 0)); then
  echo "Dry run: no infrastructure change. Run again with --apply to make the change."
  exit 0
fi
# 3. Re-check the precondition, make the change, then verify it and exit 1 if the check fails.
