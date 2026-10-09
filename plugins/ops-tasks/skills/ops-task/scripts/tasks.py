#!/usr/bin/env python3
"""Create, list and check operations task folders: tasks/NN-slug/{TODO.md, PLAN.md, scripts/}.

Purpose: keep every task folder in the same shape.
Usage:   tasks.py [--root DIR] init                      install or update tasks/lib/ from the skill (overwrites it)
         tasks.py [--root DIR] new SLUG [--title TEXT]   create the next tasks/NN-SLUG from templates
         tasks.py [--root DIR] status                    list tasks with status, deadline and checkbox counts
         tasks.py [--root DIR] lint [TASK ...] [--run-tests]
                                                         check structure; --run-tests also runs every
                                                         helper's --test and the shared test runner
         tasks.py --test                                 run this tool's own self-tests
Effect:  `init` overwrites tasks/lib/ and may add '/tasks/*/out/' and '.env' to .gitignore. `new` writes one new folder
         (and runs `init` when tasks/lib/ is missing). `status` and `lint` only read. `lint --run-tests`
         runs the offline tests of tasks/lib/ and of the helpers.
Runs on: any machine with Python 3.9 or later. Standard library only.

The repo root is the nearest parent folder of the working directory that has a `tasks/` folder,
or the folder given with --root.

What lint checks, and what it cannot prove:
- Folder names, required files and headings, the TODO status, deadline and plan lines, and
  checkbox state for done tasks. scripts/ is optional: it exists once a task has a helper.
- Inline local Markdown links `[text](path)` outside code. Reference-style links, paths with
  spaces or escapes, anchors and external links are not checked.
- Explicit secret patterns only (password/secret/token assignments, license keys, private keys).
  This is a heuristic: a clean result does not prove that no secret is present.
- PLAN.md: unique step IDs `N.M` matching their `## Phase N`, an "After check passed" box in every
  step with a `**Do:**` part, and code blocks fenced as `bash` (or another named language).
- tasks/lib/ matches the skill's assets/lib/.
- Helpers: bash only (`NN-verb-object.sh`, first line `#!/usr/bin/env bash`), the executable bit,
  header fields, a `--test` branch, a tests file, and no absolute paths to network tools or /dev/tcp.
  Finding `--test` does not prove the tests are offline or useful; `--run-tests` runs them.
- Code fences are opened by three or more backticks or tildes and closed by the same character
  repeated at least as often.
"""

import argparse
import datetime as dt
import os
import re
import shutil
import signal
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
TODO_HEADINGS = ("## Problem", "## Ideas")
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


# --- helpers ------------------------------------------------------------------------------------

def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "tasks").is_dir():
            return d
    raise SystemExit(f"No tasks/ folder found in {start} or its parents. Use --root.")


def task_dirs(root: Path):
    tasks = root / "tasks"
    return sorted(d for d in tasks.iterdir() if d.is_dir() and TASK_DIR_RE.match(d.name))


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

IGNORE_RULES = {"/tasks/*/out/": ("/tasks/*/out/", "/tasks/*/out"), ".env": (".env", "/.env")}


def has_rule(gitignore: Path, accepted) -> bool:
    """True if .gitignore has one of the accepted rules as a real line (not in a comment)."""
    if not gitignore.exists():
        return False
    return any(line.strip() in accepted for line in gitignore.read_text().splitlines())


def has_out_rule(gitignore: Path) -> bool:
    return has_rule(gitignore, IGNORE_RULES["/tasks/*/out/"])


def env_is_ignored(root: Path) -> bool:
    """True if .env is ignored: asks git in a git repo (so patterns like .env* count), else checks the rule line."""
    if (root / ".git").exists():
        proc = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".env"], capture_output=True)
        if proc.returncode in (0, 1):
            return proc.returncode == 0
    return has_rule(root / ".gitignore", IGNORE_RULES[".env"])


def cmd_init(root: Path) -> list:
    """Install or update tasks/lib/ from the skill. Always overwrites. Returns the notice lines."""
    lib = root / "tasks" / "lib"
    targets = [root / "tasks", lib, root / ".gitignore"] + [lib / n for n in LIB_FILES]
    links = [str(t.relative_to(root)) for t in targets if t.is_symlink()]
    if links:
        raise SystemExit(f"Refusing to write: {', '.join(links)} is a symbolic link. Nothing was written.")
    lib.mkdir(parents=True, exist_ok=True)
    lines = ["tasks/lib/ is installed from the ops-task plugin (skills/ops-task/assets/lib/) and is overwritten on every init.",
             "Changes made by hand in tasks/lib/ are lost; make them in the plugin repo instead."]
    changed = 0
    for name in LIB_FILES:
        src, dst = ASSETS / "lib" / name, lib / name
        new = src.read_text()
        if dst.exists() and dst.read_text() == new:
            lines.append(f"  unchanged:   tasks/lib/{name}")
            continue
        lines.append(f"  {'overwritten' if dst.exists() else 'installed'}: tasks/lib/{name}")
        dst.write_text(new)
        dst.chmod(0o755)
        changed += 1
    gi = root / ".gitignore"
    for rule, accepted in IGNORE_RULES.items():
        if rule == ".env" and env_is_ignored(root) or rule != ".env" and has_rule(gi, accepted):
            continue
        text = gi.read_text() if gi.exists() else ""
        gi.write_text(text + ("" if not text or text.endswith("\n") else "\n") + rule + "\n")
        lines.append(f"  added '{rule}' to .gitignore")
    lines.append(f"Updated {changed} file(s)." + (" Next: tasks.py lint --run-tests, then commit tasks/lib/." if changed else ""))
    return lines


# --- new ----------------------------------------------------------------------------------------

def cmd_new(root: Path, slug: str, title: str = None, today: str = None) -> Path:
    if not SLUG_RE.match(slug):
        raise SystemExit(f"Bad slug '{slug}': use lowercase letters, digits and single hyphens.")
    tasks = root / "tasks"
    existing = task_dirs(root)
    for d in existing:
        if TASK_DIR_RE.match(d.name).group(2) == slug:
            raise SystemExit(f"A task with the slug '{slug}' exists already: {d.relative_to(root)}")
    number = max((int(TASK_DIR_RE.match(d.name).group(1)) for d in existing), default=0) + 1
    target = tasks / f"{number:02d}-{slug}"
    if target.exists():
        raise SystemExit(f"{target} exists already. Nothing was written.")
    title = title or slug.replace("-", " ").capitalize()
    today = today or dt.date.today().isoformat()
    if not (root / "tasks" / "lib").is_dir():
        print("\n".join(cmd_init(root)))
    target.mkdir()
    for name in ("TODO.md", "PLAN.md"):
        text = (ASSETS / name).read_text()
        text = text.replace("{{TITLE}}", title).replace("{{DATE}}", today)
        (target / name).write_text(text)
    return target


# --- status -------------------------------------------------------------------------------------

def cmd_status(root: Path) -> list:
    rows = []
    for d in task_dirs(root):
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
                rep.error(path, f"looks like {what}; secrets never go into tasks/: use the env file "
                                f"or the password manager named in ## Connections", no)


def lint_waits(path: Path, text: str, rep: Report):
    for no, line in enumerate(text.splitlines(), 1):
        if UNBOUNDED_WAIT_RE.search(line):
            rep.warn(path, "wait without a limit; use a bounded loop with a timeout message", no)


def lint_plan_structure(plan: Path, text: str, rep: Report):
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
    lint_secrets(script, text, rep)
    lint_waits(script, text, rep)


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
        lint_plan_structure(plan, text, rep)
        lint_links(plan, text, rep)
        lint_secrets(plan, text, rep)
        lint_waits(plan, text, rep)
    elif status in PLAN_NEEDED:
        rep.error(task, f"status is '{status}' but PLAN.md is missing")
    scripts = task / "scripts"
    if scripts.is_dir():
        for s in sorted(p for p in scripts.iterdir() if p.is_file() and not p.name.startswith(".")):
            lint_script(s, rep)


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


def run_tests(root: Path, tasks: list, rep: Report):
    targets = []
    lib = root / "tasks" / "lib"
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


def cmd_lint(root: Path, names: list, with_tests: bool) -> Report:
    rep = Report(root)
    all_tasks = task_dirs(root)
    tasks = [t for t in all_tasks if not names or t.name in names]
    for n in names:
        if n not in [t.name for t in all_tasks]:
            rep.error(root / "tasks", f"no task folder '{n}'")
    for d in (root / "tasks").iterdir():
        if d.is_dir() and d.name not in ("lib",) and not TASK_DIR_RE.match(d.name):
            rep.error(d, "folder name must be NN-slug (or 'lib' for shared code)")
    for t in tasks:
        lint_task(t, rep)
    lib = root / "tasks" / "lib"
    for name in LIB_FILES:
        dst = lib / name
        if not dst.exists():
            rep.error(dst, "missing; run tasks.py init")
        elif dst.read_text() != (ASSETS / "lib" / name).read_text():
            rep.error(dst, "differs from the skill's copy; run tasks.py init (it overwrites tasks/lib/)")
        elif name.endswith(".sh"):
            lint_shebang(dst, rep)
    gi = root / ".gitignore"
    if not has_out_rule(gi):
        rep.warn(gi, "add '/tasks/*/out/' so captured state stays out of git")
    if not env_is_ignored(root):
        if (root / ".env").exists():
            rep.error(root / ".env", "exists but is not ignored by git; add '.env' to .gitignore (run tasks.py init)")
        else:
            rep.warn(gi, "add '.env' so the connection settings and credentials stay out of git")
    if with_tests:
        run_tests(root, tasks, rep)
    return rep


# --- self-tests ---------------------------------------------------------------------------------

class SelfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tasks-py-")
        self.root = Path(self.tmp.name)
        (self.root / "tasks").mkdir()
        (self.root / ".gitignore").write_text("/tasks/*/out/\n")
        cmd_init(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def make_good_task(self, name="01-demo", status="in progress"):
        t = self.root / "tasks" / name
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
        t = cmd_new(self.root, "fresh-task", today="2026-10-05")
        self.assertEqual(t.name, "08-fresh-task")
        self.assertIn("Status: open (since 2026-10-05)", (t / "TODO.md").read_text())
        self.assertIn("# Plan: Fresh task", (t / "PLAN.md").read_text())

    def test_new_refuses_bad_or_duplicate_slugs(self):
        self.make_good_task("01-demo")
        for bad in ("Bad_Slug", "-x", "a--b", ""):
            with self.assertRaises(SystemExit):
                cmd_new(self.root, bad)
        with self.assertRaises(SystemExit):
            cmd_new(self.root, "demo")

    def test_find_root_from_a_subfolder(self):
        t = self.make_good_task()
        self.assertEqual(find_root(t / "scripts"), self.root)

    def test_status_counts_only_active_checkboxes(self):
        self.make_good_task()
        self.assertEqual(cmd_status(self.root), [("01-demo", "in progress", "2026-10-09", "1/2")])

    def test_lint_accepts_a_good_task(self):
        self.make_good_task()
        rep = cmd_lint(self.root, [], False)
        self.assertEqual(rep.errors, [])

    def test_lint_reports_broken_parts(self):
        t = self.make_good_task()
        (t / "TODO.md").write_text("# Demo\n## Problem\nx\nSee [plan](MISSING.md)\npassword: Hunter2Hunter2\n")
        (t / "scripts" / "01-check-demo.sh").chmod(0o644)
        (t / "scripts" / "run.sh").write_text("#!/bin/sh\n/usr/bin/curl http://x\n")
        joined = "\n".join(cmd_lint(self.root, [], False).errors)
        for expected in ("'Status: <open", "'## Ideas' is missing", "broken link 'MISSING.md'", "no 'Deadline:",
                         "no 'Plan: [PLAN.md](PLAN.md)' line",
                         "looks like a password", "not executable", "helper name must be",
                         "header lacks 'Purpose:'", "no --test branch", "absolute path to 'curl'"):
            self.assertIn(expected, joined)

    def test_lint_flags_open_boxes_in_a_done_task(self):
        self.make_good_task(status="done")
        joined = "\n".join(cmd_lint(self.root, [], False).errors)
        self.assertIn("task is done but this checkbox is open", joined)
        self.assertNotIn("Fallback", joined)

    def test_lint_flags_a_changing_helper_without_apply(self):
        t = self.make_good_task()
        s = t / "scripts" / "02-delete-thing.sh"
        s.write_text("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: changes\n# Runs on: Mac\n# Connection: none\n# Exit: 0\n# --test\n")
        s.chmod(0o755)
        (t / "scripts" / "tests" / "02-delete-thing.json").write_text('{"cases": []}')
        self.assertIn("--apply flag", "\n".join(cmd_lint(self.root, [], False).errors))

    def test_lint_ignores_fake_secrets_and_warns_on_unbounded_waits(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text() + "GOVC_PASSWORD='not-a-real-password'\n"
                        "until govc about; do sleep 5; done\n")
        rep = cmd_lint(self.root, [], False)
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("wait without a limit" in w for w in rep.warnings))

    def test_lint_run_tests_reports_a_failing_helper(self):
        t = self.make_good_task()
        (t / "scripts" / "01-check-demo.sh").write_text(
            "#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: read-only\n# Runs on: Mac\n# Connection: none\n# Exit: 0\n"
            "[[ \"${1:-}\" == --test ]] && { echo 'FAIL demo'; echo 'boom' >&2; exit 1; }\n")
        rep = cmd_lint(self.root, [], True)
        self.assertIn("--test failed (exit 1): boom", "\n".join(rep.errors))

    def test_lint_run_tests_reports_a_helper_that_cannot_start(self):
        t = self.make_good_task()
        (t / "scripts" / "01-check-demo.sh").chmod(0o644)
        rep = cmd_lint(self.root, [], True)  # must not raise
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
            rep = cmd_lint(self.root, [], True)
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
        lib = self.root / "tasks" / "lib"
        self.assertEqual(sorted(p.name for p in lib.iterdir()), sorted(LIB_FILES))
        notice = "\n".join(cmd_init(self.root))
        self.assertIn("unchanged:   tasks/lib/stubtest.py", notice)
        self.assertIn("Updated 0 file(s).", notice)
        (lib / "with_timeout.sh").write_text("# edited by hand\n")
        notice = "\n".join(cmd_init(self.root))
        self.assertIn("overwritten: tasks/lib/with_timeout.sh", notice)
        self.assertIn("is overwritten on every init", notice)
        self.assertEqual((lib / "with_timeout.sh").read_text(), (ASSETS / "lib" / "with_timeout.sh").read_text())

    def test_init_adds_the_out_line_to_gitignore(self):
        (self.root / ".gitignore").write_text(".env")
        cmd_init(self.root)
        self.assertEqual((self.root / ".gitignore").read_text(), ".env\n/tasks/*/out/\n")

    def test_init_adds_env_to_gitignore(self):
        (self.root / ".gitignore").write_text("/tasks/*/out/\n")
        notice = "\n".join(cmd_init(self.root))
        self.assertEqual((self.root / ".gitignore").read_text(), "/tasks/*/out/\n.env\n")
        self.assertIn("added '.env' to .gitignore", notice)
        self.assertNotIn("added '.env'", "\n".join(cmd_init(self.root)))  # second run adds nothing

    def test_lint_checks_that_env_is_ignored(self):
        self.make_good_task()
        gi = self.root / ".gitignore"
        gi.write_text("/tasks/*/out/\n")
        rep = cmd_lint(self.root, [], False)
        self.assertTrue(any("add '.env'" in w for w in rep.warnings))  # no .env yet: warning only
        (self.root / ".env").write_text("export GOVC_URL='https://vcenter.test.invalid'\n")
        self.assertIn(".env: exists but is not ignored by git", "\n".join(cmd_lint(self.root, [], False).errors))
        gi.write_text("/tasks/*/out/\n.env\n")
        rep = cmd_lint(self.root, [], False)
        self.assertEqual(rep.errors, [])
        self.assertFalse(any(".env" in w for w in rep.warnings))

    def test_env_ignored_by_a_git_pattern_counts(self):
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        self.make_good_task()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("/tasks/*/out/\n.env*\n")
        (self.root / ".env").write_text("x=1\n")
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])

    def test_new_installs_the_lib_when_missing(self):
        shutil.rmtree(self.root / "tasks" / "lib")
        old, sys.stdout = sys.stdout, open(os.devnull, "w")
        try:
            cmd_new(self.root, "fresh", today="2026-10-09")
        finally:
            sys.stdout.close()
            sys.stdout = old
        self.assertTrue((self.root / "tasks" / "lib" / "stubtest.py").exists())

    def test_lint_reports_a_stale_or_missing_lib(self):
        self.make_good_task()
        (self.root / "tasks" / "lib" / "stubtest.py").write_text("# old\n")
        (self.root / "tasks" / "lib" / "with_timeout.sh").unlink()
        joined = "\n".join(cmd_lint(self.root, [], False).errors)
        self.assertIn("stubtest.py: differs from the skill's copy", joined)
        self.assertIn("with_timeout.sh: missing; run tasks.py init", joined)

    def test_helpers_must_be_bash_with_the_bash_shebang(self):
        t = self.make_good_task()
        s = t / "scripts" / "01-check-demo.sh"
        s.write_text(s.read_text().replace("#!/usr/bin/env bash", "#!/bin/sh"))
        py = t / "scripts" / "02-parse-data.py"
        py.write_text("#!/usr/bin/env python3\n")
        py.chmod(0o755)
        joined = "\n".join(cmd_lint(self.root, [], False).errors)
        self.assertIn("01-check-demo.sh: first line must be #!/usr/bin/env bash", joined)
        self.assertIn("02-parse-data.py: helpers are bash scripts", joined)

    def test_plan_fences_should_be_labelled_bash(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "```\nno label\n```\n```zsh\nzsh\n```\n```text\nCommand> shell\n```\n## Rollback"))
        warnings = [w for w in cmd_lint(self.root, [], False).warnings if "fence plan commands" in w]
        self.assertEqual(len(warnings), 2)

    def test_after_box_required_for_steps_with_a_do_part(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        base = plan.read_text()
        step = "### 2.1 Change\n**Do:**\n- [x] Action ran.\n**After** (read-only):\n"
        plan.write_text(base.replace("## Rollback", step + "## Rollback"))
        self.assertIn("step 2.1 has a **Do:** part and needs exactly one", "\n".join(cmd_lint(self.root, [], False).errors))
        # action ran, After check failed: box open, no structural error while the task is not done
        plan.write_text(base.replace("## Rollback", step + "- [ ] After check passed.\n## Rollback"))
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])
        self.assertEqual(cmd_status(self.root)[0][3], "2/4")

    def test_step_ids_are_unique_and_match_their_phase(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "## Phase 2: later\n### 2.1 A\n### 3.1 B\n### 2.1 C\n## Rollback"))
        joined = "\n".join(cmd_lint(self.root, [], False).errors)
        self.assertIn("step 3.1 sits in '## Phase 2'; its ID must start with 2.", joined)
        self.assertIn("step ID 2.1 is used twice", joined)

    def test_init_refuses_symbolic_links(self):
        victim = self.root / "victim.txt"
        victim.write_text("original")
        lib = self.root / "tasks" / "lib"
        (lib / "stubtest.py").unlink()
        (lib / "stubtest.py").symlink_to(victim)
        with self.assertRaises(SystemExit):
            cmd_init(self.root)
        self.assertEqual(victim.read_text(), "original")
        shutil.rmtree(lib)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        lib.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(SystemExit):
            cmd_init(self.root)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_gitignore_rule_must_be_a_real_line(self):
        gi = self.root / ".gitignore"
        gi.write_text("# /tasks/*/out/ will go here\n")
        self.make_good_task()
        self.assertTrue(any("add '/tasks/*/out/'" in w for w in cmd_lint(self.root, [], False).warnings))
        cmd_init(self.root)
        self.assertIn("\n/tasks/*/out/\n", gi.read_text())

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
            self.assertIn(expected, "\n".join(cmd_lint(self.root, [], False).errors), body)

    def test_indented_do_and_after_parts_are_recognised(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "### 2.1 Change\n  **Do:**\n  - [x] Act.\n  **After** (read-only):\n  - [ ] After check passed.\n## Rollback"))
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])

    def test_archived_steps_and_redirects_are_not_active_steps(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text()
            .replace("## Rollback", "### 1.2 Old step: moved to tasks/02-x, step 1.1, on 2026-10-09\n## Rollback")
            .replace("## Not used\n", "## Not used\n### 1.2 Old step (archived)\n**Do:**\n- [ ] Act.\n"))
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])

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
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])

    def test_dropped_task_keeps_partial_history(self):
        t = self.make_good_task(status="dropped")
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "### 2.1 Change\n**Do:**\n- [x] First action ran.\n- [ ] Second action not run.\n"
            "**After** (read-only):\n- [ ] After check passed.\n## Rollback"))
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])

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
            errors = "\n".join(cmd_lint(self.root, [], False).errors)
            self.assertEqual("looks like" in errors, flagged, line)

    def test_fences_with_tildes_and_longer_backtick_runs(self):
        t = self.make_good_task()
        plan = t / "PLAN.md"
        plan.write_text(plan.read_text().replace("## Rollback",
            "~~~\n- [ ] in a tilde fence\n~~~\n````md\n```\n- [ ] in a nested fence\n```\n````\n"
            "See `[x](NOT-THERE.md)` in inline code.\n## Rollback"))
        self.assertEqual(cmd_status(self.root)[0][3], "1/2")
        self.assertEqual(cmd_lint(self.root, [], False).errors, [])

    def test_status_line_must_be_exact(self):
        t = self.make_good_task()
        todo = t / "TODO.md"
        for bad in ("Status: done garbage", "Status: done", "Status: finished (since 2026-10-05)"):
            todo.write_text(todo.read_text().replace(todo.read_text().splitlines()[1], bad))
            self.assertIn("'Status: <open", "\n".join(cmd_lint(self.root, [], False).errors), bad)

    def test_dev_tcp_and_absolute_network_paths_are_rejected(self):
        t = self.make_good_task()
        s = t / "scripts" / "01-check-demo.sh"
        for body, expected in [("exec 3<>/dev/tcp/10.0.0.1/443", "/dev/tcp"),
                               ("\"/opt/homebrew/bin/govc\" about", "absolute path to 'govc'"),
                               ("x=$(/usr/bin/curl -s http://x)", "absolute path to 'curl'")]:
            s.write_text("#!/usr/bin/env bash\n# Purpose: x\n# Usage: x\n# Effect: read-only\n# Runs on: Mac\n# Connection: none\n"
                         "# Exit: 0\n# --test\n" + body + "\n")
            self.assertIn(expected, "\n".join(cmd_lint(self.root, [], False).errors))


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
    p.add_argument("--root", type=Path, help="repo root (default: nearest parent with tasks/)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="install or update tasks/lib/ from the skill (overwrites it)")
    n = sub.add_parser("new", help="create the next tasks/NN-SLUG")
    n.add_argument("slug")
    n.add_argument("--title")
    sub.add_parser("status", help="list tasks")
    l = sub.add_parser("lint", help="check structure")
    l.add_argument("tasks", nargs="*", help="task folder names, e.g. 01-certs (default: all)")
    l.add_argument("--run-tests", action="store_true", help="also run every helper's --test")
    a = p.parse_args(argv)
    if a.cmd == "init" and a.root is None and not any((d / "tasks").is_dir() for d in [Path.cwd(), *Path.cwd().parents]):
        root = Path.cwd().resolve()  # first install: the current folder becomes the repo root
    else:
        root = (a.root or find_root(Path.cwd())).resolve()

    if a.cmd == "init":
        print("\n".join(cmd_init(root)))
        return 0
    if a.cmd == "new":
        t = cmd_new(root, a.slug, a.title)
        print(f"Created {t.relative_to(root)}: fill in TODO.md first.")
        return 0
    if a.cmd == "status":
        rows = cmd_status(root)
        w = max([len(r[0]) for r in rows] + [4])
        print(f"{'TASK':<{w}}  {'STATUS':<11}  {'DEADLINE':<12}  CHECKBOXES (done/total, not a status)")
        for name, status, deadline, boxes in rows:
            print(f"{name:<{w}}  {status:<11}  {deadline:<12}  {boxes}")
        return 0
    rep = cmd_lint(root, a.tasks, a.run_tests)
    for e in rep.errors:
        print(f"ERROR {e}")
    for w in rep.warnings:
        print(f"WARN  {w}")
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
