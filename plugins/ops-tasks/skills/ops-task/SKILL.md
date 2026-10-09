---
name: ops-task
description: Create, plan, run and record infrastructure operations tasks kept as tasks/NN-slug/ folders with TODO.md (problem and ideas), PLAN.md (checked steps with exact commands and before/after checks) and scripts/ (numbered helpers with offline --test). Use it whenever the user starts a new operations task, asks for a plan or runbook, wants to tick or record a step that was done, adds or changes a helper script under tasks/, asks for the status of the tasks, or wants the task folders checked or brought into shape, even when they do not name the skill.
---

# Operations tasks

Each operations task lives in one folder with the same three parts.

```
.env                 settings and credentials of the default connection; created by the user, git-ignored
tasks/
  NN-slug/
    TODO.md          problem, ideas, status
    PLAN.md          steps with exact commands, checks and results
    scripts/         optional: exists once the task has a helper
      NN-verb-object.sh          helper, numbered by creation order in this task
      tests/NN-verb-object.json  offline test cases for the helper
      tests/testdata/            fake fixtures for the tests
    out/             captured state, one folder per run (git-ignored)
  lib/               installed from this skill's assets/lib/ by `tasks.py init`; edit the skill, not this copy
    stubtest.py      shared offline test runner for the helpers
    with_timeout.sh  shared time limit for one command and every process it starts
```

- `NN` is two digits, the next free number. `slug` is lowercase words joined by hyphens.
- Create each task with `tasks.py new <slug> --title "<Title>"`, not by hand. Commands: see Workflow.
- Write in plain language: short sentences, active voice, one term per item, `must` for requirements.

## TODO.md: the problem and the ideas

TODO.md stays short. It answers "what is wrong, and what could we do". Facts and procedures go to PLAN.md; a TODO.md that grows commands has turned into a runbook again.

Required, in this order:

1. `# Title`
2. `Status: <open | planned | in progress | done | dropped> (since YYYY-MM-DD)`. This line is the authoritative task status. Change it when the state changes.
3. `Deadline: YYYY-MM-DD` or `Deadline: none`, and `Plan: [PLAN.md](PLAN.md)`.
4. `## Problem`: 2 to 5 sentences. What is wrong, what it affects, and by when it must be fixed.
5. `## Ideas`: one line per idea with its trade-off, marked **Chosen**, **Rejected: reason**, or **Open**. Keep ideas that were rejected; they explain the plan.
6. `## Links` (optional): related tasks, tickets, documents.

Template: [assets/TODO.md](assets/TODO.md).

## PLAN.md: the steps

PLAN.md is the working record. Someone else must be able to run it, and to see afterwards what was done.

Required headings: `## Goal`, `## Stop conditions`, `## Rollback`, `## Log`. Usually also `## Facts`, `## Connections`, `## Steps` and `## Not used`. Template: [assets/PLAN.md](assets/PLAN.md).

- **Facts:** the current value of each fact the steps rely on, with when it was checked (date, time, zone), how, and when to check it again. Older values move to the Log. Before resuming a paused task or entering a change window, re-check the facts the next steps rely on.
- **Goal:** a goal that must hold over time ("stays below X") names a finite acceptance period and who monitors it afterwards.
- **Connections:** one row per system the task talks to: where its settings and its credentials come from, and which terminal or helper uses it.

### Steps

Number steps `N.M`: `N` is the phase, `M` the step in it; never renumber a step that ran. Keep all steps under `## Steps`, or, for a long plan, replace it with `## Phase N: <title>` sections, each opening with one line on when it runs and what it needs (window, downtime, gate). Inside `## Phase N`, step IDs start with `N.`.

For a step that changes infrastructure, use three parts:

- **Before** (read-only): the exact commands that show the current state, and the expected result.
- **Do:** each action as a checkbox, with the exact command and a short comment per line. Mark commands that cannot be undone. Some commands only start a job that keeps running after they return, for example a clone or a backup. Word such a box as what you did ("Start the clone task"), tick it when the job was accepted, and let the After check confirm that the job finished and succeeded.
- **After** (read-only: no infrastructure change; local evidence files and read-only sessions are fine): the exact commands that show the new state, the expected result, and one box `- [ ] After check passed.` with the step's Result under it.

A decision, a phone call or a ticket needs one checkbox and an acceptance check. A GUI action that changes something is a changing step: Before, Do with the exact click path (**Menu → Item → Button**), After.

Shell is bash everywhere. Each terminal starts with `bash` before its first block, and plan code blocks are fenced as `bash`; other content names its language (`text`, `ini`). Put anything longer than a few commands into a helper. A hidden prompt is `read -rsp 'Password: ' VAR; echo`.

Commands must be finite. Bound how often a wait polls, and make the check after it fail with a message, so the next command does not run on a bad state:

```bash
for i in $(seq 1 30); do govc vm.info vm1 | grep -q poweredOff && break; sleep 10; done   # 30 polls, 10 s apart
govc vm.info vm1 | grep -q poweredOff || { echo "STOP: vm1 is still on after 30 polls"; false; }

for i in $(seq 1 30); do curl -fsS --max-time 10 https://app.example.test/health >/dev/null && break; sleep 10; done  # each call ≤ 10 s: ≤ 10 min
curl -fsS --max-time 10 https://app.example.test/health >/dev/null || { echo "STOP: app not healthy after 30 attempts"; false; }
```

Chain the next command with `&&`, or say to run the next block only when no `STOP` was printed. This bounds the polling. Each call is bounded only if the tool has its own limit (`curl --max-time`); otherwise the operator stops a hung call with Ctrl-C. Say so in the plan. For a hard limit, use a helper with `with_timeout`; do not source a bash library into the interactive shell.

Handle the expected non-zero exits on purpose: `grep` without a match exits 1, and `diff` exits 1 when files differ. Say what that exit means next to the command. A check for absence must fail when the read fails: capture the output first (`out=$(cmd) && ! grep -q X <<<"$out"`), never pipe a failing read into `grep`.

### Ticking and recording

- Tick an action box when the action ran without error. Tick **After check passed** only when the After check passed, and put the Result under it: `Result (YYYY-MM-DD): <measured values>`. A changing step is complete only when that box is ticked; a read-only or decision step, when its acceptance check is met.
- If the After check fails, keep the ticked actions, leave the After box open, write the outcome under it, and add a Log entry. Before re-running an action, check the current state; an open box alone is no reason to retry.
- Do not repeat a Result in the Log.
- Move an alternative or optional step that was not run to `## Not used`, with the date, the reason and its step ID. Checkboxes there do not count.

### When facts change outside the plan

- Record the change in the Log: date, measured values, the exact commands. Mark any explanation "inference, not confirmed" unless the owner (named, dated) or logs confirm it.
- Update Facts to the new value. Write "corrected" when the old value was wrong, "superseded" when the system changed. Never rewrite completed Results or baselines.
- A step whose existing acceptance criteria are now verified gets its After box ticked, with a Result citing the Log entry; its unrun actions move to `## Not used`. An action that became unnecessary without that proof is recorded as "no longer needed because …". Failed or partial actions stay where they are.
- Stop only the changing actions that depend on an unexplained change to the target's identity, data integrity, ownership of an operation in progress, capacity assumptions or a usable rollback. Write the failed precondition and the evidence needed to clear it. Read-only work continues.
- A check that cannot run means "unknown", not "unchanged". Keep external deadlines; withdraw forecasts that no longer hold, with their assumptions.
- Tell the user the facts. Ask for a new go-ahead only when the authorized scope or a step's gate requires it.

### One task or two

Start a new task for a separate deliverable with its own completion criteria, or for follow-up work that would keep the current goal open. A different owner, approval, schedule or rollback is a signal, not a reason. To split: create the task with `tasks.py new` (status `open`, no inherited deadline), move only work that has not started, leave a redirect at each moved step ID and an entry in `## Not used`, record the old-to-new step mapping in the new plan, and link both TODOs.

### Stop conditions, Rollback, Log

- **Stop conditions:** states in which the work must not start or must stop, each with a command that checks it.
- **Rollback:** for each changing step, how to undo it. Say plainly when a step cannot be undone, and name the step ID.
- **Log:** dated entries only for deviations, failed attempts, and events that span steps. Refer to step IDs.

## scripts/: helpers

Write a helper when a command sequence repeats (for example the same state check before and after a change), or when it needs parsing, a guard, or a test. A one-line command used once stays in PLAN.md.

Rules, and why:

- **Bash only:** `NN-verb-object.sh`, numbered by creation order within the task, first line `#!/usr/bin/env bash`, run directly so the shebang picks the shell. Use `jq` for JSON and `awk` or `sed` for text. Link the helper from every step that uses it.
- **Header:** `Purpose:`, `Usage:`, `Effect:` (`read-only` or `changes: ...`), `Runs on:`, `Connection:` (the Connections ID) and `Exit:` codes. Template: [assets/script.sh](assets/script.sh).
- **Connection:** a helper reads settings only from the source its Connections entry names. The repo `.env`, loaded through `${OPS_ENV_FILE:-$REPO/.env}`, holds the default connection; a helper for another connection must not load it, because it would override that connection's settings.
- **Secrets:** never in `tasks/` (plans, helpers, tests, `out/`). They live in the env file or the password manager named in Connections. Read a typed secret with a hidden prompt; never print it, and never pass it as a command-line argument when the tool has another input (environment variable, standard input, file). A tool that only takes it as an argument is a documented exception: say so in the plan; other local processes can see the argument while the command runs. Never print `.env` or show its values; to see what it holds, list the variable names only (`sed 's/=.*/=<redacted>/' .env`).
- **Target:** before any call, check that the helper talks to the system named in its Connections entry, and exit 2 if not. Compare the parsed identifier exactly (host, context, account), never as a substring: `api.example.com.evil.net` contains `api.example.com`. Never print the rejected value. The template shows checks for a URL, an SSH host and a Kubernetes context.
- **`--test` first:** handle `--test` before loading credentials or any setup.
- **Dry run by default:** a helper that changes anything prints the exact target and action and changes nothing unless given `--apply`. During `--apply` it checks the preconditions again. Unknown flags exit 2. A dry run can still open sessions or write local files; it only promises no infrastructure change.
- **Finite:** a time limit on every network call (`source "$REPO/tasks/lib/with_timeout.sh"`, then `with_timeout <tool> ...`, or the tool's own limit such as `curl --max-time`), bounded retries, a non-zero exit on failure, and a printed next step after a failure. Give network calls no stdin (`</dev/null`): a tool that reads it can swallow a typed secret or a loop's list. `with_timeout` kills the command's whole process group, keeps piped input, and returns 124 on timeout. `set -euo pipefail` is a start, not the error handling.
- **Loops:** read a list on its own descriptor (`while read -r x <&3; do ...; done 3<<<"$list"`), so a command inside the loop cannot eat the list.
- **Diagnostics:** a read-only checker runs every section, prints `ERROR: ...` for each failed read, and exits 1 at the end if anything failed. A value that was read and is bad (for example health `red`) is data, not a failed read.
- **Evidence:** write captured state to a new folder per run, `tasks/NN-slug/out/$(date +%Y%m%dT%H%M%S)/`. Set it once per session and reuse it for before/after files.
- **No hidden network paths:** never call a network tool by absolute path (`/usr/bin/curl`) and never use `/dev/tcp`; both bypass the test stubs, and `lint` rejects them.

### Testing helpers

Every helper supports `--test`. It runs offline self-tests, prints one `PASS <case>` or `FAIL <case>: <reason>` line per case, and exits non-zero if any case fails.

A helper's `--test` runs `tasks/lib/stubtest.py`: it runs the real helper once per case from `scripts/tests/<helper>.json`, with a fake `.env`, stubbed commands that record every call, and no other network tools on `PATH`. It is a controlled test environment, not a network sandbox. The environment rules and the tests file format are in the runner's header ([assets/lib/stubtest.py](assets/lib/stubtest.py)).

Cover these cases, scaled by the kind of helper:

| Helper | Required cases |
|---|---|
| read-only | success with parsed output; each read failure on its own (one case per failing source); malformed or missing data; authentication failure; wrong target, including look-alike hosts; timeout; no changing call in any case (`calls_absent_regex`) |
| changing | the read-only cases, plus: dry run makes zero changing calls; `--apply` makes exactly the expected calls (`calls`); failed precondition; partial failure |

Fixtures must use fake names, addresses and credentials (`*.test.invalid`, `not-a-real-password`).

To change the shared library: edit `assets/lib/` in this skill and run its tests (`python3 assets/lib/stubtest.py --test`, `bash assets/lib/with_timeout.sh --test`), then follow Workflow step 0.

## Workflow

0. **First use in a repo, and after each change to `assets/lib/`:** `tasks.py init` (overwrites `tasks/lib/`, lists what changed), `tasks.py lint --run-tests`, then commit `tasks/lib/`. The user creates `.env` with the default connection's settings and credentials; it must be listed in `.gitignore`.
1. **New task:** `tasks.py new <slug>`. Fill in TODO.md: the problem and the ideas. Status `open`.
   - Problem, impact, deadline, owners and constraints come from the user; ask when any of them is unclear, do not guess.
   - Ideas come from your knowledge and from documentation, each with its trade-off and, where possible, a link. The user marks an idea **Chosen** or **Rejected**; until then it stays **Open**.
2. **Plan:** collect facts with read-only commands and put them, dated, in PLAN.md, each with its command. A value you could not measure is an open question, not a fact. List the Connections. Write the steps. Set status `planned`.
3. **Run:** for each step, run Before, then Do, then After. Change infrastructure only within the scope the user authorized, and honor any gate a step names. Tick each action when it ran, and the After box when the After check passed; Results and Log entries record only what the commands showed. Set status `in progress`.
4. **Close:** `done` with the date when every active checkbox is ticked; optional steps that were not run move to `## Not used`. `dropped` with the date keeps the unticked history: write the reason in the Log, and never tick a check that did not pass.
5. **Before committing:** run the checks and fix every error.

```bash
python3 .claude/skills/ops-task/scripts/tasks.py init                 # install or update tasks/lib/ (overwrites it)
python3 .claude/skills/ops-task/scripts/tasks.py status               # status, deadline, checkbox counts
python3 .claude/skills/ops-task/scripts/tasks.py lint                 # structure, links, secrets, helpers, tasks/lib/
python3 .claude/skills/ops-task/scripts/tasks.py lint --run-tests     # also run the tests of tasks/lib/ and every helper
python3 .claude/skills/ops-task/scripts/tasks.py --test               # the tool's own tests
```

`status` shows checkbox counts as counts, not as progress. The TODO.md status line is the status.

`lint` checks the shape, step IDs and After boxes, inline local links, explicit secret patterns, helper headers and shebangs, the presence of `--test`, and that `tasks/lib/` matches the skill. It does not check reference-style links, anchors or external links. It cannot prove that no secret is present, or that tests are offline and useful; `--run-tests` runs the tests, and review does the rest.
