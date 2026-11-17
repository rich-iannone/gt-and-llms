# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for tech_salaries: one per bullet in the prompt.

The "Role" spanner can't sit over role once role is the row groups (see truth.py), so it
only has to cover level.
"""

from harness.score.intent import currency


def check(t, truth):
    def col(name):
        return t.col(name, like=truth.col(name))

    money = [col("base_salary"), col("bonus"), col("equity"), col("total_comp")]
    t.grouped_by(col("role"))
    t.formatted(money, currency(0))
    t.gradient(col("total_comp"), darker="higher", color="green")
    t.text_styled(col("location"), size="smaller", color="gray")
    t.spanner([col("level")], "^Role$")
    t.spanner(money, "^Compensation$", exact=True)
    t.spanner([col("yoe"), col("location")], "^Details$", exact=True)
