"""One trial: a fresh workspace and Console session, one chatlas conversation with the writer.

Trial directory layout:

    <trial>/workspace/    Console's working directory: data/, skill/ (skill arms), the agent's
                          table.py and table.png, and Console's recordings in .agents/console/.
                          It lives in a temp dir during the trial, since the agent can't read
                          the repo, and is moved here afterwards.
    <trial>/console.yaml  the resolved Console config the server ran with
    <trial>/chat.md       the conversation, for reading
    <trial>/turns.json    the conversation, for parsing
    <trial>/trial.json    metadata and process metrics
"""

import asyncio
import json
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from chatlas import ChatAnthropic

from harness import console
from harness.arms import Arm
from harness.corpus import DATA, Item


@dataclass(frozen=True)
class Settings:
    model: str = "claude-sonnet-5"
    max_tokens: int = 16000
    max_tool_calls: int = 30
    timeout_s: float = 900


class BudgetExceeded(Exception):
    pass


def _setup(arm: Arm, item: Item) -> Path:
    workspace = console.new_workspace()
    (workspace / "data").mkdir()
    for name in item.data:
        shutil.copy(DATA / name, workspace / "data")
    arm.populate(workspace)
    return workspace


async def run(
    trial_dir: Path, arm: Arm, item: Item, repeat: int, settings: Settings, provenance: dict
) -> dict:
    workspace = _setup(arm, item)
    config_file = console.write_config(trial_dir / "console.yaml")

    chat = ChatAnthropic(
        model=settings.model, system_prompt=arm.system_prompt, max_tokens=settings.max_tokens
    )
    tool_calls = 0
    images = 0

    def on_request(_req):
        nonlocal tool_calls
        tool_calls += 1
        if tool_calls > settings.max_tool_calls:
            raise BudgetExceeded(f"tool-call budget of {settings.max_tool_calls} exceeded")

    def on_result(res):
        nonlocal images
        value = getattr(res, "value", None)
        values = value if isinstance(value, list) else [value]
        images += sum(type(v).__name__.startswith("ContentImage") for v in values)

    chat.on_tool_request(on_request)
    chat.on_tool_result(on_result)

    started = datetime.now(UTC)
    t0 = time.perf_counter()
    console_ready_s = None
    error = None
    try:
        await console.register(chat, config_file, workspace)
        console_ready_s = time.perf_counter() - t0
        await asyncio.wait_for(
            chat.chat_async(item.user_message(), echo="none"), timeout=settings.timeout_s
        )
    except Exception as e:  # noqa: BLE001 - any failure ends the trial; it's recorded, not raised
        error = f"{type(e).__name__}: {e}"
    finally:
        await chat.cleanup_mcp_tools()
    wall_s = time.perf_counter() - t0
    tmp_workspace = workspace
    workspace = Path(shutil.move(workspace, trial_dir / "workspace"))

    chat.export(trial_dir / "chat.md", overwrite=True, content="all")
    turns = [t.model_dump(mode="json") for t in chat.get_turns()]
    (trial_dir / "turns.json").write_text(json.dumps(turns, indent=1))

    last = chat.get_last_turn()
    record = {
        "arm": arm.name,
        "arm_sha256": arm.hash,
        "prompt_id": item.id,
        "prompt_sha256": item.hash,
        "split": item.split,
        "repeat": repeat,
        # Console's recordings name this path as the working directory
        "workspace_during_trial": str(tmp_workspace),
        "settings": settings.__dict__,
        "started_at": started.isoformat(),
        "wall_s": round(wall_s, 1),
        "console_ready_s": round(console_ready_s, 2) if console_ready_s else None,
        "error": error,
        "budget_exceeded": error is not None and error.startswith("BudgetExceeded"),
        "tool_calls": tool_calls,
        "images_returned": images,
        "cost_usd": chat.get_cost(),
        "tokens": chat.get_tokens(),
        "table_py": (workspace / "table.py").is_file(),
        "table_png": (workspace / "table.png").is_file(),
        "final_text": last.text if last and last.role == "assistant" else None,
        "provenance": provenance,
    }
    (trial_dir / "trial.json").write_text(json.dumps(record, indent=2, default=str))
    return record
