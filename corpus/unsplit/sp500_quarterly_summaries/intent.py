# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for sp500_quarterly_summaries: one per bullet in the prompt.

The groups can be labelled however the candidate likes ("Q1", "Q1 2015"), as long as there
are four of three months each, in order. The checks don't read the summary rows' values.
"""

import re

from harness.score.intent import currency


def check(t, truth):
    t.row_count(12)
    quarter = t.col(like=truth.col("quarter"))
    if quarter.found:
        t.grouped_by(quarter)
    else:
        labels = [t.group_labels[g] for g in t.group_ids]
        by_quarter = all(re.search(rf"Q{i // 3 + 1}", lab) for i, lab in enumerate(labels))
        t.expect(
            "grouped by quarter",
            len(labels) == 12 and len(set(t.group_ids)) == 4 and by_quarter,
            f"groups: {list(t.group_labels.values())}",
        )
    t.summary_row(grand=False)
    t.summary_row(grand=True)
    t.formatted(t.col(like=truth.col("close")), currency(2))
    t.formatted(t.col(like=truth.col("volume")), r"\d{1,3}(?:\.\d+)?\s?B")
    t.title("S&P 500 in 2015")
