#!/usr/bin/env python3
"""Create, list and check operations task folders: <ops-dir>/tasks/NN-slug/{TODO.md, PLAN.md, scripts/}.

Purpose: keep every task folder in the same shape.
Usage:   tasks.py [--root DIR] init [--dir NAME]         install or update <ops-dir>/tasks/lib/ from the skill (overwrites it)
         tasks.py [--root DIR] new SLUG [--title TEXT]   create <ops-dir>/tasks/NN-SLUG from templates, with
                                                         a number no task of this clone uses
         tasks.py [--root DIR] status                    list tasks with status, deadline and checkbox counts
         tasks.py [--root DIR] link-env                  in a linked worktree, link the main checkout's
                                                         <ops-dir>/.env* files that this worktree lacks
         tasks.py [--root DIR] lint [TASK ...] [--run-tests]
                                                         check structure; --run-tests also runs every
                                                         helper's --test and the shared test runner
         tasks.py --test                                 run this tool's own self-tests
Effect:  `init` creates <ops-dir>/.ops-tasks when no marker exists, overwrites <ops-dir>/tasks/lib/, and adds
         /<ops-dir>/tasks/*/out/ and /<ops-dir>/.env* to .gitignore when missing. `new` writes one new
         folder (and runs `init` when <ops-dir>/tasks/lib/ is missing) under a lock file: ops-tasks-new.lock
         in the clone's common git folder, or <ops-dir>/.ops-tasks.lock outside git. `link-env` creates
         symbolic links in <ops-dir>/ only: it never replaces an entry and never reads an env file.
         `status` and `lint` only read. `lint --run-tests` runs the offline tests of <ops-dir>/tasks/lib/
         and of the helpers.
Runs on: macOS or Linux with Python 3.9 or later. Standard library only. In a git repo, `new`,
         `link-env` and `lint` need Git 2.36 or later, and `new` needs Git 2.45 or later in a partial
         clone; they stop with an error on an older Git.

Task numbers (`new`):
- Inside git, the next number is one above every number found in: the task folders on disk in every
  registered worktree of the clone, and the committed <ops-dir>/tasks of every worktree HEAD (detached
  and sparse ones included) and of every local and remote-tracking branch. It reads only the current
  <ops-dir> name and never fetches (git runs with GIT_NO_LAZY_FETCH=1). Tags, unreachable history and
  unpushed branches of other clones are not scanned. Outside git, it reads the task folders of the
  --root folder only. A --root folder inside a repo that is not its top level is refused.
- A slug that a task folder on disk in any worktree uses is refused. Branches only reserve numbers.
- A place that cannot be read stops `new`: a repo git cannot read, a failing git call, an unreadable
  tree or folder, a broken symbolic link on the way to a tasks folder, or a registered worktree folder
  that is not that worktree (an empty mount point). A missing worktree that
  is locked stops `new` too, because its disk may not be mounted; a missing one that is not locked
  gives a warning, and only its last commit is scanned.

Where things are:
- The repo root is the git top-level folder of the working directory, or the folder given with --root.
  Outside git, every command stops unless --root is given.
- <ops-dir> is the folder that holds the empty marker file `.ops-tasks`, `ops` by default: `ops/` if
  `ops/.ops-tasks` exists, else the first folder in the repo root, sorted by name, that holds `.ops-tasks`.
  Without any marker, `init` creates `ops/.ops-tasks`, or NAME/.ops-tasks with --dir NAME; the other
  commands stop.
- `init` never takes over a folder that exists without the marker (it may belong to the project), and
  `init --dir NAME` stops when the marker is in another folder: later commands would use that one.
- The tasks are in <ops-dir>/tasks/. The env files are <ops-dir>/.env*; tasks.py only keeps them ignored
  by git, links them into linked worktrees (`link-env`) and never reads them.

Env files in a linked worktree (`link-env`, and the matching `lint` warnings):
- A linked worktree is one that `git worktree add` made; the main checkout is the first entry of
  `git worktree list`. A source (a main checkout entry) is usable when it is a readable regular file,
  or a symbolic link to one. The link holds the source's absolute path in the main checkout, and only
  a link to that entry itself counts as correct. The sources are in the main checkout's own <ops-dir>.
- `link-env` links each usable source that the worktree lacks. It stops outside git, in the main
  checkout, when the main repo is bare, missing or not that checkout, when the main checkout has no
  marker, when <ops-dir> is a symbolic link, and when git tracks or does not ignore an env file name
  or the git check fails.
- `lint` in a linked worktree warns about every name on either side that is not a link to a usable
  source: a missing link, a link elsewhere or a broken one, a copy, a folder, a source that is not
  usable, and an entry whose source is gone or that exists only in the worktree.

What lint checks, and what it cannot prove:
- Folder names, required files and headings, the TODO status, deadline and plan lines, and
  checkbox state for done tasks. scripts/ is optional: it exists once a task has a helper.
- Two task folders with the same number: a warning, because renaming an existing folder breaks links
  into it. Two tasks created separately with the same full NN-slug name cannot be detected.
- Inline local Markdown links `[text](path)` outside code. Reference-style links, paths with
  spaces or escapes, anchors and external links are not checked.
- Explicit secret patterns only (password/secret/token assignments, license keys, private keys).
  This is a heuristic: a clean result does not prove that no secret is present.
- PLAN.md: unique step IDs `N.M` matching their `## Phase N`, an "After check passed" box in every
  step with a `**Do:**` part, and code blocks fenced as `bash` (or another named language).
- <ops-dir>/tasks/lib/ matches the skill's assets/lib/.
- PLAN.md "## Connections": one such section, the table columns, an ID in every row, unique IDs and
  Kind (system, repo, pipeline); the IDs in `Uses:` lines and in helper `Connection:` headers exist in
  that table. Placeholder rows and IDs that start with '<' are skipped. A table with a real row needs
  exactly one `Managed systems:` line after it, at the start of a line in that section, with an
  answer that does not start with '<' (a mapping, none or unknown). lint checks that someone answered, not that
  the answer is true. Lines inside HTML comments count like any other line. It cannot check
  authorization or that a step uses the right target.
- The env files are ignored by git, or /<ops-dir>/.env* is in .gitignore when none exists yet.
- Helpers: bash only (`NN-verb-object.sh`, first line `#!/usr/bin/env bash`), the executable bit,
  header fields, a `--test` branch, a tests file, and no absolute paths to network tools or /dev/tcp.
  Finding `--test` does not prove the tests are offline or useful; `--run-tests` runs them.
- Remote helpers (header `Runs on: remote: <ID>`): the IDs also appear in `Connection:`, no `source`
  or `.` command and no with_timeout (the remote system has neither lib/ nor the env file), and all
  code sits in one `{ ... }` block. The block check reads the raw lines, and `bash -n` checks that
  the file parses and that the file cut at any line end inside the block does not, so such a cut
  runs nothing. The source and with_timeout checks look only at code: a small scanner drops
  comments, string text and here-document bodies, and keeps command substitutions. It is a
  heuristic, not a bash parser, and its mistakes cannot change the block check.
- Code fences are opened by three or more backticks or tildes and closed by the same character
  repeated at least as often.
"""

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
LIB_FILES = ("stubtest.py", "with_timeout.sh")
BASH_SHEBANG = "#!/usr/bin/env bash"
DEFAULT_OPS_DIR = "ops"
MARKER = ".ops-tasks"

TASK_DIR_RE = re.compile(r"^(\d{2,3})-([a-z0-9]+(?:-[a-z0-9]+)*)$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCRIPT_RE = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.sh$")
STATUS_RE = re.compile(r"^Status: (open|planned|in progress|done|dropped) \(since (\d{4}-\d{2}-\d{2})\)\s*$", re.M)
STATUS_LINE_RE = re.compile(r"^Status:.*$", re.M)
DEADLINE_RE = re.compile(r"^Deadline: (\d{4}-\d{2}-\d{2}|none)\b.*$", re.M)
PLAN_LINE_RE = re.compile(r"^Plan: \[PLAN\.md\]\(PLAN\.md\)\s*$", re.M)
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
STEP_RE = re.compile(r"^### (\d+)\.(\d+)\s+\S")  # "### N.M <title>": two numbers, then a title
PHASE_RE = re.compile(r"^## Phase (\d+)\b")
AFTER_BOX_RE = re.compile(r"^\s*[-*] \[[ xX]\] After check passed")
BAD_FENCE_LANGS = ("", "sh", "zsh", "shell")
CHECKBOX_RE = re.compile(r"^\s*[-*] \[([ xX])\] ")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADER_FIELDS = ("Purpose:", "Usage:", "Effect:", "Runs on:", "Connection:", "Exit:")
CONNECTION_HEADER_RE = re.compile(r"^#\s*Connection:\s*(.*)$", re.M)
REMOTE_RE = re.compile(r"^#\s*Runs on:\s*remote:\s*(.*)$", re.M)  # a helper that runs on a remote system
# Commands a remote helper cannot run there: sourcing a file (lib/ and the env file are not there) and with_timeout.
# A heuristic, matched on the code of each line (see code_lines); it does not parse shell syntax.
REMOTE_FORBIDDEN_RE = re.compile(r"(^|[;&|({!]|\b(then|do|else|elif|if|while|until|builtin|command))\s*"
                                 r"(source|\.)\s+\S|\bwith_timeout\b")
HEREDOC_RE = re.compile(r"<<(-?)[ \t]*((?:\\.|'[^']*'|\"[^\"]*\"|[^\s;&|<>()'\"\\])+)")  # the whole delimiter word
COMMAND_START_RE = re.compile(r"(^|[;&|({!]|\b(then|do|else|elif|if|while|until))\s*$")
BLOCK_OPEN_RE = re.compile(r"^\{\s*(#.*)?$")
BLOCK_CLOSE_RE = re.compile(r"^\}\s*(#.*)?$")
TODO_HEADINGS = ("## Problem", "## Ideas")
CONNECTION_COLUMNS = ("ID", "Kind", "Target", "Settings and credentials from", "Allowed actions")
CONNECTION_KINDS = ("system", "repo", "pipeline")
USES_RE = re.compile(r"^Uses:\s*(.*)$")
TABLE_BROKEN = object()  # the Connections table has an error of its own: skip the ID checks
MANAGED_NOTE = "Managed systems:"  # the note under the Connections table, at the start of a line
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")  # a cell of a Markdown table's separator row: ---, :--, --:
PLAN_HEADINGS = ("## Goal", "## Stop conditions", "## Rollback", "## Log")
PLAN_NEEDED = {"planned", "in progress", "done"}
NETWORK_TOOLS = ("curl", "wget", "openssl", "govc", "ssh", "scp", "nc", "dig", "ovftool")
# Values that are explicit fixture placeholders. Only exact values count, not substrings.
FAKE_VALUES = {"not-a-real-password", "not-a-real-token", "not-a-real-secret", "redacted", "placeholder"}
SECRET_PATTERNS = [
    (re.compile(r"(?i)(?<![a-z])(password|passwd|secret|token)[a-z0-9_]*\s*[:=]\s*['\"]?([^'\"\s<$`]{6,})"),
     "a password or token value"),
    (re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b"), "a license key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "a private key"),
]
UNBOUNDED_WAIT_RE = re.compile(r"\buntil\b[^\n]*;\s*do\b|\bwhile\s+(true|:)\s*;\s*do\b")
TEST_TIMEOUT = 300
GIT_MIN_VERSION = (2, 36)          # `git worktree list --porcelain -z` came in Git 2.36
GIT_VERSION_RE = re.compile(r"^git version (\d+)\.(\d+)")
GIT_TIMEOUT = 30                   # seconds for each git call
LOCK_WAIT = 30                     # seconds `new` waits for another `new` to finish
LOCK_NAME = "ops-tasks-new.lock"   # in the clone's common git folder, shared by all its worktrees
LOCAL_LOCK = ".ops-tasks.lock"     # next to the marker, used outside git
LOCK_BUSY = "waiting for the lock held by another tasks.py new"
NULL_SHA_RE = re.compile(r"^0+$")  # the HEAD of a worktree without commits


# --- helpers ------------------------------------------------------------------------------------

class Layout:
    """The <ops-dir> of a repo: it holds the marker, tasks/ and the .env* files."""

    def __init__(self, root: Path, ops_dir: str = DEFAULT_OPS_DIR):
        self.root = root
        self.ops_dir = ops_dir
        self.ops = root / ops_dir
        self.marker = self.ops / MARKER
        self.tasks = self.ops / "tasks"
        self.lib = self.tasks / "lib"
        self.env = f"{ops_dir}/.env*"
        self.out_rule = f"/{ops_dir}/tasks/*/out/"
        self.env_rule = f"/{self.env}"

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def env_files(self) -> list:
        """The env files, symbolic links included (a broken one too): git ignores or tracks a link by its name."""
        return sorted(p for p in self.root.glob(self.env) if p.is_file() or p.is_symlink())


def find_ops_dir(root: Path):
    """ops/ if it holds the marker, else the first folder in the repo root, sorted by name, that does."""
    if (root / DEFAULT_OPS_DIR / MARKER).is_file():
        return DEFAULT_OPS_DIR
    for d in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name):
        if (d / MARKER).is_file():
            return d.name
    return None


def find_layout(root: Path) -> Layout:
    ops_dir = find_ops_dir(root)
    if ops_dir is None:
        raise SystemExit(f"No folder in {root} holds the marker {MARKER}. Run tasks.py init (it creates "
                         f"{DEFAULT_OPS_DIR}/{MARKER}), or tasks.py init --dir <name>.")
    return Layout(root, ops_dir)


def init_layout(root: Path, ops_dir: str = None) -> Layout:
    """The layout for init: the marked folder, else a new folder ops_dir (default ops). Writes nothing."""
    if ops_dir is not None and (not ops_dir or "/" in ops_dir or ops_dir in (".", "..", ".git")):
        raise SystemExit(f"Bad --dir '{ops_dir}': use the name of a folder directly in the repo root.")
    found = find_ops_dir(root)
    if found:
        if ops_dir and ops_dir != found:
            raise SystemExit(f"The marker is already in {found}/{MARKER}, so every command uses {found}/. "
                             f"Run tasks.py init without --dir, or move the marker first. Nothing was written.")
        return Layout(root, found)
    target = ops_dir or DEFAULT_OPS_DIR
    if (root / target).exists() or (root / target).is_symlink():
        raise SystemExit(f"{target}/ exists and has no {MARKER} marker: it may belong to the project. Nothing was "
                         f"written. Ask the user which folder to use:\n"
                         f"  a new folder:   tasks.py init --dir <name>   (creates <name>/ and its marker)\n"
                         f"  {target}/ itself, only if the user confirms it may hold tasks/ and .env*:\n"
                         f"                  touch {target}/{MARKER}, then tasks.py init")
    return Layout(root, target)


def git_toplevel(start: Path):
    """The git top-level folder that holds start, or None outside git.

    Stops when git cannot read the repository there (a broken config, unsafe ownership, a bare repo). Git
    also says "not a git repository" for damaged metadata (a missing HEAD) and for a wrong GIT_DIR, so that
    answer means "outside git" only when nothing points to a repo (see repo_evidence). The same holds when
    git is missing."""
    try:
        proc = run_git(["rev-parse", "--show-toplevel"], cwd=start, env={"LC_ALL": "C", "LANGUAGE": ""})
    except GitMissing:
        if repo_evidence(start):
            raise
        return None
    out, err = os.fsdecode(proc.stdout).strip(), os.fsdecode(proc.stderr).strip()
    if proc.returncode == 0 and out:
        return Path(out)
    if proc.returncode != 0 and "not a git repository" in err:
        why = repo_evidence(start)
        if why is None:
            return None
        err = f"{err} ({why})"
    raise SystemExit(f"git cannot read the repository at {start}: {err or 'no output'}. Nothing was written.")


GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")


def repo_evidence(start: Path):
    """Why start may be in a git repo although git found none, or None: a git location variable is set,
    or start or a folder above it (by its given and by its physical path) holds a `.git` entry of any
    type, a broken symbolic link included. A folder that cannot be checked counts as evidence."""
    for var in GIT_LOCATION_VARS:
        if os.environ.get(var):
            return f"{var} is set"
    folders = []
    for p in (Path(os.path.abspath(start)), Path(os.path.realpath(start))):
        folders += [p] + list(p.parents)
    for d in dict.fromkeys(folders):
        try:
            os.lstat(d / ".git")
            return f"{d / '.git'} exists"
        except FileNotFoundError:
            continue
        except OSError as e:
            return f"cannot check {d / '.git'}: {e.strerror}"
    return None


def task_dirs(lay: Layout):
    if not lay.tasks.is_dir():
        return []
    return sorted(d for d in lay.tasks.iterdir() if d.is_dir() and TASK_DIR_RE.match(d.name))


# --- git: worktrees, branches and the task numbers they use ---------------------------------------

class ScanError(Exception):
    """A place that may hold task numbers could not be read, so the numbers in use are unknown."""


class GitMissing(SystemExit):
    """git is not installed or not on PATH."""


# GIT_NO_LAZY_FETCH stops a partial clone from fetching missing objects (Git 2.45 or later); older Git
# ignores it, so `new` refuses to scan a partial clone there. The other two keep git from prompting
# and from writing optional locks.
GIT_RUN_ENV = {"GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
GIT_NO_LAZY_FETCH_VERSION = (2, 45)


def run_git(args: list, cwd=None, input_bytes: bytes = None, env: dict = None) -> subprocess.CompletedProcess:
    """Run git with a time limit, no terminal input and no lazy fetch; output stays bytes. Stops when git hangs."""
    cmd = ["git"] + (["-C", str(cwd)] if cwd is not None else []) + list(args)
    extra = {"input": input_bytes} if input_bytes is not None else {"stdin": subprocess.DEVNULL}
    try:
        return subprocess.run(cmd, capture_output=True, timeout=GIT_TIMEOUT,
                              env=dict(os.environ, **GIT_RUN_ENV, **(env or {})), **extra)
    except FileNotFoundError:
        raise GitMissing("git is not installed or not on PATH. Nothing was written.")
    except subprocess.TimeoutExpired:
        raise SystemExit(f"`git {args[0]}` did not finish within {GIT_TIMEOUT} s. Nothing was written.")


def same_path(a, b) -> bool:
    """True if a and b name the same physical folder (symbolic links and other aliases resolved)."""
    return os.path.realpath(a) == os.path.realpath(b)


def in_git(root: Path) -> bool:
    """True if root is the top-level folder of a git worktree; False for a --root folder outside git.
    Stops for a folder inside a repo that is not its top level, and when git cannot read the repo."""
    top = git_toplevel(root)
    if top is None:
        return False
    if not same_path(top, root):
        raise SystemExit(f"{root} is inside the git repo {top} but is not its top level. Pass the top level "
                         "as --root, or a folder outside git. Nothing was written.")
    return True


def is_partial_clone(root: Path) -> bool:
    """True if the clone has a promisor remote, so reading a missing object could fetch it."""
    for args in (["config", "--get", "extensions.partialClone"],
                 ["config", "--bool", "--get-regexp", r"^remote\..*\.promisor$"]):
        proc = run_git(args, cwd=root)
        if proc.returncode not in (0, 1):
            raise SystemExit(f"`git {' '.join(args)}` failed: {os.fsdecode(proc.stderr).strip()}")
        out = os.fsdecode(proc.stdout).split()
        if args[1] == "--get" and out or args[1] == "--bool" and "true" in out:
            return True
    return False


def task_names_in(root, ops_dir: str) -> list:
    """The names in root/<ops_dir>/tasks that look like task folders, of any file type; [] when that path
    does not exist (for example outside a sparse checkout). A broken symbolic link, a part of the path that
    is not a folder, or a read error raises ScanError: the path may hide tasks."""
    path = Path(root)
    for part in (ops_dir, "tasks"):
        path = path / part
        try:
            os.lstat(path)
        except FileNotFoundError:
            return []
        except OSError as e:
            raise ScanError(f"cannot read {path}: {e.strerror}")
        try:
            mode = os.stat(path).st_mode  # follows a symbolic link; a broken one raises here
        except OSError as e:
            raise ScanError(f"cannot read {path}: {e.strerror}")
        if not stat.S_ISDIR(mode):
            raise ScanError(f"{path} is not a folder")
    try:
        with os.scandir(path) as entries:
            return sorted(e.name for e in entries if TASK_DIR_RE.match(e.name))
    except OSError as e:
        raise ScanError(f"cannot list {path}: {e.strerror}")


def parse_git_version(text: str):
    """(major, minor) from `git --version` output such as 'git version 2.39.5 (Apple Git-154)', else None."""
    m = GIT_VERSION_RE.match(text.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def require_git_version(cmd: str):
    """Stop unless Git is 2.36 or later: the worktree checks of cmd need `git worktree list --porcelain -z`."""
    need = ".".join(map(str, GIT_MIN_VERSION))
    proc = run_git(["--version"])
    text = os.fsdecode(proc.stdout).strip()
    version = parse_git_version(text) if proc.returncode == 0 else None
    if version is None:
        why = "`git --version` failed" if proc.returncode else f"`git --version` printed {text!r}"
        raise SystemExit(f"tasks.py {cmd} could not read the Git version: {why}. It needs Git {need} or later. "
                         "Nothing was written.")
    if version < GIT_MIN_VERSION:
        raise SystemExit(f"tasks.py {cmd} needs Git {need} or later for its worktree checks; this is "
                         f"{text}. Update Git. Nothing was written.")
    return version


def git_common_dir(root: Path) -> str:
    proc = run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root)
    if proc.returncode != 0:
        raise SystemExit(f"Could not find the git folder of {root}: {os.fsdecode(proc.stderr).strip()}")
    return os.fsdecode(proc.stdout).strip()


def list_worktrees(root: Path) -> list:
    """The clone's registered worktrees, the main one first: dicts with path, head, bare, locked, lock_reason."""
    proc = run_git(["worktree", "list", "--porcelain", "-z"], cwd=root)
    if proc.returncode != 0:
        raise ScanError(f"`git worktree list` failed: {os.fsdecode(proc.stderr).strip()}")
    trees, cur = [], None
    for field in proc.stdout.split(b"\0"):
        if not field:  # an empty field ends a record
            cur = None
            continue
        key, _, value = field.partition(b" ")
        key, value = key.decode("ascii", "replace"), os.fsdecode(value)
        if key == "worktree":
            cur = {"path": value, "head": None, "bare": False, "locked": False, "lock_reason": ""}
            trees.append(cur)
        elif cur is None:
            continue
        elif key == "HEAD":
            cur["head"] = value
        elif key == "bare":
            cur["bare"] = True
        elif key == "locked":
            cur["locked"], cur["lock_reason"] = True, value
    return trees


def check_worktree_folder(path: str, common: str):
    """Raise ScanError unless the folder at path is a worktree of the clone whose common git folder is common."""
    proc = run_git(["rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"], cwd=path)
    lines = os.fsdecode(proc.stdout).splitlines()
    if proc.returncode != 0 or len(lines) != 2 or not same_path(lines[0], path) or not same_path(lines[1], common):
        raise ScanError(f"{path} is registered as a worktree of this clone, but the folder there is not that "
                        "worktree (an empty mount point of a disk that is not mounted?)")


def committed_task_names(root: Path, ops_dir: str, commits: list) -> set:
    """The task folder names in <ops_dir>/tasks of each commit. Each distinct tree is listed once."""
    path = f"{ops_dir}/tasks"
    if not commits:
        return set()
    proc = run_git(["cat-file", "--batch-check"], cwd=root,
                   input_bytes="".join(f"{c}:{path}\n" for c in commits).encode())
    lines = os.fsdecode(proc.stdout).splitlines()
    if proc.returncode != 0 or len(lines) != len(commits):
        raise ScanError(f"`git cat-file --batch-check` failed: {os.fsdecode(proc.stderr).strip()}")
    trees = set()
    for commit, line in zip(commits, lines):
        parts = line.split()
        if line == f"{commit}:{path} missing":
            # Either the commit has no such folder, or one of its objects is missing: ls-tree tells them apart.
            check = run_git(["ls-tree", "-z", commit, "--", path], cwd=root)
            if check.returncode != 0 or check.stdout:
                raise ScanError(f"cannot read {path} in commit {commit[:12]}")
        elif len(parts) == 3 and parts[1] == "tree":
            trees.add(parts[0])
        elif len(parts) != 3:  # a blob or another type at that path holds no tasks; anything else is unexpected
            raise ScanError(f"unexpected answer from `git cat-file` for commit {commit[:12]}: {line}")
    names = set()
    for tree in sorted(trees):
        proc = run_git(["ls-tree", "-z", tree], cwd=root)
        if proc.returncode != 0:
            raise ScanError(f"cannot read the tree {tree[:12]} of {path}")
        for entry in filter(None, proc.stdout.split(b"\0")):
            meta, _, name = entry.partition(b"\t")
            if meta.split()[1:2] == [b"tree"]:
                names.add(os.fsdecode(name))
    return names


def scan_tasks(lay: Layout, notes: list, common: str = None) -> tuple:
    """The task numbers in use, and the slugs of task folders on disk, in this clone.

    It reads the task folders on disk in this tree. With common (the clone's common git folder) it
    also reads the task folders on disk in every registered worktree, and the committed <ops-dir>/tasks
    of every worktree HEAD and of every local and remote-tracking branch. It reads only the current
    <ops-dir> name, never fetches, and raises ScanError when a place cannot be read."""
    numbers, slugs = set(), {}

    def add(name: str, where: str = None):
        m = TASK_DIR_RE.match(name)
        if m:
            numbers.add(int(m.group(1)))
            if where is not None:
                slugs.setdefault(m.group(2), where)

    for name in task_names_in(lay.root, lay.ops_dir):
        add(name, f"{lay.ops_dir}/tasks/{name}")
    if common is None:
        return numbers, slugs
    commits = set()
    for wt in list_worktrees(lay.root):
        if wt["head"] and not NULL_SHA_RE.match(wt["head"]):
            commits.add(wt["head"])
        if wt["bare"] or same_path(wt["path"], lay.root):
            continue
        try:
            os.lstat(wt["path"])
        except FileNotFoundError:
            if wt["locked"]:
                reason = f" ({wt['lock_reason']})" if wt["lock_reason"] else ""
                raise ScanError(f"the worktree {wt['path']} is missing and locked{reason}: its disk may not be "
                                "mounted, and its uncommitted tasks may use numbers. Mount the disk, or, once the "
                                "worktree is gone for good, unlock it and run `git worktree prune`")
            notes.append(f"the worktree {wt['path']} is missing; only its last commit was scanned, so the numbers "
                         "and slugs of its uncommitted tasks can be reused. Reconnect its disk if the worktree is "
                         "still needed; run `git worktree prune` only after confirming that it is gone for good")
            continue
        except OSError as e:
            raise ScanError(f"cannot read the worktree {wt['path']}: {e.strerror}")
        check_worktree_folder(wt["path"], common)
        for name in task_names_in(wt["path"], lay.ops_dir):
            add(name, str(Path(wt["path"]) / lay.ops_dir / "tasks" / name))
    proc = run_git(["for-each-ref", "--format=%(objecttype) %(objectname)", "refs/heads", "refs/remotes"],
                   cwd=lay.root)
    if proc.returncode != 0:
        raise ScanError(f"`git for-each-ref` failed: {os.fsdecode(proc.stderr).strip()}")
    for line in os.fsdecode(proc.stdout).splitlines():
        kind, _, sha = line.partition(" ")
        if kind == "commit":
            commits.add(sha)
    for name in committed_task_names(lay.root, lay.ops_dir, sorted(commits)):
        add(name)
    return numbers, slugs


@contextlib.contextmanager
def new_lock(path: Path):
    """Hold an exclusive lock on path while one `new` scans and creates its folder. Waits up to LOCK_WAIT."""
    try:
        import fcntl
    except ImportError:
        raise SystemExit("tasks.py new needs a system with fcntl (macOS or Linux) for its lock.")
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as e:
        raise SystemExit(f"Cannot open the lock file {path}: {e.strerror}. Nothing was written.")
    try:
        deadline, told = time.monotonic() + LOCK_WAIT, False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not told:
                    print(LOCK_BUSY, file=sys.stderr, flush=True)
                    told = True
                if time.monotonic() >= deadline:
                    raise SystemExit(f"Another tasks.py new held the lock {path} for more than {LOCK_WAIT} s. "
                                     "Nothing was written. Run new again when it has finished.")
                time.sleep(0.1)
        yield
    finally:
        os.close(fd)  # closing the file releases the lock


def lines_outside_fences(text: str):
    """Yield (line_no, line) for lines outside fenced code blocks."""
    fence = None  # (character, length) of the open fence
    for no, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                continue
            yield no, line
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                and not line.strip()[len(m.group(1)):].strip():
            fence = None


def fences(text: str):
    """Yield (line_no, info) for each opening code fence; info is the language label, maybe empty."""
    fence = None
    for no, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                yield no, m.group(2).strip().split(" ")[0].lower()
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not m.group(2).strip():
            fence = None


def active_checkboxes(text: str):
    """Yield (line_no, checked) for checkboxes outside code fences and outside '## Not used'."""
    in_not_used = False
    for no, line in lines_outside_fences(text):
        if line.startswith("## "):
            in_not_used = line.strip().lower() == "## not used"
        if in_not_used:
            continue
        m = CHECKBOX_RE.match(line)
        if m:
            yield no, m.group(1).lower() == "x"


def read_status(todo: Path):
    text = todo.read_text() if todo.exists() else ""
    m = STATUS_RE.search("\n".join(text.splitlines()[:12]))
    d = DEADLINE_RE.search(text)
    return (m.group(1) if m else None), (d.group(1).strip() if d else "none")


# --- init ---------------------------------------------------------------------------------------

def has_rule(gitignore: Path, accepted) -> bool:
    """True if .gitignore has one of the accepted rules as a real line (not in a comment)."""
    if not gitignore.exists():
        return False
    return any(line.strip() in accepted for line in gitignore.read_text().splitlines())


def has_out_rule(lay: Layout) -> bool:
    return has_rule(lay.root / ".gitignore", (lay.out_rule, lay.out_rule.rstrip("/")))


def is_ignored(lay: Layout, rel: str, rules_only: bool = False) -> bool:
    """True if git ignores rel, so wider patterns such as .env* count. A tracked file is not ignored,
    unless rules_only. Outside git: True if .gitignore has a line naming rel itself or the env pattern.
    Inside a repo, a failing `git check-ignore` stops tasks.py instead of falling back to that text check."""
    cmd = ["check-ignore", "-q"] + (["--no-index"] if rules_only else []) + [rel]
    try:
        proc = run_git(cmd, cwd=lay.root, env={"LC_ALL": "C", "LANGUAGE": ""})
    except GitMissing:
        if repo_evidence(lay.root):
            raise
        proc = None
    if proc is not None:
        if proc.returncode in (0, 1):
            return proc.returncode == 0
        err = os.fsdecode(proc.stderr).strip()
        if "not a git repository" not in err or repo_evidence(lay.root):
            raise SystemExit(f"`git check-ignore` failed for {rel}: {err or 'no output'}. Nothing was written.")
    return has_rule(lay.root / ".gitignore", (rel, f"/{rel}", lay.env, lay.env_rule))


def env_rule_needed(lay: Layout) -> bool:
    """True if the env pattern itself is not ignored: git matches the pattern text like a file name."""
    return not is_ignored(lay, lay.env, rules_only=True)


def env_files_not_ignored(lay: Layout) -> list:
    return [p for p in lay.env_files() if not is_ignored(lay, lay.rel(p))]


def cmd_init(lay: Layout) -> list:
    """Install or update <ops-dir>/tasks/lib/ from the skill. Always overwrites. Returns the notice lines."""
    root, lib, gi = lay.root, lay.lib, lay.root / ".gitignore"
    targets = [lay.ops, lay.marker, lay.tasks, lib, gi] + [lib / n for n in LIB_FILES]
    links = [lay.rel(t) for t in targets if t.is_symlink()]
    if links:
        raise SystemExit(f"Refusing to write: {', '.join(links)} is a symbolic link. Nothing was written.")
    lib.mkdir(parents=True, exist_ok=True)
    created = not lay.marker.exists()
    if created:
        lay.marker.touch()
    lines = [f"{lay.rel(lib)}/ is installed from the ops-tasks plugin (cloud-simple/ops-tasks, plugins/ops-tasks/skills/ops-tasks/assets/lib/) and is overwritten on every init.",
             f"Changes made by hand in {lay.rel(lib)}/ are lost; make them in the plugin repo instead."]
    if created:
        lines.append(f"  created:     {lay.rel(lay.marker)} (marks {lay.ops_dir}/ as the folder for tasks/ and .env*)")
    changed = int(created)
    for name in LIB_FILES:
        src, dst = ASSETS / "lib" / name, lib / name
        new = src.read_text()
        if dst.exists() and dst.read_text() == new:
            lines.append(f"  unchanged:   {lay.rel(dst)}")
            continue
        lines.append(f"  {'overwritten' if dst.exists() else 'installed'}: {lay.rel(dst)}")
        dst.write_text(new)
        dst.chmod(0o755)
        changed += 1
    for rule, needed in ((lay.out_rule, not has_out_rule(lay)), (lay.env_rule, env_rule_needed(lay))):
        if not needed:
            continue
        text = gi.read_text() if gi.exists() else ""
        gi.write_text(text + ("" if not text or text.endswith("\n") else "\n") + rule + "\n")
        lines.append(f"  added '{rule}' to .gitignore")
    lines.append(f"Updated {changed} file(s)." + (f" Next: tasks.py lint --run-tests, then commit {lay.rel(lay.marker) + ' and ' if created else ''}{lay.rel(lib)}/."
                                                  if changed else ""))
    return lines


# --- new ----------------------------------------------------------------------------------------

def cmd_new(lay: Layout, slug: str, title: str = None, today: str = None, notes: list = None) -> Path:
    """Create the next task folder. The number is one above every number this clone uses (see scan_tasks);
    a lock keeps two `new` runs in the clone's worktrees from taking the same one. Warnings go to notes,
    or to stderr when notes is None."""
    if not SLUG_RE.match(slug):
        raise SystemExit(f"Bad slug '{slug}': use lowercase letters, digits and single hyphens.")
    common = None
    if in_git(lay.root):  # decided once: the lock and the scan use the same answer
        version = require_git_version("new")
        common = git_common_dir(lay.root)
        if version < GIT_NO_LAZY_FETCH_VERSION and is_partial_clone(lay.root):
            raise SystemExit("This clone is a partial clone, so reading a missing object could fetch it. In a "
                             "partial clone, tasks.py new needs Git 2.45 or later, which reads without fetching. "
                             "Nothing was written.")
        lock = Path(common) / LOCK_NAME
    else:
        lock = lay.ops / LOCAL_LOCK
    found = []
    with new_lock(lock):
        try:
            numbers, slugs = scan_tasks(lay, found, common)
        except ScanError as e:
            raise SystemExit(f"Incomplete scan: {e}. No task folder was created, because the task numbers in "
                             "use are unknown.")
        if slug in slugs:
            raise SystemExit(f"A task with the slug '{slug}' exists already: {slugs[slug]}. To continue that "
                             "task, work in its folder; do not create it again.")
        target = lay.tasks / f"{max(numbers, default=0) + 1:02d}-{slug}"
        if target.exists():
            raise SystemExit(f"{target} exists already. Nothing was written.")
        title = title or slug.replace("-", " ").capitalize()
        today = today or dt.date.today().isoformat()
        if not lay.lib.is_dir():
            print("\n".join(cmd_init(lay)))
        target.mkdir()
        try:
            for name in ("TODO.md", "PLAN.md"):
                text = (ASSETS / name).read_text()
                text = text.replace("{{TITLE}}", title).replace("{{DATE}}", today)
                (target / name).write_text(text)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
    for note in found:
        if notes is None:
            print(f"WARN  {note}", file=sys.stderr)
        else:
            notes.append(note)
    return target


# --- link-env: the main checkout's env files in a linked worktree --------------------------------

class LinkEnvError(Exception):
    """The main checkout cannot serve as the source of the env files; the message names the cause."""


def env_entries(ops: Path) -> dict:
    """{name: path} of the .env* entries in the folder ops, of any type, broken links included."""
    try:
        with os.scandir(ops) as entries:
            return {e.name: Path(e.path) for e in entries if e.name.startswith(".env")}
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise LinkEnvError(f"cannot list {ops}: {e.strerror}")


def env_source_problem(path: Path):
    """None when path is a regular file with read access, or a symbolic link to one; else why it is not
    usable. Checks the file type and the read permission only; it never opens the file."""
    try:
        mode = os.stat(path).st_mode
    except FileNotFoundError:
        return "a broken symbolic link"
    except OSError as e:
        return f"not checkable ({e.strerror})"
    if stat.S_ISDIR(mode):
        return "a folder"
    if not stat.S_ISREG(mode):
        return "not a regular file"
    return None if os.access(path, os.R_OK) else "not readable"


def entry_path(path) -> str:
    """path with its folders resolved but its last part kept, so a symbolic link names itself, not its target.

    The folders are resolved as the filesystem reads them: each symbolic link first, then any `..` after
    it. Normalizing `..` away first (as os.path.abspath does) could name a different file."""
    path = os.fspath(path)
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    head, tail = os.path.split(path)
    if tail in ("", ".", ".."):
        return os.path.realpath(path)
    return os.path.join(os.path.realpath(head), tail)


def env_link_state(dest: Path, source) -> str:
    """missing, linked (a link to the source entry itself), other-link, broken-link, file or other.

    A link counts as linked only when its target is the source entry, compared with the folders resolved
    but not the source's own last link: a link straight to the file that the source points to would miss
    a later change of the source link."""
    try:
        mode = os.lstat(dest).st_mode
    except FileNotFoundError:
        return "missing"
    if stat.S_ISLNK(mode):
        target = os.path.join(os.path.dirname(dest), os.readlink(dest))
        if source is not None and entry_path(target) == entry_path(source):
            return "linked" if os.path.exists(dest) else "broken-link"
        return "other-link" if os.path.exists(dest) else "broken-link"
    return "file" if stat.S_ISREG(mode) else "other"


def env_link_rows(lay: Layout):
    """In a linked worktree: (the main checkout's <ops-dir>, rows), with one row (name, source or None,
    source problem or None, destination state) per .env* name on either side. None in the main checkout.
    Raises LinkEnvError when the main checkout cannot serve as the source."""
    proc = run_git(["rev-parse", "--path-format=absolute", "--git-dir"], cwd=lay.root)
    if proc.returncode != 0:
        raise LinkEnvError(f"`git rev-parse --git-dir` failed: {os.fsdecode(proc.stderr).strip()}")
    common = git_common_dir(lay.root)
    if same_path(os.fsdecode(proc.stdout).strip(), common):
        return None
    try:
        trees = list_worktrees(lay.root)
    except ScanError as e:
        raise LinkEnvError(str(e))
    if not trees:
        raise LinkEnvError("`git worktree list` names no main checkout")
    main = trees[0]
    if main["bare"]:
        raise LinkEnvError("the main repo of this clone is bare, so it has no env files")
    try:
        os.lstat(main["path"])
        check_worktree_folder(main["path"], common)
        main_ops = find_ops_dir(Path(main["path"]))
    except FileNotFoundError:
        raise LinkEnvError(f"the main checkout {main['path']} is missing")
    except OSError as e:
        raise LinkEnvError(f"cannot read the main checkout {main['path']}: {e.strerror}")
    except ScanError as e:
        raise LinkEnvError(str(e))
    if main_ops is None:
        raise LinkEnvError(f"the main checkout {main['path']} has no {MARKER} marker")
    src_dir = Path(main["path"]) / main_ops  # its own <ops-dir>, which may differ from this worktree's
    sources, dests = env_entries(src_dir), env_entries(lay.ops)
    rows = []
    for name in sorted(set(sources) | set(dests)):
        source = sources.get(name)
        try:
            state = env_link_state(lay.ops / name, source)
        except OSError as e:
            raise LinkEnvError(f"cannot read {lay.rel(lay.ops / name)}: {e.strerror}")
        rows.append((name, source, env_source_problem(source) if source else None, state))
    return src_dir, rows


def env_link_warning(name: str, source, problem, state: str):
    """What is wrong with one row and how to fix it, or None for a link to a usable source."""
    if source is None:
        if state in ("other-link", "broken-link"):
            return "its source is gone from the main checkout; remove the link"
        return "exists only in this worktree and is deleted with it; create env files in the main checkout"
    if problem:
        return f"its source {source} in the main checkout is {problem}; repair or remove the source there"
    return {
        "missing": f"missing; run tasks.py link-env to link {source}",
        "linked": None,
        "other-link": f"a link that does not point to {source}; remove the link, then run tasks.py link-env",
        "broken-link": f"a broken link instead of a link to {source}; remove it, then run tasks.py link-env",
        "file": f"a copy of {source}, which goes stale after a credential change; check that it holds nothing "
                "you need, remove it, then run tasks.py link-env",
        "other": f"a folder or another entry where the link to {source} belongs",
    }[state]


def is_tracked(lay: Layout, rel: str) -> bool:
    """True if git tracks rel. `git ls-files --error-unmatch` exits 1 for an untracked path; any other
    failure (a corrupt index, for example) stops tasks.py."""
    proc = run_git(["ls-files", "--error-unmatch", "--", rel], cwd=lay.root, env={"LC_ALL": "C", "LANGUAGE": ""})
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    raise SystemExit(f"`git ls-files` failed for {rel}: {os.fsdecode(proc.stderr).strip() or 'no output'}. "
                     "Nothing was written.")


def cmd_link_env(lay: Layout) -> tuple:
    """Link each usable .env* file of the main checkout that this linked worktree lacks. Returns
    (lines, warnings). It writes symbolic links only, never replaces an entry and never reads an env file."""
    if not in_git(lay.root):
        raise SystemExit("tasks.py link-env needs a git repo: it links the main checkout's env files into a "
                         "linked worktree. Nothing was written.")
    require_git_version("link-env")
    try:
        found = env_link_rows(lay)
    except LinkEnvError as e:
        raise SystemExit(f"tasks.py link-env cannot link here: {e}. Nothing was written.")
    if found is None:
        raise SystemExit("This is the main checkout, which holds the env files. Run tasks.py link-env in a "
                         "linked worktree (one made by git worktree add). Nothing was written.")
    src_dir, rows = found
    if lay.ops.is_symlink():
        raise SystemExit(f"Refusing to write: {lay.rel(lay.ops)} is a symbolic link. Nothing was written.")
    for name, *_ in rows:
        rel = f"{lay.ops_dir}/{name}"
        if is_tracked(lay, rel):
            raise SystemExit(f"git tracks {rel}: an env file must stay out of git. Remove it from git with "
                             f"`git rm --cached {rel}` as its own change. Nothing was written.")
        if not is_ignored(lay, rel, rules_only=True):
            raise SystemExit(f"git does not ignore {rel}. Run tasks.py init as its own change to add "
                             f"'{lay.env_rule}' to .gitignore. Nothing was written.")
    lines, warnings = [], []
    for name, source, problem, state in rows:
        rel = f"{lay.ops_dir}/{name}"
        if source is not None and problem is None and state == "missing":
            try:
                os.symlink(os.path.abspath(source), lay.ops / name)
            except FileExistsError:
                warnings.append(f"{rel}: appeared while link-env ran; left as it is")
                continue
            lines.append(f"  linked: {rel} -> {source}")
        elif source is not None and problem is None and state == "linked":
            lines.append(f"  ok:     {rel}")
        else:
            warnings.append(f"{rel}: {env_link_warning(name, source, problem, state)}")
    if not rows:
        lines.append(f"The main checkout has no {src_dir.name}/.env* files.")
    return lines, warnings


# --- status -------------------------------------------------------------------------------------

def cmd_status(lay: Layout) -> list:
    rows = []
    for d in task_dirs(lay):
        status, deadline = read_status(d / "TODO.md")
        plan = d / "PLAN.md"
        boxes = list(active_checkboxes(plan.read_text())) if plan.exists() else []
        done = sum(1 for _, c in boxes if c)
        rows.append((d.name, status or "?", deadline, f"{done}/{len(boxes)}"))
    return rows


# --- lint ---------------------------------------------------------------------------------------

class Report:
    def __init__(self, root: Path):
        self.root, self.errors, self.warnings = root, [], []

    def error(self, path: Path, msg: str, line: int = None):
        self.errors.append(self._fmt(path, line, msg))

    def warn(self, path: Path, msg: str, line: int = None):
        self.warnings.append(self._fmt(path, line, msg))

    def _fmt(self, path, line, msg):
        rel = path.relative_to(self.root) if path.is_absolute() else path
        return f"{rel}{':' + str(line) if line else ''}: {msg}"


def lint_links(path: Path, text: str, rep: Report):
    for no, line in lines_outside_fences(text):
        line = re.sub(r"`[^`]*`", "", line)  # links inside inline code are examples
        for target in LINK_RE.findall(line):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            local = target.split("#", 1)[0]
            if local and not (path.parent / local).exists():
                rep.error(path, f"broken link '{target}'", no)


def lint_secrets(path: Path, text: str, rep: Report):
    for no, line in enumerate(text.splitlines(), 1):
        for pattern, what in SECRET_PATTERNS:
            for m in pattern.finditer(line):
                value = m.group(m.lastindex) if m.lastindex else m.group(0)
                if value.lower() in FAKE_VALUES:
                    continue
                rep.error(path, f"looks like {what}; secrets never go into <ops-dir>/tasks/: use the env file "
                                f"or the password manager named in ## Connections", no)


def lint_waits(path: Path, text: str, rep: Report):
    for no, line in enumerate(text.splitlines(), 1):
        if UNBOUNDED_WAIT_RE.search(line):
            rep.warn(path, "wait without a limit; use a bounded loop with a timeout message", no)


def split_ids(value: str) -> list:
    """IDs from 'vc, logsrv' or 'vc (repo .env; note)': the part before '(' or ';', comma-separated.
    Placeholders that start with '<' are skipped."""
    value = re.split(r"[(;]", value, maxsplit=1)[0]
    return [v.strip() for v in value.split(",") if v.strip() and not v.strip().startswith("<")]


def lint_connections(plan: Path, text: str, rep: Report):
    """Check the '## Connections' table and its 'Managed systems:' note. Returns the table's IDs,
    None when the plan has no such section, or TABLE_BROKEN when the table is missing or has the
    wrong columns (already reported)."""
    rows, notes, headings, in_section = [], [], [], False
    for no, line in lines_outside_fences(text):
        if line.startswith("## "):
            in_section = line.strip() == "## Connections"
            if in_section:
                headings.append(no)
            continue
        if not in_section:
            continue
        if line.lstrip().startswith("|"):
            rows.append((no, [c.strip() for c in line.strip().strip("|").split("|")]))
        elif line.startswith(MANAGED_NOTE):
            notes.append((no, line[len(MANAGED_NOTE):].strip()))
    if not headings:
        return None
    if len(headings) > 1:
        for no in headings[1:]:
            rep.error(plan, f"## Connections appears more than once (first on line {headings[0]}): "
                            "keep one Connections section", no)
        return TABLE_BROKEN
    if not rows:
        rep.error(plan, "## Connections has no table")
        return TABLE_BROKEN
    (head_no, head), body = rows[0], [r for r in rows[1:] if not all(SEPARATOR_CELL_RE.match(c) for c in r[1])]
    if tuple(head) != CONNECTION_COLUMNS:
        rep.error(plan, "Connections columns must be: " + " | ".join(CONNECTION_COLUMNS), head_no)
        return TABLE_BROKEN
    ids, real = {}, False
    for no, cells in body:
        if cells[0].startswith("<"):
            continue  # placeholder row from the template
        if len(cells) != len(CONNECTION_COLUMNS):
            rep.error(plan, f"Connections row needs {len(CONNECTION_COLUMNS)} cells", no)
            continue
        cid, kind = cells[0], cells[1]
        if not cid:
            rep.error(plan, "Connections row needs an ID", no)
            continue
        real = True
        if cid in ids:
            rep.error(plan, f"Connections ID '{cid}' is used twice (first on line {ids[cid]})", no)
        ids.setdefault(cid, no)
        if kind not in CONNECTION_KINDS:
            rep.error(plan, f"Connections '{cid}': Kind must be one of {', '.join(CONNECTION_KINDS)}", no)
    if real:
        lint_managed_note(plan, head_no, rows[-1][0], notes, rep)
    return set(ids)


def lint_managed_note(plan: Path, head_no: int, last_row_no: int, notes: list, rep: Report):
    """A Connections table with a real row needs one answered 'Managed systems:' line after the
    table, in the Connections section. lint checks that someone answered, not that the answer is true."""
    after = [(no, value) for no, value in notes if no > last_row_no]
    for no, _ in notes:
        if no < last_row_no:
            rep.error(plan, f"'{MANAGED_NOTE}' must follow the Connections table", no)
    if not after:
        if not notes:
            rep.error(plan, f"## Connections has rows but no '{MANAGED_NOTE}' line after the table: name the "
                            "repo and pipeline for each managed system, or write none or unknown", head_no)
        return
    (first_no, value), rest = after[0], after[1:]
    for no, _ in rest:
        rep.error(plan, f"'{MANAGED_NOTE}' appears more than once (first on line {first_no})", no)
    if not value:
        rep.error(plan, f"'{MANAGED_NOTE}' has no answer", first_no)
    elif value.startswith("<"):
        rep.error(plan, f"'{MANAGED_NOTE}' still holds the template text; write the answer", first_no)


def check_ids(path: Path, where: str, names: list, ids, rep: Report, no=None):
    if ids is TABLE_BROKEN:
        return
    for n in names:
        if n == "none":
            continue
        if ids is None:
            rep.error(path, f"{where} names '{n}', but PLAN.md has no ## Connections table", no)
        elif n not in ids:
            rep.error(path, f"{where} names '{n}', which is not an ID in ## Connections", no)


def lint_plan_structure(plan: Path, text: str, rep: Report, ids=None):
    """Step IDs, phases, After boxes and fence labels.

    Steps live in the execution area: `## Steps` and `## Phase N` sections. Headings elsewhere
    (Rollback, Not used, Log) are procedures or archive and are not checked as steps."""
    seen, area, phase, step = {}, False, None, None

    def close_step():
        if not step:
            return
        for no in step["misplaced"]:
            rep.error(plan, f"step {step['id']}: the 'After check passed' box belongs in the **After** part", no)
        if step["do"] and len(step["after_boxes"]) != 1:
            rep.error(plan, f"step {step['id']} has a **Do:** part and needs exactly one 'After check passed' "
                            f"box in its **After** part (found {len(step['after_boxes'])})", step["line"])

    for no, line in lines_outside_fences(text):
        if line.startswith("## "):
            close_step()
            step = None
            m = PHASE_RE.match(line)
            phase = int(m.group(1)) if m else None
            area = bool(m) or line.strip() == "## Steps"
            continue
        if not area:
            continue
        if line.startswith("### "):
            close_step()
            m = STEP_RE.match(line)
            if not m:
                rep.error(plan, "step heading must be '### N.M <title>'", no)
                step = None
                continue
            sid = f"{m.group(1)}.{m.group(2)}"
            if sid in seen:
                rep.error(plan, f"step ID {sid} is used twice (first on line {seen[sid]})", no)
            seen.setdefault(sid, no)
            if phase is not None and int(m.group(1)) != phase:
                rep.error(plan, f"step {sid} sits in '## Phase {phase}'; its ID must start with {phase}.", no)
            step = {"id": sid, "line": no, "do": False, "in_after": False, "after_boxes": [], "misplaced": []}
            continue
        if not step:
            continue
        m = USES_RE.match(line)
        if m:
            check_ids(plan, f"step {step['id']}: Uses:", split_ids(m.group(1)), ids, rep, no)
        if line.strip() == "**Do:**":
            step["do"], step["in_after"] = True, False
        elif line.strip().startswith("**After**"):
            step["in_after"] = True
        if AFTER_BOX_RE.match(line):
            step["after_boxes" if step["in_after"] else "misplaced"].append(no)
    close_step()
    for no, lang in fences(text):
        if lang in BAD_FENCE_LANGS:
            rep.warn(plan, "fence plan commands as ```bash (other content: name its language, e.g. text or ini)", no)


def lint_shebang(script: Path, rep: Report):
    first = script.read_text().splitlines()[:1]
    if first != [BASH_SHEBANG]:
        rep.error(script, f"first line must be {BASH_SHEBANG}")


def lint_script(script: Path, rep: Report):
    if script.suffix == ".py":
        rep.error(script, "helpers are bash scripts (NN-verb-object.sh)")
        return
    if not SCRIPT_RE.match(script.name):
        rep.error(script, "helper name must be NN-verb-object.sh")
    lint_shebang(script, rep)
    if not os.access(script, os.X_OK):
        rep.error(script, "helper is not executable (chmod +x)")
    text = script.read_text()
    head = "\n".join(text.splitlines()[:20])
    for field in HEADER_FIELDS:
        if field not in head:
            rep.error(script, f"header lacks '{field}'")
    effect = re.search(r"Effect:\s*(\S+)", head)
    if effect and not effect.group(1).lower().startswith(("read-only", "changes")):
        rep.error(script, "Effect must start with 'read-only' or 'changes'")
    if effect and effect.group(1).lower().startswith("changes") and "--apply" not in text:
        rep.error(script, "a changing helper needs a dry run by default and an --apply flag")
    if "--test" not in text:
        rep.error(script, "helper has no --test branch")
    if not (script.parent / "tests" / f"{script.stem}.json").exists():
        rep.error(script, f"no tests file scripts/tests/{script.stem}.json")
    for tool in NETWORK_TOOLS:
        if re.search(rf"(^|[\s;|&(\"'])/[\w./-]*/{tool}\b", text, re.M):
            rep.error(script, f"absolute path to '{tool}' bypasses the test stubs; call it by name")
    if re.search(r"/dev/(tcp|udp)/", text):
        rep.error(script, "/dev/tcp or /dev/udp opens network connections the tests cannot stub")
    remote = REMOTE_RE.search(head)
    if remote:
        lint_remote(script, text, head, remote.group(1), rep)
    lint_secrets(script, text, rep)
    lint_waits(script, text, rep)


def code_lines(text: str) -> list:
    """(line_no, code) for each line of a bash script that holds code, without its literal text.

    A small scanner, not a bash parser. It drops comments, here-document bodies, the content of
    single-quoted and $'...' strings and the text of double-quoted strings; each string stays as an
    empty pair of quotes. A command substitution, $(...) or `...`, runs, so its code stays as ( ... ),
    also inside double quotes and with its own quoted arguments. It knows here-strings (<<<),
    arithmetic ($(( )) and (( ))) and case patterns. Strings may span lines. Substitutions in the body
    of an unquoted here-document are not seen."""
    # stack: the open contexts: ' and $' strings, " string, ")" a $( ... ), ` a `...`, "(" a subshell,
    # "((" arithmetic, "case" a case statement
    out, stack, heredocs = [], [], []
    for no, line in enumerate(text.split("\n"), 1):
        if heredocs:
            strip_tabs, tag = heredocs[0]
            if (line.lstrip("\t") if strip_tabs else line) == tag:
                heredocs.pop(0)
            continue
        code, prev, j = [], " ", 0
        while j < len(line):
            c, top = line[j], (stack[-1] if stack else "")
            if top in ("'", "$'"):
                if c == "\\" and top == "$'":
                    j += 2
                    continue
                if c == "'":
                    stack.pop()
                    code.append("'")
                j += 1
                continue
            if top == '"':
                if c == "\\":
                    j += 2
                elif c == '"':
                    stack.pop()
                    code.append('"')
                    j += 1
                elif line.startswith("$(", j):
                    stack.append(")")
                    code.append("(")
                    j += 2
                elif c == "`":
                    stack.append("`")
                    code.append("(")
                    j += 1
                else:
                    j += 1
                continue
            # code: the top level, or inside $( ... ), ` ... `, ( ... ), (( ... )) or case ... esac
            if c == "#" and prev.isspace():
                break
            command_start = bool(COMMAND_START_RE.search("".join(code)))
            if line.startswith("<<<", j):  # here-string: its word follows, not a here-document
                code.append("<<<")
                j += 3
            elif line.startswith("<<", j) and "((" not in stack and HEREDOC_RE.match(line, j):
                heredoc = HEREDOC_RE.match(line, j)
                heredocs.append((heredoc.group(1) == "-", re.sub(r"['\"\\]", "", heredoc.group(2))))
                code.append(heredoc.group(0))
                j = heredoc.end()
            elif c == "\\":
                code.append(line[j:j + 2])
                j += 2
            elif line.startswith("$'", j):
                stack.append("$'")
                code.append("'")
                j += 2
            elif c in "'\"":
                stack.append(c)
                code.append(c)
                j += 1
            elif line.startswith("$((", j) or (line.startswith("((", j) and command_start):
                stack.append("((")
                code.append("((")
                j += 3 if c == "$" else 2
            elif line.startswith("$(", j):
                stack.append(")")
                code.append("(")
                j += 2
            elif c == "`":
                if top == "`":
                    stack.pop()
                    code.append(")")
                else:
                    stack.append("`")
                    code.append("(")
                j += 1
            elif c == "(":
                stack.append("(")
                code.append(c)
                j += 1
            elif c == ")":
                if top == "((" and line.startswith("))", j):
                    stack.pop()
                    code.append("))")
                    j += 2
                    prev = ")"
                    continue
                if top in ("(", ")"):
                    stack.pop()
                    code.append(c)
                else:
                    code.append(");" if top == "case" else c)  # a case pattern ends; a command follows
                j += 1
            elif command_start and re.match(r"case\s", line[j:]):
                stack.append("case")
                code.append("case")
                j += 4
            elif command_start and top == "case" and re.match(r"esac([\s;&|)`]|$)", line[j:]):
                stack.pop()
                code.append("esac")
                j += 4
            else:
                code.append(c)
                j += 1
            prev = code[-1][-1]
        joined = "".join(code).strip()
        if joined:
            out.append((no, joined))
    return out


def block_closes_early(text: str, first: int, last: int):
    """The line where the { ... } block opened on line `first` is already complete, before line `last`.

    bash -n parses the file cut after each line in between. A cut that parses would run the code before
    it, so it means the block closed there. Returns that line number, or None. Cuts inside a line are
    not checked."""
    lines = text.splitlines(keepends=True)
    for no in range(first, last):
        proc = subprocess.run(["bash", "-n"], input="".join(lines[:no]), capture_output=True, text=True)
        if proc.returncode == 0:
            return no
    return None


def lint_remote(script: Path, text: str, head: str, runs_on: str, rep: Report):
    """A remote helper runs on a system from Connections, without <ops-dir>/tasks/lib/ and the env file."""
    if not re.split(r"[(;]", runs_on, maxsplit=1)[0].strip():
        rep.error(script, "'Runs on: remote:' must name the Connections ID of the system the helper runs on")
    conn = CONNECTION_HEADER_RE.search(head)
    listed = split_ids(conn.group(1)) if conn else []
    for n in split_ids(runs_on):
        if n not in listed:
            rep.error(script, f"'Runs on: remote:' names '{n}', which 'Connection:' does not list")
    for no, line in code_lines(text):
        if REMOTE_FORBIDDEN_RE.search(line):
            rep.error(script, "a remote helper runs where <ops-dir>/tasks/lib/ and the env file do not exist: "
                              "do not source files or call with_timeout; use timeout there", no)
    # The block check reads the raw lines and asks bash, so a scanner mistake cannot cause it.
    one_block = ("a remote helper must put everything after its header in one { ... } block, with { and } on lines "
                 "of their own, so bash reads the whole file before it runs any of it")
    raw = [(no, line.strip()) for no, line in enumerate(text.splitlines(), 1)
           if line.strip() and not line.strip().startswith("#")]
    if not raw or not BLOCK_OPEN_RE.match(raw[0][1]) or not BLOCK_CLOSE_RE.match(raw[-1][1]):
        rep.error(script, one_block)
        return
    try:
        proc = subprocess.run(["bash", "-n"], input=text, capture_output=True, text=True)
        early = block_closes_early(text, raw[0][0], raw[-1][0]) if proc.returncode == 0 else None
    except OSError as exc:
        rep.error(script, f"cannot run bash -n to check the {{ ... }} block: {exc.strerror or exc}")
        return
    if proc.returncode != 0:
        rep.error(script, "bash -n: " + (proc.stderr.strip().splitlines() or ["syntax error"])[0])
    elif early:
        rep.error(script, f"the {{ ... }} block is already complete here, before the last line; {one_block}", early)


def lint_task(task: Path, rep: Report):
    if not TASK_DIR_RE.match(task.name):
        rep.error(task, "folder name must be NN-slug")
    todo, plan = task / "TODO.md", task / "PLAN.md"
    if not todo.exists():
        rep.error(task, "TODO.md is missing")
        status = None
    else:
        text = todo.read_text()
        if not text.startswith("# "):
            rep.error(todo, "first line must be the '# ' title")
        status, _ = read_status(todo)
        if status is None:
            rep.error(todo, "near the top: 'Status: <open|planned|in progress|done|dropped> (since YYYY-MM-DD)'")
        if not DEADLINE_RE.search(text):
            rep.error(todo, "no 'Deadline: YYYY-MM-DD' or 'Deadline: none' line")
        if plan.exists() and not PLAN_LINE_RE.search(text):
            rep.error(todo, "no 'Plan: [PLAN.md](PLAN.md)' line")
        for h in TODO_HEADINGS:
            if not re.search(rf"^{re.escape(h)}\s*$", text, re.M):
                rep.error(todo, f"heading '{h}' is missing")
        if len(text.splitlines()) > 80:
            rep.warn(todo, "TODO.md is long; move facts and procedures to PLAN.md")
        lint_links(todo, text, rep)
        lint_secrets(todo, text, rep)
    if plan.exists():
        text = plan.read_text()
        for h in PLAN_HEADINGS:
            if not re.search(rf"^{re.escape(h)}\s*$", text, re.M):
                rep.error(plan, f"heading '{h}' is missing")
        if status == "done":
            for no, checked in active_checkboxes(text):
                if not checked:
                    rep.error(plan, "task is done but this checkbox is open; tick it or move it to '## Not used'", no)
        ids = lint_connections(plan, text, rep)
        lint_plan_structure(plan, text, rep, ids)
        lint_links(plan, text, rep)
        lint_secrets(plan, text, rep)
        lint_waits(plan, text, rep)
    elif status in PLAN_NEEDED:
        rep.error(task, f"status is '{status}' but PLAN.md is missing")
    scripts = task / "scripts"
    if scripts.is_dir():
        for s in sorted(p for p in scripts.iterdir() if p.is_file() and not p.name.startswith(".")):
            lint_script(s, rep)
            if plan.exists() and s.suffix == ".sh":
                m = CONNECTION_HEADER_RE.search("\n".join(s.read_text().splitlines()[:20]))
                if m:
                    check_ids(s, "Connection:", split_ids(m.group(1)), ids, rep)


def _kill_session(sid: int) -> str:
    """Kill every process left in the session that a test run started. Returns an error or ''."""
    proc = subprocess.run(["ps", "-U", str(os.getuid()), "-o", "pid="], capture_output=True, text=True)
    if proc.returncode != 0:
        return f"cannot read the process list ({proc.stderr.strip() or 'ps failed'}); leftovers not checked"
    for s in proc.stdout.split():
        try:
            if int(s) != os.getpid() and os.getsid(int(s)) == sid:
                os.kill(int(s), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    return ""


def _reap(proc) -> tuple:
    """Kill the known process group of a test run, then collect its output within 10 s."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return "", ""


def run_tests(lay: Layout, tasks: list, rep: Report):
    root, lib, targets = lay.root, lay.lib, []
    if (lib / "stubtest.py").exists():
        targets.append([sys.executable, str(lib / "stubtest.py"), "--test"])
    if (lib / "with_timeout.sh").exists():
        targets.append(["bash", str(lib / "with_timeout.sh"), "--test"])
    for task in tasks:
        scripts = task / "scripts"
        if scripts.is_dir():
            for s in sorted(scripts.iterdir()):
                if s.is_file() and SCRIPT_RE.match(s.name):
                    targets.append([str(s), "--test"])
    for cmd in targets:
        label = Path(cmd[-2]).relative_to(root)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    cwd=root, stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            rep.error(label, f"--test could not start: {exc.strerror or exc}")
            continue
        try:
            out, err = proc.communicate(timeout=TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            problem = _kill_session(proc.pid)
            _reap(proc)  # kills the known group even when the process list is unreadable
            rep.error(label, f"--test gave no result within {TEST_TIMEOUT} s")
            if problem:
                rep.error(label, problem)
            continue
        problem = _kill_session(proc.pid)
        if problem:
            _reap(proc)
            rep.error(label, problem)
        print(f"--- {label} --test")
        print(out.rstrip())
        if proc.returncode != 0:
            tail = " | ".join(err.strip().splitlines()[-3:])
            rep.error(label, f"--test failed (exit {proc.returncode})" + (f": {tail}" if tail else ""))


def cmd_lint(lay: Layout, names: list, with_tests: bool) -> Report:
    rep = Report(lay.root)
    if not lay.tasks.is_dir():
        rep.error(lay.tasks, "missing; run tasks.py init")
        return rep
    all_tasks = task_dirs(lay)
    tasks = [t for t in all_tasks if not names or t.name in names]
    for n in names:
        if n not in [t.name for t in all_tasks]:
            rep.error(lay.tasks, f"no task folder '{n}'")
    for d in lay.tasks.iterdir():
        if d.is_dir() and d.name not in ("lib",) and not TASK_DIR_RE.match(d.name):
            rep.error(d, "folder name must be NN-slug (or 'lib' for shared code)")
    by_number = {}
    for t in all_tasks:
        by_number.setdefault(int(TASK_DIR_RE.match(t.name).group(1)), []).append(t.name)
    for names_with_one_number in by_number.values():
        if len(names_with_one_number) > 1:
            rep.warn(lay.tasks, f"{', '.join(names_with_one_number)} share one number. Keep both names: the slug "
                                "tells the tasks apart, and renaming a folder breaks links into it")
    for t in tasks:
        lint_task(t, rep)
    for name in LIB_FILES:
        dst = lay.lib / name
        if not dst.exists():
            rep.error(dst, "missing; run tasks.py init")
        elif dst.read_text() != (ASSETS / "lib" / name).read_text():
            rep.error(dst, f"differs from the skill's copy; run tasks.py init (it overwrites {lay.rel(lay.lib)}/)")
        elif name.endswith(".sh"):
            lint_shebang(dst, rep)
    if lay.marker.stat().st_size:
        rep.warn(lay.marker, "must be empty: it is only a marker")
    gi = lay.root / ".gitignore"
    if not has_out_rule(lay):
        rep.warn(gi, f"add '{lay.out_rule}' so captured state stays out of git")
    for f in env_files_not_ignored(lay):
        rep.error(f, f"not ignored by git: run tasks.py init to add '{lay.env_rule}' to .gitignore, "
                     "and `git rm --cached` the file if git tracks it")
    if env_rule_needed(lay):
        rep.warn(gi, f"add '{lay.env_rule}' so the connection settings and credentials stay out of git")
    if in_git(lay.root):
        require_git_version("lint")
        try:
            found = env_link_rows(lay)
        except LinkEnvError as e:
            rep.warn(lay.ops, f"env file links not checked: {e}")
            found = None
        for name, source, problem, state in (found[1] if found else []):
            msg = env_link_warning(name, source, problem, state)
            if msg:
                rep.warn(lay.ops / name, msg)
    if with_tests:
        run_tests(lay, tasks, rep)
    return rep


# --- self-tests ---------------------------------------------------------------------------------

class SelfTests(unittest.TestCase):
    # Keeps the user's git settings out of every test, including the code under test and the processes it
    # starts: every GIT_* variable is dropped, and git gets no global or system config. The real command
    # keeps the user's settings.
    GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def setUp(self):
        self.saved_env = dict(os.environ)
        for key in [k for k in os.environ if k.startswith("GIT_")]:
            del os.environ[key]
        os.environ.update(self.GIT_ENV)
        self.addCleanup(self.restore_env)
        self.tmp = tempfile.TemporaryDirectory(prefix="tasks-py-")
        self.root = Path(self.tmp.name)
        self.lay = Layout(self.root)
        self.tasks = self.lay.tasks
        self.tasks.mkdir(parents=True)
        (self.root / ".gitignore").write_text("/ops/tasks/*/out/\n")
        cmd_init(self.lay)

    def tearDown(self):
        self.tmp.cleanup()

    def restore_env(self):
        os.environ.clear()
        os.environ.update(self.saved_env)

    def make_good_task(self, name="01-demo", status="in progress"):
        t = self.tasks / name
        (t / "scripts" / "tests").mkdir(parents=True)
        (t / "TODO.md").write_text(textwrap.dedent(f"""\
            # Demo
            Status: {status} (since 2026-10-05)
            Deadline: 2026-10-09
            Plan: [PLAN.md](PLAN.md)
            ## Problem
            Something is wrong.
            ## Ideas
            - **Fix it:** cheap. Chosen
            """))
        (t / "PLAN.md").write_text(textwrap.dedent("""\
            # Plan: Demo
            ## Goal
            Fixed.
            ## Stop conditions
            - none
            ## Steps
            ### 1.1 Fix
            - [x] Did it
            - [ ] Check it
            ```bash
            - [ ] not a checkbox, inside a fence
            ```
            ## Rollback
            - Step 1: cannot be undone.
            ## Not used
            - [ ] Fallback that was not needed
            ## Log
            """))
        s = t / "scripts" / "01-check-demo.sh"
        s.write_text("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x [--test]\n# Effect: read-only\n"
                     "# Runs on: the Mac\n# Connection: none\n# Exit: 0 ok\n[[ \"${1:-}\" == --test ]] && exit 0\n")
        s.chmod(0o755)
        (t / "scripts" / "tests" / "01-check-demo.json").write_text('{"cases": []}')
        return t

    def test_new_numbers_after_the_highest(self):
        self.make_good_task("07-old")
        t = cmd_new(self.lay, "fresh-task", today="2026-10-05")
        self.assertEqual(t.name, "08-fresh-task")
        self.assertIn("Status: open (since 2026-10-05)", (t / "TODO.md").read_text())
        self.assertIn("# Plan: Fresh task", (t / "PLAN.md").read_text())

    def test_new_refuses_bad_or_duplicate_slugs(self):
        self.make_good_task("01-demo")
        for bad in ("Bad_Slug", "-x", "a--b", ""):
            with self.assertRaises(SystemExit):
                cmd_new(self.lay, bad)
        with self.assertRaises(SystemExit):
            cmd_new(self.lay, "demo")

    def test_find_the_ops_folder_by_its_marker(self):
        self.assertEqual(self.lay.marker.stat().st_size, 0)  # init created the empty marker
        self.assertEqual(find_layout(self.root).ops_dir, "ops")
        for name in ("infra", "app"):
            (self.root / name).mkdir()
            (self.root / name / MARKER).touch()
        self.assertEqual(find_layout(self.root).ops_dir, "ops")  # ops/ comes first
        self.lay.marker.unlink()
        self.assertEqual(find_layout(self.root).ops_dir, "app")  # else the first by name
        for name in ("infra", "app"):
            (self.root / name / MARKER).unlink()
        with self.assertRaises(SystemExit):
            find_layout(self.root)
        self.assertEqual(init_layout(self.root, "fresh").ops_dir, "fresh")

    def test_init_dir_and_an_existing_folder_without_the_marker(self):
        self.assertEqual(init_layout(self.root).ops_dir, "ops")
        self.assertEqual(init_layout(self.root, "ops").ops_dir, "ops")
        with self.assertRaises(SystemExit) as ctx:
            init_layout(self.root, "infra")  # the marker is in ops/
        self.assertIn("already in ops/.ops-tasks", str(ctx.exception))
        for bad in ("", ".", "..", ".git", "a/b", "/abs"):
            with self.assertRaises(SystemExit):
                init_layout(self.root, bad)
        self.lay.marker.unlink()
        for name in (None, "ops"):
            with self.assertRaises(SystemExit) as ctx:
                init_layout(self.root, name)  # ops/ exists without the marker
            self.assertIn("it may belong to the project", str(ctx.exception))
            self.assertIn("only if the user confirms", str(ctx.exception))
        self.assertFalse(self.lay.marker.exists())
        lay = init_layout(self.root, "infra")
        cmd_init(lay)
        self.assertEqual(find_layout(self.root).ops_dir, "infra")

    def test_status_counts_only_active_checkboxes(self):
        self.make_good_task()
        self.assertEqual(cmd_status(self.lay), [("01-demo", "in progress", "2026-10-09", "1/2")])

    def test_lint_accepts_a_good_task(self):
        self.make_good_task()
        rep = cmd_lint(self.lay, [], False)
        self.assertEqual(rep.errors, [])

    def test_lint_reports_broken_parts(self):
        t = self.make_good_task()
        (t / "TODO.md").write_text("# Demo\n## Problem\nx\nSee [plan](MISSING.md)\npassword: Hunter2Hunter2\n")
        (t / "scripts" / "01-check-demo.sh").chmod(0o644)
        (t / "scripts" / "run.sh").write_text("#!/bin/sh\n/usr/bin/curl http://x\n")
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        for expected in ("'Status: <open", "'## Ideas' is missing", "broken link 'MISSING.md'", "no 'Deadline:",
                         "no 'Plan: [PLAN.md](PLAN.md)' line",
                         "looks like a password", "not executable", "helper name must be",
                         "header lacks 'Purpose:'", "no --test branch", "absolute path to 'curl'"):
            self.assertIn(expected, joined)

    def test_lint_flags_open_boxes_in_a_done_task(self):
        self.make_good_task(status="done")
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("task is done but this checkbox is open", joined)
        self.assertNotIn("Fallback", joined)

    def test_lint_flags_a_changing_helper_without_apply(self):
        t = self.make_good_task()
        s = t / "scripts" / "02-delete-thing.sh"
        s.write_text("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: changes\n# Runs on: Mac\n# Connection: none\n# Exit: 0\n# --test\n")
        s.chmod(0o755)
        (t / "scripts" / "tests" / "02-delete-thing.json").write_text('{"cases": []}')
        self.assertIn("--apply flag", "\n".join(cmd_lint(self.lay, [], False).errors))

    def test_lint_ignores_fake_secrets_and_warns_on_unbounded_waits(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text() + "GOVC_PASSWORD='not-a-real-password'\n"
                        "until govc about; do sleep 5; done\n")
        rep = cmd_lint(self.lay, [], False)
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("wait without a limit" in w for w in rep.warnings))

    def test_lint_run_tests_reports_a_failing_helper(self):
        t = self.make_good_task()
        (t / "scripts" / "01-check-demo.sh").write_text(
            "#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: read-only\n# Runs on: Mac\n# Connection: none\n# Exit: 0\n"
            "[[ \"${1:-}\" == --test ]] && { echo 'FAIL demo'; echo 'boom' >&2; exit 1; }\n")
        rep = cmd_lint(self.lay, [], True)
        self.assertIn("--test failed (exit 1): boom", "\n".join(rep.errors))

    def test_lint_run_tests_reports_a_helper_that_cannot_start(self):
        t = self.make_good_task()
        (t / "scripts" / "01-check-demo.sh").chmod(0o644)
        rep = cmd_lint(self.lay, [], True)  # must not raise
        joined = "\n".join(rep.errors)
        self.assertIn("not executable", joined)
        self.assertIn("--test could not start", joined)

    def test_run_tests_timeout_with_an_unreadable_process_list(self):
        global TEST_TIMEOUT
        t = self.make_good_task()
        marker = self.root / "survived"
        (t / "scripts" / "01-check-demo.sh").write_text(
            "#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: read-only\n# Runs on: Mac\n# Connection: none\n# Exit: 0\n"
            f"[[ \"${{1:-}}\" == --test ]] && {{ sleep 1; echo survived > {marker}; }}\n")
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        (fakebin / "ps").write_text("#!/bin/sh\necho 'ps: Cannot get process list' >&2\nexit 1\n")
        (fakebin / "ps").chmod(0o755)
        old_path, old_timeout = os.environ["PATH"], TEST_TIMEOUT
        os.environ["PATH"], TEST_TIMEOUT = f"{fakebin}:{old_path}", 0.3
        t0 = time.time()
        try:
            rep = cmd_lint(self.lay, [], True)
        finally:
            os.environ["PATH"], TEST_TIMEOUT = old_path, old_timeout
        elapsed = time.time() - t0
        time.sleep(1.2)
        joined = "\n".join(rep.errors)
        self.assertIn("gave no result within 0.3 s", joined)
        self.assertIn("cannot read the process list", joined)
        self.assertLess(elapsed, 3)
        self.assertFalse(marker.exists())

    def test_init_installs_reports_and_overwrites(self):
        lib = self.tasks / "lib"
        self.assertEqual(sorted(p.name for p in lib.iterdir()), sorted(LIB_FILES))
        notice = "\n".join(cmd_init(self.lay))
        self.assertIn("unchanged:   ops/tasks/lib/stubtest.py", notice)
        self.assertIn("Updated 0 file(s).", notice)
        (lib / "with_timeout.sh").write_text("# edited by hand\n")
        notice = "\n".join(cmd_init(self.lay))
        self.assertIn("overwritten: ops/tasks/lib/with_timeout.sh", notice)
        self.assertIn("is overwritten on every init", notice)
        self.assertEqual((lib / "with_timeout.sh").read_text(), (ASSETS / "lib" / "with_timeout.sh").read_text())

    def test_init_adds_the_out_line_to_gitignore(self):
        (self.root / ".gitignore").write_text("/ops/.env*")
        cmd_init(self.lay)
        self.assertEqual((self.root / ".gitignore").read_text(), "/ops/.env*\n/ops/tasks/*/out/\n")

    def test_init_adds_the_env_rule_to_gitignore(self):
        (self.root / ".gitignore").write_text("/ops/tasks/*/out/\n")
        notice = "\n".join(cmd_init(self.lay))
        self.assertEqual((self.root / ".gitignore").read_text(), "/ops/tasks/*/out/\n/ops/.env*\n")
        self.assertIn("added '/ops/.env*' to .gitignore", notice)
        self.assertNotIn("added", "\n".join(cmd_init(self.lay)))  # a second run adds nothing

    def test_lint_checks_that_the_env_file_is_ignored(self):
        self.make_good_task()
        gi = self.root / ".gitignore"
        gi.write_text("/ops/tasks/*/out/\n")
        rep = cmd_lint(self.lay, [], False)
        self.assertEqual(rep.errors, [])  # no env file yet: a warning only
        self.assertTrue(any("add '/ops/.env*'" in w for w in rep.warnings))
        (self.root / "ops" / ".env").write_text("export GOVC_URL='https://vcenter.test.invalid'\n")
        self.assertIn("ops/.env: not ignored by git", "\n".join(cmd_lint(self.lay, [], False).errors))
        gi.write_text("/ops/tasks/*/out/\n/ops/.env*\n")
        rep = cmd_lint(self.lay, [], False)
        self.assertEqual(rep.errors, [])
        self.assertFalse(any(".env" in w for w in rep.warnings))

    def test_env_glob_covers_every_matching_file(self):
        lay = self.lay
        self.make_good_task()
        gi = self.root / ".gitignore"
        gi.write_text("/ops/tasks/*/out/\n/ops/.env.prod\n")
        for name in ("prod", "stage"):
            (self.root / "ops" / f".env.{name}").write_text("x=1\n")
        errors = "\n".join(cmd_lint(lay, [], False).errors)
        self.assertIn("ops/.env.stage: not ignored by git", errors)
        self.assertNotIn("ops/.env.prod:", errors)
        self.assertIn("added '/ops/.env*'", "\n".join(cmd_init(lay)))
        self.assertEqual(cmd_lint(lay, [], False).errors, [])

    def test_env_ignored_by_a_git_pattern_counts(self):
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        self.make_good_task()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("/ops/tasks/*/out/\n.env*\n")
        (self.root / "ops" / ".env").write_text("x=1\n")
        rep = cmd_lint(self.lay, [], False)
        self.assertEqual(rep.errors, [])
        self.assertFalse(any(".env" in w for w in rep.warnings))
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "ops/.env"], check=True)
        rep = cmd_lint(self.lay, [], False)  # tracked: an error for the file, no request for a rule that exists
        self.assertIn("ops/.env: not ignored by git", "\n".join(rep.errors))
        self.assertFalse(any(".env" in w for w in rep.warnings))
        self.assertNotIn("added", "\n".join(cmd_init(self.lay)))

    def test_another_ops_folder(self):
        self.lay.marker.unlink()
        (self.root / "infra").mkdir()
        (self.root / "infra" / MARKER).touch()
        lay = find_layout(self.root)
        (self.root / ".gitignore").write_text("")
        cmd_init(lay)
        self.assertTrue((self.root / "infra" / "tasks" / "lib" / "stubtest.py").exists())
        self.assertEqual((self.root / ".gitignore").read_text(), "/infra/tasks/*/out/\n/infra/.env*\n")
        t = cmd_new(lay, "other", today="2026-10-10")
        self.assertEqual(lay.rel(t), "infra/tasks/01-other")
        self.assertEqual(cmd_status(lay)[0][:2], ("01-other", "open"))

    def test_lint_reports_a_missing_tasks_folder_and_a_marker_with_content(self):
        shutil.rmtree(self.tasks)
        self.assertIn("ops/tasks: missing; run tasks.py init", "\n".join(cmd_lint(self.lay, [], False).errors))
        self.tasks.mkdir()
        self.lay.marker.write_text("tasks here\n")
        self.assertTrue(any("must be empty" in w for w in cmd_lint(self.lay, [], False).warnings))

    def test_first_init_uses_the_git_top_level(self):
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        with tempfile.TemporaryDirectory(prefix="tasks-py-git-") as tmp:
            top = Path(tmp).resolve()
            sub = top / "src" / "deep"
            sub.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(top)], check=True)
            old_cwd, old_out = Path.cwd(), sys.stdout
            os.chdir(sub)
            sys.stdout = open(os.devnull, "w")
            try:
                rc = main(["init"])
            finally:
                sys.stdout.close()
                sys.stdout, _ = old_out, os.chdir(old_cwd)
            self.assertEqual(rc, 0)
            self.assertTrue((top / "ops" / "tasks" / "lib" / "stubtest.py").exists())
            self.assertEqual((top / "ops" / MARKER).stat().st_size, 0)
            self.assertFalse((sub / "ops").exists())
            os.chdir(sub)
            try:
                with self.assertRaises(SystemExit):
                    main(["init", "--dir", "infra"])
            finally:
                os.chdir(old_cwd)
            self.assertFalse((top / "infra").exists())

    def test_commands_other_than_init_need_a_marker(self):
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        with tempfile.TemporaryDirectory(prefix="tasks-py-git-") as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            old_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                with self.assertRaises(SystemExit) as ctx:
                    main(["status"])
            finally:
                os.chdir(old_cwd)
            self.assertIn("holds the marker .ops-tasks", str(ctx.exception))

    def test_first_init_outside_git_stops(self):
        with tempfile.TemporaryDirectory(prefix="tasks-py-nogit-") as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                with self.assertRaises(SystemExit) as ctx:
                    main(["init"])
            finally:
                os.chdir(old_cwd)
            self.assertIn("is not in a git repository", str(ctx.exception))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_new_installs_the_lib_when_missing(self):
        shutil.rmtree(self.tasks / "lib")
        old, sys.stdout = sys.stdout, open(os.devnull, "w")
        try:
            cmd_new(self.lay, "fresh", today="2026-10-09")
        finally:
            sys.stdout.close()
            sys.stdout = old
        self.assertTrue((self.tasks / "lib" / "stubtest.py").exists())

    def test_lint_reports_a_stale_or_missing_lib(self):
        self.make_good_task()
        (self.tasks / "lib" / "stubtest.py").write_text("# old\n")
        (self.tasks / "lib" / "with_timeout.sh").unlink()
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("stubtest.py: differs from the skill's copy", joined)
        self.assertIn("with_timeout.sh: missing; run tasks.py init", joined)

    def test_connections_table_uses_lines_and_helper_ids(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        table = textwrap.dedent("""\
            ## Connections
            | ID | Kind | Target | Settings and credentials from | Allowed actions |
            |---|---|---|---|---|
            | <id> | <system, repo or pipeline> | <x> | <x> | <x> |
            | vc | system | vcenter.test.invalid | <ops-dir>/.env | read |
            | app | repo | gitlab.com/group/app | APP_REPO | read; open MR |
            | deploy | pipeline | gitlab.com/group/app, job deploy-prod, prod | CI | run deploy-prod |

            Managed systems: app declares the vc VMs; deploy applies them.
            """)
        base = plan.read_text().replace("## Stop conditions", table + "## Stop conditions")
        plan.write_text(base.replace("### 1.1 Fix\n", "### 1.1 Fix\n\nUses: vc, app, <placeholder>\n"))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])
        plan.write_text(base.replace("### 1.1 Fix\n", "### 1.1 Fix\n\nUses: staging\n")
                        .replace("| app | repo |", "| vc | repo |").replace("| pipeline |", "| ci |"))
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("step 1.1: Uses: names 'staging', which is not an ID", joined)
        self.assertIn("Connections ID 'vc' is used twice", joined)
        self.assertIn("Connections 'deploy': Kind must be one of system, repo, pipeline", joined)
        plan.write_text(base)
        helper = t / "scripts" / "01-check-demo.sh"
        helper.write_text(helper.read_text().replace("# Connection: none", "# Connection: vc, prod (see PLAN.md)"))
        self.assertIn("Connection: names 'prod'", "\n".join(cmd_lint(self.lay, [], False).errors))
        plan.write_text(base.replace("| Settings and credentials from |", "| Settings from |"))
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("Connections columns must be", joined)
        self.assertNotIn("names 'prod'", joined)  # a broken table is reported once, without follow-on ID errors

    def test_ids_are_checked_when_the_table_has_only_placeholders(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        table = textwrap.dedent("""\
            ## Connections
            | ID | Kind | Target | Settings and credentials from | Allowed actions |
            |---|---|---|---|---|
            | <id> | <system, repo or pipeline> | <x> | <x> | <x> |
            """)
        plan.write_text(plan.read_text().replace("## Stop conditions", table + "## Stop conditions")
                        .replace("### 1.1 Fix\n", "### 1.1 Fix\n\nUses: prod\n"))
        helper = t / "scripts" / "01-check-demo.sh"
        helper.write_text(helper.read_text().replace("# Connection: none", "# Connection: prod"))
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("step 1.1: Uses: names 'prod', which is not an ID", joined)
        self.assertIn("Connection: names 'prod', which is not an ID", joined)

    CONNECTIONS_HEAD = ("## Connections\n| ID | Kind | Target | Settings and credentials from | Allowed actions |\n"
                        "|---|---|---|---|---|\n")
    PLACEHOLDER_ROW = "| <id> | <system, repo or pipeline> | <x> | <x> | <x> |\n"
    REAL_ROWS = {"system": "| vc | system | vcenter.test.invalid | <ops-dir>/.env | read |\n",
                 "repo": "| app | repo | gitlab.com/group/app | APP_REPO | read |\n",
                 "pipeline": "| deploy | pipeline | gitlab.com/group/app, job deploy | CI | run deploy |\n"}

    def connection_errors(self, section, status="in progress"):
        """The lint errors about Connections and its note, for a plan with section before Stop conditions.
        The first call creates the task with status."""
        task = self.tasks / "01-demo"
        if not task.exists():
            self.make_good_task(status=status)
            self.base_plan = (task / "PLAN.md").read_text()
        (task / "PLAN.md").write_text(self.base_plan.replace("## Stop conditions", section + "## Stop conditions"))
        return [e for e in cmd_lint(self.lay, [], False).errors if "Connections" in e or MANAGED_NOTE in e]

    def test_managed_note_is_required_for_any_real_row(self):
        for kind, row in self.REAL_ROWS.items():
            errors = self.connection_errors(self.CONNECTIONS_HEAD + row)
            self.assertEqual(len(errors), 1, kind)
            self.assertIn("has rows but no 'Managed systems:' line", errors[0])
        mixed = self.CONNECTIONS_HEAD + self.PLACEHOLDER_ROW + self.REAL_ROWS["repo"]
        self.assertIn("has rows but no", "\n".join(self.connection_errors(mixed)))

    def test_managed_note_accepts_an_answer(self):
        table = self.CONNECTIONS_HEAD + self.REAL_ROWS["system"]
        for note in ("Managed systems: gitlab.com/group/infra declares vc; job apply-vsphere applies it.",
                     "Managed systems: none", "Managed systems: unknown",
                     "Managed systems: see the infra repo <https://gitlab.test.invalid/infra>."):
            self.assertEqual(self.connection_errors(table + "\nProse between the table and the note.\n\n" + note + "\n"),
                             [], note)
        aligned = self.CONNECTIONS_HEAD.replace("|---|---|---|---|---|", "|:---|---:|:---:|---|---|")
        self.assertEqual(self.connection_errors(aligned + self.REAL_ROWS["system"] + "Managed systems: none\n"), [])

    def test_managed_note_rejects_an_empty_or_template_answer(self):
        table = self.CONNECTIONS_HEAD + self.REAL_ROWS["system"]
        template = next(line for line in (ASSETS / "PLAN.md").read_text().splitlines() if line.startswith(MANAGED_NOTE))
        for note, expected in (("Managed systems:", "has no answer"), ("Managed systems:   ", "has no answer"),
                               (template, "still holds the template text")):
            self.assertIn(expected, "\n".join(self.connection_errors(table + note + "\n")), note)

    def test_managed_note_must_be_one_line_after_the_table(self):
        head, row, note = self.CONNECTIONS_HEAD, self.REAL_ROWS["system"], "Managed systems: none\n"
        cases = {
            "## Connections\n" + note + head[len("## Connections\n"):] + row: "must follow the Connections table",
            head + row + "## Connections\n" + note: "appears more than once (first on line",
            head + row + "## Connections\n" + self.PLACEHOLDER_ROW + note: "appears more than once (first on line",
            head + row + "## Connections\n" + self.REAL_ROWS["repo"] + note: "appears more than once (first on line",
            head + row + "## Facts\n" + note: "has rows but no",
            head + row + "```text\n" + note + "```\n": "has rows but no",
            head + row + "~~~\n" + note + "~~~\n": "has rows but no",
            head + row + "````md\n```\n" + note + "```\n````\n": "has rows but no",
            head + row + "    " + note: "has rows but no",
            head + row + "- " + note: "has rows but no",
            head + row + "managed systems: none\n": "has rows but no",
            head + row + note + "Managed systems: unknown\n": "appears more than once",
        }
        for section, expected in cases.items():
            self.assertIn(expected, "\n".join(self.connection_errors(section)), section)

    def test_managed_note_is_skipped_without_a_real_row(self):
        head = self.CONNECTIONS_HEAD
        self.assertEqual(self.connection_errors(""), [])  # no Connections section
        self.assertEqual(self.connection_errors(head), [])  # header only
        self.assertEqual(self.connection_errors(head + self.PLACEHOLDER_ROW), [])  # the scaffold
        broken = self.connection_errors(head.replace("| Allowed actions |", "| Actions |") + self.REAL_ROWS["system"])
        self.assertEqual(len(broken), 1)
        self.assertIn("Connections columns must be", broken[0])  # no follow-on note error
        short = self.connection_errors(head + "| vc | system | x |\n")
        self.assertEqual(len(short), 1)
        self.assertIn("Connections row needs 5 cells", short[0])
        for blank in ("|  | system | x | y | read |\n", "| | | | | |\n"):
            no_id = self.connection_errors(head + blank)
            self.assertEqual(len(no_id), 1, blank)
            self.assertIn("Connections row needs an ID", no_id[0])
        mixed = "\n".join(self.connection_errors(head + "| vc | system | x |\n" + self.REAL_ROWS["repo"]))
        self.assertIn("needs 5 cells", mixed)
        self.assertIn("has rows but no", mixed)

    def test_managed_note_applies_to_closed_tasks(self):
        table = self.CONNECTIONS_HEAD + self.REAL_ROWS["system"]
        self.assertIn("has rows but no", "\n".join(self.connection_errors(table, status="done")))
        todo = self.tasks / "01-demo" / "TODO.md"
        todo.write_text(todo.read_text().replace("Status: done", "Status: dropped"))
        self.assertIn("has rows but no", "\n".join(self.connection_errors(table)))
        dated = table + "Managed systems: unknown (not recorded; line added 2026-10-28)\n"
        self.assertEqual(self.connection_errors(dated), [])

    def test_a_new_task_passes_the_connections_checks(self):
        cmd_new(self.lay, "fresh", today="2026-10-28")
        errors = [e for e in cmd_lint(self.lay, [], False).errors if "Connections" in e or MANAGED_NOTE in e]
        self.assertEqual(errors, [])

    def test_helpers_must_be_bash_with_the_bash_shebang(self):
        t = self.make_good_task()
        s = t / "scripts" / "01-check-demo.sh"
        s.write_text(s.read_text().replace("#!/usr/bin/env bash", "#!/bin/sh"))
        py = t / "scripts" / "02-parse-data.py"
        py.write_text("#!/usr/bin/env python3\n")
        py.chmod(0o755)
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("01-check-demo.sh: first line must be #!/usr/bin/env bash", joined)
        self.assertIn("02-parse-data.py: helpers are bash scripts", joined)

    def test_plan_fences_should_be_labelled_bash(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "```\nno label\n```\n```zsh\nzsh\n```\n```text\nCommand> shell\n```\n## Rollback"))
        warnings = [w for w in cmd_lint(self.lay, [], False).warnings if "fence plan commands" in w]
        self.assertEqual(len(warnings), 2)

    def test_after_box_required_for_steps_with_a_do_part(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        base = plan.read_text()
        step = "### 2.1 Change\n**Do:**\n- [x] Action ran.\n**After** (read-only):\n"
        plan.write_text(base.replace("## Rollback", step + "## Rollback"))
        self.assertIn("step 2.1 has a **Do:** part and needs exactly one", "\n".join(cmd_lint(self.lay, [], False).errors))
        # action ran, After check failed: box open, no structural error while the task is not done
        plan.write_text(base.replace("## Rollback", step + "- [ ] After check passed.\n## Rollback"))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])
        self.assertEqual(cmd_status(self.lay)[0][3], "2/4")

    def test_step_ids_are_unique_and_match_their_phase(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "## Phase 2: later\n### 2.1 A\n### 3.1 B\n### 2.1 C\n## Rollback"))
        joined = "\n".join(cmd_lint(self.lay, [], False).errors)
        self.assertIn("step 3.1 sits in '## Phase 2'; its ID must start with 2.", joined)
        self.assertIn("step ID 2.1 is used twice", joined)

    def test_init_refuses_symbolic_links(self):
        victim = self.root / "victim.txt"
        victim.write_text("original")
        lib = self.tasks / "lib"
        (lib / "stubtest.py").unlink()
        (lib / "stubtest.py").symlink_to(victim)
        with self.assertRaises(SystemExit):
            cmd_init(self.lay)
        self.assertEqual(victim.read_text(), "original")
        shutil.rmtree(lib)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        lib.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(SystemExit):
            cmd_init(self.lay)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_gitignore_rule_must_be_a_real_line(self):
        gi = self.root / ".gitignore"
        gi.write_text("# /ops/tasks/*/out/ will go here\n")
        self.make_good_task()
        self.assertTrue(any("add '/ops/tasks/*/out/'" in w for w in cmd_lint(self.lay, [], False).warnings))
        cmd_init(self.lay)
        self.assertIn("\n/ops/tasks/*/out/\n", gi.read_text())

    def test_step_contract_edge_cases(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        base = plan.read_text()
        cases = {
            "### 1 Change\n**Do:**\n- [ ] Act.\n": "step heading must be '### N.M <title>'",
            "### 1.1.1 Bad ID\n": "step heading must be '### N.M <title>'",
            "### 2.1\n": "step heading must be '### N.M <title>'",
            "### 2.1 A\n**Do:**\n- [ ] Act.\n- [ ] After check passed.\n": "belongs in the **After** part",
            "### 2.1 A\n**Do:**\n- [ ] Act.\n**After** (read-only):\n- [ ] After check passed.\n"
            "- [ ] After check passed.\n": "(found 2)",
        }
        for body, expected in cases.items():
            plan.write_text(base.replace("## Rollback", body + "## Rollback"))
            self.assertIn(expected, "\n".join(cmd_lint(self.lay, [], False).errors), body)

    def test_indented_do_and_after_parts_are_recognised(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "### 2.1 Change\n  **Do:**\n  - [x] Act.\n  **After** (read-only):\n  - [ ] After check passed.\n## Rollback"))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])

    def test_archived_steps_and_redirects_are_not_active_steps(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text()
            .replace("## Rollback", "### 1.2 Old step: moved to tasks/02-x, step 1.1, on 2026-10-09\n## Rollback")
            .replace("## Not used\n", "## Not used\n### 1.2 Old step (archived)\n**Do:**\n- [ ] Act.\n"))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])

    def test_goal_reached_outside_the_plan_closes_cleanly(self):
        t = self.make_good_task(status="done")
        plan = t / "PLAN.md"
        plan.write_text(textwrap.dedent("""\
            # Plan: Demo
            ## Goal
            Fixed.
            ## Stop conditions
            - none
            ## Steps
            ### 1.1 Change
            **Do:**
            Actions moved to Not used: reached outside the plan, see Log 2026-10-09.
            **After** (read-only):
            - [x] After check passed.
              Result (2026-10-09): verified; reached outside the plan, see Log.
            ## Rollback
            - 1.1: none needed.
            ## Not used
            - [ ] 1.1 action: not run, the goal was reached outside the plan (2026-10-09).
            ## Log
            - 2026-10-09: the change was made outside the plan.
            """))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])

    def test_dropped_task_keeps_partial_history(self):
        t = self.make_good_task(status="dropped")
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "### 2.1 Change\n**Do:**\n- [x] First action ran.\n- [ ] Second action not run.\n"
            "**After** (read-only):\n- [ ] After check passed.\n## Rollback"))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])

    def test_secrets_in_the_forms_used_here(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        base = plan.read_text()
        for line, flagged in [("export GOVC_PASSWORD='AbC123!long'", True),
                              ("password: latest-secret-value", True),
                              ("token=0123456789abcdef", True),
                              ("export GOVC_PASSWORD='not-a-real-password'", False),
                              ("read -rsp 'ESXi root password: ' GOVC_PASSWORD", False),
                              ("GOVC_PASSWORD=<redacted>", False),
                              ("MU45K-8NH5H-H85L1-X1976-2FRP4", True)]:
            plan.write_text(base + line + "\n")
            errors = "\n".join(cmd_lint(self.lay, [], False).errors)
            self.assertEqual("looks like" in errors, flagged, line)

    def test_fences_with_tildes_and_longer_backtick_runs(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "~~~\n- [ ] in a tilde fence\n~~~\n````md\n```\n- [ ] in a nested fence\n```\n````\n"
            "See `[x](NOT-THERE.md)` in inline code.\n## Rollback"))
        self.assertEqual(cmd_status(self.lay)[0][3], "1/2")
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])

    def test_status_line_must_be_exact(self):
        t = self.make_good_task()
        todo = t / "TODO.md"
        for bad in ("Status: done garbage", "Status: done", "Status: finished (since 2026-10-05)"):
            todo.write_text(todo.read_text().replace(todo.read_text().splitlines()[1], bad))
            self.assertIn("'Status: <open", "\n".join(cmd_lint(self.lay, [], False).errors), bad)

    def test_dev_tcp_and_absolute_network_paths_are_rejected(self):
        t = self.make_good_task()
        s = t / "scripts" / "01-check-demo.sh"
        for body, expected in [("exec 3<>/dev/tcp/10.0.0.1/443", "/dev/tcp"),
                               ("\"/opt/homebrew/bin/govc\" about", "absolute path to 'govc'"),
                               ("x=$(/usr/bin/curl -s http://x)", "absolute path to 'curl'")]:
            s.write_text("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: read-only\n# Runs on: Mac\n# Connection: none\n"
                         "# Exit: 0\n# --test\n" + body + "\n")
            self.assertIn(expected, "\n".join(cmd_lint(self.lay, [], False).errors))

    def test_remote_helper_template_passes_lint_and_its_tests(self):
        t = self.make_good_task()
        s = t / "scripts" / "02-restart-demo.sh"
        text = (ASSETS / "remote-script.sh").read_text().replace('HOSTS="<host name>"', 'HOSTS="web01.test.invalid"')
        s.write_text(re.sub(r"^# Effect: .*$", "# Effect: changes: restarts demo; dry run unless --apply", text, flags=re.M))
        s.chmod(0o755)
        uname = {"uname": [{"args": ["-n"], "stdout": "web01.test.invalid\n"}]}
        (t / "scripts" / "tests" / "02-restart-demo.json").write_text(json.dumps({"cases": [
            {"name": "dry run on the right system", "stubs": dict(uname, timeout=[]),
             "expect": {"stdout_contains": ["Dry run"], "calls": [["uname", "-n"]]}},
            {"name": "a look-alike system is refused", "args": ["--apply"],
             "stubs": {"timeout": [], "uname": [{"args": ["-n"], "stdout": "web01.test.invalid.evil\n"}]},
             "expect": {"exit": 2, "stderr_contains": ["Wrong system"], "stdout_not_contains": ["Action"]}},
            {"name": "a missing tool stops it before any call", "stubs": uname,
             "expect": {"exit": 2, "stderr_contains": ["Missing on this system: timeout"], "calls": []}},
        ]}))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])
        proc = subprocess.run([str(s), "--test"], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.returncode, proc.stdout.count("PASS ")), (0, 3), proc.stdout + proc.stderr)
        remote = self.root / "remote" / "home" / "ops"  # sent through `bash -s`: $0 is bash, no lib/ nearby
        remote.mkdir(parents=True)
        with s.open() as script:
            proc = subprocess.run(["bash", "-s", "--", "--test"], stdin=script, cwd=remote,
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("runs on the operator's machine only", proc.stderr)
        # A cut-off transfer runs nothing: bash -x would print "+ <command>" for each command it ran.
        full = s.read_bytes()
        end = full.rindex(b"}")
        cuts = {i + 1 for i, b in enumerate(full[:end]) if b == ord("\n")} | set(range(end - 40, end + 1))
        for cut in sorted(cuts):
            proc = subprocess.run(["bash", "-x", "-s", "--", "--apply"], input=full[:cut], cwd=remote,
                                  capture_output=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, timeout=10)
            ran = [line for line in proc.stderr.decode().splitlines() if line.startswith("+")]
            self.assertEqual((ran, proc.stdout), ([], b""), f"the file cut after byte {cut} ran commands")

    def test_lint_checks_remote_helpers(self):
        t = self.make_good_task()
        s = t / "scripts" / "02-check-disk.sh"
        head = ("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x [--test]\n# Effect: read-only\n"
                "# Runs on: remote: web01 (Ubuntu 22.04, bash 5, as root)\n# Connection: none\n# Exit: 0 ok\n")
        bad = ['source "$HERE/../../lib/with_timeout.sh"', "main() { with_timeout df -h; }",
               "if true; then . ./env; fi", "if source ./env; then :; fi", "! . ./env", "builtin source ./env",
               'value="$(with_timeout curl https://example.test)"', 'value="$(source ./env; echo ok)"',
               'value="$(with_timeout curl "$URL")"', 'value="$(source "$ENV_FILE"; echo ok)"',
               'n="$(wc -l < "$(dirname "$0")/x")"; v=`builtin source "$F"`',
               'value="$(case "$kind" in a) source "$F"; echo ok ;; *) echo no ;; esac)"']
        s.write_text(head + "echo before the block\n{\n" + "\n".join(bad) + '\nmain "$@"\n}\n')
        s.chmod(0o755)
        (t / "scripts" / "tests" / "02-check-disk.json").write_text('{"cases": []}')
        joined = "\n".join(e for e in cmd_lint(self.lay, [], False).errors if "02-check-disk" in e)
        for no in range(10, 10 + len(bad)):
            self.assertIn(f"02-check-disk.sh:{no}: a remote helper runs where", joined)
        self.assertIn("in one { ... } block", joined)
        self.assertIn("'Runs on: remote:' names 'web01', which 'Connection:' does not list", joined)
        s.write_text(head.replace("web01 (", "(") + '{\nmain() { :; }\nmain "$@"\n}\n')
        self.assertIn("must name the Connections ID", "\n".join(cmd_lint(self.lay, [], False).errors))
        s.write_text(head + "{\necho EARLY\n}\n{\necho LATE\n}\n")  # cut after line 10, it runs EARLY
        self.assertIn("02-check-disk.sh:10: the { ... } block is already complete here",
                      "\n".join(cmd_lint(self.lay, [], False).errors))
        s.write_text(head.replace("# Connection: none", "# Connection: web01") +
                     '# Never source "$LIB/with_timeout.sh" here.\n{   # one block\n'
                     'main() { echo "data source: disk"; timeout 30 df -h </dev/null; }\n'
                     'echo "with_timeout is not installed"\nrun systemctl status app # replaces with_timeout\n'
                     "printf '%s\\n' 'then source file'\nmain \"$@\"\n"
                     "cat > /etc/profile.d/app.sh <<'EOF'\n. /etc/app/env\nsource /etc/app/more\nEOF\n"
                     'echo "a string over two lines,\nsource on the second"\n'
                     'x="${y#*/}"; n=$#; d="$(dirname "$(pwd)")"; echo "it\'s #1"\n'
                     "read -r state <<< healthy\nbits=2\nn=$((1 << bits))\nif ((n > 2)); then echo big; fi\n"
                     "cat <<'END-CONFIG'\nsource /etc/example\nEND-CONFIG\ncat <<END-CONFIG\nx\nEND-CONFIG\n"
                     "printf '%s\\n' $'it\\'s fine'\n"
                     'v="$(case "$k" in a) echo source closed ;; esac)"\n}  # end\n\n# end\n')
        errors = [e for e in cmd_lint(self.lay, [], False).errors if "02-check-disk" in e]
        self.assertEqual(errors, ["ops/tasks/01-demo/scripts/02-check-disk.sh: Connection: names 'web01', "
                                  "but PLAN.md has no ## Connections table"])

    # --- task numbers across worktrees and branches ----------------------------------------------

    def git(self, cwd, *args) -> str:
        proc = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            self.fail(f"git {' '.join(args)}: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def make_clone(self) -> tuple:
        """A git repo next to self.root's ops/, with ops/ initialized and committed: (top, layout)."""
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        top = (self.root / "clone").resolve()
        top.mkdir()
        self.git(top, "init", "-q", "-b", "main")
        lay = Layout(top)
        lay.tasks.mkdir(parents=True)
        cmd_init(lay)
        self.commit_task(top, "01-base")
        return top, lay

    def commit_task(self, cwd, name, ops_dir="ops"):
        d = Path(cwd) / ops_dir / "tasks" / name
        d.mkdir(parents=True)
        (d / "TODO.md").write_text(f"# {name}\n")
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "-qm", name)

    def worktree(self, top, name, *args) -> Path:
        path = self.root / name
        self.git(top, "worktree", "add", "-q", *args, str(path))
        return path.resolve()

    def test_new_numbers_after_tasks_in_worktrees_and_branches(self):
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-a", "-b", "a")
        (wt / "ops" / "tasks" / "02-wip").mkdir()                     # uncommitted, on disk in another worktree
        side = self.worktree(top, "wt-side", "-b", "side")
        self.commit_task(side, "04-side")
        self.git(top, "worktree", "remove", str(side))                # the task now exists only on branches
        self.git(top, "branch", "dup", "side")                        # a duplicate branch tip
        self.git(top, "switch", "-q", "-c", "old")
        self.commit_task(top, "06-old")
        self.git(top, "update-ref", "refs/remotes/origin/old", "old")  # a stale remote-tracking branch
        self.git(top, "switch", "-q", "main")
        self.git(top, "branch", "-D", "old")
        self.git(top, "switch", "-q", "-c", "renamed")
        self.commit_task(top, "09-infra", ops_dir="infra")             # another <ops-dir> name is not scanned
        self.git(top, "switch", "-q", "main")
        notes = []
        self.assertEqual(cmd_new(lay, "side", today="2026-11-09", notes=notes).name, "07-side")  # branch slugs pass
        self.assertEqual(notes, [])
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "wip")
        self.assertIn("slug 'wip' exists already", str(ctx.exception))
        self.assertEqual(cmd_new(Layout(wt), "from-a", today="2026-11-09").name, "08-from-a")

    def test_new_scans_detached_and_sparse_worktree_heads(self):
        top, lay = self.make_clone()
        det = self.worktree(top, "wt-det", "--detach")
        self.commit_task(det, "03-det")                                # on no branch: only its HEAD has it
        sparse = self.worktree(top, "wt-sparse", "--detach")
        self.commit_task(sparse, "05-sparse")
        self.git(sparse, "sparse-checkout", "set", "--no-cone", "/.gitignore")
        self.assertFalse((sparse / "ops").exists())
        self.assertEqual(cmd_new(lay, "next", today="2026-11-09").name, "06-next")

    def test_new_and_missing_worktrees(self):
        top, lay = self.make_clone()
        gone = self.worktree(top, "wt-gone", "--detach")
        self.commit_task(gone, "04-gone")
        (gone / "ops" / "tasks" / "05-unsaved").mkdir()
        shutil.move(str(gone), str(self.root / "wt-gone.away"))
        notes = []
        self.assertEqual(cmd_new(lay, "after-gone", today="2026-11-09", notes=notes).name, "05-after-gone")
        self.assertEqual(len(notes), 1)
        self.assertIn("is missing; only its last commit was scanned", notes[0])
        self.assertIn("run `git worktree prune` only after confirming", notes[0])
        usb = self.worktree(top, "wt-usb", "-b", "usb")
        self.git(top, "worktree", "lock", "--reason", "usb disk", str(usb))
        shutil.move(str(usb), str(self.root / "wt-usb.away"))
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "blocked")
        self.assertIn("wt-usb is missing and locked (usb disk)", str(ctx.exception))
        usb.mkdir()                                                    # an empty mount point at the registered path
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "blocked")
        self.assertIn("the folder there is not that worktree", str(ctx.exception))
        self.assertFalse(any(p.name.endswith("-blocked") for p in lay.tasks.iterdir()))

    def test_new_accepts_the_main_checkout_and_a_worktree_by_any_path(self):
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-b", "-b", "b")
        link = self.root / "link-to-wt"
        link.symlink_to(wt)
        self.assertEqual(cmd_new(Layout(link), "via-link", today="2026-11-09").name, "02-via-link")
        self.assertEqual(cmd_new(lay, "in-main", today="2026-11-09").name, "03-in-main")

    def test_new_stops_when_a_committed_tree_cannot_be_read(self):
        top, lay = self.make_clone()
        self.git(top, "switch", "-q", "-c", "broken")
        self.commit_task(top, "02-broken")
        tree = self.git(top, "rev-parse", "broken:ops/tasks")
        self.git(top, "switch", "-q", "main")
        (top / ".git" / "objects" / tree[:2] / tree[2:]).unlink()
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "unsure")
        self.assertIn("Incomplete scan: cannot read", str(ctx.exception))

    def test_new_waits_for_the_lock_and_scans_after_taking_it(self):
        import fcntl
        import select
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-c", "-b", "c")
        fd = os.open(top / ".git" / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "new", "racer"], cwd=wt,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    text=True)
            ready, _, _ = select.select([proc.stderr], [], [], 20)
            line = proc.stderr.readline() if ready else ""
            (top / "ops" / "tasks" / "02-competing").mkdir()              # created while new waits
        finally:
            os.close(fd)
        out, err = proc.communicate(timeout=60)
        self.assertEqual(line.strip(), LOCK_BUSY)
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("ops/tasks/03-racer", out)

    def test_new_gives_up_after_the_lock_wait(self):
        import fcntl
        global LOCK_WAIT
        old_wait, LOCK_WAIT = LOCK_WAIT, 0.3
        fd = os.open(self.lay.ops / LOCAL_LOCK, os.O_RDWR | os.O_CREAT, 0o600)   # outside git: the local lock
        fcntl.flock(fd, fcntl.LOCK_EX)
        old_err, sys.stderr = sys.stderr, open(os.devnull, "w")
        try:
            with self.assertRaises(SystemExit) as ctx:
                cmd_new(self.lay, "late")
        finally:
            sys.stderr.close()
            sys.stderr, LOCK_WAIT = old_err, old_wait
            os.close(fd)
        self.assertIn("held the lock", str(ctx.exception))
        self.assertFalse(any(p.name.endswith("-late") for p in self.tasks.iterdir()))
        self.assertEqual(cmd_new(self.lay, "late", today="2026-11-09").name, "01-late")

    def test_git_version_check(self):
        for text, ok in (("git version 2.36.0", True), ("git version 2.35.9", False), ("git version 3.0.1", True),
                         ("git version 2.39.5 (Apple Git-154)", True), ("git version 10.2", True),
                         ("version 2.40", False), ("", False)):
            version = parse_git_version(text)
            self.assertEqual(version is not None and version >= GIT_MIN_VERSION, ok, text)
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir()
        fake = bin_dir / "git"
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
        try:
            for script, expected in (("echo 'git version 2.35.1'", "needs Git 2.36 or later"),
                                     ("exit 1", "`git --version` failed"),
                                     ("echo 'something else'", "printed 'something else'")):
                fake.write_text(f"#!/bin/sh\n{script}\n")
                fake.chmod(0o755)
                with self.assertRaises(SystemExit) as ctx:
                    require_git_version("new")
                self.assertIn(expected, str(ctx.exception))
            fake.write_text("#!/bin/sh\necho 'git version 2.36.0'\n")
            require_git_version("new")
        finally:
            os.environ["PATH"] = old_path

    def test_new_stops_when_git_cannot_read_the_repo(self):
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-p", "-b", "p")
        (wt / "ops" / "tasks" / "07-pending").mkdir()
        with (top / ".git" / "config").open("a") as f:
            f.write("[broken\n")
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "probe")
        self.assertIn("git cannot read the repository", str(ctx.exception))
        self.assertEqual(task_names_in(top, "ops"), ["01-base"])
        sub = self.root / "plain" / "inner"
        sub.mkdir(parents=True)
        self.git(self.root / "plain", "init", "-q")
        (sub / "ops").mkdir()
        (sub / "ops" / MARKER).touch()
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(Layout(sub), "probe")
        self.assertIn("is not its top level", str(ctx.exception))

    def test_new_stops_when_git_finds_no_repo_but_one_is_there(self):
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-p", "-b", "p")
        (wt / "ops" / "tasks" / "07-pending").mkdir()
        (top / ".git" / "HEAD").rename(top / ".git" / "HEAD.saved")   # damaged metadata
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "probe")
        self.assertIn("not a git repository", str(ctx.exception))
        self.assertIn(".git exists", str(ctx.exception))
        (top / ".git" / "HEAD.saved").rename(top / ".git" / "HEAD")
        os.environ["GIT_DIR"] = str(self.root / "no-such-git-dir")    # a wrong repository location
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "probe")
        self.assertIn("GIT_DIR is set", str(ctx.exception))
        del os.environ["GIT_DIR"]
        loose = self.root / "loose"
        (loose / "ops" / "tasks").mkdir(parents=True)
        (loose / "ops" / MARKER).touch()
        (loose / ".git").symlink_to(self.root / "unmounted" / "repo.git")  # a broken .git link
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(Layout(loose), "probe")
        self.assertIn(".git exists", str(ctx.exception))
        self.assertEqual(task_names_in(top, "ops"), ["01-base"])
        self.assertEqual(task_names_in(loose, "ops"), [])
        self.assertEqual(cmd_new(self.lay, "control", today="2026-11-09").name, "01-control")  # outside git

    def test_new_stops_on_a_broken_link_to_task_folders(self):
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-l", "-b", "l")
        (wt / "ops" / "tasks" / "07-pending").mkdir()
        shutil.move(str(wt / "ops" / "tasks"), str(self.root / "tasks.away"))
        (wt / "ops" / "tasks").symlink_to(self.root / "unmounted" / "tasks")
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "probe")
        self.assertIn("Incomplete scan: cannot read ", str(ctx.exception))
        self.assertIn("wt-l/ops/tasks", str(ctx.exception))
        with self.assertRaises(ScanError):
            task_names_in(wt, "ops")
        self.assertEqual(task_names_in(wt, "infra"), [])                   # a path that does not exist

    def test_new_never_fetches_in_a_partial_clone(self):
        top, lay = self.make_clone()
        remote = self.root / "remote.git"
        self.git(self.root, "init", "-q", "--bare", str(remote))
        self.git(top, "remote", "add", "origin", str(remote))
        self.git(top, "switch", "-q", "-c", "side")
        self.commit_task(top, "08-side")
        self.git(top, "push", "-q", "origin", "side")
        tree = self.git(top, "rev-parse", "side:ops/tasks")
        self.git(top, "switch", "-q", "main")
        self.git(top, "config", "remote.origin.promisor", "true")
        self.git(top, "config", "extensions.partialClone", "origin")
        (top / ".git" / "objects" / tree[:2] / tree[2:]).unlink()
        with self.assertRaises(SystemExit) as ctx:
            cmd_new(lay, "probe")
        version = parse_git_version(os.fsdecode(run_git(["--version"]).stdout))
        expected = "Incomplete scan: cannot read" if version >= GIT_NO_LAZY_FETCH_VERSION else "partial clone"
        self.assertIn(expected, str(ctx.exception))
        self.assertFalse((top / ".git" / "objects" / tree[:2] / tree[2:]).exists())
        self.assertEqual(list((top / ".git" / "objects" / "pack").glob("*.pack")), [])   # nothing was fetched
        self.assertEqual(task_names_in(top, "ops"), ["01-base"])

    # --- link-env ------------------------------------------------------------------------------

    def test_link_env_links_usable_sources_and_reports_every_other_state(self):
        top, lay = self.make_clone()
        src = top / "ops"
        elsewhere = self.root / "elsewhere.env"
        elsewhere.write_text("OTHER=1\n")
        vault = self.root / "vault" / "app.env"
        vault.parent.mkdir()
        vault.write_text("VAULT=1\n")
        (src / ".env").write_text("API_TOKEN=REAL_SENTINEL\n")
        for name in (".env.copy", ".env.other", ".env.broken-dest", ".env.folder-dest"):
            (src / name).write_text("X=1\n")
        (src / ".env.dir").mkdir()                                           # a source that is a folder
        (src / ".env.dangling").symlink_to(self.root / "nowhere.env")         # a broken source link
        (src / ".env.vault").symlink_to(vault)                               # a source link to a real file
        (src / ".env.direct").symlink_to(vault)
        wt = self.worktree(top, "wt-e", "-b", "e")
        dst = wt / "ops"
        (dst / ".env.copy").write_text("COPY=1\n")
        (dst / ".env.other").symlink_to(elsewhere)
        (dst / ".env.broken-dest").symlink_to(self.root / "nowhere.env")
        (dst / ".env.folder-dest").mkdir()
        (dst / ".env.orphan").symlink_to(src / ".env.gone")
        (dst / ".env.local").write_text("LOCAL=1\n")
        (dst / ".env.direct").symlink_to(vault)                  # skips the source link: misses a retarget
        lines, warnings = cmd_link_env(Layout(wt))
        self.assertEqual(lines, [f"  linked: ops/.env -> {src / '.env'}", f"  linked: ops/.env.vault -> {src / '.env.vault'}"])
        self.assertEqual(os.readlink(dst / ".env"), str(src / ".env"))
        self.assertEqual((dst / ".env.copy").read_text(), "COPY=1\n")             # never replaced
        self.assertEqual(os.readlink(dst / ".env.other"), str(elsewhere))
        expected = {".env.broken-dest": "a broken link instead of a link to",
                    ".env.copy": "which goes stale after a credential change",
                    ".env.dangling": "in the main checkout is a broken symbolic link",
                    ".env.dir": "in the main checkout is a folder",
                    ".env.direct": "a link that does not point to",
                    ".env.folder-dest": "a folder or another entry where the link to",
                    ".env.local": "exists only in this worktree",
                    ".env.orphan": "its source is gone from the main checkout",
                    ".env.other": "a link that does not point to"}
        self.assertEqual(len(warnings), len(expected), warnings)
        for (name, text), warning in zip(sorted(expected.items()), warnings):
            self.assertTrue(warning.startswith(f"ops/{name}: ") and text in warning, warning)
        self.assertNotIn("REAL_SENTINEL", "\n".join(lines + warnings))           # it never reads an env file
        again, _ = cmd_link_env(Layout(wt))
        self.assertEqual(again, ["  ok:     ops/.env", "  ok:     ops/.env.vault"])
        lint_warnings = [w for w in cmd_lint(Layout(wt), [], False).warnings if w.startswith("ops/.env")]
        self.assertEqual(sorted(w.split(":")[0] for w in lint_warnings), [f"ops/{n}" for n in sorted(expected)])
        self.assertFalse(any(w.startswith("ops/.env") for w in cmd_lint(lay, [], False).warnings))  # main checkout

    def test_link_env_compares_the_link_target_as_the_filesystem_reads_it(self):
        top, lay = self.make_clone()
        (top / "ops" / ".env").write_text("FAKE=main\n")
        other = self.root / "other"
        (other / "ops").mkdir(parents=True)
        (other / "nested").mkdir()
        (other / "ops" / ".env").write_text("FAKE=other\n")
        (top / "alias").symlink_to(other / "nested")
        wt = self.worktree(top, "wt-a", "-b", "a")
        dest = wt / "ops" / ".env"
        for target in (f"{top}/alias/../ops/.env", f"../../{top.name}/alias/../ops/.env"):
            dest.symlink_to(target)
            self.assertEqual(dest.read_text(), "FAKE=other\n")              # what the link really reads
            lines, warnings = cmd_link_env(Layout(wt))
            self.assertEqual(lines, [], target)
            self.assertEqual(len(warnings), 1, target)
            self.assertIn("a link that does not point to", warnings[0])
            dest.unlink()
        dest.symlink_to(f"../../{top.name}/ops/.env")                           # a correct relative link
        self.assertEqual(cmd_link_env(Layout(wt)), (["  ok:     ops/.env"], []))

    def test_link_env_follows_new_and_renamed_sources(self):
        top, lay = self.make_clone()
        (top / "ops" / ".env").write_text("A=1\n")
        wt = self.worktree(top, "wt-n", "-b", "n")
        gone = self.worktree(top, "wt-gone", "-b", "gone")
        shutil.move(str(gone), str(self.root / "wt-gone.away"))                 # an unrelated missing worktree
        self.assertEqual(cmd_link_env(Layout(wt))[0], [f"  linked: ops/.env -> {top / 'ops' / '.env'}"])
        (top / "ops" / ".env.staging").write_text("B=1\n")
        (top / "ops" / ".env").rename(top / "ops" / ".env.prod")
        warnings = [w for w in cmd_lint(Layout(wt), [], False).warnings if w.startswith("ops/.env")]
        self.assertEqual([w.split(": ", 1)[1].split(";")[0] for w in warnings],
                         ["its source is gone from the main checkout", "missing", "missing"])
        lines, warnings = cmd_link_env(Layout(wt))
        self.assertEqual([line.split(" -> ")[0] for line in lines], ["  linked: ops/.env.prod", "  linked: ops/.env.staging"])
        self.assertEqual(warnings, ["ops/.env: its source is gone from the main checkout; remove the link"])

    def test_link_env_refuses_to_run_where_it_cannot_link_safely(self):
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(self.lay)
        self.assertIn("needs a git repo", str(ctx.exception))
        top, lay = self.make_clone()
        (top / "ops" / ".env").write_text("A=1\n")
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(lay)
        self.assertIn("This is the main checkout", str(ctx.exception))
        wt = self.worktree(top, "wt-r", "-b", "r")
        gi = wt / ".gitignore"
        gi.write_text(gi.read_text().replace("/ops/.env*\n", ""))
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(Layout(wt))
        self.assertIn("git does not ignore ops/.env", str(ctx.exception))
        self.git(wt, "checkout", "--", ".gitignore")
        (wt / "ops" / ".env.tracked").write_text("T=1\n")
        self.git(wt, "add", "-f", "ops/.env.tracked")
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(Layout(wt))
        self.assertIn("git tracks ops/.env.tracked", str(ctx.exception))
        self.git(wt, "rm", "-q", "--cached", "ops/.env.tracked")
        (wt / "ops" / ".env.tracked").unlink()
        self.assertFalse((wt / "ops" / ".env").is_symlink())
        (top / "ops" / MARKER).rename(top / "marker.saved")             # the main checkout moved to infra/
        (top / "infra").mkdir()
        (top / "infra" / MARKER).touch()
        (top / "infra" / ".env").write_text("A=2\n")
        self.assertEqual(cmd_link_env(Layout(wt))[0], [f"  linked: ops/.env -> {top / 'infra' / '.env'}"])
        bare = self.root / "bare.git"
        self.git(self.root, "clone", "-q", "--bare", str(top), str(bare))
        wt_bare = self.root / "wt-bare"
        self.git(bare, "worktree", "add", "-q", str(wt_bare), "main")
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(Layout(wt_bare))
        self.assertIn("is bare", str(ctx.exception))

    def test_link_env_stops_when_a_git_check_fails(self):
        top, lay = self.make_clone()
        (top / "ops" / ".env").write_text("A=1\n")
        wt = self.worktree(top, "wt-i", "-b", "i")
        index = Path(self.git(wt, "rev-parse", "--path-format=absolute", "--git-path", "index"))
        saved = index.read_bytes()
        index.write_bytes(b"not an index")
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(Layout(wt))
        self.assertIn("`git ls-files` failed for ops/.env", str(ctx.exception))
        index.write_bytes(saved)
        real_git = shutil.which("git")
        bin_dir = self.root / "failing-git-bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(f'#!/bin/sh\n[ "$3" = check-ignore ] && {{ echo "fatal: broken" >&2; exit 128; }}\n'
                                     f'exec "{real_git}" "$@"\n')
        (bin_dir / "git").chmod(0o755)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
        with self.assertRaises(SystemExit) as ctx:
            cmd_link_env(Layout(wt))
        self.assertIn("`git check-ignore` failed for ops/.env: fatal: broken", str(ctx.exception))
        self.assertFalse(os.path.lexists(wt / "ops" / ".env"))

    def test_helper_tests_read_the_fake_env_file_not_the_linked_one(self):
        top, lay = self.make_clone()
        (top / "ops" / ".env").write_text("API_TOKEN=REAL_SENTINEL\n")
        wt = self.worktree(top, "wt-h", "-b", "h")
        cmd_link_env(Layout(wt))
        scripts = wt / "ops" / "tasks" / "02-env" / "scripts"
        (scripts / "tests").mkdir(parents=True)
        helper = scripts / "01-show-token.sh"
        helper.write_text("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x [--test]\n# Effect: read-only\n"
                          "# Runs on: the Mac\n# Connection: none\n# Exit: 0 ok\nset -euo pipefail\n"
                          'HERE="$(cd "$(dirname "$0")" && pwd)"\nLIB="$(cd "$HERE/../../lib" && pwd)"\n'
                          '[[ "${1:-}" == --test ]] && exec python3 "$LIB/stubtest.py" "$0"\n'
                          'source "${OPS_ENV_FILE:-$HERE/../../../.env}"\necho "token=$API_TOKEN"\n')
        helper.chmod(0o755)
        (scripts / "tests" / "01-show-token.json").write_text(json.dumps({"cases": [
            {"name": "the fake env file", "env_file": "API_TOKEN=fake-sentinel\n",
             "expect": {"stdout_contains": ["token=fake-sentinel"], "stdout_not_contains": ["REAL_SENTINEL"]}}]}))
        proc = subprocess.run([str(helper), "--test"], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "PASS the fake env file"), proc.stderr)
        proc = subprocess.run([str(helper)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.stdout.strip(), "token=REAL_SENTINEL")               # the link works outside tests

    def test_lint_and_link_env_stop_on_an_old_git(self):
        top, lay = self.make_clone()
        wt = self.worktree(top, "wt-o", "-b", "o")
        real_git = shutil.which("git")
        bin_dir = self.root / "old-git-bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "git version 2.35.1"; exit 0; }}\n'
                                     f'exec "{real_git}" "$@"\n')
        (bin_dir / "git").chmod(0o755)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
        for run, cmd in ((lambda: cmd_lint(lay, [], False), "lint"), (lambda: cmd_link_env(Layout(wt)), "link-env"),
                         (lambda: cmd_new(lay, "old"), "new")):
            with self.assertRaises(SystemExit) as ctx:
                run()
            self.assertIn(f"tasks.py {cmd} needs Git 2.36 or later", str(ctx.exception))
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])                 # outside git: any Git

    def test_new_outside_git_uses_the_local_lock(self):
        self.make_good_task("03-local")
        self.assertEqual(cmd_new(self.lay, "next", today="2026-11-09").name, "04-next")
        self.assertTrue((self.lay.ops / LOCAL_LOCK).is_file())
        self.assertEqual(cmd_lint(self.lay, [], False).errors, [])

    def test_lint_warns_when_two_task_folders_share_a_number(self):
        self.make_good_task("05-alpha")
        self.assertFalse(any("share one number" in w for w in cmd_lint(self.lay, [], False).warnings))
        self.make_good_task("05-beta")
        warnings = cmd_lint(self.lay, [], False).warnings
        self.assertIn("ops/tasks: 05-alpha, 05-beta share one number. Keep both names: the slug tells the tasks "
                      "apart, and renaming a folder breaks links into it", warnings)


def self_test() -> int:
    """Run the unittest cases and print one PASS or FAIL line per case."""
    suite = unittest.TestLoader().loadTestsFromTestCase(SelfTests)
    failed = 0
    for test in suite:
        result = unittest.TestResult()
        devnull = open(os.devnull, "w")
        old = sys.stdout
        sys.stdout = devnull  # lint --run-tests prints helper output; keep the report clean
        try:
            test.run(result)
        finally:
            sys.stdout = old
            devnull.close()
        name = test.id().rsplit(".", 1)[-1]
        problems = result.failures + result.errors
        if problems:
            failed += 1
            last = problems[0][1].strip().splitlines()[-1]
            print(f"FAIL {name}: {last}")
        else:
            print(f"PASS {name}")
    return 1 if failed else 0


# --- main ---------------------------------------------------------------------------------------

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--test"]:
        return self_test()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", type=Path, help="repo root (default: the git top-level folder)")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="install or update <ops-dir>/tasks/lib/ from the skill (overwrites it)")
    i.add_argument("--dir", help="folder in the repo root for the marker, tasks/ and .env* "
                                 "(default: the folder with the marker, else ops)")
    n = sub.add_parser("new", help="create the next <ops-dir>/tasks/NN-SLUG")
    n.add_argument("slug")
    n.add_argument("--title")
    sub.add_parser("status", help="list tasks")
    sub.add_parser("link-env", help="link the main checkout's <ops-dir>/.env* files into this linked worktree")
    l = sub.add_parser("lint", help="check structure")
    l.add_argument("tasks", nargs="*", help="task folder names, e.g. 01-certs (default: all)")
    l.add_argument("--run-tests", action="store_true", help="also run every helper's --test")
    a = p.parse_args(argv)
    cwd = Path.cwd()
    root = a.root or git_toplevel(cwd)
    if root is None:
        raise SystemExit(f"{cwd} is not in a git repository. Run tasks.py inside one, or pass --root. "
                         "Nothing was written.")
    root = root.resolve()
    lay = init_layout(root, a.dir) if a.cmd == "init" else find_layout(root)

    if a.cmd == "init":
        print("\n".join(cmd_init(lay)))
        return 0
    if a.cmd == "new":
        t = cmd_new(lay, a.slug, a.title)
        print(f"Created {lay.rel(t)}: fill in TODO.md first.")
        return 0
    if a.cmd == "status":
        rows = cmd_status(lay)
        w = max([len(r[0]) for r in rows] + [4])
        print(f"{'TASK':<{w}}  {'STATUS':<11}  {'DEADLINE':<12}  CHECKBOXES (done/total, not a status)")
        for name, status, deadline, boxes in rows:
            print(f"{name:<{w}}  {status:<11}  {deadline:<12}  {boxes}")
        return 0
    if a.cmd == "link-env":
        lines, warnings = cmd_link_env(lay)
        print("\n".join(lines))
        for w in warnings:
            print(f"WARN  {w}")
        return 0
    rep = cmd_lint(lay, a.tasks, a.run_tests)
    for e in rep.errors:
        print(f"ERROR {e}")
    for w in rep.warnings:
        print(f"WARN  {w}")
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
