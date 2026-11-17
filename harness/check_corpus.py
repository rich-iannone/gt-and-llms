"""Check corpus items (plan Phase 3's exit criterion): each truth.py runs under the agent's
Python, builds a GT and renders, and the item's intent.py, where there is one, passes on its
own truth. Each truth must also score 1 on L2 (data) against itself. The render is saved as truth.png next to the truth, for reading; it isn't a style
target.

    uv run harness/check_corpus.py             # every item with a truth.py
    uv run harness/check_corpus.py films_by_decade towny_growth_trends
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import REPO, console, corpus

RUNNER = REPO / "harness/score/runner.py"


def run_script(
    script: Path,
    data: list[str],
    out_dir: Path,
    truth: Path | None = None,
    intent: Path | None = None,
) -> dict:
    """Run a table script under the agent's Python in a scratch dir holding its data, and
    its L2 data check and intent checks against `truth` if given."""
    extra = ["--truth", str(truth)] if truth else []
    extra += ["--intent", str(intent)] if intent else []
    with tempfile.TemporaryDirectory(prefix="gt-check-") as tmp:
        work = Path(tmp)
        (work / "data").mkdir()
        for name in data:
            shutil.copy(corpus.DATA / name, work / "data")
        env = {**os.environ, **console.agent_env()}
        env.pop("VIRTUAL_ENV", None)
        env["PYTHONPATH"] = str(REPO / "console/agent_site")
        proc = subprocess.run(
            [str(console.AGENT_PYTHON), str(RUNNER), str(script), str(out_dir), *extra],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        return {"error": f"runner exited {proc.returncode}:\n{proc.stderr[-2000:]}", "warnings": []}
    return json.loads((out_dir / "result.json").read_text())


def check(item: corpus.Item) -> dict:
    truth = item.dir / "truth.py"
    intent = item.dir / "intent.py"
    with tempfile.TemporaryDirectory(prefix="gt-out-") as tmp:
        out = Path(tmp)
        result = run_script(
            truth, item.data, out, truth=truth, intent=intent if intent.is_file() else None
        )
        if (out / "table.png").is_file():
            shutil.copy(out / "table.png", item.dir / "truth.png")
    return result


def _indent(text: str) -> str:
    return "       " + text.replace("\n", "\n       ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", help="corpus item ids (default: all with a truth.py)")
    args = parser.parse_args()
    ids = args.ids or [i for i in corpus.ids() if (corpus.load(i).dir / "truth.py").is_file()]

    failed, no_intent = [], []
    for pid in ids:
        item = corpus.load(pid)
        result = check(item)
        checks = result.get("intent") or []
        bad = [c for c in checks if not c["passed"]]
        data = result.get("data") or {}
        ok = not result["error"] and not result.get("score_error") and not bad
        ok = ok and data.get("score") in (1, None)
        if not (item.dir / "intent.py").is_file():
            no_intent.append(pid)
            summary = "no intent.py"
        else:
            summary = f"intent {len(checks) - len(bad)}/{len(checks)}"
        print(
            f"{'ok  ' if ok else 'FAIL'} {item.split}/{pid}: {result.get('rows')} rows, {summary}"
        )
        for w in result["warnings"]:
            print(_indent(f"warning: {w}"))
        for key in ("error", "score_error"):
            if result.get(key):
                print(_indent(result[key]))
        if data.get("unmatched"):
            print(_indent(f"L2 against itself: unmatched {data['unmatched']}"))
        for c in bad:
            print(_indent(f"failed: {c['check']}: {c['detail']}"))
        if not ok:
            failed.append(pid)
    print(
        f"\n{len(ids) - len(failed)}/{len(ids)} items pass; {len(no_intent)} have no intent.py yet"
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
