# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for peeps_tallest.

The prompt's "10 tallest". The data is L2's job.
"""


def check(t, truth):
    t.row_count(10)
