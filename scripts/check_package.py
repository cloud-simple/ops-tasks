#!/usr/bin/env python3
"""Purpose: Check that both agents ship the same working ops-tasks skill.
Usage: python3 scripts/check_package.py [REPO]
Effect: Read the package and create temporary test files; no network calls.
Runs on: A machine with Python 3.9 or later, bash and git.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


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


def check(root):
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
    print("PASS marketplace paths, shared skill and matching versions", flush=True)

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
        print("PASS copied plugin: init, new, status and lint --run-tests", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit("Usage: python3 scripts/check_package.py [REPO]")
    root = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path(__file__).resolve().parent.parent
    try:
        check(root)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        sys.exit(f"FAIL {exc}")
