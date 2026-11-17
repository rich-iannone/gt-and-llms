# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for gtcars_hp_price.

Every car in gtcars (gt-skill's REQUIRED_INSTRUCTIONS has no count for this item; "the gt
cars" means all of them). The data is L2's job.
"""


def check(t, truth):
    t.row_count(47)
