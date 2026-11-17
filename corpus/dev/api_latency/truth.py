# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for api_latency (spec style): one call per bullet in the prompt, nothing else.

Readings:
- "the millisecond columns" are avg_ms, p95_ms, p99_ms. Every number column here is a count
  of whole units, so `fmt_integer()` gives the comma separators without adding decimals.
- "highlights rows" fills the whole row, the stub cell included.
- "light red" is #FFE0E0; any light red should pass.
- Sorting happens on the data before GT, which keeps the stub order the same as the sort.
"""

import polars as pl
from great_tables import GT, loc, style

df = pl.read_csv("data/api_latency.csv").sort("p99_ms", descending=True)
slow = pl.col("p99_ms") > 1000

gt = (
    GT(df, rowname_col="endpoint")
    .tab_header(title="API Performance Dashboard")
    .fmt_integer(columns=["avg_ms", "p95_ms", "p99_ms"])
    .fmt_integer(columns="requests")
    .fmt_integer(columns="errors")
    .tab_style(
        style=style.fill(color="#FFE0E0"), locations=[loc.body(rows=slow), loc.stub(rows=slow)]
    )
)

gt_tbl = gt
