# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for reactions_cyclic_alkenes: one per bullet in the prompt.

Subscripts and superscripts can be HTML (`fmt_chem()`, `fmt_units()`, <sub>) or Unicode.
"""

import re

from harness.score.intent import fold, scientific

K = ["OH_k298", "O3_k298", "NO3_k298"]


def check(t, truth):
    def col(name):
        return t.col(name, like=truth.col(name))

    t.row_count(15)
    name, formula = col("cmpd_name"), col("cmpd_formula")
    t.has_columns(name, formula)
    subscripts = formula.found and all(re.search(r"<sub|[₀-₉]", h) for h in formula.html)
    t.expect("formulas have subscripts", subscripts)

    ks = [col(k) for k in K]
    t.formatted(ks, scientific(2))
    t.spanner(ks, r"Rate constant at 298\s?K", exact=True)
    units = [
        s
        for s in t.spanners
        if set(s["vars"]) >= {k.var for k in ks}
        and "cm3molecule-1s-1" in fold(s["html"])
        and re.search(r"<sup|[³⁻¹]", s["html"])
    ]
    t.expect(
        "spanner shows the units", bool(units), f"spanners: {[s['label'] for s in t.spanners]}"
    )
    labels = [fold(k.label) for k in ks]
    scripted = all(re.search(r"<sub|₃", k.label_html) for k in ks[1:])
    t.expect(
        "rate constants labelled", labels == ["oh", "o3", "no3"] and scripted, f"labels: {labels}"
    )

    t.order(ks[0], descending=True)
    t.title("Cyclic Monoalkene Reactivity")
