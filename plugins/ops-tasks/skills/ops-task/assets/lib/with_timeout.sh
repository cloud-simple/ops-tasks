#!/usr/bin/env bash
# ops-task lib, installed by tasks.py init from the ops-task plugin (skills/ops-task/assets/lib/).
# Edit it in the plugin repo, not here: tasks.py init overwrites this file.
# Purpose: with_timeout, a time limit for one command and every process it starts.
# Usage:   source "$LIB/with_timeout.sh"; TIMEOUT=60; with_timeout govc about   (LIB is <ops-dir>/tasks/lib)
#          <ops-dir>/tasks/lib/with_timeout.sh --test     run the self-tests
# Effect:  read-only. The self-tests start and stop local sleep and cat processes only.
# Runs on: the Mac, with bash 3.2 or later (macOS /bin/bash and Homebrew bash).
# Exit:    the command's exit code, or 124 when the time limit was hit.
#
# How it works: the command runs in its own process group. After $TIMEOUT seconds the whole
# group gets TERM, 2 seconds later KILL. When the command ends in time, processes it left
# in its group are killed too, so they cannot hold a pipe open. Standard input is passed on.

# Every cleanup step tolerates processes that are already gone, so the function also works
# when the caller runs with `set -e`.
with_timeout() {
  local pid watcher rc=0 flag monitor=0
  [[ $- == *m* ]] && monitor=1
  flag=$(mktemp "${TMPDIR:-/tmp}/with_timeout.XXXXXX")
  set -m                                     # background jobs get their own process groups
  "$@" <&0 &                                 # keep stdin, so a pipe into with_timeout reaches the command
  pid=$!
  # The watcher gets its own group too, so killing that group also kills its sleep.
  (
    sleep "${TIMEOUT:-60}"
    kill -0 "$pid" 2>/dev/null || exit 0
    rm -f "$flag"                            # a missing flag file means "timed out"
    kill -TERM -- "-$pid" 2>/dev/null
    sleep 2
    kill -KILL -- "-$pid" 2>/dev/null
  ) </dev/null >/dev/null 2>&1 &
  watcher=$!
  ((monitor)) || set +m                      # restore the caller's monitor setting
  { wait "$pid" || rc=$?; } 2>/dev/null      # hide the shell's "Killed: 9" job message
  kill -KILL -- "-$watcher" 2>/dev/null || true   # the watcher and its sleep; may be gone already
  { wait "$watcher" || true; } 2>/dev/null
  kill -KILL -- "-$pid" 2>/dev/null || true  # descendants still in the command's group
  if [[ -e "$flag" ]]; then
    rm -f "$flag" || true
    return "$rc"
  fi
  return 124
}

_with_timeout_self_test() {
  local failed=0 t0 out rc me procs long
  _check() { if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; failed=$((failed + 1)); fi; }
  TIMEOUT=1
  me="${BASH_SOURCE[0]}"
  long="30.$$"   # a sleep length unique to this run, so the leftover check sees only our processes

  rc=0; bash -c 'set -euo pipefail; source "$1"; TIMEOUT=0.3; with_timeout bash -c "trap \"\" TERM; sleep 8"; echo unreachable' _ "$me" >/dev/null 2>&1 || rc=$?
  _check "under set -e a timeout returns 124 to the caller" '[[ $rc -eq 124 ]]'

  rc=0; out=$(bash -c 'set -euo pipefail; source "$1"; TIMEOUT=5; with_timeout true; echo reached' _ "$me" 2>&1) || rc=$?
  _check "under set -e a fast command continues the caller" '[[ $rc -eq 0 && $out == reached ]]'

  out=$(bash -c 'set -m; source "$1"; with_timeout true; [[ $- == *m* ]] && echo on || echo off' _ "$me" 2>/dev/null)
  _check "the caller's monitor setting is kept" '[[ $out == on ]]'
  out=$(bash -c 'source "$1"; with_timeout true; [[ $- == *m* ]] && echo on || echo off' _ "$me" 2>/dev/null)
  _check "monitor stays off when it was off" '[[ $out == off ]]'

  rc=0; with_timeout true || rc=$?
  _check "fast command keeps exit 0" '[[ $rc -eq 0 ]]'

  rc=0; with_timeout bash -c 'exit 3' || rc=$?
  _check "failing command keeps its exit code" '[[ $rc -eq 3 ]]'

  t0=$SECONDS; rc=0; with_timeout bash -c "trap '' TERM; sleep $long" || rc=$?
  _check "TERM-resistant command is killed, exit 124" '[[ $rc -eq 124 && $((SECONDS - t0)) -le 6 ]]'

  t0=$SECONDS; rc=0; out=$(with_timeout bash -c "sleep $long & sleep $long") || rc=$?
  _check "child holding stdout is killed, exit 124" '[[ $rc -eq 124 && $((SECONDS - t0)) -le 6 ]]'

  t0=$SECONDS; rc=0; out=$(with_timeout bash -c "sleep $long & echo done") || rc=$?
  _check "leftover child after a fast exit does not block" '[[ $rc -eq 0 && $out == done && $((SECONDS - t0)) -le 2 ]]'

  out=$(echo payload | with_timeout cat)
  _check "piped input reaches the command" '[[ $out == payload ]]'

  out=$(printf 'a\nb\nc\n' | { n=0; while read -r _ <&3; do with_timeout true; n=$((n + 1)); done 3<&0; echo "$n"; })
  _check "loop on fd 3 keeps all its input" '[[ $out == 3 ]]'

  sleep 0.5
  # Look only for this run's sleep length, and fail when the process list cannot be read.
  if procs=$(ps -U "$(id -u)" -o command= 2>/dev/null); then
    _check "no process started by these tests is left" '! grep -qx "sleep $long" <<<"$procs"'
  else
    echo "FAIL no process started by these tests is left: cannot read the process list"
    failed=$((failed + 1))
  fi

  return $((failed > 0))
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    --test) _with_timeout_self_test; exit $? ;;
    *) echo "Usage: source $0, or run $0 --test" >&2; exit 2 ;;
  esac
fi
