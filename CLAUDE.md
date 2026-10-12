# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code plugin marketplace with one plugin, `ops-tasks`, which holds one skill, also named
`ops-tasks`. The skill teaches Claude to keep infrastructure operations tasks as folders
(`<ops-dir>/tasks/NN-slug/` with `TODO.md`, `PLAN.md` and `scripts/`) in the repos of the people
who install it. This repo contains no tasks itself. Everything that ships lives under
`plugins/ops-tasks/skills/ops-tasks/`:

- `SKILL.md`: the rules Claude follows in a user's repo. It is the specification; `tasks.py` enforces
  the mechanical parts of it.
- `scripts/tasks.py`: one Python file, standard library only, Python 3.9 or later. Subcommands
  `init`, `new`, `status`, `lint [--run-tests]`, plus `--test` for its own self-tests.
- `assets/TODO.md`, `assets/PLAN.md`, `assets/script.sh`: templates that `tasks.py new` copies.
- `assets/lib/stubtest.py` and `assets/lib/with_timeout.sh`: the shared library that `tasks.py init`
  copies into each user repo as `<ops-dir>/tasks/lib/`. `lint` fails in a user repo when that copy
  differs from the plugin's copy, so a change here forces a re-init in every repo that uses the skill.

Edit the skill's assets in this repo only. The installed copies in user repos are overwritten by `init`.

## Commands

Run all tests before each commit. They make no network calls.

```bash
S=plugins/ops-tasks/skills/ops-tasks
$S/scripts/tasks.py --test                        # 43 unittest cases, one PASS/FAIL line each
$S/assets/lib/stubtest.py --test
$S/assets/lib/with_timeout.sh --test
claude plugin validate .                          # the marketplace manifest only
claude plugin validate --strict plugins/ops-tasks # the plugin manifest and its skill
```

Run one `tasks.py` self-test by its unittest name:

```bash
cd plugins/ops-tasks/skills/ops-tasks/scripts
python3 -m unittest -q tasks.SelfTests.test_new_numbers_after_the_highest
```

The self-tests are the `SelfTests` class at the bottom of `tasks.py`. Each builds a throwaway git
repo in a temp folder and runs the commands against it, so a new behaviour in `init`, `new`,
`status` or `lint` gets a case there.

To try the tool against a real layout without a user repo, pass `--root <dir>` to any subcommand.
Outside git every subcommand stops unless `--root` is given.

## How tasks.py is organised

- `Layout` (found by `find_layout` or created by `init_layout`) resolves the repo root and
  `<ops-dir>`: the folder holding the empty marker `.ops-tasks`, `ops/` by default, else the first
  folder in the repo root, sorted by name, that holds the marker. `init` never takes over a folder
  that exists without the marker.
- `cmd_init`, `cmd_new`, `cmd_status`, `cmd_lint` are the subcommands. `status` and `lint` only read.
- `lint` is a set of `lint_*` functions that append to a `Report` (errors fail, warnings do not).
  The regexes near the top of the file (`STATUS_RE`, `STEP_RE`, `AFTER_BOX_RE`, `SECRET_PATTERNS`,
  `NETWORK_TOOLS`, and so on) define the shape that `lint` accepts; `SKILL.md` and the templates must
  stay consistent with them. When you change a rule, change all three: the regex, `SKILL.md` and the
  template, and add a self-test.
- `lint --run-tests` runs `stubtest.py --test`, `with_timeout.sh --test` and every helper's `--test`
  in its own process session with a time limit (`TEST_TIMEOUT`), then kills what the session left.

`stubtest.py` is the offline test runner for helpers: it runs a helper once per case from
`scripts/tests/<helper>.json` with a fake env file, stubbed commands on `PATH` and a closed list of
allowed local tools. Its module docstring is the reference for the tests file format and the
environment rules. `with_timeout.sh` is a bash function that runs a command in its own process
group under a time limit and kills the whole group afterwards.

## Conventions

- Plain language in every prose file, `SKILL.md` included: short sentences, active voice, one term
  per item, `must` for requirements.
- Every script and template opens with the same header fields: `Purpose:`, `Usage:`, `Effect:`,
  `Runs on:`, and for helpers `Connection:` and `Exit:`. `lint` checks these fields in helpers.
- Shell is bash 3.2 or later (macOS `/bin/bash`), never zsh-only syntax. Helpers are bash only.
- Never write `${CLAUDE_SKILL_DIR}` or the plugin cache path into a user repo; it changes with every
  plugin version. The skill's `allowed-tools` rule only matches `tasks.py` run directly, not through
  `python3`.
- The two library files carry a two-line header saying they are installed copies; keep it, because
  it is what tells a reader in a user repo where to edit.

## Branches and releases

`main` is protected: every change reaches it through a pull request with a squash merge.

1. Raise `version` in `plugins/ops-tasks/.claude-plugin/plugin.json` in the pull request. Installs
   read from `origin/main`, so an unmerged version is not released. Installed copies update only
   when the version changes.
2. On a clean local `main` that matches `origin/main`, run
   `claude plugin tag --push plugins/ops-tasks`. It checks that `plugin.json` and the marketplace
   entry agree and pushes only the tag `ops-tasks--v<version>`.

After a change to `assets/lib/`, each repo that uses the skill must run `tasks.py init` again and
commit its `<ops-dir>/tasks/lib/`.
