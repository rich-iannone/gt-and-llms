"""Process metrics for a trial (plan §6), from its Console recordings and trial.json: cells
run, Python errors, and GT API errors.

Console keeps each cell's full output in capture/sessions/<n>/cell-<k>.txt (what the model
saw was capped at 8 KiB). A cell with a traceback is a Python error. It's a GT API error when
the exception is one an API misuse raises (AttributeError, TypeError, ...) and either the
traceback passes through great_tables or the message names GT or one of its functions, e.g.
"'GT' object has no attribute 'fmt_numbr'" or "fmt_number() got an unexpected keyword
argument 'decimal'". This runs on the host, outside the agent's environment.
"""

import json
import re
from pathlib import Path

_TRACEBACK = "Traceback (most recent call last):"
_EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception))(?::\s?(.*))?$", re.M)
_API_EXCEPTIONS = {
    "AttributeError",
    "TypeError",
    "ValueError",
    "KeyError",
    "ImportError",
    "NameError",
    "NotImplementedError",
}
_GT_FRAME = re.compile(r'File "[^"]*/great_tables/')
_GT_NAME = re.compile(
    r"\bGT\b|great_tables|\b(?:fmt|tab|cols|opt|sub|text)_\w+|\b(?:loc|style|vals)\.\w+|"
    r"\b(?:data_color|summary_rows|grand_summary_rows|gtsave|nanoplot_options)\b"
)


def cell_outputs(workspace: Path) -> list[str]:
    """Each cell's full output, in the order run."""
    files = workspace.glob(".agents/console/sessions/*/capture/sessions/*/cell-*.txt")
    # cell-003.txt, not the cell-003-001.png beside it; sorted by session dir, then cell
    cells = sorted(f for f in files if re.fullmatch(r"cell-\d+\.txt", f.name))
    return [f.read_text(errors="replace") for f in cells]


def errors(output: str) -> list[dict]:
    """The exceptions in one cell's output: {type, message, gt_api}."""
    out = []
    for block in output.split(_TRACEBACK)[1:]:
        found = _EXCEPTION.findall(block)
        if not found:
            continue
        kind, message = found[-1]
        name = kind.rsplit(".", 1)[-1]
        gt_api = name in _API_EXCEPTIONS and bool(
            _GT_FRAME.search(block) or _GT_NAME.search(message)
        )
        out.append({"type": name, "message": message.strip()[:300], "gt_api": gt_api})
    return out


def metrics(trial_dir: Path) -> dict:
    trial = json.loads((trial_dir / "trial.json").read_text())
    cells = cell_outputs(trial_dir / "workspace")
    errs = [e for c in cells for e in errors(c)]
    return {
        "cells": len(cells),
        "python_errors": len(errs),
        "gt_api_errors": sum(e["gt_api"] for e in errs),
        "errors": errs,
        "tool_calls": trial["tool_calls"],
        "images_returned": trial["images_returned"],
        "wall_s": trial["wall_s"],
        "cost_usd": trial["cost_usd"],
        "trial_error": trial["error"],
    }
