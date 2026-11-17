# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for countrypops_g7_flags: one per bullet in the prompt.

A flag is an SVG or image (`fmt_flag()`), or an emoji flag. It must be in its own column,
right before or after the country's name. The flags' own text varies, so L2 leaves them to
the check below.
"""

import re

from harness.score.intent import values_match

FLAG = re.compile(r"<svg|<img|[\U0001F1E6-\U0001F1FF]{2}")

DATA_COLUMNS = ["country_name", "population"]


def check(t, truth):
    # A flag's text is its country's name, so the name column is the one without flags
    names = [
        c
        for c in t.visible()
        if values_match(c, truth.col("country_name")) and not all(FLAG.search(h) for h in c.html)
    ]
    name = names[0] if names else t.col("a country name column")
    population = t.col(like=truth.col("population"))
    t.row_count(7)

    # Columns as displayed: the stub first
    shown = sorted(t.visible(), key=lambda c: c.kind != "stub")
    shown = [c for c in shown if c.kind in ("stub", "default")]
    at = next((i for i, c in enumerate(shown) if c is name), None)
    flags = [
        i for i, c in enumerate(shown) if c is not name and all(FLAG.search(h) for h in c.html)
    ]
    t.expect(
        "flag column next to the name",
        at is not None and any(abs(i - at) == 1 for i in flags),
        f"flag columns: {[shown[i].var for i in flags]}",
    )

    t.formatted(population, r"\d{1,3}\.\d\s?M")
    t.order(population, descending=True)
    t.title("G7 Populations, 2022")
