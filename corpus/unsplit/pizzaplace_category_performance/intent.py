# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for pizzaplace_category_performance.

One row per category (gt-skill's REQUIRED_INSTRUCTIONS has no count for this item; the four
categories are implied by "for each category"). The data is L2's job.
"""


def check(t, truth):
    t.row_count(4)
