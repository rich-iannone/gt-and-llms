"""The dev/test split (plan §4.3 and §7): about 1/3 of the items go to test, stratified by
(difficulty, style), from a recorded seed.

    uv run harness/split.py --seed N             # show the split it would make
    uv run harness/split.py --seed N --apply     # move the items and write corpus/split.json

Takes every item outside dev/ and test/. Items already in dev/ (api_latency, which Phase 2
ran) stay there and count towards their stratum's dev share. Each stratum's test quota is
its size / 3, rounded so the quotas sum to round(total / 3) (largest remainders first, ties
broken by the seeded shuffle). corpus/split.json records the seed and a hash of every item's
files at the time of the split, so a later edit to a test item shows.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import corpus

RECORD = corpus.CORPUS / "split.json"


def item_hash(item: corpus.Item) -> str:
    h = hashlib.sha256()
    for name in ("prompt.json", "truth.py", "intent.py"):
        path = item.dir / name
        h.update(name.encode())
        h.update(path.read_bytes() if path.is_file() else b"")
    return h.hexdigest()


def assign(items: list[corpus.Item], seed: int) -> dict[str, str]:
    """Item id -> "dev" or "test"."""
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[corpus.Item]] = defaultdict(list)
    for item in items:
        strata[(item.meta["difficulty"], item.meta["style"])].append(item)
    keys = sorted(strata)
    for k in keys:
        strata[k].sort(key=lambda i: i.id)
        rng.shuffle(strata[k])

    exact = {k: len(strata[k]) / 3 for k in keys}
    quota = {k: math.floor(exact[k]) for k in keys}
    tiebreak = {k: rng.random() for k in keys}
    by_remainder = sorted(keys, key=lambda k: (-(exact[k] - quota[k]), tiebreak[k]))
    for k in by_remainder[: round(len(items) / 3) - sum(quota.values())]:
        quota[k] += 1

    out = {}
    for k in keys:
        movable = [i for i in strata[k] if i.split != "dev"]
        pinned = [i for i in strata[k] if i.split == "dev"]
        if quota[k] > len(movable):
            raise SystemExit(f"stratum {k}: test quota {quota[k]} > {len(movable)} movable items")
        for n, item in enumerate(movable):
            out[item.id] = "test" if n < quota[k] else "dev"
        for item in pinned:
            out[item.id] = "dev"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="move the items")
    args = parser.parse_args()
    if RECORD.exists():
        raise SystemExit(f"{RECORD} exists: the corpus is already split")

    items = [corpus.load(i) for i in corpus.ids()]
    if any(i.split == "test" for i in items):
        raise SystemExit("corpus/test/ already has items")
    split = assign(items, args.seed)

    by_stratum = defaultdict(lambda: {"dev": 0, "test": 0})
    for item in items:
        by_stratum[f"{item.meta['difficulty']}/{item.meta['style']}"][split[item.id]] += 1
    for stratum, counts in sorted(by_stratum.items()):
        print(f"{stratum:<14} dev {counts['dev']:>2}  test {counts['test']:>2}")
    n_test = sum(s == "test" for s in split.values())
    print(f"{'total':<14} dev {len(split) - n_test:>2}  test {n_test:>2}")
    if not args.apply:
        print("\n(dry run: pass --apply to move the items; test ids aren't printed)")
        return

    record = {
        "seed": args.seed,
        "date": dt.date.today().isoformat(),
        "items": {
            i.id: {"split": split[i.id], "from": i.split, "sha256": item_hash(i)} for i in items
        },
    }
    for item in items:
        dest = corpus.CORPUS / split[item.id] / item.id
        if item.dir != dest:
            dest.parent.mkdir(exist_ok=True)
            shutil.move(item.dir, dest)
    for d in corpus.CORPUS.iterdir():
        if d.is_dir() and d.name not in ("dev", "test") and not any(d.iterdir()):
            d.rmdir()
    RECORD.write_text(json.dumps(record, indent=2) + "\n")
    print(f"\nmoved; wrote {RECORD.relative_to(corpus.REPO)}")


if __name__ == "__main__":
    main()
