# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for towny_population_trends (spec style): one call per bullet in the prompt.

Readings:
- The line chart is a nanoplot of the six census populations, oldest first.
- The change is computed here, (2021 / 1996 - 1) as a percentage; the data's own
  pop_change_* columns are per period, not over the whole span.
"""

import polars as pl
from great_tables import GT

years = [1996, 2001, 2006, 2011, 2016, 2021]

df = (
    pl.read_csv("data/towny.csv")
    .sort("population_2021", descending=True)
    .head(10)
    .select(
        "name",
        "population_2021",
        trend=pl.concat_list([pl.col(f"population_{y}").cast(pl.Float64) for y in years]),
        change=pl.col("population_2021") / pl.col("population_1996") - 1,
    )
)

gt = (
    GT(df, rowname_col="name")
    .tab_header(title="Ontario's Largest Municipalities")
    .cols_label(population_2021="Population, 2021", trend="1996–2021", change="Change")
    .fmt_integer("population_2021")
    .fmt_nanoplot("trend")
    .fmt_percent("change", decimals=1)
)

gt_tbl = gt
