# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for towny_growth_trends.

The row count is gt-skill's REQUIRED_INSTRUCTIONS for the item. The prompt asks for the
densities and the changes between Censuses, so L2 doesn't require the truth's rank and
total-growth columns.
"""

YEARS = (1996, 2001, 2006, 2011, 2016, 2021)

DATA_COLUMNS = [
    "name",
    *(f"density_{y}" for y in YEARS),
    *(f"pop_change_{a}_{b}_pct" for a, b in zip(YEARS, YEARS[1:])),
]


def check(t, truth):
    t.row_count(15)
