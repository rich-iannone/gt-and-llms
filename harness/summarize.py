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
    judge        mean of the judge's five grades, 1 to 5 (harness/judge.py absolute); a
                 table that didn't render counts as 1
    cost_usd     per trial
    convergence  share of repeat pairs agreeing on each structure field, averaged over the
                 fields (prompts with 2+ repeats)

Then, for each pairwise comparison judged in the run (harness/judge.py pairwise), the arm's
win rate (a tie counts half), averaged over a prompt's repeats and then over prompts, and the
share of pairs where the judge's two orders agreed. With two or more comparisons, a
Bradley-Terry fit to all of them gives each arm's probability of beating the baseline, so arms
never compared directly can be ranked too.

Writes runs/<run-id>/summary.json. Trials without a score.json, scored with different intent
files or scoring code, or judged with different judge instructions, are reported.
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

METRICS = ("l0", "l1", "l1_all", "l2", "gt_api", "judge", "cost_usd")
BOOTSTRAP = 2000


def trial_metrics(score: dict, judged: dict | None = None) -> dict[str, float | None]:
    """A trial's metrics; `judged` is its judge/absolute.json, if it has been judged."""
    l1, l2 = score["l1"], score["l2"]
    judge = None if judged is None else (judged["mean"] if judged["grades"] else 1.0)
    return {
        "l0": float(score["l0"]["passed"]),
        "l1": l1["rate"] if l1 else None,
        "l1_all": float(l1["all"]) if l1 else None,
        "l2": l2.get("score") if l2 else None,
        "gt_api": float(score["process"]["gt_api_errors"] > 0),
        "judge": judge,
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
    judge_hashes: set = set()
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
        judge_path = path.parent / "judge/absolute.json"
        judged = json.loads(judge_path.read_text()) if judge_path.is_file() else None
        if judged:
            judge_hashes.add(judged["instructions_sha256"])
        trials.append({"trial": trial, "score": score, "judged": judged})
    for key, seen in sorted(hashes.items()):
        if len(seen) > 1:
            prompt, what = key.split(":")
            problems.append(f"{prompt}: trials scored with {len(seen)} different {what[:-7]}s")
    if len(judge_hashes) > 1:
        problems.append(f"trials judged with {len(judge_hashes)} different judge instructions")
    return trials, problems


def load_pairs(run_dir: Path, split: str | None) -> dict[str, list[dict]]:
    """Pairwise records by comparison (<arm>-vs-<other>), each with its prompt."""
    out = {}
    for comp in sorted(p for p in (run_dir / "pairwise").glob("*-vs-*") if p.is_dir()):
        records = []
        for path in sorted(comp.glob("*/r*.json")):
            if split and corpus.load(path.parent.name).split != split:
                continue
            records.append(json.loads(path.read_text()) | {"prompt": path.parent.name})
        out[comp.name] = records
    return out


def pairwise(pairs: dict[str, list[dict]], seed: int = 0) -> dict:
    """Each pairwise comparison's win rate for its arm, and the share of pairs whose two
    orders agreed (pairs decided by a missing render aren't counted in it)."""
    rng = random.Random(seed)
    out = {}
    for comp, records in pairs.items():
        scores: dict[str, list[float]] = defaultdict(list)
        for rec in records:
            scores[rec["prompt"]].append(rec["arm_score"])
        consistent = [float(rec["consistent"]) for rec in records if "consistent" in rec]
        row = bootstrap({p: _mean(xs) for p, xs in scores.items()}, rng)
        row["pairs"] = len(records)
        row["consistent"] = _mean(consistent) if consistent else None
        row["instructions"] = len({rec["instructions_sha256"] for rec in records})
        out[comp] = row
    return out


# Each pair of arms compared gets one virtual tie, so that an arm that wins (or loses) every
# pair still gets a finite strength
BT_PRIOR = 1.0


def _bt_fit(games: dict[tuple[str, str], list[float]]) -> dict[str, float]:
    """Bradley-Terry strengths by minorization-maximization (Hunter 2004), a tie counting
    half a win to each side. `games` maps (i, j) to [games played, i's score]."""
    arms = sorted({a for pair in games for a in pair})
    wins = dict.fromkeys(arms, 0.0)
    played: dict[str, dict[str, float]] = {a: defaultdict(float) for a in arms}
    for (i, j), (n, w) in games.items():
        n, w = n + BT_PRIOR, w + BT_PRIOR / 2
        wins[i] += w
        wins[j] += n - w
        played[i][j] += n
        played[j][i] += n
    p = dict.fromkeys(arms, 1.0)
    for _ in range(1000):
        new = {i: wins[i] / sum(n / (p[i] + p[j]) for j, n in played[i].items()) for i in arms}
        total = sum(new.values())
        new = {i: v * len(arms) / total for i, v in new.items()}
        done = max(abs(new[i] - p[i]) for i in arms) < 1e-10
        p = new
        if done:
            break
    return p


def bradley_terry(pairs: dict[str, list[dict]], seed: int = 0) -> dict | None:
    """Every arm's probability of beating the baseline, from a Bradley-Terry fit to all the
    comparisons at once, with a bootstrap over prompts. None with fewer than two comparisons
    (one comparison's win rate says it all)."""
    if len(pairs) < 2:
        return None
    # prompt -> (arm, other) -> [pairs, arm's score]
    by_prompt: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for comp, records in pairs.items():
        arm, other = comp.split("-vs-")
        for rec in records:
            g = by_prompt[rec["prompt"]][(arm, other)]
            g[0] += 1
            g[1] += rec["arm_score"]
    arms = sorted({a for comp in pairs for a in comp.split("-vs-")})
    ref = "baseline" if "baseline" in arms else arms[0]
    # Strengths only compare within arms linked by a chain of comparisons
    reached, edges = {ref}, [comp.split("-vs-") for comp in pairs]
    while new := {b for e in edges for a, b in (e, e[::-1]) if a in reached} - reached:
        reached |= new
    if reached != set(arms):
        return None

    def fit(prompts: list[str]) -> dict[str, float]:
        games: dict = defaultdict(lambda: [0.0, 0.0])
        for prompt in prompts:
            for key, (n, w) in by_prompt[prompt].items():
                games[key][0] += n
                games[key][1] += w
        p = _bt_fit(games)
        return {a: p[a] / (p[a] + p[ref]) if a in p else None for a in arms}

    prompts = sorted(by_prompt)
    if not prompts:
        return None
    point = fit(prompts)
    rng = random.Random(seed)
    draws = [fit(rng.choices(prompts, k=len(prompts))) for _ in range(BOOTSTRAP)]
    out = {"reference": ref, "prompts": len(prompts), "arms": {}}
    for a in arms:
        xs = sorted(d[a] for d in draws if d[a] is not None)
        ci = [xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]] if xs else None
        out["arms"][a] = {"mean": point[a], "ci": ci}
    return out


def summarize(trials: list[dict], seed: int = 0) -> dict:
    rng = random.Random(seed)
    # arm -> prompt -> [trial metrics], and the structures for convergence
    by_arm: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    structures: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for t in trials:
        arm, prompt = t["trial"]["arm"], t["trial"]["prompt_id"]
        by_arm[arm][prompt].append(trial_metrics(t["score"], t.get("judged")))
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


# How to show a metric and its difference from baseline
FORMATS = {
    "pct": (lambda x: f"{100 * x:.0f}%", lambda x: f"{100 * x:+.0f}"),
    "usd": (lambda x: f"${x:.3f}", lambda x: f"{x:+.3f}"),
    "grade": (lambda x: f"{x:.2f}", lambda x: f"{x:+.2f}"),
}
KIND = {"cost_usd": "usd", "judge": "grade"}


def _fmt(cell: dict, kind: str) -> str:
    if cell["mean"] is None:
        return "-"
    f, g = FORMATS[kind]
    text = f"{f(cell['mean'])} [{f(cell['ci'][0])}, {f(cell['ci'][1])}]"
    if "vs_baseline" in cell and cell["vs_baseline"]["mean"] is not None:
        d = cell["vs_baseline"]
        text += f" ({g(d['mean'])} [{g(d['ci'][0])}, {g(d['ci'][1])}])"
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--split", choices=["dev", "test", "unsplit"])
    args = parser.parse_args()
    trials, problems = load(args.run_dir, args.split)
    summary = summarize(trials)
    records = load_pairs(args.run_dir, args.split)
    pairs, bt = pairwise(records), bradley_terry(records)
    for comp, row in pairs.items():
        if row["instructions"] > 1:
            problems.append(
                f"{comp}: pairs judged with {row['instructions']} different judge instructions"
            )
    (args.run_dir / "summary.json").write_text(
        json.dumps(
            {
                "split": args.split,
                "summary": summary,
                "pairwise": pairs,
                "bradley_terry": bt,
                "problems": problems,
            },
            indent=2,
        )
    )

    cols = [*METRICS, "convergence"]
    print("| arm | trials | " + " | ".join(cols) + " |")
    print("|---|---|" + "---|" * len(cols))
    for arm, row in summary.items():
        cells = [_fmt(row[c], KIND.get(c, "pct")) for c in cols]
        print(f"| {arm} | {row['trials']} | " + " | ".join(cells) + " |")
    print("\nMeans over prompts with 95% bootstrap CIs; (differences from baseline, in points).")
    if pairs:
        print("\n| comparison | pairs | win rate | orders agree |\n|---|---|---|---|")
        for comp, row in pairs.items():
            agree = "-" if row["consistent"] is None else f"{100 * row['consistent']:.0f}%"
            print(f"| {comp} | {row['pairs']} | {_fmt(row, 'pct')} | {agree} |")
        print("\nWin rate: the arm's, a tie counting half; 50% is no difference.")
    if bt:
        ref = bt["reference"]
        print(f"\n| arm | P(beats {ref}) |\n|---|---|")
        for arm, cell in bt["arms"].items():
            if arm != ref:
                print(f"| {arm} | {_fmt(cell, 'pct')} |")
        print(f"\nBradley-Terry, fitted to all {len(pairs)} comparisons at once.")
    for p in problems:
        print(f"warning: {p}")


if __name__ == "__main__":
    main()
