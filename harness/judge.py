"""The judge (plan §6, L3 and L3'): Opus 5 grades each render against its request, and
compares two arms' renders of the same request blind, in pairs.

    uv run harness/judge.py absolute runs/<run-id>
    uv run harness/judge.py pairwise runs/<run-id> --arm rich --vs baseline
    uv run harness/judge.py absolute runs/<run-id> --force    # judge again

The judge sees the request, a summary of its data files, and the render that score_trials.py
made (score/table.png), never the code, the arm or the truth. Its instructions are
judge/absolute.md or judge/pairwise.md followed by judge/rubric.md. Each record holds a hash
of those instructions, so results from a changed rubric can't be mixed with frozen ones
(summarize.py warns). A render taller than the model takes in one image is sent as parts, cut
between lines of text; the parts go in <trial>/judge/parts/.

Absolute grades go to <trial>/judge/absolute.json. A trial without a render (it failed L0)
gets no call and no grades. Pairwise verdicts go to
runs/<run-id>/pairwise/<arm>-vs-<other>/<prompt>/r<n>.json. Each pair is judged in both
orders, so that a preference for the first or second table cancels out. `arm_score` is the
arm's mean over the two orders: 1 for a win, 0.5 for a tie, 0 for a loss. Where only one
of the two rendered, that one wins with no call, and where neither did, it's a tie.
"""

import argparse
import asyncio
import csv
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chatlas import ChatAnthropic, content_image_file
from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageStat
from pydantic import BaseModel, Field

from harness import REPO, corpus

JUDGE = REPO / "judge"
MODEL = "claude-opus-5"
MAX_TOKENS = 4000
DIMENSIONS = ("answers_prompt", "labels", "hierarchy", "precision", "layout")

# Anthropic scales an image down until its long edge is at most 1568px and it has at most
# about 1.15 megapixels. Parts are cut to fit both, so a tall table's text stays legible.
MAX_EDGE = 1568
MAX_PIXELS = 1_150_000
# A cut moves up by at most this share of a part's height to fall between lines of text
CUT_SEARCH = 0.25

MISSING = {"", "NA", "NaN", "nan", "null", "None"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")


class Grade(BaseModel):
    rationale: str = Field(description="One to three sentences citing what you see")
    score: Literal[1, 2, 3, 4, 5]


class Grades(BaseModel):
    answers_prompt: Grade
    labels: Grade
    hierarchy: Grade
    precision: Grade
    layout: Grade


class Verdict(BaseModel):
    rationale: str = Field(description="One to three sentences naming the deciding differences")
    verdict: Literal["A", "B", "tie"]


def instructions(kind: Literal["absolute", "pairwise"]) -> str:
    return (JUDGE / f"{kind}.md").read_text().strip() + "\n\n" + (JUDGE / "rubric.md").read_text()


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _kind(values: list[str]) -> str:
    if not values:
        return "empty"
    try:
        [float(v) for v in values]
        return "number"
    except ValueError:
        pass
    return "date" if all(ISO_DATE.match(v) for v in values) else "text"


def _short(value: str, width: int = 40) -> str:
    return value if len(value) <= width else value[: width - 1] + "…"


def data_summary(item: corpus.Item) -> str:
    """Each data file's size and columns: a column's type, its range or a few of its values,
    and how many values are missing."""
    blocks = []
    for name in item.data:
        with (corpus.DATA / name).open(newline="") as f:
            header, *rows = list(csv.reader(f))
        lines = [f"`{name}`: {len(rows)} rows, {len(header)} columns"]
        for i, col in enumerate(header):
            values = [r[i] if i < len(r) else "" for r in rows]
            present = [v for v in values if v not in MISSING]
            kind = _kind(present)
            if kind == "number":
                nums = sorted(present, key=float)
                desc = f"{nums[0]} to {nums[-1]}"
            elif kind == "date":
                desc = f"{min(present)} to {max(present)}"
            else:
                distinct = list(dict.fromkeys(present))
                shown = ", ".join(_short(v) for v in distinct[:4])
                desc = f"{len(distinct)} distinct" + (f", e.g. {shown}" if shown else "")
            missing = len(values) - len(present)
            lines.append(f"- {col} ({kind}): {desc}" + (f"; {missing} missing" if missing else ""))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _cut(img: Image.Image, y: int, floor: int) -> int:
    """Where to cut, at or above y and below floor: the lowest row of one colour, which no text
    crosses; failing that (column borders cross every row), the lowest row that's the same as
    the row above it; failing that, the row least different from the row above it."""
    w = img.width
    same, best, best_diff = None, y, None
    for row in range(y, floor, -1):
        here = img.crop((0, row, w, row + 1))
        if all(lo == hi for lo, hi in here.getextrema()):
            return row
        diff = ImageChops.difference(here, img.crop((0, row - 1, w, row)))
        if diff.getbbox() is None:
            same = row if same is None else same
            continue
        total = sum(ImageStat.Stat(diff).sum)
        if best_diff is None or total < best_diff:
            best, best_diff = row, total
    return best if same is None else same


def split_render(png: Path, out_dir: Path) -> list[Path]:
    """The render as images the model reads without scaling it down past legibility:
    the PNG itself if it fits, or parts of it, top to bottom, written to out_dir."""
    img = Image.open(png).convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_EDGE / w)
    part_h = int(min(MAX_EDGE, MAX_PIXELS / (w * scale)) / scale)
    if h <= part_h:
        return [png]
    cuts = [0]
    while h - cuts[-1] > part_h:
        y = cuts[-1] + part_h
        cuts.append(_cut(img, y, y - int(CUT_SEARCH * part_h)))
    cuts.append(h)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("part-*.png"):
        old.unlink()
    parts = []
    for n, (top, bottom) in enumerate(zip(cuts, cuts[1:]), start=1):
        path = out_dir / f"part-{n}.png"
        img.crop((0, top, w, bottom)).save(path)
        parts.append(path)
    return parts


def _render_content(paths: list[Path]) -> list:
    if len(paths) == 1:
        return [content_image_file(str(paths[0]), resize="none")]
    content = []
    for n, path in enumerate(paths, start=1):
        content += [f"Part {n} of {len(paths)}:", content_image_file(str(path), resize="none")]
    return content


def _request(item: corpus.Item) -> str:
    return f"<request>\n{item.prompt}\n</request>\n\n<data>\n{data_summary(item)}\n</data>"


def _render(trial_dir: Path) -> Path | None:
    png = trial_dir / "score/table.png"
    return png if png.is_file() else None


async def _ask(system: str, content: list, data_model: type[BaseModel]) -> tuple[dict, dict]:
    chat = ChatAnthropic(model=MODEL, system_prompt=system, max_tokens=MAX_TOKENS)
    answer = await chat.chat_structured_async(*content, data_model=data_model)
    return answer.model_dump(), {"cost_usd": chat.get_cost(), "tokens": chat.get_tokens()}


def _base(kind: Literal["absolute", "pairwise"], item: corpus.Item) -> dict:
    return {
        "model": MODEL,
        "instructions_sha256": sha256(instructions(kind)),
        "rubric_sha256": sha256((JUDGE / "rubric.md").read_bytes()),
        "prompt_sha256": item.hash,
        "judged_at": datetime.now(UTC).isoformat(),
    }


async def absolute(trial_dir: Path) -> dict:
    trial = json.loads((trial_dir / "trial.json").read_text())
    item = corpus.load(trial["prompt_id"])
    record = _base("absolute", item)
    png = _render(trial_dir)
    if png is None:
        record |= {"grades": None, "mean": None, "note": "no render (L0 failed)"}
    else:
        parts = split_render(png, trial_dir / "judge/parts")
        content = [_request(item), "The table:", *_render_content(parts)]
        grades, usage = await _ask(instructions("absolute"), content, Grades)
        record |= {
            "render_sha256": sha256(png.read_bytes()),
            "parts": len(parts),
            "grades": grades,
            "mean": sum(grades[d]["score"] for d in DIMENSIONS) / len(DIMENSIONS),
            **usage,
        }
    out = trial_dir / "judge/absolute.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2, default=str))
    return record


_SCORE = {"win": 1.0, "tie": 0.5, "loss": 0.0}


async def _order(item: corpus.Item, a: Path, b: Path) -> dict:
    content = [_request(item)]
    for label, trial_dir in (("A", a), ("B", b)):
        parts = split_render(_render(trial_dir), trial_dir / "judge/parts")
        content += [f"Table {label}:", *_render_content(parts)]
    verdict, usage = await _ask(instructions("pairwise"), content, Verdict)
    return {"a": a.relative_to(REPO).as_posix(), "b": b.relative_to(REPO).as_posix()} | (
        verdict | usage
    )


def result(verdict: str, arm_is: str) -> str:
    """A verdict (A, B or tie) as the arm's result, when the arm's table was `arm_is`."""
    if verdict == "tie":
        return "tie"
    return "win" if verdict == arm_is else "loss"


def pair_record(run_dir: Path, arm: str, vs: str, rel: Path) -> Path:
    """Where the verdict on the arm's trial <prompt>/r<n> (`rel`) and vs's goes."""
    return run_dir / "pairwise" / f"{arm}-vs-{vs}" / rel.parent / f"{rel.name}.json"


async def pairwise(arm_dir: Path, other_dir: Path, out: Path) -> dict:
    trial = json.loads((arm_dir / "trial.json").read_text())
    item = corpus.load(trial["prompt_id"])
    record = _base("pairwise", item) | {
        "arm": arm_dir.relative_to(REPO).as_posix(),
        "other": other_dir.relative_to(REPO).as_posix(),
    }
    mine, theirs = _render(arm_dir), _render(other_dir)
    if mine is None or theirs is None:
        outcome = "tie" if mine is None and theirs is None else ("win" if mine else "loss")
        record |= {"orders": [], "results": [outcome], "decided_by": "render missing"}
    else:
        orders = [await _order(item, arm_dir, other_dir), await _order(item, other_dir, arm_dir)]
        results = [result(orders[0]["verdict"], "A"), result(orders[1]["verdict"], "B")]
        record |= {
            "orders": orders,
            "results": results,
            "consistent": results[0] == results[1],
            "cost_usd": sum(o["cost_usd"] or 0 for o in orders),
        }
    record["arm_score"] = sum(_SCORE[r] for r in record["results"]) / len(record["results"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, default=str))
    return record


def scored_trials(run_dir: Path, arm: str | None = None) -> list[Path]:
    pattern = f"{arm or '*'}/*/r*/score.json"
    return sorted(p.parent for p in run_dir.glob(pattern))


async def _gather(jobs: int, coros: list) -> None:
    sem = asyncio.Semaphore(jobs)

    async def one(coro) -> None:
        async with sem:
            await coro

    await asyncio.gather(*(one(c) for c in coros))


async def _absolute(run_dir: Path, force: bool, jobs: int) -> None:
    trials = scored_trials(run_dir)
    todo = [t for t in trials if force or not (t / "judge/absolute.json").is_file()]
    print(f"{len(todo)} of {len(trials)} scored trials to judge")

    async def one(trial_dir: Path) -> None:
        label = trial_dir.relative_to(REPO)
        try:
            rec = await absolute(trial_dir)
        except Exception as e:  # noqa: BLE001 - reported; the trial is judged on the next run
            print(f"{label}: ERROR {type(e).__name__}: {e}")
            return
        if rec["grades"] is None:
            print(f"{label}: {rec['note']}")
            return
        scores = " ".join(f"{d}={rec['grades'][d]['score']}" for d in DIMENSIONS)
        print(f"{label}: {scores} (${rec['cost_usd']:.3f})")

    await _gather(jobs, [one(t) for t in todo])


async def _pairwise(run_dir: Path, arm: str, vs: str, force: bool, jobs: int) -> None:
    others = {t.relative_to(run_dir / vs): t for t in scored_trials(run_dir, vs)}
    pairs = []
    for t in scored_trials(run_dir, arm):
        key = t.relative_to(run_dir / arm)
        if key in others:
            pairs.append((t, others[key], pair_record(run_dir, arm, vs, key)))
    todo = [p for p in pairs if force or not p[2].is_file()]
    print(f"{len(todo)} of {len(pairs)} pairs ({arm} vs {vs}) to judge")

    async def one(arm_dir: Path, other_dir: Path, out: Path) -> None:
        label = out.relative_to(REPO)
        try:
            rec = await pairwise(arm_dir, other_dir, out)
        except Exception as e:  # noqa: BLE001 - reported; the pair is judged on the next run
            print(f"{label}: ERROR {type(e).__name__}: {e}")
            return
        how = rec.get("decided_by") or ("consistent" if rec["consistent"] else "split")
        print(f"{label}: {arm} {'/'.join(rec['results'])} ({how}), score {rec['arm_score']}")

    await _gather(jobs, [one(*p) for p in todo])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("kind", choices=["absolute", "pairwise"])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--arm", help="pairwise: the arm being compared")
    parser.add_argument("--vs", default="baseline", help="pairwise: the arm it's compared with")
    parser.add_argument("--force", action="store_true", help="judge again")
    parser.add_argument("--jobs", type=int, default=4, help="judge calls at once")
    args = parser.parse_args()
    load_dotenv(REPO / ".env")
    run_dir = args.run_dir.resolve()
    if args.kind == "absolute":
        asyncio.run(_absolute(run_dir, args.force, args.jobs))
    else:
        if not args.arm:
            parser.error("pairwise needs --arm")
        asyncio.run(_pairwise(run_dir, args.arm, args.vs, args.force, args.jobs))


if __name__ == "__main__":
    main()
