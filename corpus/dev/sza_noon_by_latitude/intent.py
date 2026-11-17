# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for sza_noon_by_latitude.

One row per month. The data is L2's job.
"""


def check(t, truth):
    t.row_count(12)
