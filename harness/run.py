"""Run trials.

    uv run harness/run.py --arm baseline --prompt api_latency
    uv run harness/run.py --arm baseline --prompt api_latency github_repos --repeats 2

Trials go to runs/<run-id>/<arm>/<prompt>/r<repeat>/ (see harness/trial.py). Re-using a
--run-id skips trials that already finished, so an interrupted run can be resumed.
"""

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from harness import REPO, arms, corpus, provenance, trial


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--prompt", nargs="+", required=True, help="corpus ids, or 'dev' / 'test'")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--model", default=trial.Settings.model)
    ap.add_argument("--max-tool-calls", type=int, default=trial.Settings.max_tool_calls)
    a = ap.parse_args()

    load_dotenv(REPO / ".env")
    arm = arms.load(a.arm)
    prompt_ids = [pid for p in a.prompt for pid in (corpus.ids(p) if p in ("dev", "test") else [p])]
    items = [corpus.load(pid) for pid in prompt_ids]
    settings = trial.Settings(model=a.model, max_tool_calls=a.max_tool_calls)
    prov = provenance.collect()
    run_dir = REPO / "runs" / a.run_id

    for item in items:
        for repeat in range(1, a.repeats + 1):
            trial_dir = run_dir / arm.name / item.id / f"r{repeat}"
            label = f"{arm.name}/{item.id}/r{repeat}"
            if (trial_dir / "trial.json").exists():
                print(f"{label}: done already, skipping")
                continue
            # A trial dir without trial.json is a trial that was interrupted
            shutil.rmtree(trial_dir, ignore_errors=True)
            trial_dir.mkdir(parents=True)
            rec = asyncio.run(trial.run(trial_dir, arm, item, repeat, settings, prov))
            status = rec["error"] or ("ok" if rec["table_png"] else "no table.png")
            print(
                f"{label}: {status} ({rec['tool_calls']} tool calls, {rec['images_returned']} "
                f"images, {rec['wall_s']}s, ${rec['cost_usd']:.3f})"
            )
            print(f"  {trial_dir.relative_to(REPO)}")
    (run_dir / "provenance.json").write_text(json.dumps(prov, indent=2))


if __name__ == "__main__":
    main()
