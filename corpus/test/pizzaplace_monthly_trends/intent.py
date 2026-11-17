# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for pizzaplace_monthly_trends.

One row per category, a chart in some column, and the year's total as a grand summary row
(a total added as a body row would also fail L2, which compares four rows).
"""


def check(t, truth):
    t.row_count(4)
    plots = [c for c in t.visible() if c.html and all("<svg" in h for h in c.html)]
    t.nanoplot(plots[0] if plots else "a chart column")
    t.summary_row(grand=True)
