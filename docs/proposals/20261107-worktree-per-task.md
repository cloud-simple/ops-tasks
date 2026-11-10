# Proposal: a branch per task, and a worktree per task for parallel work

Each branch must hold one task and must be created before the task's first change. A task that runs while another task or agent session is active in the same clone gets its own git worktree, next to the repo. `tasks.py` gets these changes: numbering across worktrees and branches under a lock, a duplicate number warning, a new `link-env` subcommand for env files, worktree checks in `lint`, and `status --all-worktrees`.

Today the skill assumes one checkout. The changes of all tasks collect on one branch, and Workflow step 6 splits them into one branch and one merge request (MR) per task at commit time.

## Why

- **Late splits are manual.** Each task needs its own `git add` and `git commit -- <paths>`, and a file that two tasks changed must go to one of them.
- **Sessions in one checkout mix their work.** Two agent sessions see each other's uncommitted files. A workflow that stages everything (`git add -A`) puts one task's files into the other task's commit.
- **Remote helpers must be committed before they run.** On a shared branch, that commit mixes tasks or forces an early split.
- **A worktree is cheap.** It shares the object store of the clone.

## Gaps found

Each gap was reproduced in a throwaway repo with `tasks.py` 0.5.1 on 2026-11-06 and 2026-11-07.

| Gap | Reproduction |
|---|---|
| Duplicate task numbers | `tasks.py new` takes the highest number in its own tree plus one (`tasks.py:329-344`). Two worktrees made from the same commit both created `02-` (`02-alpha`, `02-beta`). After both branches were merged, `tasks.py lint` reported 0 errors. |
| No env files | Git does not copy ignored files into a new worktree. Helpers load `${OPS_ENV_FILE:-$HERE/../../../.env}`, a path relative to the helper, so they find no `<ops-dir>/.env`. |
| Broken links are invisible | `Layout.env_files()` keeps only paths where `is_file()` is true (`tasks.py:150-151`), so a broken link is not listed at all. |
| Evidence loss | `git worktree remove` without `--force` removed a worktree that held `<ops-dir>/tasks/02-alpha/out/run1/f`. Git does not count ignored files as changes. |
| Worktree inside the repo | A worktree under `.claude/worktrees/` (where `claude --worktree` puts it) shows as untracked in the main checkout. `git add -A` there staged it as an embedded repository. The [Claude Code docs](https://code.claude.com/docs/en/worktrees) tell users to add `.claude/worktrees/` to `.gitignore`. |
| Hidden tasks | `tasks.py status` lists only the tasks in the tree it runs in. Tasks in other worktrees stay invisible until they are merged. |

## Branches and worktrees

- **One task per branch.** Create the branch from the updated default branch before the task's first change. A task can have several branches over its life, one per batch of changes, but a branch never holds two tasks.
- **A worktree for parallel work.** A task gets its own worktree when another task or agent session is active in the same clone. With one task at a time, the main checkout works: check that `git status --porcelain` prints nothing, then run `git switch -c ops/<slug> origin/<default>`.
- **Next to the repo.** A worktree goes in a folder next to the repo, not inside it. A worktree nested in the repo must have its path ignored by git before anyone stages broadly.
- **The session starts in the worktree.** The agent session that writes the task must start in the worktree. A shell `cd` does not move a running session's working folder or sandbox.
- **Lock a worktree on a removable disk.** A worktree on a removable or network disk must be locked: `git worktree lock --reason "<disk>" "$wt"`. Git then keeps its records while the disk is not mounted, and `tasks.py new` stops instead of reusing its task numbers (see Missing worktree folders). Unlock it with `git worktree unlock "$wt"` before you remove it.
- **One shared credential file.** Linked env files point to the main checkout's files. A write through a link changes the main checkout's file, and a credential rotation there reaches every worktree at once. A worktree is not a credential boundary, so helpers keep their exact target checks.

### Start a task in a worktree

```bash
top=$(git rev-parse --show-toplevel) &&
wt="$(dirname "$top")/$(basename "$top")-<slug>" &&   # next to the repo, never inside it
git -C "$top" fetch origin &&
git -C "$top" worktree add -b ops/<slug> "$wt" origin/<default> &&
cd "$wt" &&
tasks.py link-env &&                                  # links the main checkout's env files
tasks.py new <slug> --title "<Title>" ||              # assigns the number
{ echo "STOP: worktree setup failed; read the output above"; false; }
```

Start the agent session in `$wt` only after this block printed no `STOP` and exited with status 0.

The branch carries the slug, not the number, because `tasks.py new` assigns the number after the branch exists. When `ops/<slug>` exists already, the task may exist on that branch: resume it with `git worktree add "$wt" ops/<slug>`. Never run `new` to continue an existing task.

### Continue after a merge

After an MR of the task is squash-merged, the next batch of changes starts on a fresh branch from the updated default branch, for example `ops/<slug>-2`. The task folder and its identity stay. When commits were made after the merged MR's source head, review that range and move only those commits (`git rebase --onto` or `git cherry-pick`). Never feed the squash-merged commits into a normal rebase. When there are no later commits, the fresh branch is enough.

### Remove a worktree

A merged last MR alone is no reason to remove the worktree.

Choose the evidence destination before the task's final MR. The usual destination is the main checkout's `<ops-dir>/tasks/NN-slug/out/`. The main checkout can belong to another session; if the user's rules forbid writing there, the destination is a folder the user chooses outside all worktrees, for example `../<repo>-ops-evidence/<NN-slug>/<run>/`. Record that folder in the Log of this task's PLAN.md as part of the final MR. Do not switch or update the main checkout, and do not edit its files, to make the copy work.

Before `git worktree remove "$wt"`:

1. Check that the worktree has no uncommitted changes and no commits after the source head of its last merged MR.
2. Check that no agent session runs in the worktree.
3. List the evidence: `tasks.py status --all-worktrees` shows the `out/` run count per task.
4. Copy each run folder to the destination. The copy creates only new run folders of this task, never overwrites a run and never follows an unexpected symlink at the destination.
5. Compare each copy with its source.
6. Run the checks of steps 1 and 2 again. Remove the worktree only when they still pass and every copy matches. A change in the worktree after step 1, such as a new Log entry, needs its own commit and MR first, and then the checks start over.

Neither `status` nor `lint` can stop a later `git worktree remove`. The rule above protects the evidence, not the tools.

Workflow step 6 keeps its split instructions for changes that already cover several tasks.

## `tasks.py new`: numbers across worktrees and branches

- **Lock:** `new` holds a lock file in the clone's common git folder (`git rev-parse --git-common-dir`) from the start of the scan until the task folder exists. When the lock is busy, `new` prints `waiting for the lock held by another tasks.py new` to stderr and waits up to a time limit. It continues when it gets the lock within that limit, and fails with a clear message when the limit runs out. When it fails after taking the lock, it removes what it created. The lock covers the worktrees of one clone, not other clones.
- **Snapshots:** the next number is the highest number found in these places, plus one:
  - the task folders on disk in this worktree and in every other registered worktree (`git worktree list --porcelain -z`);
  - the committed tree of every registered worktree's `HEAD`, detached ones included, which also covers a sparse checkout;
  - every local and remote-tracking branch (`refs/heads`, `refs/remotes`). Duplicate commits and trees are removed first, so each distinct tree costs one `git ls-tree`.
- **No fetch, bounded calls:** `new`, `status` and `lint` never fetch. Each git call has a time limit.
- **Incomplete scan:** a failing git call, an unreadable tree, a worktree folder that exists but cannot be read, or an unresolvable `HEAD` stops `new` with an error. It never frees a number.
- **Missing worktree folders:** git cannot tell a deleted worktree folder from one on a disk that is not mounted; both are missing paths. In a test on 2026-11-09, `git worktree list --porcelain -z` listed a moved-away unlocked worktree as `prunable gitdir file points to non-existent location`, and a moved-away locked one as `locked <reason>` without `prunable`. The lock flag records an instruction to keep the worktree, not the reason it is unavailable. It decides:
  - a missing worktree that is locked stops `new` with an error that names its path and lock reason. Its disk may be unmounted, and its uncommitted tasks may hold numbers and slugs.
  - a missing worktree that is not locked gives a warning: `new` scans its recorded `HEAD` and warns that uncommitted tasks from that folder cannot be found, so their numbers and slugs can be reused. The hint says to reconnect the disk if the worktree is still needed, and to run `git worktree prune` only after confirming that the worktree is gone for good. `new` never runs `prune`.
- **Present but invalid worktree folders:** an unmounted disk can leave an empty mount point at the registered path. On 2026-11-09, an empty folder at each registered path left git's report unchanged (`locked` and `prunable`), while the folder itself passed as a folder. Before `new` reads a present folder as a worktree, it checks that the folder is this clone's registered worktree: `git -C <path> rev-parse --path-format=absolute --show-toplevel` must name that path, and `git -C <path> rev-parse --path-format=absolute --git-common-dir` must name this clone's common folder. Both sides of each comparison are resolved to physical paths first (symlinks and other path aliases resolved), because git prints a relative `.git` without `--path-format=absolute`. A present folder that fails this check stops `new`, whether the worktree is locked or not. A permission error or another read error also stops `new`; only a path that does not exist counts as missing.
- **Slugs:** `new` refuses a slug that exists in this worktree or in another worktree's folder. Branch snapshots only reserve numbers. The full `NN-slug` identifies a task; the same slug can appear in old branches.
- **Stale branches** keep their numbers reserved until they are deleted. This is intended, because gaps in the numbers are harmless.
- **Not scanned:** tags, deleted or unreachable history, and unpushed branches in other clones. A new number avoids every number the scan observed. Duplicate numbers that exist already stay allowed. The `lint` warning below finds a reused number only once both folders are visible in the same linted tree.
- **Outside git:** `tasks.py` accepts `--root` with a folder outside any git repo, and existing self-tests use it. There, `new`, `status` and `lint` keep their local behavior: `new` scans only that folder, under a lock file next to the marker (`<ops-dir>/.ops-tasks.lock`). `link-env` and `status --all-worktrees` stop with a message that they need a git repo.

### Current layout only

Every snapshot is read at the current `<ops-dir>` path. SKILL.md states this limit, with a rule for moving `<ops-dir>`:

1. Move `<ops-dir>` only after every open task branch is merged, or rebased onto the commit that moves it.
2. Before the next `new`, check that every active task folder exists under the new path, in its branch or worktree. Include uncommitted task folders in worktrees: a rebase does not move an untracked folder. Move their `out/` evidence and env links with them.

A task branch abandoned in the old layout can lose its number to reuse. `lint` warns about it only when both task folders are visible in the same linted tree.

## `lint`

- **Duplicate numbers:** a warning when two different task folders in the linted tree share a number. Copies of one task in different worktrees are not a collision, because `lint` reads one tree. Two tasks created separately with the same full `NN-slug` name do not trigger this warning. Git may merge their files without a conflict; this warning cannot detect that the records came from separate tasks. It is a warning, not an error: the slug keeps folder names unique, and renaming an established folder breaks links into it.
- **Env links:** in a linked worktree, a warning for each state other than a correct link (see the table below).
- **Nested worktrees:** a warning for a registered worktree inside the repo whose path git does not ignore.
- **Missing worktrees:** a warning that names each registered worktree that is missing or invalid, with its lock state. `lint` then goes on with the checks of the current tree; a missing unrelated worktree does not fail them.

## `tasks.py link-env`: env file links

A new subcommand. It only creates links and writes nothing else: no `lib/` and no `.gitignore` change. `init` stays as it is, because it also overwrites `lib/` and edits `.gitignore`, which would put a library upgrade into a task's MR.

- A linked worktree is one that `git worktree add` created: `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`. The main checkout is the first entry of `git worktree list --porcelain -z`. Its layout is resolved on its own.
- `link-env` stops with an error when: it runs outside a linked worktree; the main repo is bare; the main checkout is missing or has no marker; this worktree has no initialized `<ops-dir>`; git does not ignore the destination path (checked with `is_ignored()`, so wider patterns count); or the destination is tracked. For a missing marker or ignore rule, the fix is `tasks.py init` as its own change.
- It lists the `<ops-dir>/.env*` entries of both sides by name, the main checkout's (the sources) and this worktree's (the destinations), with `lstat`, so broken links count. `lint` checks every name on either side, so a link whose source was renamed or deleted is found too.
- A source is usable when it is a regular file with read access, or a symlink that resolves to one. The link holds the source's own path in the main checkout, so a source symlink keeps working as the main checkout set it up. A folder, a device, a broken symlink or a file without read access is not usable.
- It checks only file types and read access. It never reads, sources or prints an env file, and it keeps `init`'s refusal to write through a path that is a symlink (`cmd_init`).

| Source in the main checkout | Destination in the worktree | `link-env` | `lint` |
|---|---|---|---|
| usable | missing | creates a link holding the source's absolute path | warning: run `tasks.py link-env` |
| usable | link to the source | nothing | nothing |
| usable | link to another path, or broken link | nothing | warning: remove the link, then run `link-env` |
| usable | regular file | nothing | warning: a copy goes stale after a credential change |
| usable | folder or other type | nothing | warning |
| not usable | any | nothing | warning: repair or remove the source in the main checkout |
| absent (renamed or deleted) | link | nothing | warning: the source is gone; remove the link |
| absent | regular file | nothing | warning: this file exists only in this worktree and is deleted with it |

Rules in SKILL.md:

- Create and change env files in the main checkout only. A file created in a worktree stays there and is deleted with it.
- After the main checkout gets a new env file, run `tasks.py link-env` in each worktree that needs it.
- Every loader keeps the form `${OPS_ENV_FILE:-<path>}`. `stubtest.py` sets `OPS_ENV_FILE` to a fake file and rejects a case that overrides it (`stubtest.py:273-280`), so tests never read a real linked file. A loader that hard-codes the path bypasses this.
- A helper whose connection needs an env file must stop when the file is missing or unreadable. The template's unconditional `source` under `set -euo pipefail` does that; a guarded optional `source` does not.

Rejected:

- **Copy the env files**, as `.worktreeinclude` does in Claude Code and in the ChatGPT desktop app's managed worktrees: each worktree gets one more secret copy, and the copies go stale.
- **Set `OPS_ENV_FILE` in the shell:** it covers one env file, and every shell must set it.
- **A git `post-checkout` hook:** git runs it after `git worktree add` for any tool, but installing a hook clashes with hook setups the repo already has.
- **Helpers find the main checkout:** every helper would call `git`, and the closed tool list of `stubtest.py` would have to allow it.
- **Links made by `init`:** see above.

## `status`

- `status` adds the observed `out/` run count per task: the number of run folders it could list. It prints `unreadable` instead of a number when it cannot list `out/`. The count is not proof that all evidence was found or copied.
- `status --all-worktrees` also lists the tasks of every registered worktree, with the worktree's path and its branch or detached state. Copies of one task in different worktrees stay separate rows. A missing worktree shows as one row with its path: `missing (locked: <reason>)` or `missing`. That row never counts as zero tasks or zero runs. Without the flag, `status` reads the current tree only.
- Branches without a worktree do not appear. It is a worktree status, not a full list of the repo's tasks.

## Git version

The worktree features need Git 2.36 or later. Git 2.36 added `git worktree list --porcelain -z`, and Git 2.31 added its `locked` and `prunable` lines (Git release notes). In a git repo, `new`, `lint`, `link-env` and `status --all-worktrees` read `git --version` first and stop with an error when Git is older. The error names the installed and the required version. In a partial clone (a clone with a promisor remote), `new` needs Git 2.45 or later: git runs with `GIT_NO_LAZY_FETCH=1`, which older Git ignores, so it would fetch missing objects while reading them. The check compares the numbers of the version, not the text, and stops with an error when it cannot run `git --version` or cannot read a version from its output. These have no Git 2.36 minimum: `init` and plain `status` in a git repo, and `init`, `new`, plain `status` and `lint` outside git (`--root` with a folder outside any repo).

`link-env` is not blocked by a missing or locked worktree that it does not use. It needs only the current worktree and the main checkout. When either is missing or invalid, it stops with an error and never takes another checkout as the source of the env files.

## Not changed

- The Read access rule stays: `git worktree add` needs its own allowed action. It covers a repo named in Connections, not the repo that holds `<ops-dir>`.
- Session worktrees are not the default for a task, because a task can outlive a session. Claude Code puts its worktree inside the repo, under `.claude/worktrees/<name>/` on the branch `worktree-<name>`, and offers to remove it when the session ends ([docs](https://code.claude.com/docs/en/worktrees)). `codex-cli` 0.167.0 has `--worktree`. Not verified: where it puts the worktree and how it handles ignored files. The Codex docs page on git worktrees describes the desktop app's worktrees under `$CODEX_HOME/worktrees`.
- `init` does not add `/.claude/worktrees/` to `.gitignore`. The nested worktree warning in `lint` covers that case.

## Self-tests

- **Lock:** a contention test and a timeout test. The contention test holds the lock, starts `new` in another worktree, reads its stderr with a bounded wait until the busy line appears, creates a competing numbered task, releases the lock, and expects the number after the competing task. The timeout test expects a clear failure after the bound.
- **Scan:** duplicate branch tips; a task that exists only on a branch; a detached and a sparse worktree; a missing locked worktree that stops `new` and a missing unlocked one that gives a warning; an empty folder at a locked worktree's registered path that stops `new`; the path comparison accepts the main checkout and a linked worktree; a missing unrelated worktree that leaves `link-env` working; stale remote-tracking refs; a renamed `<ops-dir>` that is not scanned (it documents the limit); an unreadable tree that stops `new`.
- **Env links:** each row of the table, including a deleted, a broken, a folder and a symlinked source; a new env file in the main checkout; a renamed source; no overwrite; no read of an env file (checked with sentinel values); `OPS_ENV_FILE` wins over a real linked file in `--test` (fake sentinels); a bare main repo; a tracked destination; a missing ignore rule.
- **`lint`:** two different folders with one number; a nested worktree that git does not ignore.
- **`status`:** the `out/` run count, and `unreadable` for an `out/` it cannot list; copies of one task in two worktrees stay separate rows.
- **Outside git:** `new`, `status` and `lint` with `--root` keep working; `link-env` and `status --all-worktrees` stop with their message.
- **Git version:** a Git older than 2.36 stops `new`, `lint`, `link-env` and `status --all-worktrees`; 2.36 exactly and a newer major version pass; a vendor suffix such as `git version 2.39.5 (Apple Git-154)` is read correctly; malformed output and a failing `git --version` stop with an error.

Copying evidence before a removal is a SKILL.md procedure, not `tasks.py` code, so it has no self-test. When SKILL.md gets exact copy commands, rehearse their no-overwrite behavior on fake evidence before publishing them.

## Where the change goes

In `cloud-simple/ops-tasks`:

- `tasks.py`: `new`, `lint`, `status` and the new `link-env`, with the self-tests above.
- `SKILL.md`: Workflow steps 1 and 6, a Worktrees section (start, continue, remove, move `<ops-dir>`), the env file rules, the `lint` paragraph and the command list.
- `AGENTS.md`: the subcommand list, the self-test count and the Git 2.36 requirement next to the Python 3.9 one.
- A version bump to 0.6.0. With Git 2.36 or later, `lint` adds warnings only, so every plan that passes today still passes. With an older Git in a git repo, `lint` now fails its Git version check. The release notes state the new Git requirement.
