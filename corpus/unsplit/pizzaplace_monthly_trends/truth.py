# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for pizzaplace_monthly_trends (intent style).

Readings:
- "Pizza category" is `type`; the data is all 2015. Revenue is the sum of `price`, and each
  row is one pizza sold.
- The chart is a nanoplot of the 12 monthly revenues, January first; a bar chart is as good.
- "A total for the whole year" is a grand summary row with the revenue and count totals.
  Its `fmt=` applies to every column, so the revenue total has no dollar sign here; a
  candidate that gets one (with a second summary row, or by building the row itself) is
  fine.
"""

from functools import partial

import polars as pl
from great_tables import GT, vals

pizzas = pl.read_csv("data/pizzaplace.csv", try_parse_dates=True)

monthly = (
    pizzas.group_by("type", pl.col("date").dt.month().alias("month"))
    .agg(revenue=pl.col("price").sum())
    .sort("month")
    .group_by("type")
    .agg(by_month=pl.col("revenue"))
)
df = (
    pizzas.group_by("type")
    .agg(revenue=pl.col("price").sum(), sold=pl.len())
    .join(monthly, on="type")
    .sort("revenue", descending=True)
    .with_columns(pl.col("type").str.to_titlecase())
)

gt = (
    GT(df, rowname_col="type")
    .tab_header(title="Pizza Sales by Category, 2015")
    .cols_label(revenue="Revenue", sold="Pizzas Sold", by_month="Monthly Revenue")
    .fmt_currency("revenue", decimals=0)
    .fmt_integer("sold")
    .fmt_nanoplot("by_month")
    .grand_summary_rows(
        fns={"Total": [pl.col("revenue").sum(), pl.col("sold").sum()]},
        fmt=partial(vals.fmt_number, decimals=0),
    )
)

gt_tbl = gt
