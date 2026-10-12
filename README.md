# ops-tasks

A Claude Code plugin for infrastructure operations tasks. Each task is a folder with the problem, a
checked plan and tested helper scripts. The plugin holds one skill, `ops-tasks`.

## Install

From inside Claude Code 2.1.275 or later:

```
/plugin install ops-tasks --marketplace cloud-simple/ops-tasks
```

On older versions, add the marketplace first:

```
/plugin marketplace add cloud-simple/ops-tasks
/plugin install ops-tasks@ops-tasks
```

The repo is private: the machine needs read access to `github.com/cloud-simple/ops-tasks`.

## What a task looks like

```
<ops-dir>/                 ops/ by default
  .ops-tasks               empty marker: this folder holds tasks/ and the .env* files
  .env                     settings and credentials, created by the user, git-ignored
  tasks/
    lib/                   shared test library, installed by `tasks.py init`
    NN-slug/
      TODO.md              problem, ideas, status
      PLAN.md              facts, connections, steps with Before/Do/After checks, results, log
      scripts/             optional: numbered bash helpers, each with an offline --test
```

`<ops-dir>` is `ops/` when `ops/.ops-tasks` exists, else the first folder in the repo root, sorted by
name, that holds `.ops-tasks`. The skill works only inside a git repo.

## Use

Ask Claude to start an operations task, write a plan or runbook, record a step that was done, add a
helper, or show the status of the tasks. The skill triggers on these requests without being named.

In a new repo, the first run is `tasks.py init`. It creates `ops/.ops-tasks` (or `NAME/.ops-tasks` with
`--dir NAME`), installs `<ops-dir>/tasks/lib/`, and adds `/<ops-dir>/tasks/*/out/` and
`/<ops-dir>/.env*` to `.gitignore`. It stops when the folder exists without the marker, because the
folder may belong to the project; create the marker there yourself only if the folder is meant for
tasks. Commit `<ops-dir>/.ops-tasks` and `<ops-dir>/tasks/lib/` afterwards.

Claude runs `tasks.py` from the installed plugin as `${CLAUDE_SKILL_DIR}/scripts/tasks.py`:

| Command | What it does |
|---|---|
| `init [--dir NAME]` | install or update `<ops-dir>/tasks/lib/` (overwrites it) |
| `new SLUG [--title TEXT]` | create the next `<ops-dir>/tasks/NN-SLUG/` from the templates |
| `status` | list tasks with status, deadline and checkbox counts |
| `lint [TASK ...] [--run-tests]` | check structure, links, secret patterns, helpers, `lib/`, Connections and git-ignored env files; `--run-tests` also runs the offline tests |
| `--test` | run the tool's own self-tests |

`status` and `lint` only read. `lint` cannot prove that no secret is present, that an action is
authorized, or that a step uses the right target; review does that.

## Layout of this repo

```
.claude-plugin/marketplace.json            the ops-tasks marketplace
plugins/ops-tasks/
  .claude-plugin/plugin.json               the plugin manifest and its version
  skills/ops-tasks/
    SKILL.md                               the rules Claude follows
    scripts/tasks.py                       init, new, status, lint
    assets/                                TODO.md, PLAN.md and script.sh templates
    assets/lib/                            stubtest.py and with_timeout.sh, copied into each repo by init
```

## Develop

Run all tests before each commit. They need Python 3.9 or later, bash 3.2 or later and git, and make
no network calls.

```bash
S=plugins/ops-tasks/skills/ops-tasks
$S/scripts/tasks.py --test
$S/assets/lib/stubtest.py --test
$S/assets/lib/with_timeout.sh --test
claude plugin validate .                          # the marketplace manifest only
claude plugin validate --strict plugins/ops-tasks # the plugin manifest and its skill
```

To release:

1. Raise `version` in `plugins/ops-tasks/.claude-plugin/plugin.json`, commit, and get it onto
   `origin/main`: merge the pull request, or after a local merge run `git push origin main`.
   Installs read the plugin from `origin/main`, so a version that is only local is not released.
2. Update the local `main` to `origin/main`. On that clean `main`, run
   `claude plugin tag --push plugins/ops-tasks`. It checks that `plugin.json` and the marketplace
   entry agree, then creates and pushes only the tag `ops-tasks--v<version>`.

Installed copies update only when the version changes. After a change to `assets/lib/`, run
`tasks.py init` in each repo that uses the skill and commit its `<ops-dir>/tasks/lib/`.
