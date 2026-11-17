"""Spike (a)+(c): one end-to-end trial with chatlas + mcp-console + Sonnet 5.

Creates runs/<stamp>/ as the Console workspace, has the model build a GT table that is saved to
table.py/table.png, and reports tokens, cost, wall-clock, and whether an image came back.

Usage: python trial.py [--model claude-sonnet-5] [--max-turns 20] [--prompt-index 0]
"""

import argparse
import asyncio
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import mcp_console
import yaml
from chatlas import ChatAnthropic
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
load_dotenv(REPO / ".env")

CHROME = HERE / ".browsers/chrome-headless-shell-mac-arm64/chrome-headless-shell"
CONSOLE = HERE / ".venv/bin/mcp-console"

BASE_PROMPT = """\
You are a data analyst who builds display tables in Python with the Great Tables package.

You work through the Console `send` tool, which runs Python in a persistent session whose working
directory is the project directory. Data files are in `data/`. Do not install packages.

Deliverable: write a self-contained script `table.py` in the working directory that loads the data,
builds the table as a variable named `gt_tbl`, and ends with `gt_tbl.gtsave("table.png")`. Run it in
Console (for example with `exec(open("table.py").read())`).

To see the rendered result, run `from evalhelpers import show_png; show_png("table.png")`; the image
is returned to you. Check it against the request and revise `table.py` if needed. When the table is
done, reply with a one-paragraph summary.
"""

PROMPTS = [json.loads(l) for l in (REPO / "eval_dataset_no_docs.jsonl").read_text().splitlines() if l.strip()]


def console_config(trial_dir: Path) -> dict:
    return {
        "languages": ["python"],
        # A uv-locked env (agent-env/) rather than managed Python: tighter pinning, and with R on
        # the host, managed preparation goes through R's `ir`, which fails on R 4.2.3 here.
        "python": str(HERE / "agent-env/.venv"),
        # Even Python-only sessions otherwise prepare R bridge packages through `ir` (same failure)
        "r": {"resolution": "disabled"},
        "sandbox": {
            "profile": "workspace",
            "network": {
                "proxy": {"mode": "full", "domains": {"allow": []}},
                # nokap binds a loopback port for Chrome's DevTools endpoint
                "allow_local_binding": True,
            },
        },
        "environment": {
            "CHROME_PATH": str(CHROME),
            "NOKAP_SPIKE_ARGS": "--single-process",
            "PYTHONPATH": str(HERE / "agent_site"),
            "MPLBACKEND": "agg",
        },
    }


async def run(model: str, max_turns: int, prompt_index: int = 0) -> dict:
    item = PROMPTS[prompt_index]
    csv = item["metadata"]["example"] + ".csv"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    trial_dir = HERE / "runs" / stamp
    (trial_dir / "data").mkdir(parents=True)
    # An existing .agents/console makes Console keep recordings inside the trial dir
    (trial_dir / ".agents/console").mkdir(parents=True)
    shutil.copy(REPO / "data" / csv, trial_dir / "data")
    cfg_path = trial_dir.parent / f"{stamp}.console.yaml"
    cfg_path.write_text(yaml.safe_dump(console_config(trial_dir), sort_keys=False))

    chat = ChatAnthropic(model=model, system_prompt=BASE_PROMPT, max_tokens=16000)

    n_tool_calls = 0
    n_images = 0

    def on_request(req):
        nonlocal n_tool_calls
        n_tool_calls += 1
        if n_tool_calls > max_turns:
            raise RuntimeError(f"tool-call budget of {max_turns} exceeded")

    def on_result(res):
        nonlocal n_images
        value = res.value if hasattr(res, "value") else None
        items = value if isinstance(value, list) else [value]
        n_images += sum(1 for v in items if type(v).__name__.startswith("ContentImage"))

    chat.on_tool_request(on_request)
    chat.on_tool_result(on_result)

    t0 = time.perf_counter()
    error = None
    try:
        await mcp_console.chatlas.register(
            chat,
            command=str(CONSOLE),
            args=["serve", "--config-file", str(cfg_path)],
            transport_kwargs={"cwd": str(trial_dir)},
        )
        t_ready = time.perf_counter() - t0
        await chat.chat_async(f"Data file: `data/{csv}`.\n\n{item['input']}", echo="none")
    except Exception as e:
        t_ready = None
        error = f"{type(e).__name__}: {e}"
    finally:
        await chat.cleanup_mcp_tools()
    wall = time.perf_counter() - t0

    try:
        chat.export(trial_dir / "chat.md", overwrite=True, content="all")
    except Exception as e:
        print(f"chat export failed: {type(e).__name__}: {e}")
    tokens = chat.get_tokens()
    # What the model actually received: content types of each turn (shows whether images arrived)
    content_types = [
        [type(c).__name__ + (f"[{type(getattr(c, 'value', None)).__name__}]" if hasattr(c, "value") else "") for c in t.contents]
        for t in chat.get_turns()
    ]
    result = {
        "content_types": content_types,
        "trial_dir": str(trial_dir.relative_to(HERE)),
        "model": model,
        "prompt": item["metadata"],
        "error": error,
        "wall_s": round(wall, 1),
        "console_ready_s": round(t_ready, 1) if t_ready else None,
        "tool_calls": n_tool_calls,
        "images_returned": n_images,
        "turn_tokens": tokens,
        "cost_usd": chat.get_cost(),
        "table_py": (trial_dir / "table.py").exists(),
        "table_png": (trial_dir / "table.png").exists(),
        "final_text": chat.get_last_turn().text if chat.get_last_turn() else None,
    }
    (trial_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--prompt-index", type=int, default=0)
    a = ap.parse_args()
    print(json.dumps(asyncio.run(run(a.model, a.max_turns, a.prompt_index)), indent=2, default=str))
