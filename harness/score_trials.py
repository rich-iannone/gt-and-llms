"""Score trials: L0–L2, structure and process metrics (plan §6). The judge (L3) is separate.

    uv run harness/score_trials.py runs/<run-id>
    uv run harness/score_trials.py runs/<run-id> --force    # re-score trials already scored

Each trial's table.py is re-run in a fresh Console session with no model attached, under the
same sandbox as the trials, in a new Python process. Its workspace holds only fresh copies
of data/, table.py and the arm's skill/, so a script that leans on state left in the trial's
session fails L0. The item's truth.py and intent.py, and the scoring code, are copied in beside it.
Writes, per trial:

    <trial>/score/       the re-run: result.json (score/runner.py), table.png (the render the
                         judge sees), and Console's recording in console/
    <trial>/score.json   l0, l1, l2, structure and process, plus hashes of the truth, the
                         intent file and the scoring code it was scored with
"""

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import REPO, console, corpus
from harness.score import process

SCORE = REPO / "harness/score"
TIMEOUT_S = 600


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def scorer_hash() -> str:
    h = hashlib.sha256()
    for path in sorted(SCORE.glob("*.py")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _workspace(trial_dir: Path, item: corpus.Item) -> Path:
    ws = console.new_workspace()
    agent_ws = trial_dir / "workspace"
    # Fresh copies, in case the agent changed its own
    (ws / "data").mkdir()
    for name in item.data:
        shutil.copy(corpus.DATA / name, ws / "data")
    shutil.copy(agent_ws / "table.py", ws)
    if (agent_ws / "skill").is_dir():
        shutil.copytree(agent_ws / "skill", ws / "skill")
    lib = ws / "_score/harness"
    (lib / "score").mkdir(parents=True)
    shutil.copy(REPO / "harness/__init__.py", lib)
    for path in SCORE.glob("*.py"):
        shutil.copy(path, lib / "score")
    for name in ("truth.py", "intent.py"):
        if (item.dir / name).is_file():
            shutil.copy(item.dir / name, ws / "_score" / name)
    return ws


def _cell(ws: Path) -> str:
    args = ["_score/harness/score/runner.py", "table.py", "_score/out"]
    if (ws / "_score/truth.py").is_file():
        args += ["--truth", "_score/truth.py"]
    if (ws / "_score/intent.py").is_file():
        args += ["--intent", "_score/intent.py"]
    return (
        "import json, subprocess, sys\n"
        "try:\n"
        f"    p = subprocess.run([sys.executable, *{args!r}], capture_output=True, text=True,"
        f" timeout={TIMEOUT_S})\n"
        "    r = {'returncode': p.returncode, 'stderr': p.stderr[-3000:]}\n"
        "except subprocess.TimeoutExpired:\n"
        f"    r = {{'returncode': None, 'stderr': 'timed out after {TIMEOUT_S}s'}}\n"
        "print('SCORE ' + json.dumps(r))\n"
    )


async def rerun(trial_dir: Path, item: corpus.Item) -> dict:
    """Re-run the trial's table.py in Console; runner.py's result.json, or an error."""
    ws = _workspace(trial_dir, item)
    out_dir = trial_dir / "score"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir()
    try:
        config = console.write_config(out_dir / "console.yaml")
        async with console.session(config, ws) as c:
            output = await console.run_cell(c, _cell(ws), TIMEOUT_S + 60)
        status = next(
            (json.loads(line[6:]) for line in output.splitlines() if line.startswith("SCORE ")),
            {"returncode": None, "stderr": output[-3000:]},
        )
        if (ws / "_score/out").is_dir():
            for path in (ws / "_score/out").iterdir():
                shutil.move(path, out_dir)
        shutil.move(ws / ".agents/console", out_dir / "console")
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    if status["returncode"] != 0 or not (out_dir / "result.json").is_file():
        return {"error": f"runner exited {status['returncode']}:\n{status['stderr']}"}
    return json.loads((out_dir / "result.json").read_text())


def _l1(result: dict, has_intent: bool) -> dict | None:
    if not has_intent:
        return None
    checks = result.get("intent") or []
    passed = sum(c["passed"] for c in checks)
    # A table that didn't build, or checks that didn't run, passes nothing
    ran = bool(checks) and not result.get("score_error")
    return {
        "passed": passed if ran else 0,
        "total": len(checks),
        "rate": passed / len(checks) if ran else 0.0,
        "all": ran and passed == len(checks),
        "checks": checks,
    }


async def score(trial_dir: Path) -> dict:
    trial = json.loads((trial_dir / "trial.json").read_text())
    item = corpus.load(trial["prompt_id"])
    truth, intent = item.dir / "truth.py", item.dir / "intent.py"
    has_table = (trial_dir / "workspace/table.py").is_file()
    result = await rerun(trial_dir, item) if has_table else {"error": "no table.py"}

    l0_passed = not result.get("error") and (trial_dir / "score/table.png").is_file()
    l2 = result.get("data")
    if l2 is None and truth.is_file() and not result.get("score_error"):
        l2 = {"score": 0.0, "note": "the table didn't build"}
    record = {
        "l0": {
            "passed": l0_passed,
            "error": result.get("error"),
            "warnings": result.get("warnings", []),
        },
        "l1": _l1(result, intent.is_file()),
        "l2": l2,
        "structure": result.get("structure"),
        "process": process.metrics(trial_dir),
        "score_error": result.get("score_error"),
        "prompt_changed": item.hash != trial["prompt_sha256"],
        "scored_with": {
            "truth_sha256": _sha256(truth),
            "intent_sha256": _sha256(intent),
            "scorer_sha256": scorer_hash(),
        },
        "scored_at": datetime.now(UTC).isoformat(),
    }
    (trial_dir / "score.json").write_text(json.dumps(record, indent=2, default=str))
    return record


def _line(trial_dir: Path, rec: dict) -> str:
    l1, l2, p = rec["l1"], rec["l2"], rec["process"]
    parts = ["L0 ok" if rec["l0"]["passed"] else "L0 FAIL"]
    parts.append(f"L1 {l1['passed']}/{l1['total']}" if l1 else "L1 -")
    parts.append(f"L2 {l2['score']:.2f}" if l2 and l2.get("score") is not None else "L2 -")
    parts.append(f"{p['gt_api_errors']} GT API errors")
    if rec["score_error"]:
        parts.append("SCORE ERROR")
    if rec["prompt_changed"]:
        parts.append("prompt changed since the trial")
    return f"{trial_dir.relative_to(REPO)}: {', '.join(parts)}"


async def _main(run_dir: Path, force: bool, jobs: int) -> None:
    trials = sorted(p.parent for p in run_dir.glob("*/*/r*/trial.json"))
    todo = [t for t in trials if force or not (t / "score.json").is_file()]
    print(f"{len(todo)} of {len(trials)} trials to score")
    sem = asyncio.Semaphore(jobs)

    async def one(trial_dir: Path) -> None:
        async with sem:
            rec = await score(trial_dir)
        print(_line(trial_dir, rec))

    await asyncio.gather(*(one(t) for t in todo))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--force", action="store_true", help="re-score trials already scored")
    parser.add_argument("--jobs", type=int, default=4, help="trials scored at once")
    args = parser.parse_args()
    asyncio.run(_main(args.run_dir.resolve(), args.force, args.jobs))


if __name__ == "__main__":
    main()
