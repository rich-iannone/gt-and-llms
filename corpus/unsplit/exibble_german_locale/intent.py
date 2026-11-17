# Model-drafted 2026-11-16; review pending (PROVENANCE.md).
"""Checks for exibble_german_locale: one per bullet in the prompt.

The euro sign can go before or after the amount, with any number of decimals. A long date
can have a weekday or a period after the day ("Donnerstag, 15. Januar 2015").
"""

from harness.score.intent import currency, number

MONTHS = "Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"


def check(t, truth):
    cols = {n: t.col(n, like=truth.col(n)) for n in ("char", "num", "currency", "date")}
    t.has_columns(*cols.values())
    t.formatted(cols["num"], number(2, sep=".", dec=","))
    t.formatted(cols["currency"], currency(symbol="€", sep=".", dec=","))
    t.formatted(cols["date"], rf"(?:\w+,\s)?\d{{1,2}}\.?\s(?:{MONTHS})\s\d{{4}}")
    missing = [
        (c.var, x)
        for c in cols.values()
        for x, m in zip(c.text, c.is_missing)
        if m and x != "\N{EM DASH}"
    ]
    t.expect("missing values shown as an em dash", not missing, f"cells: {missing[:6]}")
    t.title("Exibble auf Deutsch")
