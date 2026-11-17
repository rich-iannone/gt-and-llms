# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for nuclides_stable_isotopes.

Twenty isotopes in one group per element (labelled by symbol or name), and an uncertainty
for each of abundance and atomic mass: merged with its value ("± 0.0078%", or "(14)"
notation) or in a column of its own.
"""

import re
from collections import Counter

UNCERTAINTY = re.compile(r"±|\+/-|\(\d+\)")


def check(t, truth):
    t.row_count(20)
    element = t.col(like=truth.col("element"))
    if element.found:
        t.grouped_by(element)
    else:
        sizes = sorted(Counter(t.group_ids).values())
        want = sorted(Counter(truth.group_ids).values())
        t.expect("grouped by element", bool(t.group_ids) and sizes == want, f"sizes: {sizes}")

    for value, uncert in (("abundance", "abundance_uncert"), ("atomic_mass", "atomic_mass_uncert")):
        c = t.col(like=truth.col(value))
        n = int((~truth.col(uncert).is_missing).sum())
        merged = c.found and sum(bool(UNCERTAINTY.search(x)) for x in c.text) >= n
        separate = t.col(like=truth.col(uncert)).found
        t.expect(f"{value} with its uncertainty", merged or separate, f"column: {c.var}")
