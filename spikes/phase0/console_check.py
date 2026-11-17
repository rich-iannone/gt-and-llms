"""Spike (b) inside a real Console session (no model): gtsave() + show_png() image return."""

import shutil
import tempfile
from pathlib import Path

import yaml
from mcp_console import MCPConsole

import trial

work = Path(tempfile.mkdtemp(prefix="gt-console-check-"))
cfg = work.parent / f"{work.name}.yaml"
cfg.write_text(yaml.safe_dump(trial.console_config(work)))

code = """
from great_tables import GT, exibble
from evalhelpers import show_png
GT(exibble.head(4)).tab_header(title="Console check").gtsave("check.png")
import os; print("png bytes:", os.path.getsize("check.png"))
show_png("check.png")
"""

with MCPConsole(command=str(trial.CONSOLE), args=["serve", "--config-file", str(cfg)], server_parameters={"cwd": str(work)}) as c:
    res = c.send(python=code)
    print(type(res).__name__)
    print(res)
print("workspace:", work, sorted(p.name for p in work.iterdir()))
shutil.rmtree(work)
cfg.unlink()
