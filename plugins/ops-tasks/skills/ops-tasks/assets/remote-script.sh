#!/usr/bin/env bash
# Purpose:    <what the helper does on the remote system, in one line>
# Usage:      ssh -o BatchMode=yes -o ConnectTimeout=10 <host> 'bash -s -- [--apply]' < NN-verb-object.sh
#                 <dry run without --apply; drop --apply for read-only helpers; 'sudo bash -s' for root>
#             NN-verb-object.sh --test   on the operator's machine only: run the offline self-tests
# Effect:     <read-only | changes: what it changes on the remote system; dry run unless --apply>
# Runs on:    remote: <ID from PLAN.md "## Connections"> (<OS, bash version, user>)
# Connection: <the same ID; add any system the helper calls from there>
# Exit:       0 done, 1 a check or action failed, 2 wrong arguments, wrong system, missing tool or
#             failed precondition, 124 a command hit its time limit (when the helper passes that code on).
#
# A remote helper runs on a system from PLAN.md "## Connections", which has no <ops-dir>/tasks/lib/
# and no env file: it sources nothing and needs only the tools there. Everything below sits in one
# { ... } block. Bash reads the whole block before it runs any of it, so a cut-off file runs nothing.
{
set -euo pipefail

HOSTS="<host name>"   # the exact `uname -n` values this helper may run on, space-separated
TOOLS="timeout uname" # every tool the helper calls; add the ones you use
TIMEOUT=60            # seconds per command, used by run; for one longer command: TIMEOUT=600 run ...

# Run a command that can hang (service or package manager, mount, network call) with a time limit
# and no stdin. timeout is from GNU coreutils; it returns 124 when the limit is hit. A limit of 0
# means no limit, so TIMEOUT must stay above 0. Stopping the local ssh does not stop this helper
# on the remote system; only these limits do.
run() { timeout -k 5 "$TIMEOUT" "$@" </dev/null; }

main() {
  local apply=0 lib tool host h ok=0
  [[ $# -le 1 ]] || { echo "Too many arguments: use one of --apply, --test" >&2; exit 2; }
  case "${1:-}" in
    --test)   # finds the runner through this file's path, so it works only in the task folder
      lib="$(cd "$(dirname "$0")/../../lib" 2>/dev/null && pwd)" && [[ -f "$lib/stubtest.py" ]] ||
        { echo "--test runs on the operator's machine only, from the task's scripts/ folder" >&2; exit 2; }
      exec python3 "$lib/stubtest.py" "$0" ;;
    --apply) apply=1 ;;
    "") ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac

  for tool in $TOOLS; do
    command -v "$tool" >/dev/null || { echo "Missing on this system: $tool" >&2; exit 2; }
  done

  # Target: before any other command, check that this is the system named for this helper in
  # PLAN.md "## Connections". Compare the whole name, never a substring: web01.example.com.evil.net
  # contains web01.example.com. uname -n reads the local name; hostname -f can hang on a DNS lookup.
  host="$(uname -n)"
  for h in $HOSTS; do
    if [[ "$host" == "$h" ]]; then ok=1; fi
  done
  ((ok)) || { echo "Wrong system: see the Connections entry in PLAN.md" >&2; exit 2; }

  # Call each command that can hang through run, and stub timeout in scripts/tests/<helper>.json:
  # state="$(run systemctl is-active app)" || true    # is-active exits 3 for an inactive unit
  # run curl -fsS --max-time 10 http://127.0.0.1:8080/health >/dev/null

  # 1. Check the precondition (read-only). Exit 2 with the reason when it fails.
  # 2. Show the exact system and action. Never print credentials.
  echo "System: $host. Action: <what --apply would do>."
  if ((apply == 0)); then
    echo "Dry run: no change. Run again with --apply to make the change."
    exit 0
  fi
  # 3. Re-check the precondition, make the change, then verify it and exit 1 if the check fails.
}

main "$@"
exit
}
