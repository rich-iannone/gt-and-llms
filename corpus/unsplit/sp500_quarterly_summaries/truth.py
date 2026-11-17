# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for sp500_quarterly_summaries (spec style): one call per bullet in the prompt.

Readings:
- "The month's average closing price" is the mean of `close` over its trading days.
- Summary rows only carry volume, as the prompt asks; the price column shows the missing
  text there. With Polars data, `summary_rows()` and `grand_summary_rows()` take Polars
  expressions, and neither supports `columns=` on the pin.
- Billions with one decimal is `compact=True`, which gives "65.2B" at this scale.
"""

from functools import partial

import polars as pl
from great_tables import GT, vals

df = (
    pl.read_csv("data/sp500.csv", try_parse_dates=True)
    .filter(pl.col("date").dt.year() == 2015)
    .group_by(pl.col("date").dt.month().alias("m"))
    .agg(close=pl.col("close").mean(), volume=pl.col("volume").sum())
    .sort("m")
    .select(
        quarter=pl.format("Q{}", (pl.col("m") - 1) // 3 + 1),
        month=pl.date(2015, pl.col("m"), 1).dt.strftime("%B"),
        close="close",
        volume="volume",
    )
)
billions = partial(vals.fmt_number, decimals=1, compact=True)

gt = (
    GT(df, rowname_col="month", groupname_col="quarter")
    .tab_header(title="S&P 500 in 2015")
    .cols_label(close="Average Close", volume="Volume")
    .fmt_currency("close", decimals=2)
    .fmt_number("volume", decimals=1, compact=True)
    .summary_rows(fns={"Quarter total": pl.col("volume").sum()}, fmt=billions)
    .grand_summary_rows(fns={"Year total": pl.col("volume").sum()}, fmt=billions)
)

gt_tbl = gt
