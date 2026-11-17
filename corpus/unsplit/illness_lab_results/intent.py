# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for illness_lab_results.

The normal range can be one column ("4–10", "≤ 25") or two, in any format, as long as each
row shows its limits; L2 leaves the range (and the units, which the prompt doesn't ask
for) to this check. "Easy to see" accepts any marking
of the cells outside the range (fill, text color or weight, a symbol) that no cell inside
the range shares, from a small set of styles (so a color scale over all the values doesn't
count).
"""

import math
import re

from harness.score.intent import fold, values_match

DAYS = [f"day_{d}" for d in range(3, 10)]

DATA_COLUMNS = ["test", *DAYS]


def _numbers(text):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))]


def _shows(nums, v):
    return any(abs(x - v) <= max(0.05, 0.001 * abs(v)) for x in nums)


def check(t, truth):
    days = [t.col(d, like=truth.col(d)) for d in DAYS]
    lo, hi = truth.col("norm_l").raw, truth.col("norm_u").raw
    values = {d: truth.col(d).raw for d in DAYS}

    # The truth's row for each of the candidate's rows: by position if the rows are in the
    # same order, else by test name
    if values_match(days[0], truth.col("day_3"), ordered=True):
        rows = list(range(truth.n_rows))
    else:
        names = [fold(x) for x in truth.col("test").text]
        test = t.col(like=truth.col("test"))
        rows = [
            next((i for i, n in enumerate(names) if fold(x).startswith(n)), None) for x in test.text
        ]
    if len(rows) != t.n_rows or None in rows:
        t.expect("rows matched to the truth's", False, f"{t.n_rows} rows")
        return

    # The units' digits ("×10^9/L") don't count as limits
    units = t.col("units", like=truth.col("units"))
    others = [c for c in t.visible() if all(c is not d for d in [*days, units])]
    unshown = []
    for r, i in enumerate(rows):
        nums = [x for c in others for x in _numbers(c.text[r])]
        limits = [v for v in (lo[i], hi[i]) if not _missing(v)]
        if not all(_shows(nums, v) for v in limits):
            unshown.append(truth.col("test").text[i])
    t.expect("normal range shown", not unshown, f"rows without their limits: {unshown[:6]}")

    inside, outside = set(), set()
    for d, c in zip(DAYS, days):
        if not c.found:
            continue
        var = "<stub>" if c.kind == "stub" else c.var
        for r, i in enumerate(rows):
            v = values[d][i]
            if _missing(v) or _missing(hi[i]):
                continue
            style = t.text_style(r, var)
            mark = (
                t.fill(r, var),
                tuple(sorted((k, str(style[k])) for k in style)),
                re.sub(r"[\d.,\s\N{MINUS SIGN}-]", "", c.text[r]),
            )
            out = v > hi[i] or (not _missing(lo[i]) and v < lo[i])
            (outside if out else inside).add(mark)
    t.expect(
        "results outside the range marked",
        bool(outside) and not outside & inside and len(outside | inside) <= 4,
        f"outside: {sorted(map(str, outside))[:3]}; inside: {sorted(map(str, inside))[:3]}",
    )


def _missing(v):
    return v is None or (isinstance(v, float) and math.isnan(v))
