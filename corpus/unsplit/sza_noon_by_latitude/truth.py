# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for sza_noon_by_latitude (intent style, replaces airquality_wind_regime).

Readings:
- "Solar noon" is true solar time 1200 (`tst == 1200`), the last time in the data.
- Months are rows in calendar order and the four latitudes are columns, under a spanner.
  The transpose (latitudes as rows) is an equally good reading.
"""

import polars as pl
from great_tables import GT

months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
lats = ["20", "30", "40", "50"]

df = (
    pl.read_csv("data/sza.csv")
    .filter(pl.col("tst") == 1200)
    .pivot(on="latitude", index="month", values="sza")
    .with_columns(order=pl.col("month").replace_strict(months, list(range(12))))
    .sort("order")
    .select(pl.col("month").str.to_titlecase(), *lats)
)

gt = (
    GT(df, rowname_col="month")
    .tab_header(title="Solar Zenith Angle at Solar Noon", subtitle="Degrees, by month")
    .tab_spanner("Latitude", lats)
    .cols_label(**{lat: f"{lat}°N" for lat in lats})
    .fmt_number(lats, decimals=1)
)

gt_tbl = gt
