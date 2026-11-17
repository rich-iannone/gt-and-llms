"""Everything that touches mcp-console, kept in one place because Console is a development preview."""

import tempfile
from pathlib import Path
from typing import Any

import mcp_console
import yaml

from harness import REPO

CONFIG = REPO / "console/config.yaml"
COMMAND = REPO / ".venv/bin/mcp-console"
AGENT_PYTHON = REPO / "console/agent-env/.venv/bin/python"

# Settings in console/config.yaml that hold repo-relative paths
_PATH_KEYS = [("python",), ("environment", "NOKAP_CACHE_DIR"), ("environment", "PYTHONPATH")]
# Top-level repo entries the agent's Python reads; everything else in the repo is denied
_AGENT_NEEDS = {"console", ".browsers"}


def _denied() -> list[str]:
    repo = [p for p in REPO.iterdir() if p.name not in _AGENT_NEEDS]
    siblings = [p for p in REPO.parent.iterdir() if p != REPO]
    return [str(p) for p in sorted(repo + siblings)]


def resolved_config() -> dict:
    cfg = yaml.safe_load(CONFIG.read_text())
    for keys in _PATH_KEYS:
        parent = cfg
        for key in keys[:-1]:
            parent = parent[key]
        parent[keys[-1]] = str(REPO / parent[keys[-1]])
    fs = cfg["sandbox"]["filesystem"]
    fs["deny"] = [str(Path(p).expanduser()) for p in fs["deny"]] + _denied()
    return cfg


def agent_env() -> dict[str, str]:
    """The environment variables the agent's Python runs with."""
    return resolved_config()["environment"]


def write_config(path: Path) -> Path:
    path.write_text(yaml.safe_dump(resolved_config(), sort_keys=False))
    return path


def new_workspace() -> Path:
    """A fresh directory outside the repo (which the agent can't read) for one trial."""
    workspace = Path(tempfile.mkdtemp(prefix="gt-eval-"))
    # An existing .agents/console makes Console keep its recordings inside the workspace
    (workspace / ".agents/console").mkdir(parents=True)
    return workspace


def session(config_file: Path, workspace: Path) -> mcp_console.AsyncMCPConsole:
    """A fresh Console server (one isolated session) driven from Python, with no model; for
    use as `async with session(...) as c`."""
    return mcp_console.AsyncMCPConsole(
        command=str(COMMAND),
        args=["serve", "--config-file", str(config_file)],
        server_parameters={"cwd": str(workspace)},
    )


_RUNNING = "[running; poll with an empty send]"


async def run_cell(c: mcp_console.AsyncMCPConsole, python: str, timeout_s: float) -> str:
    """Run one Python cell to completion and return its output."""
    out = await c.send(python=python, timeout_ms=int(timeout_s * 1000))
    while out.rstrip().endswith(_RUNNING):
        out = out.rstrip().removesuffix(_RUNNING) + await c.send(timeout_ms=int(timeout_s * 1000))
    return out


async def register(chat: Any, config_file: Path, workspace: Path) -> None:
    """Start a fresh Console server (one isolated session) and give its tools to `chat`."""
    await mcp_console.chatlas.register(
        chat,
        command=COMMAND,
        args=["serve", "--config-file", str(config_file)],
        transport_kwargs={"cwd": str(workspace)},
    )
