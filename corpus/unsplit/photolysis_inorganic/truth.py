# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for photolysis_inorganic (intent style, replaces islands_sizes's role as the
vague easy prompt).

Readings:
- "inorganic photolysis reactions" are the rows whose type is "inorganic reactions".
- "each compound" is its name and formula; "what it breaks down into" is `products`. A
  compound with two product channels (ozone, the nitrate radical) has a row per channel.
- `fmt_chem()` gives the formulas their subscripts. On the pin it leaves excited states like
  `O(^1D)` as written.
"""

import polars as pl
from great_tables import GT

df = (
    pl.read_csv("data/photolysis.csv")
    .filter(pl.col("type") == "inorganic reactions")
    .select("cmpd_name", "cmpd_formula", "products")
)

gt = (
    GT(df)
    .tab_header(title="Inorganic Photolysis Reactions")
    .cols_label(cmpd_name="Compound", cmpd_formula="Formula", products="Products")
    .fmt_chem(["cmpd_formula", "products"])
)

gt_tbl = gt
