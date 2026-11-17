# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for gtcars_top10_by_country.

All three are gt-skill's REQUIRED_INSTRUCTIONS for the item: 10 rows, the same grouping as
the truth's, and the most expensive first within each group. The data is L2's job.
"""


def check(t, truth):
    t.row_count(10)
    t.grouped_by(t.col(like=truth.col("ctry_origin")))
    t.order(t.col(like=truth.col("msrp")), descending=True, within_groups=True)
