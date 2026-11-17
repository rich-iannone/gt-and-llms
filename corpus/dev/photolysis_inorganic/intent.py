# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for photolysis_inorganic.

All eight inorganic reactions, one row per product channel. The data is L2's job.
"""


def check(t, truth):
    t.row_count(8)
