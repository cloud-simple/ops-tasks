# Changelog

The changes in each release of the `ops-tasks` plugin, newest first. Dates are release dates in
UTC, and numbers in parentheses are pull requests. "Repo only" lists changes to this repo that do
not ship in the plugin. Versions 0.2.0 and 0.2.1 are tagged `ops-tasks--v0.2.0` and
`ops-tasks--v0.2.1`. Later versions are tagged `v<version>`.

## 0.7.0 (2026-11-12)

### Added

- An alias in the operator's `~/.ssh/config` can be the settings source of a connection. That
  connection needs no env file. The helper template shows a target check that reads `ssh -G`
  under a time limit, stops when the read fails and compares the host name exactly (#25).

### Changed

- The user creates `<ops-dir>/.env` only when the default connection uses an env file (#25).

## 0.6.0 (2026-11-10)

### Added

- `tasks.py new` takes the number after every task number the clone uses: the task folders in
  every worktree, and the committed tasks of every worktree HEAD and every local and
  remote-tracking branch. A lock keeps two `new` runs from taking the same number. `new` stops
  when it cannot read one of these places. `lint` warns when two task folders share a number
  (#21).
- `tasks.py link-env` links the main checkout's `<ops-dir>/.env*` files into a linked worktree.
  In a linked worktree, `lint` warns about each env file that is not such a link (#22).
- `tasks.py status` shows a RUNS column, and `status --all-worktrees` lists the tasks of every
  worktree. `lint` warns about a worktree that is missing or not that worktree, and about a
  worktree inside the checkout that git tracks or does not ignore. `SKILL.md` describes how to
  run tasks in worktrees (#23).

### Changed

- In a git repo, `new`, `lint`, `link-env` and `status --all-worktrees` need Git 2.36 or later,
  and `new` needs Git 2.45 or later in a partial clone. With an older Git they stop with an
  error, so `lint` fails in a git repo with an older Git (#21, #22, #23).

## 0.5.1 (2026-11-01)

### Changed

- The skill's workflow requires one merge request per task. Changes that cover several tasks are
  split into one branch and one merge request per task (#19).

## 0.5.0 (2026-10-31)

### Changed

- `lint` fails a plan whose Connections table has a real row but no answered `Managed systems:`
  line after the table. To fix a plan, add that line: the repo and pipeline for each managed
  system, `none` or `unknown`. In the plan of a done or dropped task, write `unknown` with the
  date you added the line (#16).
- `lint` rejects a second `## Connections` section and a row with an empty ID (#16).

### Repo only

- `scripts/check_package.py --release <tag>` checks the tag, a clean checkout and `main` on
  `origin` before a release is tagged (#14). It reads the versions from `HEAD` and kills the
  whole git process group on a timeout (#15).
- `AGENTS.md` states that the repo is public and keeps client details and outside release tools
  out of it (#17).

## 0.4.0 (2026-10-26)

### Repo only

- `AGENTS.md` holds the agent instructions, and `CLAUDE.md` imports it (#11).
- A release needs the same `version` in both plugin manifests on `main`. Tags are
  `v<version>` from this release on, and `v0.3.0` marks the same commit as `ops-tasks--v0.3.0`
  (#12).

## 0.3.0 (2026-10-26)

### Added

- Remote helpers: task scripts that run on a system from `## Connections` instead of the
  operator's machine, with the template `assets/remote-script.sh`. A remote helper loads no
  shared library, env file or secret from the operator's machine. It keeps its code in one
  `{ ... }` block, so a cut-off transfer runs nothing, and limits each command with GNU `timeout`
  (#9).
- `lint` checks each remote helper: its `Runs on: remote:` ID is in `Connection:`, it calls no
  `source` or `with_timeout`, and its code sits in one `{ ... }` block (#9).

### Repo only

- A backlog item on scoping an env file to one task (#8).

## 0.2.1 (2026-10-13)

### Changed

- The skill no longer starts for a standalone script, playbook or configuration file that is not
  part of an operations task (#6).

### Repo only

- Self-tests for the package checker: `scripts/check_package.py --test` (#5).

## 0.2.0 (2026-10-13)

### Added

- Codex support: a Codex marketplace, plugin manifest and skill display metadata. Both agents
  share one skill with its helper scripts and templates (#4).

### Changed

- Helper paths resolve from the loaded `SKILL.md`, and the working directory stays in the user's
  repo (#4).

### Removed

- The skill-level `allowed-tools` rule for Claude Code. Commands use each agent's normal
  permissions (#4).

### Repo only

- Packaging checks, and install and release instructions (#4).
