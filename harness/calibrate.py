"""Judge calibration (plan §6): a person rates a sample of tables blind to arm, and the
judge's grades are compared with theirs.

    uv run harness/calibrate.py sample runs/<run-id> --name pilot --seed N [--n 50]
    uv run harness/calibrate.py sample runs/<run-id> --name pilot-pairs --seed N --arm rich --vs baseline
    uv run harness/calibrate.py agree calibration/<name>

`sample` draws rendered trials (or, with --arm, pairs of trials of the same prompt and repeat)
in turn from each (arm, difficulty) stratum, so arms and difficulties are evenly represented.
It writes calibration/<name>/:

    rate.html     each table (or pair) with its request and data summary, as the judge sees
                  them; the rubric is at the top
    ratings.csv   one row per table, to fill in: a score from 1 to 5 per dimension, or a
                  verdict (A, B or tie) per pair, and optional notes
    tables/       the renders, under blind ids. A pair's tables are put in random order.
    key.json      which trial each id is. Don't open it until the ratings are in.

`agree` reads ratings.csv and the judge's records for the same trials (judge.py must have
judged them) and reports, per dimension and for the mean, Spearman's rho and the share of
tables where the two are within a point; for pairs, the share of verdicts that agree, with
each of the judge's two orders counted separately.
"""

import argparse
import csv
import html
import json
import random
import shutil
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import REPO, corpus, judge

CALIBRATION = REPO / "calibration"


def _strata(units: list[tuple[str, str, Path]], rng: random.Random) -> list[list]:
    by: dict[tuple, list] = defaultdict(list)
    for arm, difficulty, unit in units:
        by[(arm, difficulty)].append(unit)
    strata = [by[k] for k in sorted(by)]
    for s in strata:
        rng.shuffle(s)
    return strata


def draw(units: list[tuple[str, str, Path]], n: int, rng: random.Random) -> list:
    """Up to n units, taken one at a time from each stratum in turn."""
    strata = _strata(units, rng)
    picked: list = []
    while len(picked) < n and any(strata):
        for s in strata:
            if s and len(picked) < n:
                picked.append(s.pop())
    rng.shuffle(picked)
    return picked


def _trial(trial_dir: Path) -> dict:
    return json.loads((trial_dir / "trial.json").read_text())


def _rendered(run_dir: Path, arm: str | None = None) -> list[Path]:
    return [t for t in judge.scored_trials(run_dir, arm) if (t / "score/table.png").is_file()]


def _page(title: str, sections: list[str]) -> str:
    rubric = html.escape((judge.JUDGE / "rubric.md").read_text())
    style = (
        "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em}"
        "pre{white-space:pre-wrap;background:#f6f6f6;padding:.8em}"
        "img{max-width:100%;border:1px solid #ddd}section{margin:3em 0}"
    )
    return (
        f"<!doctype html><meta charset='utf-8'><title>{title}</title><style>{style}</style>"
        f"<h1>{title}</h1><details><summary>Rubric</summary><pre>{rubric}</pre></details>"
        + "".join(sections)
    )


def _request_html(item: corpus.Item) -> str:
    return (
        f"<pre>{html.escape(item.prompt)}</pre><details><summary>Data</summary>"
        f"<pre>{html.escape(judge.data_summary(item))}</pre></details>"
    )


def sample(run_dir: Path, name: str, n: int, seed: int, arm: str | None, vs: str) -> Path:
    out = CALIBRATION / name
    if out.exists():
        raise SystemExit(f"{out.relative_to(REPO)} exists already")
    rng = random.Random(seed)
    if arm:
        others = {t.relative_to(run_dir / vs): t for t in _rendered(run_dir, vs)}
        units = [
            (arm, corpus.load(_trial(t)["prompt_id"]).meta["difficulty"], (t, others[key]))
            for t in _rendered(run_dir, arm)
            if (key := t.relative_to(run_dir / arm)) in others
        ]
    else:
        units = [
            (_trial(t)["arm"], corpus.load(_trial(t)["prompt_id"]).meta["difficulty"], t)
            for t in _rendered(run_dir)
        ]
    picked = draw(units, n, rng)
    if not picked:
        raise SystemExit("nothing to sample: no rendered trials (run score_trials.py first)")

    (out / "tables").mkdir(parents=True)
    key, sections, rows = {}, [], []
    for i, unit in enumerate(picked, start=1):
        bid = f"{i:02d}"
        if arm:
            pair = list(unit)
            rng.shuffle(pair)
            item = corpus.load(_trial(pair[0])["prompt_id"])
            imgs = ""
            for label, t in zip("AB", pair):
                shutil.copy(t / "score/table.png", out / f"tables/{bid}{label}.png")
                imgs += f"<h3>Table {label}</h3><img src='tables/{bid}{label}.png'>"
            rel = unit[0].relative_to(run_dir / arm)
            key[bid] = {
                "A": pair[0].relative_to(REPO).as_posix(),
                "B": pair[1].relative_to(REPO).as_posix(),
                "arm_side": "A" if pair[0] == unit[0] else "B",
                "judged": judge.pair_record(run_dir, arm, vs, rel).relative_to(REPO).as_posix(),
            }
            rows.append({"id": bid, "verdict": "", "notes": ""})
        else:
            item = corpus.load(_trial(unit)["prompt_id"])
            shutil.copy(unit / "score/table.png", out / f"tables/{bid}.png")
            imgs = f"<img src='tables/{bid}.png'>"
            key[bid] = unit.relative_to(REPO).as_posix()
            rows.append({"id": bid, **dict.fromkeys(judge.DIMENSIONS, ""), "notes": ""})
        sections.append(f"<section><h2>{bid}</h2>{_request_html(item)}{imgs}</section>")

    kind = "pairs" if arm else "tables"
    (out / "rate.html").write_text(_page(f"Calibration: {name} ({len(picked)} {kind})", sections))
    with (out / "ratings.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    meta = {
        "run": run_dir.relative_to(REPO).as_posix(),
        "kind": "pairwise" if arm else "absolute",
        "seed": seed,
        "n": len(picked),
        "sampled_at": datetime.now(UTC).isoformat(),
        "rubric_sha256": judge.sha256((judge.JUDGE / "rubric.md").read_bytes()),
    }
    (out / "key.json").write_text(json.dumps({"meta": meta, "ids": key}, indent=2))
    return out


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman's rho, with tied values given their average rank; None if either side is
    constant."""
    if len(xs) < 2:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else None


def _read_ratings(out: Path) -> list[dict]:
    with (out / "ratings.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def agree_absolute(out: Path, key: dict) -> dict:
    human: dict[str, list[float]] = defaultdict(list)
    model: dict[str, list[float]] = defaultdict(list)
    missing, rated = [], 0
    for row in _read_ratings(out):
        if not all(row[d].strip() for d in judge.DIMENSIONS):
            continue
        record = REPO / key[row["id"]] / "judge/absolute.json"
        grades = json.loads(record.read_text())["grades"] if record.is_file() else None
        if not grades:
            missing.append(row["id"])
            continue
        rated += 1
        h = [float(row[d]) for d in judge.DIMENSIONS]
        m = [float(grades[d]["score"]) for d in judge.DIMENSIONS]
        for d, a, b in zip(judge.DIMENSIONS, h, m):
            human[d].append(a)
            model[d].append(b)
        human["mean"].append(sum(h) / len(h))
        model["mean"].append(sum(m) / len(m))
    result = {}
    for d in [*judge.DIMENSIONS, "mean"]:
        pairs = list(zip(human[d], model[d]))
        result[d] = {
            "spearman": spearman(human[d], model[d]),
            "within_1": sum(abs(a - b) <= 1 for a, b in pairs) / len(pairs) if pairs else None,
            "judge_minus_human": sum(b - a for a, b in pairs) / len(pairs) if pairs else None,
        }
    return {"rated": rated, "not_judged": missing, "agreement": result}


def agree_pairwise(out: Path, key: dict) -> dict:
    hits, total, rated, missing = 0, 0, 0, []
    for row in _read_ratings(out):
        verdict = row["verdict"].strip()
        if verdict not in ("A", "B", "tie"):
            continue
        entry = key[row["id"]]
        human = judge.result(verdict, entry["arm_side"])
        record = REPO / entry["judged"]
        if not record.is_file():
            missing.append(row["id"])
            continue
        rated += 1
        for result in json.loads(record.read_text())["results"]:
            hits += result == human
            total += 1
    return {"rated": rated, "not_judged": missing, "agreement": hits / total if total else None}


def agree(out: Path) -> dict:
    data = json.loads((out / "key.json").read_text())
    if data["meta"]["kind"] == "pairwise":
        return agree_pairwise(out, data["ids"])
    return agree_absolute(out, data["ids"])


def _fmt(x: float | None, signed: bool = False) -> str:
    return "-" if x is None else (f"{x:+.2f}" if signed else f"{x:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("run_dir", type=Path)
    s.add_argument("--name", required=True)
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--n", type=int, default=50)
    s.add_argument("--arm", help="sample pairs of this arm's trials and --vs's")
    s.add_argument("--vs", default="baseline")
    a = sub.add_parser("agree")
    a.add_argument("dir", type=Path)
    args = parser.parse_args()

    if args.command == "sample":
        out = sample(args.run_dir.resolve(), args.name, args.n, args.seed, args.arm, args.vs)
        print(f"Wrote {out.relative_to(REPO)}/: rate {out.relative_to(REPO)}/ratings.csv")
        return
    out = args.dir.resolve()
    result = agree(out)
    (out / "agreement.json").write_text(json.dumps(result, indent=2))
    print(f"{result['rated']} rated and judged")
    if result["not_judged"]:
        print(f"not judged yet: {', '.join(result['not_judged'])}")
    if isinstance(result["agreement"], dict):
        print("| dimension | Spearman | within 1 | judge − human |\n|---|---|---|---|")
        for d, r in result["agreement"].items():
            row = [_fmt(r["spearman"]), _fmt(r["within_1"]), _fmt(r["judge_minus_human"], True)]
            print(f"| {d} | " + " | ".join(row) + " |")
    else:
        print(f"verdicts agreeing: {_fmt(result['agreement'])}")


if __name__ == "__main__":
    main()
