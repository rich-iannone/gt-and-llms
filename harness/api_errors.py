"""Report the GT API errors agents hit in scored runs (plan Phase 5): which errors, how often,
in which arms and prompts. Run it on dev runs of baseline and prose to see where agents get
GT's API wrong without a skill, or with one; it doesn't suggest skill text.

    uv run harness/api_errors.py runs/<run-id> [runs/<run-id> ...] --split dev
    uv run harness/api_errors.py runs/<run-id> --all      # every Python error

Errors come from each trial's score.json (score/process.py decides which are GT API errors).
The same message from different trials is counted once per trial; messages are grouped after
dropping what varies between trials (addresses, quoted values that aren't GT names). Then the
GT names the messages mention (`fmt_number`, `loc.body`, ...), by arm. Writes nothing.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import corpus
from harness.score.process import _GT_NAME

_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
# Not the apostrophe in "can't"
_QUOTED = re.compile(r"(?<!\w)'([^']*)'(?!\w)|(?<!\w)\"([^\"]*)\"(?!\w)")
# Quoted text that's kept: identifiers, which name what went wrong ('fmt_numbr', 'decimal')
_IDENT = re.compile(r"[A-Za-z_][\w.]*")


def pattern(error: dict) -> str:
    """An error's message with what varies between trials replaced: `{type}: {message}`."""
    msg = _ADDRESS.sub("0x…", error["message"])
    msg = _QUOTED.sub(lambda m: m[0] if _IDENT.fullmatch(m[1] or m[2] or "") else "'…'", msg)
    return f"{error['type']}: {' '.join(msg.split())[:160]}"


def gt_names(message: str) -> set[str]:
    return {n for n in _GT_NAME.findall(message) if n not in ("GT", "great_tables")}


def load(run_dirs: list[Path], split: str | None, every: bool) -> tuple[list[dict], Counter]:
    """One row per trial's distinct error pattern, and each arm's trial count."""
    rows, trials = [], Counter()
    for run_dir in run_dirs:
        for path in sorted(run_dir.glob("*/*/r*/score.json")):
            arm, prompt, rep = path.parts[-4:-1]
            if split and corpus.load(prompt).split != split:
                continue
            trials[arm] += 1
            errors = json.loads(path.read_text())["process"]["errors"]
            seen = {}
            for e in errors:
                if every or e["gt_api"]:
                    seen.setdefault(pattern(e), e)
            for pat, e in seen.items():
                rows.append(
                    {
                        "run": run_dir.name,
                        "arm": arm,
                        "prompt": prompt,
                        "trial": rep,
                        "pattern": pat,
                        "gt_api": e["gt_api"],
                        "names": sorted(gt_names(e["message"])),
                    }
                )
    return rows, trials


def report(rows: list[dict], trials: Counter) -> dict:
    arms = sorted(trials)
    per_arm = {}
    for arm in arms:
        hit = {(r["run"], r["prompt"], r["trial"]) for r in rows if r["arm"] == arm}
        per_arm[arm] = {"trials": trials[arm], "trials_with_errors": len(hit)}
    by_pattern: dict[str, dict] = {}
    for r in rows:
        g = by_pattern.setdefault(
            r["pattern"], {"trials": 0, "arms": Counter(), "prompts": set(), "gt_api": r["gt_api"]}
        )
        g["trials"] += 1
        g["arms"][r["arm"]] += 1
        g["prompts"].add(r["prompt"])
    names: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for n in r["names"]:
            names[n][r["arm"]] += 1
    patterns = [
        {"pattern": p, **g, "arms": dict(g["arms"]), "prompts": sorted(g["prompts"])}
        for p, g in sorted(by_pattern.items(), key=lambda kv: (-kv[1]["trials"], kv[0]))
    ]
    return {
        "arms": per_arm,
        "patterns": patterns,
        "names": {
            n: dict(c) for n, c in sorted(names.items(), key=lambda kv: -sum(kv[1].values()))
        },
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--split", choices=["dev", "test", "unsplit"])
    parser.add_argument("--all", action="store_true", help="every Python error, not just GT's")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()
    if args.split == "test":
        print("warning: test runs are for the final comparison only (plan §5)", file=sys.stderr)
    rows, trials = load(args.run_dirs, args.split, args.all)
    out = report(rows, trials)
    if args.json:
        print(json.dumps(out, indent=2))
        return
    kind = "Python" if args.all else "GT API"
    arms = list(out["arms"])
    print(f"| arm | trials | with {kind} errors |\n|---|---|---|")
    for arm, a in out["arms"].items():
        print(f"| {arm} | {a['trials']} | {a['trials_with_errors']} |")
    if not out["patterns"]:
        print(f"\nNo {kind} errors.")
        return
    print(f"\n| error | trials | {' | '.join(arms)} | prompts |")
    print("|---|---|" + "---|" * len(arms) + "---|")
    for p in out["patterns"]:
        counts = " | ".join(str(p["arms"].get(a, "")) for a in arms)
        prompts = ", ".join(p["prompts"][:4]) + (" …" if len(p["prompts"]) > 4 else "")
        mark = "" if p["gt_api"] or not args.all else " (not GT)"
        print(f"| `{_cell(p['pattern'])}`{mark} | {p['trials']} | {counts} | {prompts} |")
    if out["names"]:
        print(f"\n| GT name | {' | '.join(arms)} |\n|---|" + "---|" * len(arms))
        for n, c in out["names"].items():
            print(f"| `{n}` | " + " | ".join(str(c.get(a, "")) for a in arms) + " |")
    print("\nCounts are trials: an error a trial hit several times counts once.")


if __name__ == "__main__":
    main()
