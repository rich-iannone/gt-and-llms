# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for peeps_canada_directory (spec style): one call per bullet in the prompt.

Readings:
- The merges use `cols_merge()`, which keeps the data columns for sorting and checks;
  building the strings in Polars first is just as good.
- "Clickable link" is a mailto: link, from `fmt_email()`.
- The icons are Font Awesome's "person-dress" and "person", through `fmt_icon()`. Other
  woman/man icons (or ♀/♂) are fine; the gender text itself shouldn't remain.
- Only the columns the prompt names are shown.
"""

import polars as pl
from great_tables import GT

df = (
    pl.read_csv("data/peeps.csv")
    .filter(pl.col("country") == "CAN")
    .sort("name_family")
    .with_columns(
        gender=pl.col("gender").replace_strict({"female": "person-dress", "male": "person"})
    )
    .select("name_given", "name_family", "city", "state_prov", "email_addr", "gender")
)

gt = (
    GT(df)
    .tab_header(title="Canadian Contacts")
    .cols_merge(["name_given", "name_family"], pattern="{0} {1}")
    .cols_merge(["city", "state_prov"], pattern="{0}, {1}")
    .cols_label(name_given="Name", city="Location", email_addr="Email", gender="Gender")
    .fmt_email("email_addr")
    .fmt_icon("gender")
)

gt_tbl = gt
