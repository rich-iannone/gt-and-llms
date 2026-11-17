# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for gtcars_country_matrix.

One row per country of origin (gt-skill's REQUIRED_INSTRUCTIONS has no count for this item;
the five countries are implied by "for each country"). The data is L2's job.
"""


def check(t, truth):
    t.row_count(5)
