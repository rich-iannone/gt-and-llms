"""A table's structure, for convergence across repeats (plan §6): what a reader would see as
the same design, read from the GT object. Two repeats agree on a field if its values are
equal."""

import functools
from typing import Any

import great_tables as gt

from harness.score.intent import Table, _norm

FIELDS = ("columns", "stub", "groups", "spanners", "formats", "heading", "summary_rows")


def _formatter(fns: Any) -> str:
    fn = getattr(fns, "html", None) or fns.default
    while isinstance(fn, functools.partial):
        fn = fn.func
    name = getattr(fn, "__name__", "")
    return name.removesuffix("_context") if name.startswith(("fmt_", "vals.")) else "fmt"


def signature(tbl: gt.GT) -> dict:
    """Each FIELDS entry as a JSON-able value. Columns are named by data name."""
    t = Table(tbl)
    shown = {c.var for c in t.visible()}
    formats: dict[str, str] = {}
    for f in tbl._formats:  # later formats win, as when rendering
        for var in f.cells.cols:
            if var in shown:
                formats[var] = _formatter(f.func)
    for c in t.visible():
        if any("<svg" in h for h in c.html):
            formats[c.var] = "nanoplot"
    stub = t.stub_col
    groups = next((c.var for c in t.columns if c.kind == "row_group"), None)
    if groups is None and t.group_ids:
        groups = "<groups>"  # rows grouped without a group column
    # Labels of the per-group and the grand summary rows
    summaries = [
        sorted({_norm(r.label) for rows in s._d.values() for r in rows})
        for s in (tbl._summary_rows, tbl._summary_rows_grand)
    ]
    return {
        "columns": [c.var for c in t.visible() if c.kind not in ("stub", "row_group")],
        "stub": stub.var if stub else None,
        "groups": groups,
        "spanners": sorted(sorted(s["vars"]) for s in t.spanners),
        "formats": dict(sorted(formats.items())),
        "heading": [bool(t.title_text), bool(t.subtitle_text), len(t.source_notes)],
        "summary_rows": summaries,
    }
