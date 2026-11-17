# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for reactions_cyclic_alkenes (spec style): one call per bullet in the prompt.

Readings:
- 15 compounds have all three of OH_k298, O3_k298 and NO3_k298.
- The units in the spanner use GT's units notation, `{{cm^3 molecule^-1 s^-1}}`; any
  rendering with real superscripts is fine.
- The O₃ and NO₃ labels use Unicode subscripts; `fmt_chem`-style markup is fine.
"""

import polars as pl
from great_tables import GT

k = ["OH_k298", "O3_k298", "NO3_k298"]

df = (
    pl.read_csv("data/reactions.csv", infer_schema_length=None)
    .filter(pl.col("cmpd_type") == "cyclic monoalkene")
    .drop_nulls(k)
    .sort("OH_k298", descending=True)
    .select("cmpd_name", "cmpd_formula", *k)
)

gt = (
    GT(df)
    .tab_header(title="Cyclic Monoalkene Reactivity")
    .fmt_chem("cmpd_formula")
    .fmt_scientific(k, decimals=2)
    .tab_spanner("Rate constant at 298 K, {{cm^3 molecule^-1 s^-1}}", k)
    .cols_label(
        cmpd_name="Compound", cmpd_formula="Formula", OH_k298="OH", O3_k298="O₃", NO3_k298="NO₃"
    )
)

gt_tbl = gt
