"""Tests for harness/score/intent.py, on small synthetic tables. They need GT, so they run in
the agent's environment, with pytest added for the run only:

    uv run --project console/agent-env --with pytest pytest tests
"""

import re
import sys
from pathlib import Path

import pandas as pd
import polars as pl
import pytest
from great_tables import GT, html, loc, style

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.score.intent import (  # noqa: E402
    INTEGER,
    Table,
    color_is,
    compact,
    currency,
    decimal_mark,
    number,
    parse_number,
    percent,
)

API = pl.DataFrame(
    {
        "endpoint": ["/a", "/b", "/c", "/d"],
        "method": ["GET", "POST", "GET", "GET"],
        "p99_ms": [4321, 2345, 892, 145],
        "requests": [8934, 12456, 34521, 125043],
    }
)


def results(t: Table) -> list[bool]:
    return [r.passed for r in t.results]


@pytest.fixture
def api() -> Table:
    slow = pl.col("p99_ms") > 1000
    return Table(
        GT(API, rowname_col="endpoint")
        .tab_header(title="API Performance Dashboard", subtitle="p99 latency")
        .fmt_integer(columns=["p99_ms", "requests"])
        .tab_style(style.fill("#FFE0E0"), [loc.body(rows=slow), loc.stub(rows=slow)])
        .tab_spanner("Traffic", ["p99_ms", "requests"])
        .tab_source_note("Source: logs")
    )


def test_parse_number():
    assert parse_number("$1,234.5") == (1234.5, 0.05)
    assert parse_number("23.5K") == (23500, 50)
    assert parse_number("−3.0%") == (-3.0, 0.05)
    assert parse_number("($5)") == (-5, 0.5)
    assert parse_number("Ferrari") is None
    assert parse_number("1.007825 ± 1.4 × 10-11") == (1.007825, 0.0000005)
    assert parse_number("4–10") is None


def test_decimal_comma():
    assert parse_number("5.550,00", dec=",") == (5550, 0.005)
    assert parse_number("€1.325,81", dec=",") == (1325.81, 0.005)
    assert decimal_mark(["0,11", "1.234"]) == "," and decimal_mark(["1.234"]) == "."
    assert decimal_mark(["8.880.000"]) == "," and decimal_mark(["1,234", "5.5"]) == "."
    # Read per column: German integers with a group separator aren't decimals
    df = pl.DataFrame({"n": [1234.0, 5.5]})
    de = Table(GT(df).fmt_number("n", decimals=1, locale="de"))
    assert de.col("n").decimal_mark == ","
    assert de.same_values("n", Table(GT(df)).col("n"), ordered=True)
    assert de.formatted("n", number(1, sep=".", dec=",")) and not de.formatted("n", number(1))
    eur = Table(GT(df).fmt_currency("n", currency="EUR", locale="de"))
    assert eur.formatted("n", currency(2, "€", sep=".", dec=","))
    assert re.fullmatch(currency(2, "€", sep=".", dec=","), "1.234,50 €")


def test_colors():
    assert color_is("#FFE0E0", "red", light=True)
    assert color_is("lightcoral", "red")
    assert not color_is("#FFE0E0", "red", light=False)
    assert color_is("lightgreen", "green") and color_is("lightyellow", "yellow")
    assert color_is("gray", "gray") and color_is("#888888", "gray")
    assert not color_is("green", "gray") and not color_is(None, "red")


def test_format_patterns():
    assert re.fullmatch(INTEGER, "125,043") and not re.fullmatch(INTEGER, "125043")
    assert re.fullmatch(currency(0), "$1,416,362") and not re.fullmatch(currency(0), "$5.00")
    assert re.fullmatch(currency(2), "−$5.00")
    assert re.fullmatch(percent(1), "+12.5%") and re.fullmatch(percent(1), "−0.4%")
    assert re.fullmatch(compact(1), "23.5K") and re.fullmatch(compact(1), "950")
    # Signs are only -, + and the unicode minus
    for pattern in (INTEGER, percent(1), compact(1), currency(0)):
        assert not re.fullmatch(pattern, "x5") and not re.fullmatch(pattern, "=5")
    assert re.fullmatch(INTEGER, "−5") and re.fullmatch(INTEGER, "+5")


def test_heading_and_structure(api: Table):
    assert api.title("performance dashboard")
    assert not api.title("latency report")
    assert api.subtitle() and api.source_note("logs")
    assert api.row_count(4) and api.row_count((3, 5)) and not api.row_count(10)
    assert api.stub("endpoint") and not api.stub("method")
    assert api.has_columns("method", "p99_ms") and not api.has_columns("nope")
    assert api.spanner(["p99_ms", "requests"], label="traffic")
    assert api.spanner(["requests"]) and not api.spanner(["requests"], exact=True)
    assert not api.spanner(["method"])
    assert api.order("p99_ms", descending=True) and not api.order("p99_ms")
    assert api.formatted(["p99_ms", "requests"], INTEGER)
    assert not api.formatted("p99_ms", currency())
    assert api.no_raw_missing()


def test_columns_by_label_and_values(api: Table):
    renamed = Table(GT(API.rename({"p99_ms": "P99 (ms)"})).cols_label(method="HTTP Method"))
    assert renamed.col("http method").var == "method"
    found = renamed.col(like=api.col("p99_ms"))
    assert found.found and found.var == "P99 (ms)"
    assert not renamed.col("missing").found
    # A not-found column fails its check instead of raising
    assert not renamed.order("missing") and "not found" in renamed.results[-1].detail


def test_values_match_shown_text_and_scales():
    truth = Table(GT(pl.DataFrame({"share": [0.125, 0.5, 0.375]})))
    as_text = Table(GT(pl.DataFrame({"pct": ["50.0%", "12.5%", "37.5%"]})))
    assert as_text.same_values("pct", truth.col("share"))
    assert not as_text.same_values("pct", truth.col("share"), ordered=True)
    # Compared at the precision shown: 37.5 shown as "38" matches, shown as "37.9" doesn't
    rounded = Table(GT(pl.DataFrame({"pct": [12.0, 50.0, 38.0]})).fmt_number("pct", decimals=0))
    assert rounded.same_values("pct", truth.col("share"))
    off = Table(GT(pl.DataFrame({"pct": [12.5, 50.0, 37.9]})).fmt_number("pct", decimals=1))
    assert not off.same_values("pct", truth.col("share"))


def test_highlight(api: Table):
    slow = api.col("p99_ms").num > 1000
    assert api.filled(slow, color="red", light=True)
    assert not api.filled(slow, color="green")
    assert not api.filled(~slow, color="red")
    # The stub cell is part of the row unless stub=False ...
    no_stub = Table(GT(API, rowname_col="endpoint").tab_style(style.fill("pink"), loc.body()))
    every = [True] * 4
    assert not no_stub.filled(every) and no_stub.filled(every, stub=False)
    # ... and a color scale on one column isn't a row highlight
    scaled = Table(
        GT(API, rowname_col="endpoint")
        .data_color("requests", palette=["white", "red"])
        .tab_style(style.fill("#FFE0E0"), [loc.body(rows=[0, 1]), loc.stub(rows=[0, 1])])
    )
    assert scaled.filled(scaled.col("p99_ms").num > 1000, color="red")


def test_gradient_and_text_style():
    df = pl.DataFrame({"name": ["a", "b", "c"], "v": [1, 9, 5], "loc": ["x", "y", "z"]})
    t = Table(
        GT(df)
        .data_color("v", palette=["white", "green"])
        .tab_style(style.text(size="smaller", color="gray"), loc.body(columns="loc"))
    )
    assert t.gradient("v", color="green") and not t.gradient("v", darker="lower")
    assert not t.gradient("name")
    assert t.text_styled("loc", size="smaller", color="gray")
    assert not t.text_styled("name", size="smaller")
    # Styled through markup a formatter emits (GT escapes markup in plain strings)
    span = '<span style="font-size:0.8em;color:#999">{}</span>'
    inline = Table(GT(df).fmt(span.format, columns="loc"))
    assert inline.text_styled("loc", size="smaller", color="gray")
    assert not Table(GT(pd.DataFrame({"loc": [span.format("x")]}))).text_styled("loc", "smaller")


def test_groups_and_summaries():
    df = pl.DataFrame({"g": ["b", "a", "b", "a"], "k": ["w", "x", "y", "z"], "v": [2, 9, 1, 3]})
    t = Table(
        GT(df, rowname_col="k", groupname_col="g")
        .grand_summary_rows(fns={"Total": pl.col("v").sum()})
        .tab_header(title=html("<b>Grouped</b>"))
    )
    assert t.title("^grouped$")
    assert t.grouped_by("g") and not t.grouped_by("v")
    assert t.order("v", descending=True, within_groups=True)
    assert not t.order("v", descending=True)
    assert t.summary_row("total", grand=True) and not t.summary_row(grand=False)
    flat = Table(GT(df))
    assert not flat.grouped_by("g") and flat.results[-1].detail == "no row groups"


REPO = Path(__file__).resolve().parents[1]
TRUTHS = sorted(REPO.glob("corpus/*/*/truth.py"))


@pytest.mark.parametrize("truth", TRUTHS, ids=[p.parent.name for p in TRUTHS])
def test_reads_real_tables(truth: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """On every corpus truth: the cell text the library reads is what the HTML shows, and
    each column's values match themselves."""
    from harness.score.runner import build

    (tmp_path / "data").symlink_to(REPO / "data")
    monkeypatch.chdir(tmp_path)
    tbl = build(truth)
    t = Table(tbl)
    page = tbl.as_raw_html()
    for c in t.visible():
        if c.kind == "row_group":
            continue
        for cell in c.html:
            if "<svg" not in cell:
                assert cell in page, f"{c.var}: {cell[:80]!r} isn't in the HTML"
        assert t.same_values(c, c, ordered=True), c.var


def test_missing_values_and_nanoplots():
    df = pd.DataFrame({"x": [1.0, None], "s": [[1, 2, 3], [3, 2, 1]]})
    raw = Table(GT(df).fmt_nanoplot("s"))
    assert not raw.no_raw_missing()
    assert raw.nanoplot("s") and not raw.nanoplot("x")
    assert Table(GT(df).sub_missing("x")).no_raw_missing()
