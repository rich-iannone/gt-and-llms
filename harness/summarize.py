"""Summarize a scored run (plan §6): each arm's metrics with bootstrap CIs over prompts, its
difference from the baseline, and convergence across repeats.

    uv run harness/summarize.py runs/<run-id>
    uv run harness/summarize.py runs/<run-id> --split dev

Each prompt counts once: a metric is averaged over a prompt's repeats, then over prompts, and
the CI resamples prompts. "vs baseline" is the mean difference over the prompts both arms ran,
with a paired bootstrap. Metrics:

    l0           re-run and rendered (share of trials)
    l1           share of intent checks passed (items with an intent.py)
    l1_all       all intent checks passed (share of trials)
    l2           share of the truth's columns shown (score/data.py)
    gt_api       trials with at least one GT API error (share)
    cost_usd     per trial
    convergence  share of repeat pairs agreeing on each structure field, averaged over the
                 fields (prompts with 2+ repeats)

Writes runs/<run-id>/summary.json. Trials without a score.json, or scored with different
intent files or scoring code, are reported.
"""

import argparse
import itertools
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import corpus

METRICS = ("l0", "l1", "l1_all", "l2", "gt_api", "cost_usd")
BOOTSTRAP = 2000


def trial_metrics(score: dict) -> dict[str, float | None]:
    l1, l2 = score["l1"], score["l2"]
    return {
        "l0": float(score["l0"]["passed"]),
        "l1": l1["rate"] if l1 else None,
        "l1_all": float(l1["all"]) if l1 else None,
        "l2": l2.get("score") if l2 else None,
        "gt_api": float(score["process"]["gt_api_errors"] > 0),
        "cost_usd": score["process"]["cost_usd"],
    }


def convergence(structures: list[dict | None]) -> float | None:
    """Share of repeat pairs that agree, averaged over the fields of score/structure.py. A
    table that didn't build agrees with nothing."""
    pairs = list(itertools.combinations(structures, 2))
    fields = sorted({f for s in structures if s for f in s})
    if not pairs or not fields:
        return 0.0 if pairs else None
    per_field = [
        sum(a is not None and b is not None and a[f] == b[f] for a, b in pairs) / len(pairs)
        for f in fields
    ]
    return sum(per_field) / len(per_field)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def bootstrap(per_prompt: dict[str, float], rng: random.Random) -> dict:
    keys = sorted(per_prompt)
    if not keys:
        return {"mean": None, "ci": None, "prompts": 0}
    vals = [per_prompt[k] for k in keys]
    means = sorted(_mean(rng.choices(vals, k=len(vals))) for _ in range(BOOTSTRAP))
    ci = [means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP) - 1]]
    return {"mean": _mean(vals), "ci": ci, "prompts": len(keys)}


def load(run_dir: Path, split: str | None) -> tuple[list[dict], list[str]]:
    trials, problems = [], []
    hashes: dict[str, set] = defaultdict(set)
    for path in sorted(run_dir.glob("*/*/r*/trial.json")):
        trial = json.loads(path.read_text())
        item_split = corpus.load(trial["prompt_id"]).split
        if split and item_split != split:
            continue
        score_path = path.parent / "score.json"
        if not score_path.is_file():
            problems.append(f"not scored: {path.parent.relative_to(run_dir)}")
            continue
        score = json.loads(score_path.read_text())
        for key in ("intent_sha256", "scorer_sha256"):
            hashes[f"{trial['prompt_id']}:{key}"].add(score["scored_with"][key])
        trials.append({"trial": trial, "score": score})
    for key, seen in sorted(hashes.items()):
        if len(seen) > 1:
            prompt, what = key.split(":")
            problems.append(f"{prompt}: trials scored with {len(seen)} different {what[:-7]}s")
    return trials, problems


def summarize(trials: list[dict], seed: int = 0) -> dict:
    rng = random.Random(seed)
    # arm -> prompt -> [trial metrics], and the structures for convergence
    by_arm: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    structures: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for t in trials:
        arm, prompt = t["trial"]["arm"], t["trial"]["prompt_id"]
        by_arm[arm][prompt].append(trial_metrics(t["score"]))
        structures[arm][prompt].append(t["score"]["structure"])

    def per_prompt(arm: str, metric: str) -> dict[str, float]:
        out = {}
        for prompt, ms in by_arm[arm].items():
            xs = [m[metric] for m in ms if m[metric] is not None]
            if xs:
                out[prompt] = _mean(xs)
        return out

    out: dict = {}
    for arm in sorted(by_arm):
        row: dict = {"trials": sum(len(v) for v in by_arm[arm].values())}
        for metric in METRICS:
            row[metric] = bootstrap(per_prompt(arm, metric), rng)
            if arm != "baseline" and "baseline" in by_arm:
                mine, base = per_prompt(arm, metric), per_prompt("baseline", metric)
                diffs = {p: mine[p] - base[p] for p in mine.keys() & base.keys()}
                row[metric]["vs_baseline"] = bootstrap(diffs, rng)
        conv = {p: c for p, s in structures[arm].items() if (c := convergence(s)) is not None}
        row["convergence"] = bootstrap(conv, rng)
        out[arm] = row
    return out


def _fmt(cell: dict, pct: bool) -> str:
    if cell["mean"] is None:
        return "-"
    f = (lambda x: f"{100 * x:.0f}%") if pct else (lambda x: f"${x:.3f}")
    text = f"{f(cell['mean'])} [{f(cell['ci'][0])}, {f(cell['ci'][1])}]"
    if "vs_baseline" in cell and cell["vs_baseline"]["mean"] is not None:
        d = cell["vs_baseline"]
        g = (lambda x: f"{100 * x:+.0f}") if pct else (lambda x: f"{x:+.3f}")
        text += f" ({g(d['mean'])} [{g(d['ci'][0])}, {g(d['ci'][1])}])"
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--split", choices=["dev", "test", "unsplit"])
    args = parser.parse_args()
    trials, problems = load(args.run_dir, args.split)
    summary = summarize(trials)
    (args.run_dir / "summary.json").write_text(
        json.dumps({"split": args.split, "summary": summary, "problems": problems}, indent=2)
    )

    cols = [*METRICS, "convergence"]
    print("| arm | trials | " + " | ".join(cols) + " |")
    print("|---|---|" + "---|" * len(cols))
    for arm, row in summary.items():
        cells = [_fmt(row[c], pct=c != "cost_usd") for c in cols]
        print(f"| {arm} | {row['trials']} | " + " | ".join(cells) + " |")
    print("\nMeans over prompts with 95% bootstrap CIs; (differences from baseline, in points).")
    for p in problems:
        print(f"warning: {p}")


if __name__ == "__main__":
    main()
