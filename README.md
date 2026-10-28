# ops-tasks

A plugin for Claude Code and Codex that keeps infrastructure operations tasks as folders. Each task
holds the problem, a checked plan and tested helper scripts. Both agents use the same `ops-tasks`
skill, scripts and templates.

## Install

### Codex

From the command line:

```bash
codex plugin marketplace add cloud-simple/ops-tasks
codex plugin add ops-tasks@ops-tasks
```

Start a new Codex session after installation. Ask for an operations task, or invoke `$ops-tasks`
explicitly. To refresh the marketplace and install the current version:

```bash
codex plugin marketplace upgrade ops-tasks
codex plugin add ops-tasks@ops-tasks
```

### Claude Code

From inside Claude Code 2.1.275 or later:

```
/plugin install ops-tasks --marketplace cloud-simple/ops-tasks
```

On older versions, add the marketplace first:

```
/plugin marketplace add cloud-simple/ops-tasks
/plugin install ops-tasks@ops-tasks
```

From the command line, outside a Claude Code session:

```bash
claude plugin install ops-tasks --marketplace cloud-simple/ops-tasks
```

This adds the marketplace when it is missing, then installs the plugin for the current user. Add
`--scope project` to record the install in the repo's `.claude/settings.json` instead, so the team
gets the plugin with the checkout. The two-step form also works:

```bash
claude plugin marketplace add cloud-simple/ops-tasks
claude plugin install ops-tasks@ops-tasks
```

Restart Claude Code after the install. To update later:

```bash
claude plugin update ops-tasks@ops-tasks
```

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
      scripts/             optional: numbered bash helpers (local or remote), each with an offline --test
```

`<ops-dir>` is `ops/` when `ops/.ops-tasks` exists, else the first folder in the repo root, sorted by
name, that holds `.ops-tasks`. The skill works only inside a git repo.

## Use

Ask Claude Code or Codex to start an operations task, write a plan or runbook, record a step that was
done, add a helper, or show the status of the tasks. The skill triggers on these requests without
being named.

In a new repo, the first run is `tasks.py init`. It creates `ops/.ops-tasks` (or `NAME/.ops-tasks` with
`--dir NAME`), installs `<ops-dir>/tasks/lib/`, and adds `/<ops-dir>/tasks/*/out/` and
`/<ops-dir>/.env*` to `.gitignore`. It stops when the folder exists without the marker, because the
folder may belong to the project; create the marker there yourself only if the folder is meant for
tasks. Commit `<ops-dir>/.ops-tasks` and `<ops-dir>/tasks/lib/` afterwards.

Both agents resolve `scripts/tasks.py` from the directory containing the loaded `SKILL.md` and run
it by absolute path. The working directory stays in the user's repo so the tool finds the right
git root. `tasks.py` below means that resolved path; it is not installed on `PATH`. Commands use
each agent's normal permissions.

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
.agents/plugins/marketplace.json          the Codex marketplace
.claude-plugin/marketplace.json            the Claude Code marketplace
scripts/check_package.py                  checks manifests, paths and a copied plugin
plugins/ops-tasks/
  .codex-plugin/plugin.json                the Codex manifest and version
  .claude-plugin/plugin.json               the Claude Code manifest and version
  skills/ops-tasks/
    SKILL.md                               the rules both agents follow
    agents/openai.yaml                     Codex display metadata and starter prompt
    scripts/tasks.py                       init, new, status, lint
    assets/                                TODO.md, PLAN.md, script.sh and remote-script.sh templates
    assets/lib/                            stubtest.py and with_timeout.sh, copied into each repo by init
```

## Develop

`main` is protected: every change reaches it through a pull request with a squash merge. Direct
pushes, force pushes and deleting `main` are refused.

Run all tests before each commit. They need Python 3.9 or later, bash 3.2 or later and git, and make
no network calls.

```bash
S=plugins/ops-tasks/skills/ops-tasks
$S/scripts/tasks.py --test
$S/assets/lib/stubtest.py --test
$S/assets/lib/with_timeout.sh --test
python3 scripts/check_package.py --test           # the package checker's own tests
python3 scripts/check_package.py
claude plugin validate .                          # the marketplace manifest only
claude plugin validate --strict plugins/ops-tasks # the plugin manifest and its skill
```

To release a new version, raise `version` in both `plugins/ops-tasks/.claude-plugin/plugin.json`
and `plugins/ops-tasks/.codex-plugin/plugin.json` to the same value in a pull request, and release
from `main` after it is merged. The release version must be the same as `version` in
`plugin.json`. The install commands above read the plugin from the default branch, so a version
that is not merged is not released. Immediately before creating the release tag, run
`python3 scripts/check_package.py --release <tag>` with the selected tag, and stop if it fails. It
checks that the tag is `v` plus that version, that the checkout is clean, and that `HEAD` is the
commit of `main` on `origin`.

Use the update commands for each agent above after a release. After a change to `assets/lib/`, run
`tasks.py init` in each repo that uses the skill and commit its `<ops-dir>/tasks/lib/`.
