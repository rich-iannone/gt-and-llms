# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for countrypops_g7_flags (spec style): one call per bullet in the prompt.

Readings:
- The G7 are matched by their two-letter codes, which avoids depending on how the data
  spells "United Kingdom" or "United States".
- "Next to its name" puts the flag column immediately before the name; after it is fine.
- Millions with one decimal is `fmt_number(scale_by=1e-6, pattern="{x}M")`; `compact=True`
  gives the same text here, since every value is in the millions.
"""

import polars as pl
from great_tables import GT

g7 = ["CA", "FR", "DE", "IT", "JP", "GB", "US"]

df = (
    pl.read_csv("data/countrypops.csv")
    .filter(pl.col("year") == 2022, pl.col("country_code_2").is_in(g7))
    .sort("population", descending=True)
    .select(flag="country_code_2", country_name="country_name", population="population")
)

gt = (
    GT(df)
    .tab_header(title="G7 Populations, 2022")
    .fmt_flag("flag")
    .cols_label(flag="", country_name="Country", population="Population")
    .fmt_number("population", decimals=1, scale_by=1e-6, pattern="{x}M")
)

gt_tbl = gt
