"""Run one table script and report on the GT it builds. Runs under the agent's Python, which
has GT, in a working directory that holds the script's data/:

    console/agent-env/.venv/bin/python harness/score/runner.py SCRIPT OUT_DIR \
        [--truth TRUTH [--intent INTENT]]

Scripts must define `gt_tbl`. Their `gtsave()` calls are skipped, so a script can't write
outside OUT_DIR. Writes OUT_DIR/table.png and OUT_DIR/result.json:

    error         the exception that stopped the script or the render, or null
    warnings      warnings raised while building or rendering, as "Category: message"
    rows          the number of rows in the table's data
    columns       the data's column names
    structure     the table's structure, for convergence (score/structure.py)
    data          with --truth: L2, how much of TRUTH's data the table shows (score/data.py)
    intent        with --intent: each check's {check, passed, detail}, from running the intent
                  file's check(candidate, truth) against TRUTH's table
    score_error   the truth, the intent file or a check that failed to run, if one did
"""

import argparse
import json
import runpy
import sys
import traceback
import warnings
from pathlib import Path

import great_tables as gt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.score.data import data_check  # noqa: E402
from harness.score.intent import Table, run_intent  # noqa: E402
from harness.score.structure import signature  # noqa: E402


def build(script: Path) -> gt.GT:
    """Run a table script and return its `gt_tbl`, skipping any gtsave() calls."""
    real_gtsave = gt.GT.gtsave
    gt.GT.gtsave = lambda self, *a, **k: None
    try:
        ns = runpy.run_path(str(script), run_name="__main__")
    finally:
        gt.GT.gtsave = real_gtsave
    tbl = ns.get("gt_tbl")
    if not isinstance(tbl, gt.GT):
        raise TypeError(f"gt_tbl is {type(tbl).__name__}, not GT")
    return tbl


def run(script: Path, out_dir: Path, truth: Path | None, intent: Path | None) -> dict:
    result: dict = {"error": None, "warnings": [], "rows": None, "columns": None}
    result |= {"structure": None, "data": None, "intent": None}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            tbl = build(script)
            data = tbl._tbl_data
            result["rows"] = len(data)
            result["columns"] = [str(c) for c in data.columns]
            tbl.gtsave(str(out_dir / "table.png"))
        except Exception:  # noqa: BLE001 - reported in result.json
            result["error"] = traceback.format_exc(limit=-3).strip()
        result["warnings"] = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
    if result["error"]:
        return result
    try:
        result["structure"] = signature(tbl)
        if truth:
            ref = tbl if truth == script else build(truth)
            columns = runpy.run_path(str(intent)).get("DATA_COLUMNS") if intent else None
            result["data"] = data_check(Table(tbl), Table(ref), columns)
            if intent:
                result["intent"] = run_intent(intent, tbl, ref)
    except Exception:  # noqa: BLE001 - the truth, the intent file or a check failed to run
        result["score_error"] = traceback.format_exc(limit=-3).strip()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--intent", type=Path)
    args = parser.parse_args()
    if args.intent and not args.truth:
        parser.error("--intent needs --truth")
    truth = args.truth.resolve() if args.truth else None
    intent = args.intent.resolve() if args.intent else None
    script, out_dir = args.script.resolve(), args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run(script, out_dir, truth, intent)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
