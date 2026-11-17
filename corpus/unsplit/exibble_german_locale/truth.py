# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for exibble_german_locale (spec style): one call per bullet in the prompt.

Readings:
- "German conventions" is `locale="de"`: `.` groups thousands and `,` marks decimals.
- The long German date is `date_style="day_month_year"` ("15 Januar 2015"). Other styles
  that spell the month out ("15. Januar 2015") are fine.
- `sub_missing()`'s default text renders as an em dash.
"""

import polars as pl
from great_tables import GT

df = pl.read_csv("data/exibble.csv", try_parse_dates=True).select("char", "num", "currency", "date")

gt = (
    GT(df)
    .tab_header(title="Exibble auf Deutsch")
    .fmt_number("num", decimals=2, locale="de")
    .fmt_currency("currency", currency="EUR", locale="de")
    .fmt_date("date", date_style="day_month_year", locale="de")
    .sub_missing()
)

gt_tbl = gt
