# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for sp500_monthly_performance.

The row count is gt-skill's REQUIRED_INSTRUCTIONS for the item; the data is L2's job.
"""


def check(t, truth):
    t.row_count(72)
