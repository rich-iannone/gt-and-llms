# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for pizzaplace_daypart_by_category.

All three are gt-skill's REQUIRED_INSTRUCTIONS for the item: 16 rows, grouped by day-part,
and the highest revenue first within each group. The prompt itself doesn't ask for that
order. Day-part groups can be labelled however the candidate likes, as long as each label
names its day-part ("Dinner (5pm on)").
"""

DAYPARTS = ("morning", "lunch", "afternoon", "dinner")


def check(t, truth):
    t.row_count(16)
    daypart = t.col(like=truth.col("daypart"))
    if daypart.found:
        t.grouped_by(daypart)
    else:
        labels = {g: lab.casefold() for g, lab in t.group_labels.items()}
        named = [[d for d in DAYPARTS if d in lab] for lab in labels.values()]
        t.expect(
            "grouped by day-part",
            len(labels) == 4 and sorted(n[0] for n in named if len(n) == 1) == sorted(DAYPARTS),
            f"groups: {list(t.group_labels.values())}",
        )
    t.order(t.col(like=truth.col("revenue")), descending=True, within_groups=True)
