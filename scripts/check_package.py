#!/usr/bin/env python3
"""Purpose: Check that both agents ship the same working ops-tasks skill.
Usage: python3 scripts/check_package.py [REPO]    check the package in REPO (default: this repo)
       python3 scripts/check_package.py --test    run this script's own self-tests
Effect: Read the package and create temporary test files; no network calls.
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


# --- self-tests ----------------------------------------------------------------------------------
# Each case copies this repo's package files to a temp folder, breaks one thing and checks that
# check_manifests names it. The copied-plugin stage is not self-tested: running this script proves
# it, and the commands it calls have their own tests in tasks.py.

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
    if len(argv) > 1 or (argv and argv[0].startswith("--")):
        # A mistyped option like --tset must not be resolved as a folder. A repo whose name
        # starts with one dash still works; one that starts with two is passed as ./--name.
        print("Usage: python3 scripts/check_package.py [REPO | --test]", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent.parent
    try:
        check(root)
    except ERRORS as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
