# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for constants_planck_units (spec style): one call per bullet in the prompt.

Readings:
- Seven constants start with "Planck"; two of them (the Planck constant in J Hz⁻¹ and in
  eV Hz⁻¹) are exact and have no uncertainty.
- The prompt doesn't set the digits: `fmt_scientific()`'s default (2 decimals) is used, and
  any count should pass.
- `fmt_units()` gives the superscripts; hand-written <sup> markup would also do.
"""

import polars as pl
from great_tables import GT

df = (
    pl.read_csv("data/constants.csv")
    .filter(pl.col("name").str.starts_with("Planck"))
    .select("name", "value", "uncert", "units")
)

gt = (
    GT(df, rowname_col="name")
    .tab_header(title="Planck Constants")
    .cols_label(value="Value", uncert="Uncertainty", units="Units")
    .fmt_scientific(["value", "uncert"])
    .sub_missing("uncert", missing_text="exact")
    .fmt_units("units")
)

gt_tbl = gt
