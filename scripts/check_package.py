#!/usr/bin/env python3
"""Purpose: Check that both agents ship the same working ops-tasks skill.
Usage: python3 scripts/check_package.py [REPO]         check the package in REPO (default: this repo)
       python3 scripts/check_package.py --release TAG  check this repo just before tagging release TAG
       python3 scripts/check_package.py --test         run this script's own self-tests
Effect: Read the package and create temporary test files. Only --release makes a network call: one
        read-only `git ls-remote` to origin. It fetches nothing and changes no git refs.
Runs on: A machine with Python 3.9 or later, bash and git.
Exit: 0 all checks passed, 1 a check or a self-test failed, 2 wrong arguments.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired)
RELEASE_REMOTE = "origin"
RELEASE_BRANCH = "main"
REMOTE_TIMEOUT = 30  # seconds for the lookup of main on origin


@contextlib.contextmanager
def chdir(path):
    """Change the working directory for a block. contextlib.chdir needs Python 3.11."""
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def package_path(root, value):
    require(isinstance(value, str) and value.startswith("./"),
            "Package paths must start with ./")
    require(".." not in Path(value).parts, "Package paths must not contain ..")
    path = (root / value).resolve()
    require(root.resolve() in path.parents and path.is_dir(),
            "Package paths must name a directory inside their root")
    return path


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=90)
    require(result.returncode == 0,
            f"Command failed ({result.returncode}): {args}\n{result.stdout}")
    return result.stdout


def check_manifests(root):
    """Check the two marketplaces and the two plugin manifests. Return the plugin folder."""
    claude_catalog = read_json(root / ".claude-plugin/marketplace.json")
    codex_catalog = read_json(root / ".agents/plugins/marketplace.json")
    require(claude_catalog["name"] == codex_catalog["name"] == "ops-tasks",
            "Both marketplaces must be named ops-tasks")
    require(len(claude_catalog["plugins"]) == len(codex_catalog["plugins"]) == 1,
            "Each marketplace must contain one plugin")
    claude_entry = claude_catalog["plugins"][0]
    codex_entry = codex_catalog["plugins"][0]
    require(codex_entry["source"]["source"] == "local",
            "The Codex marketplace must use the plugin in this repo")
    plugin = package_path(root, claude_entry["source"])
    require(plugin == package_path(root, codex_entry["source"]["path"]),
            "Both marketplaces must point to the same plugin")
    claude = read_json(plugin / ".claude-plugin/plugin.json")
    codex = read_json(plugin / ".codex-plugin/plugin.json")
    require(claude["name"] == codex["name"] == claude_entry["name"]
            == codex_entry["name"] == "ops-tasks", "Plugin names must match")
    require(claude["version"] == codex["version"], "Plugin versions must match")
    skills = package_path(plugin, codex["skills"])
    require(skills == (plugin / "skills").resolve(),
            "Codex must use Claude's default skills directory")
    require(list(skills.glob("*/SKILL.md")) == [skills / "ops-tasks/SKILL.md"],
            "The plugin must ship one shared ops-tasks skill")
    for name in ("scripts/tasks.py", "assets/lib/stubtest.py", "assets/lib/with_timeout.sh"):
        require(os.access(skills / "ops-tasks" / name, os.X_OK),
                f"The bundled file must be executable: {name}")
    return plugin


def check_copied_plugin(plugin):
    """Copy the plugin and run its commands from a nested folder of a throwaway git repo."""
    with tempfile.TemporaryDirectory(prefix="ops-tasks-package-") as temp:
        base = Path(temp)
        copied = base / "installed plugin"
        shutil.copytree(plugin, copied)
        repo = base / "user repo"
        repo.mkdir()
        run(["git", "init", "-q", str(repo)], base)
        nested = repo / "nested directory"
        nested.mkdir()
        script = copied / "skills/ops-tasks/scripts/tasks.py"
        run([str(script), "init"], nested)
        require((repo / "ops/.ops-tasks").is_file(), "init must target the user's repo")
        run([str(script), "new", "package-check", "--title", "Package check"], nested)
        task = repo / "ops/tasks/01-package-check"
        require("# Package check" in (task / "TODO.md").read_text(),
                "new must load the bundled template")
        # Replace the plan's scaffold with a local task that needs no connections.
        (task / "PLAN.md").write_text(
            "# Plan: Package check\n\n## Goal\n\nVerify local packaging.\n\n"
            "## Stop conditions\n\nStop if a command fails.\n\n"
            "## Steps\n\n### 1.1 Inspect\n\n- [ ] Inspect the local package.\n\n"
            "## Rollback\n\nNo infrastructure changes.\n\n## Log\n"
        )
        require("01-package-check" in run([str(script), "status"], nested),
                "status must find the task from a nested working directory")
        run([str(script), "lint", "--run-tests"], nested)
        require(not (copied / "ops").exists(), "Commands must not create tasks in the plugin")


def check(root):
    plugin = check_manifests(root)
    print("PASS marketplace paths, shared skill and matching versions", flush=True)
    check_copied_plugin(plugin)
    print("PASS copied plugin: init, new, status and lint --run-tests", flush=True)


def git(root, args, timeout=30):
    """Run a read-only git command in root. Never prompts: stdin is closed and so is the
    terminal prompt for credentials."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(root)] + args, text=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)


def check_release(root, tag):
    """Check root just before the release tag is created: the tag matches both manifests, the
    checkout is clean, and HEAD is the commit of main on origin, read live from the server."""
    plugin = check_manifests(root)
    version = read_json(plugin / ".claude-plugin/plugin.json")["version"]
    require(tag == f"v{version}",
            f"The release tag must be v{version}, the version in both plugin manifests, not {tag}")
    status = git(root, ["status", "--porcelain", "--untracked-files=all"])
    require(status.returncode == 0, f"git status failed: {status.stderr.strip()}")
    require(status.stdout == "",
            "The checkout must be clean: no staged, unstaged or untracked files")
    head = git(root, ["rev-parse", "--verify", "HEAD^{commit}"])
    require(head.returncode == 0, f"Cannot read HEAD: {head.stderr.strip()}")
    head = head.stdout.strip()
    ref = f"refs/heads/{RELEASE_BRANCH}"
    try:
        live = git(root, ["ls-remote", "--exit-code", RELEASE_REMOTE, ref], timeout=REMOTE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ValueError(f"{RELEASE_REMOTE} did not answer within {REMOTE_TIMEOUT} s")
    require(live.returncode != 2, f"{RELEASE_REMOTE} has no {RELEASE_BRANCH} branch")
    require(live.returncode == 0,
            f"Cannot read {RELEASE_BRANCH} from {RELEASE_REMOTE}: {live.stderr.strip()}")
    lines = live.stdout.strip().splitlines()
    require(len(lines) == 1 and lines[0].split("\t")[1:] == [ref],
            f"Unexpected answer from {RELEASE_REMOTE} for {ref}: {live.stdout.strip()}")
    remote = lines[0].split("\t")[0]
    require(head == remote,
            f"HEAD {head[:12]} is not {RELEASE_BRANCH} on {RELEASE_REMOTE} ({remote[:12]}): tag only the "
            f"merged commit, after git pull --ff-only")
    print(f"PASS release {tag}: manifests, clean checkout and {RELEASE_BRANCH} on {RELEASE_REMOTE}",
          flush=True)


# --- self-tests ----------------------------------------------------------------------------------
# Each case copies this repo's package files to a temp folder, breaks one thing and checks that
# check_manifests names it. The copied-plugin stage is not self-tested: running this script proves
# it, and the commands it calls have their own tests in tasks.py. The release cases make the copy a
# git repo whose origin is a local bare repo, so they need no network.

class SelfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ops-tasks-check-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        src = Path(__file__).resolve().parent.parent
        self.root.mkdir()
        for part in (".claude-plugin", ".agents", "plugins"):
            shutil.copytree(src / part, self.root / part,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        self.plugin = self.root / "plugins/ops-tasks"
        self.skill = self.plugin / "skills/ops-tasks"

    def edit_json(self, rel, change):
        path = self.root / rel
        data = read_json(path)
        change(data)
        path.write_text(json.dumps(data, indent=2))

    def assert_rejects(self, message):
        with self.assertRaises(ValueError) as ctx:
            check_manifests(self.root)
        self.assertIn(message, str(ctx.exception))

    def git_ok(self, cwd, *args):
        """Run git in cwd with a fixed identity and without the user's signing or hooks."""
        return run(["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", "-c", "commit.gpgsign=false",
                    "-c", "core.hooksPath=/dev/null", *args], cwd)

    def make_release_repo(self):
        """Make the copied package a git repo whose origin is a local bare repo with its main.
        Return the release tag for the manifest version."""
        self.remote = self.root.parent / "remote.git"
        self.git_ok(self.root.parent, "init", "-q", "--bare", str(self.remote))
        self.git_ok(self.root, "init", "-q")
        self.git_ok(self.root, "add", "-A")
        self.git_ok(self.root, "commit", "-q", "-m", "package")
        self.git_ok(self.root, "remote", "add", "origin", str(self.remote))
        self.git_ok(self.root, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.git_ok(self.root, "fetch", "-q", "origin")
        return "v" + read_json(self.plugin / ".claude-plugin/plugin.json")["version"]

    def assert_release_rejects(self, tag, message):
        with self.assertRaises(ValueError) as ctx, contextlib.redirect_stdout(io.StringIO()):
            check_release(self.root, tag)
        self.assertIn(message, str(ctx.exception))

    def test_release_passes_for_the_tag_of_the_manifest_version(self):
        tag = self.make_release_repo()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            check_release(self.root, tag)
        self.assertIn(f"PASS release {tag}", out.getvalue())

    def test_release_rejects_a_tag_that_differs_from_the_manifests(self):
        tag = self.make_release_repo()
        for wrong in ("v9.9.9", tag[1:], f"ops-tasks--{tag}"):
            self.assert_release_rejects(wrong, f"must be {tag}")

    def test_release_rejects_a_checkout_that_is_not_clean(self):
        tag = self.make_release_repo()
        skill_md = self.skill / "SKILL.md"
        skill_md.write_text(skill_md.read_text() + "changed\n")
        self.assert_release_rejects(tag, "must be clean")  # unstaged
        self.git_ok(self.root, "add", "-A")
        self.assert_release_rejects(tag, "must be clean")  # staged
        self.git_ok(self.root, "reset", "-q", "--hard")
        self.git_ok(self.root, "config", "status.showUntrackedFiles", "no")
        (self.root / "notes.txt").write_text("untracked\n")
        self.assert_release_rejects(tag, "must be clean")  # untracked, although git status hides it

    def test_release_rejects_head_that_is_not_main_on_origin(self):
        tag = self.make_release_repo()
        other = self.root.parent / "other"
        self.git_ok(self.root.parent, "clone", "-q", "-b", "main", str(self.remote), str(other))
        (other / "later.txt").write_text("later\n")
        self.git_ok(other, "add", "-A")
        self.git_ok(other, "commit", "-q", "-m", "later")
        self.git_ok(other, "push", "-q", "origin", "HEAD:refs/heads/main")
        # origin/main in the checkout still equals HEAD; only the live lookup sees the new commit.
        self.assert_release_rejects(tag, "is not main on origin")
        self.git_ok(self.root, "pull", "-q", "--ff-only", "origin", "main")
        with contextlib.redirect_stdout(io.StringIO()):
            check_release(self.root, tag)
        (self.root / "CHANGELOG.md").write_text("local commit\n")
        self.git_ok(self.root, "add", "-A")
        self.git_ok(self.root, "commit", "-q", "-m", "changelog")
        self.assert_release_rejects(tag, "is not main on origin")  # a commit that is not merged

    def test_release_rejects_a_missing_main_on_origin(self):
        tag = self.make_release_repo()
        self.git_ok(self.remote, "update-ref", "-d", "refs/heads/main")
        self.assert_release_rejects(tag, "origin has no main branch")

    def test_release_rejects_a_failed_lookup(self):
        tag = self.make_release_repo()
        self.git_ok(self.root, "remote", "set-url", "origin", str(self.root.parent / "missing.git"))
        self.assert_release_rejects(tag, "Cannot read main from origin")

    def test_main_parses_the_release_option(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(["--release"]), 2)
            self.assertEqual(main(["--release", "v1.0.0", "extra"]), 2)
            self.assertEqual(main(["--release", "--test"]), 2)
        self.assertIn("--release TAG", err.getvalue())

    def test_the_repo_package_passes(self):
        self.assertEqual(check_manifests(self.root), self.plugin.resolve())

    def test_versions_must_match(self):
        self.edit_json("plugins/ops-tasks/.codex-plugin/plugin.json",
                       lambda d: d.update(version="9.9.9"))
        self.assert_rejects("Plugin versions must match")

    def test_names_must_match(self):
        self.edit_json("plugins/ops-tasks/.codex-plugin/plugin.json",
                       lambda d: d.update(name="other-tasks"))
        self.assert_rejects("Plugin names must match")

    def test_marketplaces_must_point_to_the_same_plugin(self):
        other = self.root / "plugins/other"
        shutil.copytree(self.plugin, other)
        self.edit_json(".agents/plugins/marketplace.json",
                       lambda d: d["plugins"][0]["source"].update(path="./plugins/other"))
        self.assert_rejects("Both marketplaces must point to the same plugin")

    def test_codex_marketplace_must_be_local(self):
        self.edit_json(".agents/plugins/marketplace.json",
                       lambda d: d["plugins"][0]["source"].update(source="git"))
        self.assert_rejects("must use the plugin in this repo")

    def test_paths_must_start_with_dot_slash(self):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].update(source=str(self.plugin)))
        self.assert_rejects("Package paths must start with ./")

    def test_paths_must_not_leave_the_root(self):
        outside = self.root.parent / "plugins/ops-tasks"
        shutil.copytree(self.plugin, outside)
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].update(source="./../plugins/ops-tasks"))
        self.assert_rejects("Package paths must not contain ..")

    def test_paths_must_name_an_existing_directory(self):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].update(source="./plugins/missing"))
        self.edit_json(".agents/plugins/marketplace.json",
                       lambda d: d["plugins"][0]["source"].update(path="./plugins/missing"))
        self.assert_rejects("must name a directory inside their root")

    def test_codex_skills_must_be_the_default_folder(self):
        shutil.copytree(self.plugin / "skills", self.plugin / "other-skills")
        self.edit_json("plugins/ops-tasks/.codex-plugin/plugin.json",
                       lambda d: d.update(skills="./other-skills/"))
        self.assert_rejects("default skills directory")

    def test_exactly_one_skill_ships(self):
        extra = self.plugin / "skills/extra"
        extra.mkdir()
        (extra / "SKILL.md").write_text("---\nname: extra\ndescription: x\n---\n")
        self.assert_rejects("one shared ops-tasks skill")

    def test_bundled_scripts_must_be_executable(self):
        script = self.skill / "assets/lib/with_timeout.sh"
        script.chmod(0o644)
        self.assert_rejects("must be executable: assets/lib/with_timeout.sh")

    def test_main_rejects_a_mistyped_option(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(["--tset"]), 2)
            self.assertEqual(main(["--test", "extra"]), 2)
        self.assertIn("Usage:", err.getvalue())

    def test_main_accepts_a_repo_path_that_starts_with_a_dash(self):
        # Run from the temp folder so the relative name is resolved and checked as a path.
        self.root.rename(self.root.parent / "-repo")
        self.root = self.root.parent / "-repo"
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].update(source="./plugins/missing"))
        with chdir(self.root.parent), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(["-repo"]), 1)
        self.assertIn("must name a directory inside their root", err.getvalue())


def self_test():
    """Run the unittest cases and print one PASS or FAIL line per case."""
    suite = unittest.TestLoader().loadTestsFromTestCase(SelfTests)
    failed = 0
    for test in suite:
        result = unittest.TestResult()
        test.run(result)
        name = test.id().rsplit(".", 1)[-1]
        problems = result.failures + result.errors
        if problems:
            failed += 1
            last = problems[0][1].strip().splitlines()[-1]
            print(f"FAIL {name}: {last}")
        else:
            print(f"PASS {name}")
    return 1 if failed else 0


def main(argv):
    if argv == ["--test"]:
        return self_test()
    release = len(argv) == 2 and argv[0] == "--release" and not argv[1].startswith("-")
    if not release and (len(argv) > 1 or (argv and argv[0].startswith("--"))):
        # A mistyped option like --tset must not be resolved as a folder. A repo whose name
        # starts with one dash still works; one that starts with two is passed as ./--name.
        print("Usage: python3 scripts/check_package.py [REPO | --release TAG | --test]", file=sys.stderr)
        return 2
    this_repo = Path(__file__).resolve().parent.parent
    try:
        if release:
            check_release(this_repo, argv[1])
            return 0
        check(Path(argv[0]).resolve() if argv else this_repo)
    except ERRORS as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
