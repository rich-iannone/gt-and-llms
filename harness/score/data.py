"""Data correctness: L2 of the scoring (plan §6). Does the candidate show the truth's data?

Each of the truth's visible columns (the stub and row groups included) is matched to a
candidate column holding the same values, compared as `values_match` does: at the precision
the candidate shows, at any of the usual scalings, in any row order (order is L1's job). Each
candidate column matches at most one truth column. The score is the share of truth columns
matched; candidate columns with no match in the truth aren't penalized. A candidate with a different
number of rows matches nothing, so it scores 0.

An intent.py can set `DATA_COLUMNS = ["car", "msrp", ...]` (truth columns by name or label)
when only some of the truth's columns are what the prompt asks for. Nanoplot columns are
skipped, since what they show is a picture.
"""

from collections.abc import Sequence

from harness.score.intent import Column, Table, values_match


def _is_plot(c: Column) -> bool:
    return any("<svg" in h for h in c.html)


def data_check(cand: Table, truth: Table, columns: Sequence[str] | None = None) -> dict:
    """{"score", "rows": [candidate, truth], "matched": {truth var: candidate var},
    "unmatched": [...], "skipped": [...]}"""
    if columns:
        wanted = [truth.col(name) for name in columns]
        lost = [c.var for c in wanted if not c.found]
        if lost:
            raise ValueError(f"DATA_COLUMNS not in the truth: {', '.join(lost)}")
    else:
        wanted = truth.visible()
    skipped = [c.var for c in wanted if _is_plot(c)]
    wanted = [c for c in wanted if not _is_plot(c)]

    matched: dict[str, str] = {}
    if cand.n_rows == truth.n_rows:
        free = [c for c in cand.visible() if not _is_plot(c)]
        for t in wanted:
            hit = next((c for c in free if values_match(c, t)), None)
            if hit is not None:
                matched[t.var] = hit.var
                free.remove(hit)
    return {
        "score": len(matched) / len(wanted) if wanted else None,
        "rows": [cand.n_rows, truth.n_rows],
        "matched": matched,
        "unmatched": [t.var for t in wanted if t.var not in matched],
        "skipped": skipped,
    }
