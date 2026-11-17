# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for towny_top10_by_population.

The row count is gt-skill's REQUIRED_INSTRUCTIONS for the item. "How their population
density changed" can be shown as both densities or as the change, so L2 leaves the density
columns to the check below.
"""

DATA_COLUMNS = ["name", "population_2021", "growth_pct"]


def check(t, truth):
    t.row_count(10)
    both = all(t.col(like=truth.col(f"density_{y}")).found for y in (2011, 2021))
    change = t.col(like=truth.col("density_change")).found
    t.expect("density change shown", both or change, f"both densities: {both}, change: {change}")
