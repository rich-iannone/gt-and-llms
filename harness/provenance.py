"""Versions and hashes recorded with every trial (plan §4.5)."""

import hashlib
import json
import os
import subprocess
from importlib.metadata import version

from harness import REPO
from harness.console import AGENT_PYTHON, agent_env

_AGENT_PROBE = """
import json, subprocess
from importlib.metadata import version
import nokap
pkgs = ["great-tables", "nokap", "polars", "pandas", "numpy", "matplotlib"]
chrome = nokap.find_chrome()
out = subprocess.run([chrome, "--version"], capture_output=True, text=True, timeout=30)
print(json.dumps({
    "packages": {p: version(p) for p in pkgs},
    "chrome_path": chrome,
    "chrome_version": out.stdout.strip(),
}))
"""


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def collect() -> dict:
    env = {**os.environ, **agent_env()}
    env.pop("CHROME_PATH", None)
    probe = subprocess.run(
        [str(AGENT_PYTHON), "-c", _AGENT_PROBE],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise SystemExit(f"agent env probe failed (run harness/prepare.py?):\n{probe.stderr}")
    return {
        "repo_sha": _git("rev-parse", "HEAD"),
        "repo_dirty": bool(_git("status", "--porcelain")),
        "harness": {p: version(p) for p in ("chatlas", "mcp-console", "anthropic")},
        "agent": json.loads(probe.stdout),
        "agent_lock_sha256": _sha256(REPO / "console/agent-env/uv.lock"),
        "harness_lock_sha256": _sha256(REPO / "uv.lock"),
        "console_config_sha256": _sha256(REPO / "console/config.yaml"),
    }
