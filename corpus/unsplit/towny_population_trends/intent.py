# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for towny_population_trends: one per bullet in the prompt.

The chart can be in any column; the change has to be a percentage with one decimal.
"""

from harness.score.intent import number, percent


def check(t, truth):
    t.row_count(10)
    t.formatted(t.col("population_2021", like=truth.col("population_2021")), number())
    plots = [c for c in t.visible() if c.html and all("<svg" in h for h in c.html)]
    t.nanoplot(plots[0] if plots else "a chart column")
    t.formatted(t.col(like=truth.col("change")), percent(1))
    t.stub(t.col("name", like=truth.col("name")))
    t.title("Ontario.s Largest Municipalities")
