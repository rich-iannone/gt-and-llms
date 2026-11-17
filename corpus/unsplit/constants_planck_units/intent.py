# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for constants_planck_units: one per bullet in the prompt.

The prompt doesn't fix the digits of the scientific notation. "exact" may come from
`sub_missing()` or from text put in the data. L2 compares the units as `fold` reads them, so
"J Hz^-1" left as typed doesn't match; the superscript check makes sure they aren't just
"J Hz-1" either.
"""

import re

from harness.score.intent import fold, scientific

SUPERSCRIPT = re.compile(r"<sup|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]")


def check(t, truth):
    def col(name):
        return t.col(name, like=truth.col(name))

    name, value, uncert, units = col("name"), col("value"), col("uncert"), col("units")
    t.row_count(7)
    t.has_columns(name, value, uncert, units)

    exact_names = {
        fold(n) for n, m in zip(truth.col("name").text, truth.col("uncert").is_missing) if m
    }
    exact = [fold(n) in exact_names for n in name.text]
    t.formatted(value, scientific())
    t.formatted(uncert, scientific(), rows=[not e for e in exact])
    shown = [x for x, e in zip(uncert.text, exact) if e]
    t.expect(
        '"exact" where there is no uncertainty',
        uncert.found and bool(shown) and all(x.casefold() == "exact" for x in shown),
        f"shown: {shown}",
    )

    want = sum("^" in str(u) for u in truth.col("units").raw)
    got = sum(bool(SUPERSCRIPT.search(h)) and "^" not in x for h, x in zip(units.html, units.text))
    t.expect("units have superscripts", units.found and got >= want, f"{got} of {want} cells")

    t.stub(name)
    t.title("Planck Constants")
