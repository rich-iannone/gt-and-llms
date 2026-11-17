# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for pizzaplace_top_pizzas.

The row count is gt-skill's REQUIRED_INSTRUCTIONS for the item; the data is L2's job.
"""


def check(t, truth):
    t.row_count(10)
