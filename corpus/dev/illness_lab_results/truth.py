# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for illness_lab_results (intent style, replaces airquality_monthly_summary).

Readings:
- One row per test, in the data's order, with the test (and its units) in the stub and a
  column per day.
- The normal range is norm_l to norm_u as one column of text. Four tests have only an upper
  limit, shown as "≤ 25"; `cols_merge_range()` would render those as "——25". Tests without
  a range (viral load, for one) show a dash and are never flagged.
- "Easy to see" is a red, bold result where it's below norm_l or above norm_u. Any clear
  per-cell marking (color, fill, weight) should count.
- The units are written in GT's units notation (`x10^9 / L`), so `fmt_units()` renders them.
"""

import polars as pl
from great_tables import GT, loc, style

df = pl.read_csv("data/illness.csv")
days = [f"day_{d}" for d in range(3, 10)]


def _num(col: str) -> pl.Expr:
    """A limit as text, without trailing zeros (2.2, not 2.20)."""
    return pl.col(col).round(2).cast(pl.String).str.replace(r"\.0$", "")


df = df.with_columns(
    normal=pl.when(pl.col("norm_l").is_null())
    .then(pl.format("≤ {}", _num("norm_u")))
    .otherwise(pl.format("{}–{}", _num("norm_l"), _num("norm_u")))
)

gt = (
    GT(df, rowname_col="test")
    .tab_header(title="Laboratory Results, Days 3 to 9")
    .cols_hide(["norm_l", "norm_u"])
    .cols_label(units="Units", normal="Normal Range", **{d: f"Day {d[4:]}" for d in days})
    .tab_spanner("Day of Illness", days)
    .fmt_number(days, decimals=2, drop_trailing_zeros=True)
    .fmt_units("units")
    .sub_missing()
)
for d in days:
    outside = (pl.col(d) < pl.col("norm_l")) | (pl.col(d) > pl.col("norm_u"))
    gt = gt.tab_style(style.text(color="#C62828", weight="bold"), loc.body(columns=d, rows=outside))

gt_tbl = gt
