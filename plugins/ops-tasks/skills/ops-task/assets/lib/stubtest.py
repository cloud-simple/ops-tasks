#!/usr/bin/env python3
# ops-task lib, installed by tasks.py init from the ops-tasks plugin (cloud-simple/ops-tasks, plugins/ops-tasks/skills/ops-task/assets/lib/).
# Edit it in the plugin repo, not here: tasks.py init overwrites this file.
"""Offline test runner for task helper scripts.

Purpose: run a helper script against canned command outputs in a controlled test environment.
Usage:   stubtest.py SCRIPT        run the cases in SCRIPT's tests file
         stubtest.py --test        run this runner's own self-tests
Effect:  read-only. It runs the script in a temporary folder and changes nothing else.
Runs on: the Mac, Python 3.9 or later, standard library only.
Exit:    0 all cases passed, 1 a case failed, 2 wrong arguments.

A helper calls this runner from its own `--test` flag, before any other setup:

    if [[ "${1:-}" == "--test" ]]; then exec python3 "$LIB/stubtest.py" "$0"; fi

The cases for `<ops-dir>/tasks/NN-slug/scripts/01-check-state.sh` live in
`<ops-dir>/tasks/NN-slug/scripts/tests/01-check-state.json`:

    {
      "allow": ["jq", "base64"],            # optional tools from OPTIONAL_ALLOW
      "env_file": "export GOVC_URL=...",    # default fake .env for every case (optional)
      "cases": [
        {
          "name": "healthy vCenter",
          "args": [],
          "env": {"OPS_TIMEOUT": "1"},       # extra variables; sandbox variables cannot be overridden
          "env_file": "export GOVC_URL=...", # content of the fake .env (OPS_ENV_FILE)
          "timeout": 30,                     # seconds for the whole case (default 30)
          "stdin": "typed text\n",           # standard input for the helper (default: none)
          "stubs": {
            "govc": [
              {"args": ["about"], "stdout": "Name: fake"},
              {"args_regex": "^object\\.collect ", "stdout_file": "testdata/collect.txt"},
              {"args_regex": "^alarms$", "delay": 5},
              {"args_regex": ".*", "exit": 1, "stderr": "fake failure"}
            ]
          },
          "expect": {
            "exit": 0,                       # or "exit_nonzero": true
            "stdout_contains": ["connected"],
            "stdout_not_contains": ["ERROR"],
            "stderr_contains": [],
            "stderr_not_contains": [],
            "calls": [["govc", "about"]],    # exact call sequence, optional
            "calls_absent_regex": ["^govc (vm\\.destroy|vm\\.power)"]
          }
        }
      ]
    }

The test environment:

- The environment holds only the sandbox variables (PATH, HOME, TMPDIR, LANG, LC_ALL, OPS_TEST,
  OPS_ENV_FILE, OPS_OUT_DIR, STUB_*) and the case's `env`. A case cannot override a sandbox
  variable. No GOVC_* variable from the real shell reaches the script.
- PATH holds two folders: the stubs of this case, and links to a closed list of local tools
  (DEFAULT_ALLOW, plus the tools from OPTIONAL_ALLOW that the tests file names). A command that
  is neither stubbed nor allowed is not found, so the script cannot fall back to the real curl,
  openssl, govc or ssh by name.
- A stubbed command answers with the first rule whose args match. A call that matches no rule
  exits with code 97 and fails the case.
- The script runs in its own session. When it ends, or its time is up, every process left in
  that session is killed. A case that leaves processes running fails.

This is a controlled test environment, not an enforced network sandbox: bash can still open
/dev/tcp connections, and a script can run a tool by absolute path. `tasks.py lint` rejects both
patterns in helpers.

Output: one line per case, `PASS <name>` or `FAIL <name>: <reason>`.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

# Local tools every helper may use. None of them opens a network connection by itself.
DEFAULT_ALLOW = (
    "bash", "sh", "cat", "grep", "egrep", "sed", "awk", "tr", "sort", "uniq", "head", "tail",
    "cut", "wc", "date", "mktemp", "dirname", "basename", "printf", "echo", "test", "tee", "paste",
    "diff", "mkdir", "rm", "ls", "true", "false", "seq", "expr", "sleep",
)
# Reviewed local tools a tests file may add with "allow".
OPTIONAL_ALLOW = ("jq", "base64", "column", "shasum", "od", "fold", "comm", "join", "nl", "rev")
SANDBOX_VARS = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "OPS_TEST", "OPS_ENV_FILE", "OPS_OUT_DIR")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
CASE_TIMEOUT = 30
EXIT_UNEXPECTED_CALL = 97

STUB_TEMPLATE = """#!{python}
import json, os, re, sys, time
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps([name] + args) + "\\n")
with open(os.environ["STUB_SPEC"]) as f:
    rules = json.load(f).get(name, [])
joined = " ".join(args)
for rule in rules:
    if "args" in rule and rule["args"] != args:
        continue
    if "args_regex" in rule and not re.search(rule["args_regex"], joined):
        continue
    try:
        sys.stdin.read()  # drain piped input, like the real command would
    except Exception:
        pass
    time.sleep(rule.get("delay", 0))  # simulate a slow or hanging endpoint
    out = rule.get("stdout", "")
    if "stdout_file" in rule:
        with open(os.path.join(os.environ["STUB_BASE"], rule["stdout_file"])) as f:
            out = f.read()
    sys.stdout.write(out)
    sys.stderr.write(rule.get("stderr", ""))
    sys.exit(rule.get("exit", 0))
sys.stderr.write("STUB: unexpected call: %s %s\\n" % (name, joined))
with open(os.environ["STUB_LOG"] + ".unexpected", "a") as bad:
    bad.write(json.dumps([name] + args) + "\\n")
sys.exit({unexpected})
"""


class CaseError(Exception):
    """A tests file or case that the runner refuses to run."""


def _tests_file(script: Path) -> Path:
    return script.parent / "tests" / (script.stem + ".json")


def _check_name(name, what: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name) or name in (".", ".."):
        raise CaseError(f"{what} '{name}' must be a plain command name")
    return name


def _place(folder: Path, name: str) -> Path:
    """Path for a new file directly inside folder; refuses anything that escapes it."""
    path = folder / _check_name(name, "file name")
    if path.parent.resolve() != folder.resolve() or path.is_symlink() or path.exists():
        raise CaseError(f"refusing to write '{name}' outside {folder} or over an existing file")
    return path


def _build_allowlist(target: Path, names) -> None:
    for name in names:
        _check_name(name, "allowed tool")
        if name not in DEFAULT_ALLOW and name not in OPTIONAL_ALLOW:
            raise CaseError(f"tool '{name}' is not in the reviewed allowlist; stub it instead")
        real = shutil.which(name)
        if real is not None:
            _place(target, name).symlink_to(real)


class InspectError(Exception):
    """The process list could not be read, so cleanup cannot be verified."""


LEFTOVER_NAMES = []  # names of the last leftovers, for the failure reason


def _session_pids(sid: int) -> list:
    """PIDs of this user's live processes in session sid. Raises InspectError if ps fails.

    Zombies (state Z) are skipped: they have ended and only wait to be reaped."""
    proc = subprocess.run(["ps", "-U", str(os.getuid()), "-o", "pid=,stat=,comm="],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise InspectError(f"cannot read the process list: {proc.stderr.strip() or 'ps failed'}")
    pids = []
    for line in proc.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2 or parts[1].startswith("Z"):
            continue
        try:
            pid = int(parts[0])
            if pid != os.getpid() and os.getsid(pid) == sid:
                pids.append(pid)
                LEFTOVER_NAMES.append(os.path.basename(parts[2]) if len(parts) > 2 else "?")
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    return pids


def _kill_session(sid: int) -> int:
    """Kill every process of the session. Returns how many were still running."""
    LEFTOVER_NAMES.clear()
    pids = _session_pids(sid)
    names = list(LEFTOVER_NAMES)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for _ in range(20):
        if not _session_pids(sid):
            break
        time.sleep(0.05)
    LEFTOVER_NAMES[:] = names
    return len(pids)


def _reap(proc) -> tuple:
    """Kill the known process group, then collect the output. Never waits longer than 10 s.

    This works even when the process list cannot be read: the group of the started command
    is known from its PID."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:  # a process in another group still holds the pipes
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


def run_isolated(cmd, env, cwd, timeout, stdin=None):
    """Run cmd in a new session. Returns (returncode or None, stdout, stderr, leftovers).

    returncode is None when the command itself was still running at the time limit.
    leftovers counts processes still running in the session after the command ended;
    they are killed in every case."""
    proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE, start_new_session=True)
    sid = proc.pid
    try:
        out, err = proc.communicate(input=stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        rc = proc.poll()  # a number here: the script ended, but a child kept the pipes open
        problem = None
        try:
            _kill_session(sid)
        except InspectError as exc:
            problem = exc
        out, err = _reap(proc)  # always: kills the known group and bounds the wait
        if problem:
            raise InspectError(f"{problem} after the time limit")
        return rc, out, err, (1 if rc is not None else 0)
    try:
        return proc.returncode, out, err, _kill_session(sid)
    except InspectError:
        _reap(proc)
        raise


def run_case(script: Path, case: dict, allow, base: Path) -> tuple:
    """Run one case. Returns (passed, reason). Raises CaseError for a case it refuses to run."""
    with tempfile.TemporaryDirectory(prefix="stubtest-") as tmp:
        tmp = Path(tmp)
        stubs, tools, home, out = tmp / "stubs", tmp / "tools", tmp / "home", tmp / "out"
        for d in (stubs, tools, home, out):
            d.mkdir()
        spec = case.get("stubs", {})
        stubbed = {_check_name(c, "stub") for c in spec}
        env = {
            "PATH": f"{stubs}:{tools}", "HOME": str(home), "TMPDIR": str(tmp), "LANG": "C", "LC_ALL": "C",
            "OPS_TEST": "1", "OPS_ENV_FILE": str(tmp / "fake.env"), "OPS_OUT_DIR": str(out),
            "STUB_SPEC": str(tmp / "spec.json"), "STUB_LOG": str(tmp / "calls.jsonl"), "STUB_BASE": str(base),
        }
        for key, value in case.get("env", {}).items():
            if key in SANDBOX_VARS or key.startswith("STUB_"):
                raise CaseError(f"case env may not override the sandbox variable {key}")
            env[key] = str(value)
        _build_allowlist(tools, [n for n in allow if n not in stubbed])
        for cmd in sorted(stubbed):
            stub = _place(stubs, cmd)
            stub.write_text(STUB_TEMPLATE.format(python=sys.executable, unexpected=EXIT_UNEXPECTED_CALL))
            stub.chmod(0o755)
        (tmp / "spec.json").write_text(json.dumps(spec))
        log = tmp / "calls.jsonl"
        log.touch()
        (tmp / "fake.env").write_text(case.get("env_file", "export GOVC_URL='https://vcenter.test.invalid'\n"
                                                           "export GOVC_USERNAME='tester@test.invalid'\n"
                                                           "export GOVC_PASSWORD='not-a-real-password'\n"
                                                           "export GOVC_INSECURE=1\n"))

        cmd = [shutil.which("bash"), str(script)]
        limit = case.get("timeout", CASE_TIMEOUT)
        try:
            rc, stdout, stderr, leftovers = run_isolated(cmd + case.get("args", []), env, tmp, limit,
                                                         case.get("stdin"))
        except InspectError as exc:
            return False, f"{exc}; leftover processes cannot be checked"
        if rc is None:
            return False, f"no result within {limit} s"
        if leftovers:
            return False, f"left {leftovers} process(es) running after it ended: {', '.join(LEFTOVER_NAMES)}"
        unexpected = Path(str(log) + ".unexpected")
        if unexpected.exists():
            return False, f"unexpected call {unexpected.read_text().splitlines()[0]}"
        calls = [json.loads(line) for line in log.read_text().splitlines() if line]
        return check_expect(case.get("expect", {}), rc, stdout, stderr, calls)


def check_expect(expect: dict, rc: int, stdout: str, stderr: str, calls: list) -> tuple:
    if expect.get("exit_nonzero"):
        if rc == 0:
            return False, "exit code 0, expected non-zero"
    elif rc != expect.get("exit", 0):
        tail = (stderr or stdout).strip().splitlines()[-1:] or [""]
        return False, f"exit code {rc}, expected {expect.get('exit', 0)} ({tail[0]})"
    for text in expect.get("stdout_contains", []):
        if text not in stdout:
            return False, f"stdout lacks {text!r}"
    for text in expect.get("stdout_not_contains", []):
        if text in stdout:
            return False, f"stdout has {text!r}"
    for text in expect.get("stderr_contains", []):
        if text not in stderr:
            return False, f"stderr lacks {text!r}"
    for text in expect.get("stderr_not_contains", []):
        if text in stderr:
            return False, f"stderr has {text!r}"
    if "calls" in expect and calls != expect["calls"]:
        return False, f"calls {calls} differ from expected {expect['calls']}"
    for pattern in expect.get("calls_absent_regex", []):
        for call in calls:
            if re.search(pattern, " ".join(call)):
                return False, f"forbidden call {' '.join(call)!r}"
    return True, ""


def run_script_tests(script: Path) -> int:
    script = script.resolve()
    if script.suffix != ".sh":
        print(f"FAIL {script.name}: helpers are bash scripts (NN-verb-object.sh); this runner tests only those")
        return 1
    tests = _tests_file(script)
    if not tests.exists():
        print(f"FAIL {script.name}: no tests file {tests}")
        return 1
    data = json.loads(tests.read_text())
    cases = data.get("cases", [])
    if not cases:
        print(f"FAIL {script.name}: tests file has no cases")
        return 1
    allow = list(dict.fromkeys(list(DEFAULT_ALLOW) + data.get("allow", [])))
    failed = 0
    for case in cases:
        if "env_file" in data:
            case.setdefault("env_file", data["env_file"])
        try:
            passed, reason = run_case(script, case, allow, tests.parent)
        except CaseError as exc:
            passed, reason = False, f"refused: {exc}"
        except Exception as exc:  # a broken case or fixture is a failure, not a crash
            passed, reason = False, f"runner error: {exc}"
        name = case.get("name", "unnamed")
        print(f"PASS {name}" if passed else f"FAIL {name}: {reason}")
        failed += 0 if passed else 1
    return 1 if failed else 0


def self_test() -> int:
    """Run the runner against small fake helpers."""
    checks = []

    def refused(fn):
        try:
            fn()
            return False
        except CaseError:
            return True

    with tempfile.TemporaryDirectory(prefix="stubtest-self-") as tmp:
        tmp = Path(tmp)
        scripts = tmp / "scripts"
        base = scripts / "tests"
        base.mkdir(parents=True)

        def helper(name, body):
            p = scripts / name
            p.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
            p.chmod(0o755)
            return p

        demo = helper("01-demo.sh", """\
            set -euo pipefail
            source "$OPS_ENV_FILE"
            [[ -z "${REAL_SECRET:-}" ]] || { echo "leak"; exit 3; }
            name=$(govc about | sed -n 's/^Name: //p')
            echo "name=$name url=$GOVC_URL"
            if [[ "${1:-}" == "--apply" ]]; then govc vm.power -off demo; fi
            """)
        (base / "01-demo.json").write_text(json.dumps({"cases": [
            {"name": "parse output", "stubs": {"govc": [{"args": ["about"], "stdout": "Name: fake\n"}]},
             "expect": {"stdout_contains": ["name=fake", "vcenter.test.invalid"],
                        "calls": [["govc", "about"]], "calls_absent_regex": ["^govc vm\\.power"]}},
            {"name": "--apply issues the change", "args": ["--apply"],
             "stubs": {"govc": [{"args": ["about"], "stdout": "Name: fake\n"}, {"args": ["vm.power", "-off", "demo"]}]},
             "expect": {"calls": [["govc", "about"], ["govc", "vm.power", "-off", "demo"]]}},
        ]}))
        os.environ["REAL_SECRET"] = "must-not-reach-the-sandbox"
        devnull = open(os.devnull, "w")
        old, sys.stdout = sys.stdout, devnull
        try:
            checks.append(("a good tests file passes, real variables stay out", run_script_tests(demo) == 0))
        finally:
            sys.stdout = old
            devnull.close()
            del os.environ["REAL_SECRET"]

        allow = list(DEFAULT_ALLOW)
        passed, reason = run_case(demo, {"stubs": {"govc": [{"args": ["other"]}]}}, allow, base)
        checks.append(("a call without a matching rule fails", not passed and "unexpected call" in reason))

        probe = helper("02-probe.sh", "for t in curl openssl govc ssh python3 perl nc; do command -v $t && exit 1; done; exit 0\n")
        passed, reason = run_case(probe, {}, allow, base)
        checks.append(("network tools and interpreters are not found", passed))

        victim = tmp / "victim.txt"
        victim.write_text("original")
        checks.append(("an absolute stub name is refused and nothing is overwritten",
                       refused(lambda: run_case(probe, {"stubs": {str(victim): []}}, allow, base))
                       and victim.read_text() == "original"))
        for bad in ("../x", ".", "a/b"):
            checks.append((f"stub name {bad!r} is refused",
                           refused(lambda: run_case(probe, {"stubs": {bad: []}}, allow, base))))
        for var in ("PATH", "HOME", "OPS_ENV_FILE", "STUB_LOG"):
            checks.append((f"a case cannot override {var}",
                           refused(lambda: run_case(probe, {"env": {var: "/usr/bin:/bin"}}, allow, base))))
        for tool in ("curl", "python3.12", "perl", "../bin/sh"):
            checks.append((f"the allowlist refuses {tool}", refused(lambda: _build_allowlist(tmp / "x", [tool]))))

        apply_case = {"args": ["--apply"],
                      "stubs": {"govc": [{"args": ["about"], "stdout": "Name: x\n"}, {"args_regex": "^vm\\.power"}]},
                      "expect": {"calls_absent_regex": ["^govc vm\\.power"]}}
        passed, reason = run_case(demo, apply_case, allow, base)
        checks.append(("a forbidden call fails the case", not passed and "forbidden call" in reason))

        reader = helper("09-read.sh", "read -rsp 'Password: ' P; echo; echo \"got ${#P} chars\"\n")
        passed, reason = run_case(reader, {"stdin": "not-a-real-password\n",
                                           "expect": {"stdout_contains": ["got 19 chars"]}}, allow, base)
        checks.append(("a case can feed standard input to the helper", passed))

        hang = helper("03-hang.sh", "while true; do :; done\n")
        passed, reason = run_case(hang, {"timeout": 1}, allow, base)
        checks.append(("the time limit stops a busy loop", not passed and "no result" in reason))

        marker = tmp / "survived"
        child = helper("04-child.sh", f"( sleep 1; echo survived > {marker} ) &\nwait\n")
        passed, reason = run_case(child, {"timeout": 0.3}, allow, base)
        time.sleep(1.5)
        checks.append(("a timeout also kills the children", not passed and not marker.exists()))

        orphan = helper("05-orphan.sh", f"( sleep 1; echo survived > {marker} ) >/dev/null 2>&1 &\nexit 0\n")
        passed, reason = run_case(orphan, {}, allow, base)
        time.sleep(1.5)
        checks.append(("processes left after the end fail the case and are killed",
                       not passed and "left" in reason and not marker.exists()))

        fakebin = tmp / "fakebin"
        fakebin.mkdir()
        (fakebin / "ps").write_text("#!/bin/sh\necho 'ps: Cannot get process list' >&2\nexit 1\n")
        (fakebin / "ps").chmod(0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{fakebin}:{old_path}"
        try:
            passed, reason = run_case(probe, {}, allow, base)
        finally:
            os.environ["PATH"] = old_path
        checks.append(("an unreadable process list fails the case", not passed and "cannot read the process list" in reason))

        slow = helper("07-slow.sh", f"sleep 1; echo survived > {marker}\n")
        os.environ["PATH"] = f"{fakebin}:{old_path}"
        t0 = time.time()
        try:
            passed, reason = run_case(slow, {"timeout": 0.3}, allow, base)
        finally:
            os.environ["PATH"] = old_path
        elapsed = time.time() - t0
        time.sleep(1.2)
        checks.append(("a timeout with an unreadable process list is reported, bounded, and kills the child",
                       not passed and "cannot read the process list" in reason and elapsed < 3 and not marker.exists()))

        py = scripts / "08-python.py"
        py.write_text("#!/usr/bin/env python3\nprint('hi')\n")
        (base / "08-python.json").write_text(json.dumps({"cases": [{"name": "x"}]}))
        devnull = open(os.devnull, "w")
        old, sys.stdout = sys.stdout, devnull
        try:
            refused_py = run_script_tests(py) == 1
        finally:
            sys.stdout = old
            devnull.close()
        checks.append(("a non-bash helper is refused with a clear message", refused_py))

        group = helper("06-group.sh", f"set -m\n( sleep 1; echo survived > {marker} ) >/dev/null 2>&1 &\nset +m\nexit 0\n")
        passed, reason = run_case(group, {}, allow, base)
        time.sleep(1.5)
        checks.append(("a child in its own process group is killed too", not passed and not marker.exists()))

    failed = 0
    for name, ok in checks:
        print(f"PASS {name}" if ok else f"FAIL {name}")
        failed += 0 if ok else 1
    return 1 if failed else 0


def main(argv) -> int:
    if len(argv) != 2:
        print("Usage: stubtest.py SCRIPT | --test", file=sys.stderr)
        return 2
    if argv[1] == "--test":
        return self_test()
    return run_script_tests(Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
