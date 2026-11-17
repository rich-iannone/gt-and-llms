# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for github_repos: one per bullet in the prompt.

The prompt asks for the stars both as "23.4K" and as a bar, which one cell can't show (see
truth.py). Either reading passes: a stars column in K next to a chart, or a chart whose own
label is in K. "Colors" can be a fill or the text's color.
"""

import re

from harness.score.intent import color_is, compact, number, values_match

K_LABEL = re.compile(r"\d{1,3}(?:\.\d+)?\s?K\s*$")


def check(t, truth):
    def col(name):
        return t.col(name, like=truth.col(name))

    plots = [c for c in t.visible() if c.html and all("<svg" in h for h in c.html)]
    in_k = [
        c
        for c in t.visible()
        if all(c is not p for p in plots)
        and values_match(c, truth.col("stars"))
        and all(re.fullmatch(compact(), x) for x in c.text)
    ]
    plot_in_k = [c for c in plots if all(K_LABEL.search(x) for x in c.text)]
    t.expect(
        "stars with a K suffix",
        bool(in_k or plot_in_k),
        f"columns: {[c.var for c in in_k + plot_in_k]}",
    )
    t.formatted(col("forks"), number())
    t.nanoplot(plots[0] if plots else "a chart column")

    days = col("last_commit_days")
    var = "<stub>" if days.kind == "stub" else days.var
    want = ["green" if d < 3 else "yellow" if d <= 7 else "red" for d in days.num]
    got = [t.fill(r, var) or t.text_style(r, var).get("color") for r in range(t.n_rows)]
    bad = [(r, w, g) for r, (w, g) in enumerate(zip(want, got)) if not color_is(g, w)]
    t.expect("last_commit_days colored by age", days.found and not bad, f"cells: {bad[:6]}")

    t.spanner([col("issues_open"), col("issues_closed")], "^Issues$", exact=True)
    t.title("GitHub Repository Metrics")
