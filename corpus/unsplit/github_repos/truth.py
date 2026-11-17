# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for github_repos (spec style): one call per bullet in the prompt, nothing else.

Readings:
- The prompt conflicts with itself: a nanoplot replaces the cell's text, so the stars column
  can't show both "23.5K" and a bar. Here the bar goes in an unlabelled copy of stars placed
  right after it, so the two read as one column. A single stars column holding a bar nanoplot,
  whose value label is already compact ("23.5K"), is the other defensible reading.
- "K suffix" is `fmt_number(compact=True)` with one decimal, matching the "23.4K" example.
- The colors fill the cell background: <3 green, 3 to 7 (inclusive) yellow, >7 red. No repo
  in this data is >7 days, so the red rule never applies; it's still part of the table.
"""

import polars as pl
from great_tables import GT, loc, style

df = (
    pl.read_csv("data/github_repos.csv")
    .with_columns(stars_bar=pl.col("stars"))
    .select(
        "repo", "language", "stars", "stars_bar", "forks",
        "issues_open", "issues_closed", "prs_merged", "last_commit_days",
    )
)  # fmt: skip
days = pl.col("last_commit_days")

gt = (
    GT(df)
    .tab_header(title="GitHub Repository Metrics")
    .fmt_number(columns="stars", compact=True, decimals=1)
    .fmt_integer(columns="forks")
    .fmt_nanoplot(columns="stars_bar", plot_type="bar")
    .cols_label(stars_bar="")
    .tab_style(
        style=style.fill(color="lightgreen"), locations=loc.body("last_commit_days", days < 3)
    )
    .tab_style(
        style=style.fill(color="lightyellow"),
        locations=loc.body("last_commit_days", (days >= 3) & (days <= 7)),
    )
    .tab_style(
        style=style.fill(color="lightcoral"), locations=loc.body("last_commit_days", days > 7)
    )
    .tab_spanner(label="Issues", columns=["issues_open", "issues_closed"])
)

gt_tbl = gt
