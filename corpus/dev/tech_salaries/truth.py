# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for tech_salaries (spec style): one call per bullet in the prompt, nothing else.

Readings:
- The prompt conflicts with itself: grouping by role turns role into row-group labels, so
  the "Role" spanner can't also sit over a role column. Here it spans level alone. Keeping
  role as a column as well as the groups would also satisfy the prompt.
- "salary/compensation columns" are base_salary, bonus, equity and total_comp.
- The gradient is white to green over total_comp's range, so the highest value is darkest.
- "smaller, gray font" is `size="smaller"` and `color="gray"` on the location body cells.
"""

import polars as pl
from great_tables import GT, loc, style

money = ["base_salary", "bonus", "equity", "total_comp"]

df = pl.read_csv("data/tech_salaries.csv")

gt = (
    GT(df, groupname_col="role")
    .fmt_currency(columns=money, decimals=0)
    .data_color(columns="total_comp", palette=["white", "green"])
    .tab_style(
        style=style.text(size="smaller", color="gray"), locations=loc.body(columns="location")
    )
    .tab_spanner(label="Role", columns="level")
    .tab_spanner(label="Compensation", columns=money)
    .tab_spanner(label="Details", columns=["yoe", "location"])
)

gt_tbl = gt
