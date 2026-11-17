"""Set up the agent's environment: sync console/agent-env, install the pinned
chrome-headless-shell into .browsers/, warm up Console, then check a real Console session:
the agent can render, and can't write outside its workspace, reach the network, or read
eval material.

    uv run harness/prepare.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mcp_console

from harness import REPO, console

# Chrome for Testing version; the one Phase 0 validated under Console's sandbox
CHROME_VERSION = "156.0.8078.80"

# Run inside Console. Each probe should succeed (True) or be blocked (False).
_PROBE = """
import json, urllib.request
from pathlib import Path

def ok(fn):
    try:
        fn()
        return True
    except Exception:
        return False

def render():
    import great_tables as gt, polars as pl
    gt.GT(pl.DataFrame({"x": [1, 2]})).gtsave("check.png")

def show():
    from evalhelpers import show_png

repo, home = Path(REPO), Path.home()
print(json.dumps({
    "render a table": ok(render),
    "import evalhelpers": ok(show),
    "write in workspace": ok(lambda: Path("ok.txt").write_text("x")),
    "write in repo": ok(lambda: (repo / "probe.txt").write_text("x")),
    "write in home": ok(lambda: (home / "probe.txt").write_text("x")),
    "read .env": ok(lambda: (repo / ".env").read_text()),
    "read .git": ok(lambda: list((repo / ".git").iterdir())),
    "list corpus/": ok(lambda: list((repo / "corpus").iterdir())),
    "list arms/": ok(lambda: list((repo / "arms").iterdir())),
    "list runs/": ok(lambda: list((repo / "runs").iterdir())),
    "list ~/.claude": ok(lambda: list((home / ".claude").iterdir())),
    "list ~/py_projects": ok(lambda: list((home / "py_projects").iterdir())),
    "list a repo sibling": ok(lambda: [p.stat() for p in repo.parent.iterdir() if p != repo][0]),
    "HTTP to example.com": ok(lambda: urllib.request.urlopen("https://example.com", timeout=5)),
}))
"""

_EXPECTED = {"render a table": True, "import evalhelpers": True, "write in workspace": True}


async def _check_session(config_file: Path, workspace: Path) -> dict[str, bool]:
    async with mcp_console.AsyncMCPConsole(
        command=console.COMMAND,
        args=["serve", "--config-file", str(config_file)],
        server_parameters={"cwd": str(workspace)},
    ) as c:
        out = await c.send(python=_PROBE.replace("REPO", repr(str(REPO))))
    return json.loads(out.text.strip().splitlines()[-1])


def main() -> None:
    # Under `uv run`, VIRTUAL_ENV points at the harness env, and uv warns that it's ignored
    host_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    subprocess.run(
        ["uv", "sync", "--locked", "--project", "console/agent-env"],
        cwd=REPO,
        env=host_env,
        check=True,
    )

    env = {**host_env, **console.agent_env()}
    install = f"import nokap; print(nokap.install_chrome({CHROME_VERSION!r}))"
    subprocess.run([str(console.AGENT_PYTHON), "-c", install], env=env, check=True)

    with tempfile.TemporaryDirectory() as tmp:
        cfg = console.write_config(Path(tmp) / "console.yaml")
        subprocess.run([str(console.COMMAND), "warmup", "--config-file", str(cfg)], check=True)
        workspace = console.new_workspace()
        try:
            results = asyncio.run(_check_session(cfg, workspace))
        finally:
            shutil.rmtree(workspace)

    failures = []
    for name, allowed in results.items():
        expected = _EXPECTED.get(name, False)
        print(
            f"  {'ok  ' if allowed == expected else 'FAIL'} {name}: "
            f"{'allowed' if allowed else 'blocked'}"
        )
        if allowed != expected:
            failures.append(name)
    if failures:
        raise SystemExit(f"sandbox check failed: {', '.join(failures)}")
    print("Sandbox check passed.")


if __name__ == "__main__":
    main()
