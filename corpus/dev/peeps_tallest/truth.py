# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for peeps_tallest (intent style, replaces airquality_hottest_days).

Readings:
- "people" are named by given and family name together, in the stub.
- "the country they live in" is the `country` code; the 10th and 11th tallest differ
  (184 vs 183 cm), so there's no tie at the cut.
"""

import polars as pl
from great_tables import GT

df = (
    pl.read_csv("data/peeps.csv")
    .sort("height_cm", descending=True)
    .head(10)
    .select(
        name=pl.concat_str("name_given", "name_family", separator=" "),
        country="country",
        height_cm="height_cm",
        weight_kg="weight_kg",
    )
)

gt = (
    GT(df, rowname_col="name")
    .tab_header(title="The 10 Tallest People")
    .cols_label(country="Country", height_cm="Height (cm)", weight_kg="Weight (kg)")
    .fmt_number("weight_kg", decimals=1)
)

gt_tbl = gt
