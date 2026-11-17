"""Assertions for a corpus item's intent.py: L1 of the scoring (plan §6).

An intent.py defines `check(t, truth)`. `t` is the candidate table and `truth` is the item's
truth.py table, both as `Table` views of a built GT. Each assertion on `t` records a pass or
a fail and returns it; nothing raises, so one failure doesn't hide the rest. For example:

    from harness.score.intent import INTEGER

    def check(t, truth):
        t.title("dashboard")
        t.row_count(6)
        t.stub("endpoint")
        t.order("p99_ms", descending=True)
        t.formatted(["avg_ms", "p95_ms", "p99_ms", "requests", "errors"], INTEGER)
        t.filled(t.col("p99_ms").num > 1000, color="red", light=True)

Columns are named as a string, a `Column`, or a list of either. A string matches a data
column's name, then a column label, ignoring case. When the prompt doesn't fix the names,
find the column by its values instead: `t.col(like=truth.col("msrp"))` is whichever of the
candidate's columns holds the same values as the truth's msrp column (any row order, any of
the usual scalings, and the shown text if the data holds strings).

Everything is read from the GT object and its built cell text: what the table shows, not
how the code got there. A column that isn't found is a `Column` with `found=False`; checks
on it fail with "not found", and its values are all NaN, so masks built from it select
no rows.
"""

import html as html_lib
import math
import re
import runpy
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import great_tables as gt
import numpy as np
import pandas as pd
from great_tables._data_color.constants import COLOR_NAME_TO_HEX
from great_tables._tbl_data import _get_cell, cast_frame_to_string, replace_null_frame

# ---- Text ------------------------------------------------------------------------------


def plain(x: Any) -> str:
    """Text without markup: GT Text objects, HTML tags and entities, extra whitespace."""
    if x is None:
        return ""
    x = getattr(x, "text", x)
    s = re.sub(r"<[^>]+>", " ", str(x))
    return re.sub(r"\s+", " ", html_lib.unescape(s)).strip()


def _norm(x: Any) -> str:
    return plain(x).casefold()


_MISSING_TEXT = {"nan", "none", "<na>", "null", "nat", "na"}
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9, "t": 1e12}
_NUM_RE = re.compile(r"^\(?([+-]?)(\d[\d,.]*|[.,]\d+)\)?\s*(k|m|bn|b|t)?\s*(%)?$", re.I)


def _clean(text: str) -> str:
    """A cell's text reduced to what _NUM_RE reads: no markup, symbols or spaces, and only
    the value of a merged "value ± uncertainty"."""
    s = re.split(r"±|\+/-", plain(text))[0]
    s = s.replace("\N{MINUS SIGN}", "-").replace("\N{EN DASH}", "-")
    return re.sub(r"[$€£¥₹\s\N{NO-BREAK SPACE}\N{NARROW NO-BREAK SPACE}]|USD|EUR|GBP", "", s)


def decimal_mark(texts: Sequence[str]) -> str:
    """The decimal mark: a comma if any of the texts unambiguously uses one ("5.550,00",
    "0,11", "1.234.567"), else a period. Read per column, so German "1.234" isn't 1.234."""
    for t in texts:
        m = _NUM_RE.match(_clean(t))
        if not m:
            continue
        d = m.group(2)
        if "," in d and "." in d:
            if d.rfind(",") > d.rfind("."):
                return ","
        elif d.count(".") > 1 or (d.count(",") == 1 and len(d.split(",")[1]) != 3):
            return ","
    return "."


def parse_number(text: str, dec: str = ".") -> tuple[float, float] | None:
    """A shown number and the half-unit of its last digit (its rounding tolerance), or None.

    Understands currency symbols, separators, a unicode minus, accounting parentheses,
    a % sign, K/M/B/T suffixes, and the value of a merged "value ± uncertainty":
    "$1,234.5" -> (1234.5, 0.05); "23.5K" -> (23500, 50). `dec` is the decimal mark; the
    other of "," and "." is then the group separator."""
    s = _clean(text)
    m = _NUM_RE.match(s)
    if not m:
        return None
    sign, digits, suffix, _pct = m.groups()
    digits = digits.replace("." if dec == "," else ",", "")
    if digits.count(dec) > 1 or not digits.strip(dec):
        return None
    value = float(digits.replace(dec, "."))
    decimals = len(digits.split(dec)[1]) if dec in digits else 0
    scale = _SUFFIX[suffix.lower()] if suffix else 1.0
    negative = sign == "-" or s.startswith("(")
    return (-value if negative else value) * scale, 0.5 * 10**-decimals * scale


# ---- Colors ----------------------------------------------------------------------------


def parse_color(css: str | None) -> tuple[float, float, float] | None:
    """A CSS color (hex, name, rgb()/rgba()) as RGB in 0-1, or None."""
    if not css:
        return None
    c = css.strip().lower()
    c = COLOR_NAME_TO_HEX.get(c, c)
    if m := re.fullmatch(r"#([0-9a-f]{3,8})", c.lower()):
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h[:3])
        return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    if m := re.fullmatch(r"rgba?\(([^)]*)\)", c):
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        try:
            return tuple(
                float(p[:-1]) / 100 if p.endswith("%") else float(p) / 255 for p in parts[:3]
            )
        except ValueError:
            return None
    return None


def _hsl(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    hi, lo = max(rgb), min(rgb)
    lum = (hi + lo) / 2
    if hi == lo:
        return 0.0, 0.0, lum
    d = hi - lo
    sat = d / (2 - hi - lo) if lum > 0.5 else d / (hi + lo)
    if hi == r:
        hue = ((g - b) / d) % 6
    elif hi == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return hue * 60, sat, lum


def luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG relative luminance: 0 is black, 1 is white."""

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# Hue ranges in degrees; "gray" is low saturation instead
_HUES = {
    "red": [(0, 15), (345, 360)],
    "orange": [(15, 45)],
    "yellow": [(45, 70)],
    "green": [(70, 170)],
    "cyan": [(170, 200)],
    "blue": [(200, 260)],
    "purple": [(260, 300)],
    "pink": [(300, 345)],
}


def color_is(css: str | None, family: str | None = None, light: bool | None = None) -> bool:
    """Whether a CSS color is in a color family ("red", "gray", ...) and, if `light` is
    given, light (HSL lightness >= 0.7) or not. Families are broad on purpose: a prompt's
    "light red" accepts any pale red, pink-red or salmon."""
    rgb = parse_color(css)
    if rgb is None:
        return False
    hue, sat, lum = _hsl(rgb)
    if light is not None and (lum >= 0.7) != light:
        return False
    if family is None:
        return True
    if family in ("gray", "grey"):
        return sat < 0.15 or (lum > 0.97 or lum < 0.05)
    if family == "white":
        return lum > 0.95
    if sat < 0.15:
        return False
    return any(lo <= hue < hi for lo, hi in _HUES[family])


# ---- Formats (regexes over a cell's shown text) ---------------------------------------

_MINUS = "[-\N{MINUS SIGN}]?"
_SIGN = "[-+\N{MINUS SIGN}]?"


def _num(decimals: int | None, sep: str, dec: str) -> str:
    """Digits grouped by `sep` in threes, then `decimals` digits after `dec` (any number of
    them if None, none if 0)."""
    s, d = re.escape(sep), re.escape(dec)
    grouped = rf"\d{{1,3}}(?:{s}\d{{3}})*"
    if decimals is None:
        return rf"{grouped}(?:{d}\d+)?"
    return rf"{grouped}{d}\d{{{decimals}}}" if decimals else grouped


def currency(decimals: int | None = None, symbol: str = "$", sep: str = ",", dec: str = ".") -> str:
    """Currency with separators: $1,234 or $1,234.56 (and -$5, $-5, ($5)), or with the
    symbol after: 1.234,56 € (with sep=".", dec=",")."""
    s = re.escape(symbol)
    num = _num(decimals, sep, dec)
    return rf"(?:{_MINUS}{s}{_MINUS}{num}|\({s}{num}\)|{_MINUS}{num}\s?{s})"


def percent(decimals: int | None = None, sep: str = ",", dec: str = ".") -> str:
    """A percentage: 12%, 12.5%, -3.0%, +4.1%."""
    return rf"{_SIGN}{_num(decimals, sep, dec)}\s?%"


def number(decimals: int | None = None, sep: str = ",", dec: str = ".") -> str:
    """A number with separators: 1,234.5, or 1.234,5 with sep=".", dec=","."""
    return rf"{_SIGN}{_num(decimals, sep, dec)}"


def compact(decimals: int | None = None) -> str:
    """A number with a K/M/B suffix where it's large enough: 950, 1.8K, 23.5K, 2.1M."""
    frac = r"(?:\.\d+)?" if decimals is None else (rf"\.\d{{{decimals}}}" if decimals else "")
    return rf"{_SIGN}\$?(?:\d{{1,3}}{frac}\s?[KMBT]|\d{{1,3}}(?:\.\d+)?)"


INTEGER = number(0)
CURRENCY = currency()
PERCENT = percent()


# ---- The table view ------------------------------------------------------------------


@dataclass
class Result:
    check: str
    passed: bool
    detail: str = ""


@dataclass
class Column:
    """One column, with its values in display order."""

    var: str
    label: str = ""
    kind: str = "default"  # default, stub, row_group, hidden
    raw: list[Any] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    html: list[str] = field(default_factory=list)
    found: bool = True

    def __repr__(self) -> str:
        return f"Column({self.var!r})" if self.found else f"Column({self.var!r}, not found)"

    @property
    def num(self) -> np.ndarray:
        """Values as floats: the data if it's numeric, else parsed from the shown text.
        NaN where there's no number."""
        out, dec = [], self.decimal_mark
        for raw, text in zip(self.raw, self.text, strict=True):
            if isinstance(raw, int | float | np.number) and not isinstance(raw, bool):
                out.append(float(raw))
            else:
                parsed = parse_number(text, dec)
                out.append(parsed[0] if parsed else math.nan)
        return np.array(out, dtype=float)

    @property
    def decimal_mark(self) -> str:
        """The decimal mark the shown text uses: "," for a table in, say, German."""
        return decimal_mark(self.text)

    @property
    def is_missing(self) -> np.ndarray:
        return np.array([_is_missing(v) for v in self.raw], dtype=bool)


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _to_pandas(df: Any) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else df.to_pandas()


def _inline_css(cell_html: str) -> dict[str, str]:
    """CSS properties set inline in a cell's own HTML, for tables styled that way."""
    props = {}
    for decl in re.findall(r'style="([^"]*)"', cell_html or ""):
        for part in decl.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                props[k.strip().lower()] = v.strip()
    return props


class Table:
    """A read-only view of a GT for assertions. `results` collects what each check found."""

    def __init__(self, tbl: gt.GT, name: str = "table"):
        self.gt = tbl
        self.name = name
        self.results: list[Result] = []

        data = _to_pandas(tbl._tbl_data)
        built = tbl._build_data("html")
        # As the HTML renderer does: unformatted cells show the data cast to strings
        body = replace_null_frame(built._body.body, cast_frame_to_string(built._tbl_data))

        groups = [g for g in built._stub.group_rows if g.group_id is not None]
        self.order_idx = (
            [int(i) for g in groups for i in g.indices] if groups else list(range(len(data)))
        )
        self.group_ids = [tbl._stub.rows[i].group_id for i in self.order_idx] if groups else []
        self.group_labels = {g.group_id: plain(g.group_label or g.group_id) for g in groups}
        self.n_rows = len(self.order_idx)

        self.columns: list[Column] = []
        for info in tbl._boxhead:
            if info.var not in data.columns:
                continue
            # The renderer shows str() of each cell, so an unhandled missing value reads "None"
            cells = [str(_get_cell(body, i, info.var)) for i in self.order_idx]
            self.columns.append(
                Column(
                    var=info.var,
                    label=plain(info.column_label),
                    kind=info.type.name,
                    raw=[data[info.var].iloc[i] for i in self.order_idx],
                    text=[plain(c) for c in cells],
                    html=cells,
                )
            )
        self.spanners = [
            {"label": plain(s.spanner_label), "vars": list(s.vars), "level": s.spanner_level}
            for s in tbl._spanners
        ]
        self.title_text = plain(tbl._heading.title)
        self.subtitle_text = plain(tbl._heading.subtitle)
        self.source_notes = [plain(n) for n in tbl._source_notes]

        # Styles per displayed cell: {(display row, var or "<stub>"): [CellStyle...]}
        pos = {data_i: d for d, data_i in enumerate(self.order_idx)}
        self._cell_styles: dict[tuple[int, str], list[Any]] = {}
        for s in tbl._styles:
            kind = type(s.locname).__name__
            if s.rownum is None or s.rownum not in pos:
                continue
            if kind == "LocBody" and s.colname:
                key = (pos[s.rownum], s.colname)
            elif kind == "LocStub":
                key = (pos[s.rownum], "<stub>")
            else:
                continue
            self._cell_styles.setdefault(key, []).extend(s.styles)

    # ---- Lookups (these don't record results) ----

    def col(self, *names: str, like: Column | None = None) -> Column:
        """A column by data name or label (ignoring case), or by values `like` another
        table's column. The first match wins; `found=False` if nothing matches."""
        for name in names:
            for c in self.columns:
                if c.var == name:
                    return c
            for c in self.columns:
                if c.var.casefold() == name.casefold() or c.label.casefold() == name.casefold():
                    return c
        if like is not None and like.found:
            for c in self.visible():
                if values_match(c, like):
                    return c
        want = names[0] if names else f"like {like.var}" if like else "?"
        return Column(
            var=want,
            raw=[None] * self.n_rows,
            text=[""] * self.n_rows,
            html=[""] * self.n_rows,
            found=False,
        )

    def visible(self) -> list[Column]:
        return [c for c in self.columns if c.kind != "hidden"]

    @property
    def stub_col(self) -> Column | None:
        return next((c for c in self.columns if c.kind == "stub"), None)

    def fill(self, row: int, var: str) -> str | None:
        """The background color of a displayed cell, or None. `var` "<stub>" is the stub."""
        color = None
        for st in self._cell_styles.get((row, var), []):
            if type(st).__name__ == "CellStyleFill":
                color = st.color
        if color is None and var != "<stub>":
            css = _inline_css(self._col_html(row, var))
            color = css.get("background-color") or css.get("background")
        return color

    def text_style(self, row: int, var: str) -> dict[str, str]:
        """Text properties set on a displayed cell: color, size, weight, style, ..."""
        props = {}
        for st in self._cell_styles.get((row, var), []):
            if type(st).__name__ == "CellStyleText":
                props.update({k: v for k, v in vars(st).items() if v is not None})
        css = _inline_css(self._col_html(row, var))
        for k in ("color", "font-size", "font-weight", "font-style"):
            if k in css:
                props.setdefault(k.removeprefix("font-"), css[k])
        return props

    def _col_html(self, row: int, var: str) -> str:
        c = self.col(var)
        return c.html[row] if c.found else ""

    # ---- Recording ----

    def _record(self, check: str, passed: bool, detail: str = "") -> bool:
        self.results.append(Result(check, bool(passed), detail))
        return bool(passed)

    def _resolve(self, cols: str | Column | Sequence[str | Column]) -> list[Column]:
        items = [cols] if isinstance(cols, str | Column) else list(cols)
        return [c if isinstance(c, Column) else self.col(c) for c in items]

    def _missing(self, check: str, cols: list[Column]) -> bool:
        lost = [c.var for c in cols if not c.found]
        if lost:
            self._record(check, False, f"not found: {', '.join(lost)}")
        return bool(lost)

    # ---- Heading and notes ----

    def title(self, pattern: str | None = None) -> bool:
        """A title, matching `pattern` (case-insensitive regex search) if given."""
        return self._text_check("title", self.title_text, pattern)

    def subtitle(self, pattern: str | None = None) -> bool:
        return self._text_check("subtitle", self.subtitle_text, pattern)

    def source_note(self, pattern: str | None = None) -> bool:
        """At least one source note, one of them matching `pattern` if given."""
        notes = self.source_notes
        ok = any(re.search(pattern, n, re.I) for n in notes) if pattern else bool(notes)
        return self._record(f"source note {pattern or ''}".strip(), ok, f"notes: {notes}")

    def _text_check(self, what: str, text: str, pattern: str | None) -> bool:
        ok = bool(re.search(pattern, text, re.I)) if pattern else bool(text)
        return self._record(f"{what} {pattern or ''}".strip(), ok, f"{what}: {text!r}")

    # ---- Rows and columns ----

    def row_count(self, n: int | tuple[int, int]) -> bool:
        """Exactly n body rows, or between lo and hi for a (lo, hi) pair."""
        lo, hi = (n, n) if isinstance(n, int) else n
        return self._record(f"row count {n}", lo <= self.n_rows <= hi, f"{self.n_rows} rows")

    def has_columns(self, *cols: str | Column) -> bool:
        """Each column is shown (as a column, the stub, or row groups)."""
        resolved = self._resolve(list(cols))
        if self._missing("has columns", resolved):
            return False
        hidden = [c.var for c in resolved if c.kind == "hidden"]
        return self._record("has columns", not hidden, f"hidden: {hidden}" if hidden else "")

    def same_values(
        self, col: str | Column, expected: Column | Sequence[Any], ordered: bool = False
    ) -> bool:
        """A column holds the expected values (e.g. `truth.col("car")`), in display order
        if `ordered`. Numbers match within rounding; text ignores case and markup."""
        (c,) = self._resolve(col)
        check = f"values of {c.var}"
        if self._missing(check, [c]):
            return False
        exp = expected if isinstance(expected, Column) else _as_column(expected)
        detail = f"{len(c.raw)} shown vs {len(exp.raw)} expected; shown: {c.text[:12]}"
        return self._record(check, values_match(c, exp, ordered), detail)

    def stub(self, col: str | Column) -> bool:
        """The column is the stub (row labels)."""
        (c,) = self._resolve(col)
        if self._missing("stub", [c]):
            return False
        stub = self.stub_col
        return self._record(f"stub is {c.var}", c.kind == "stub", f"stub: {stub and stub.var}")

    def grouped_by(self, col: str | Column) -> bool:
        """Row groups split the rows exactly as the column's values do (group labels and
        order are free)."""
        (c,) = self._resolve(col)
        check = f"grouped by {c.var}"
        if self._missing(check, [c]):
            return False
        if not self.group_ids:
            return self._record(check, False, "no row groups")
        by_value: dict[str, set[int]] = {}
        by_group: dict[Any, set[int]] = {}
        for i, (v, g) in enumerate(zip(c.raw, self.group_ids, strict=True)):
            by_value.setdefault(_norm(v), set()).add(i)
            by_group.setdefault(g, set()).add(i)
        same = sorted(map(sorted, by_value.values())) == sorted(map(sorted, by_group.values()))
        return self._record(check, same, f"groups: {list(self.group_labels.values())}")

    def order(
        self, col: str | Column, descending: bool = False, within_groups: bool = False
    ) -> bool:
        """Rows are sorted by the column (ties in any order), across the whole table or,
        with `within_groups`, inside each row group."""
        (c,) = self._resolve(col)
        check = f"sorted by {c.var}{' desc' if descending else ''}"
        if self._missing(check, [c]):
            return False
        nums = c.num
        numeric = not np.isnan(nums).all()
        keys = list(nums) if numeric else [_norm(t) for t in c.text]
        segments = (
            [[i for i, g in enumerate(self.group_ids) if g == gid] for gid in self.group_labels]
            if within_groups and self.group_ids
            else [list(range(self.n_rows))]
        )
        for seg in segments:
            # Rows without a value (missing, or not a number) can sit anywhere
            vals = [keys[i] for i in seg if not (numeric and np.isnan(keys[i]))]
            if vals != sorted(vals, reverse=descending):
                return self._record(check, False, f"order: {[c.text[i] for i in seg][:12]}")
        return self._record(check, True)

    def spanner(
        self, over: Sequence[str | Column], label: str | None = None, exact: bool = False
    ) -> bool:
        """A spanner over these columns (and maybe others; only these if `exact`), with a
        label matching `label` (case-insensitive regex search) if given."""
        cols = self._resolve(list(over))
        check = f"spanner over {[c.var for c in cols]}"
        if self._missing(check, cols):
            return False
        want = {c.var for c in cols}
        for s in self.spanners:
            got = set(s["vars"])
            if (got == want if exact else want <= got) and (
                label is None or re.search(label, s["label"], re.I)
            ):
                return self._record(check, True, f"spanner {s['label']!r}")
        found = [(s["label"], s["vars"]) for s in self.spanners]
        return self._record(check, False, f"spanners: {found}")

    def summary_row(self, label: str | None = None, grand: bool | None = None) -> bool:
        """A summary row (grand if `grand`, per-group if `grand` is False), its label
        matching `label` if given."""
        rows = []
        if grand is not False:
            rows += self.gt._summary_rows_grand._d.get("grand", [])
        if grand is not True:
            for v in self.gt._summary_rows._d.values():
                rows += v
        labels = [plain(r.label) for r in rows]
        ok = any(re.search(label, lab, re.I) for lab in labels) if label else bool(rows)
        return self._record(f"summary row {label or ''}".strip(), ok, f"labels: {labels}")

    # ---- Cell text ----

    def formatted(
        self, cols: str | Column | Sequence[str | Column], pattern: str, rows: Any = None
    ) -> bool:
        """Every non-missing shown cell in the columns fully matches the regex `pattern`
        (see currency(), percent(), number(), compact()). `rows` is a boolean mask."""
        resolved = self._resolve(cols)
        check = f"format of {[c.var for c in resolved]}"
        if self._missing(check, resolved):
            return False
        mask = _mask(rows, self.n_rows)
        bad = [
            (c.var, t)
            for c in resolved
            for i, (t, miss) in enumerate(zip(c.text, c.is_missing, strict=True))
            if mask[i] and not miss and not re.fullmatch(pattern, t)
        ]
        return self._record(check, not bad, f"unmatched: {bad[:6]}" if bad else "")

    def no_raw_missing(self) -> bool:
        """No shown cell reads like a raw missing value (nan, None, <NA>, null, NaT)."""
        bad = [(c.var, t) for c in self.visible() for t in c.text if t.casefold() in _MISSING_TEXT]
        return self._record("no raw missing values", not bad, f"cells: {bad[:6]}" if bad else "")

    def nanoplot(self, col: str | Column) -> bool:
        """Every cell in the column holds an inline SVG plot."""
        (c,) = self._resolve(col)
        check = f"nanoplot in {c.var}"
        if self._missing(check, [c]):
            return False
        ok = all("<svg" in h for h in c.html)
        return self._record(check, ok)

    # ---- Styling ----

    def filled(
        self,
        rows: Any,
        cols: str | Column | Sequence[str | Column] | None = None,
        color: str | None = None,
        light: bool | None = None,
        stub: bool = True,
    ) -> bool:
        """Cells in the masked rows have a background in the color family (see color_is),
        and cells in other rows don't. `cols` defaults to the whole row, and `stub` counts
        the stub cell as part of the row."""
        mask = _mask(rows, self.n_rows)
        targets = self._resolve(cols) if cols is not None else self.visible()
        check = f"fill {color or 'any'} on {int(mask.sum())} rows"
        if self._missing(check, targets):
            return False
        vars_ = ["<stub>" if c.kind == "stub" else c.var for c in targets]
        vars_ = [v for v, c in zip(vars_, targets, strict=True) if c.kind in ("default", "stub")]
        if cols is None and not stub:
            vars_ = [v for v in vars_ if v != "<stub>"]

        def hit(r: int, v: str) -> bool:
            f = self.fill(r, v)
            return f is not None and color_is(f, color, light)

        missed = [(r, v) for r in range(self.n_rows) if mask[r] for v in vars_ if not hit(r, v)]
        # Another row counts only if it's filled the same way across all the target cells,
        # so a color scale on one column doesn't read as highlighting
        extra = [r for r in range(self.n_rows) if not mask[r] and all(hit(r, v) for v in vars_)]
        detail = []
        if missed:
            detail.append(f"unfilled (row, column) in selected rows: {missed[:6]}")
        if extra:
            detail.append(f"other rows filled the same way: {extra[:6]}")
        return self._record(check, not missed and not extra, "; ".join(detail))

    def gradient(self, col: str | Column, darker: str = "higher", color: str | None = None) -> bool:
        """Every cell in the column has a fill, darker for higher values (or "lower"), in
        the color family if given (the lightest end may be white or gray)."""
        (c,) = self._resolve(col)
        check = f"gradient on {c.var}, {darker} darker"
        if self._missing(check, [c]):
            return False
        fills = [self.fill(r, c.var) for r in range(self.n_rows)]
        rgbs = [parse_color(f) for f in fills]
        if any(rgb is None for rgb in rgbs):
            return self._record(check, False, f"cells without a fill: {fills.count(None)}")
        lum = [luminance(rgb) for rgb in rgbs]
        pairs = sorted(zip(c.num, lum, strict=True), key=lambda p: p[0])
        seq = [lu for _, lu in pairs]
        if darker == "lower":
            seq = seq[::-1]
        monotone = all(b <= a + 1e-9 for a, b in zip(seq, seq[1:], strict=False))
        varied = max(seq) - min(seq) > 0.05
        hue_ok = color is None or any(color_is(f, color) for f in fills if not color_is(f, "gray"))
        ok = monotone and varied and hue_ok
        return self._record(check, ok, f"fills: {fills[:8]}")

    def text_styled(
        self,
        col: str | Column,
        size: str | None = None,
        color: str | None = None,
        weight: str | None = None,
        rows: Any = None,
    ) -> bool:
        """Body cells in the column have the text style. `size="smaller"` accepts any
        reduction from the default; `color` is a color family; `weight` e.g. "bold"."""
        (c,) = self._resolve(col)
        check = f"text style on {c.var}"
        if self._missing(check, [c]):
            return False
        mask = _mask(rows, self.n_rows)
        var = "<stub>" if c.kind == "stub" else c.var
        bad = []
        for r in range(self.n_rows):
            if not mask[r]:
                continue
            props = self.text_style(r, var)
            if size == "smaller" and not _is_smaller(props.get("size")):
                bad.append((r, "size", props.get("size")))
            elif size not in (None, "smaller") and props.get("size") != size:
                bad.append((r, "size", props.get("size")))
            if color and not color_is(props.get("color"), color):
                bad.append((r, "color", props.get("color")))
            if weight and str(props.get("weight", "")).lower() not in _WEIGHTS[weight]:
                bad.append((r, "weight", props.get("weight")))
        return self._record(check, not bad, f"cells: {bad[:6]}" if bad else "")


_WEIGHTS = {"bold": {"bold", "bolder", "600", "700", "800", "900"}, "normal": {"normal", "400"}}


def _is_smaller(size: str | None) -> bool:
    if not size:
        return False
    s = str(size).strip().lower()
    if s in ("smaller", "small", "x-small", "xx-small"):
        return True
    m = re.fullmatch(r"([\d.]+)\s*(px|em|rem|%|pt)", s)
    if not m:
        return False
    v, unit = float(m.group(1)), m.group(2)
    return {"px": v < 16, "em": v < 1, "rem": v < 1, "%": v < 100, "pt": v < 12}[unit]


def _mask(rows: Any, n: int) -> np.ndarray:
    if rows is None:
        return np.ones(n, dtype=bool)
    if callable(rows):
        rows = [rows(i) for i in range(n)]
    arr = np.asarray(rows)
    if arr.dtype == bool:
        return arr
    out = np.zeros(n, dtype=bool)
    out[arr.astype(int)] = True
    return out


def _as_column(values: Sequence[Any]) -> Column:
    vals = list(values)
    return Column(var="expected", raw=vals, text=[plain(v) for v in vals], html=[])


_SCALES = [1, 100, 0.01, 1e3, 1e-3, 1e6, 1e-6, 1e9, 1e-9]


def values_match(cand: Column, exp: Column, ordered: bool = False) -> bool:
    """Whether a column shows the expected values: numbers at the precision the column
    shows them (at any of the usual scalings, e.g. 0.12 vs 12%), otherwise text ignoring
    case and markup."""
    if len(cand.raw) != len(exp.raw):
        return False
    e = exp.num
    if not np.isnan(e).all():
        return _numbers_match(cand, e, ordered)
    a = [_norm(t) for t in cand.text]
    b = [_norm(t) for t in exp.text]
    return a == b if ordered else sorted(a) == sorted(b)


def _numbers_match(cand: Column, expected: np.ndarray, ordered: bool) -> bool:
    # Each candidate number with its tolerance: the shown number at the precision shown,
    # else the data's number, tightly
    vals, tols, dec = [], [], cand.decimal_mark
    for raw, text in zip(cand.raw, cand.text, strict=True):
        if parsed := parse_number(text, dec):
            vals.append(parsed[0])
            tols.append(parsed[1])
        elif isinstance(raw, int | float | np.number) and not isinstance(raw, bool):
            vals.append(float(raw))
            tols.append(1e-9)
        else:
            vals.append(math.nan)
            tols.append(0.0)
    v, tol = np.array(vals), np.array(tols)
    for scale in _SCALES:
        x = expected * scale
        if ordered:
            cv, ct, cx = v, tol, x
        else:
            ia, ib = np.argsort(v, kind="stable"), np.argsort(x, kind="stable")
            cv, ct, cx = v[ia], tol[ia], x[ib]
        both_nan = np.isnan(cv) & np.isnan(cx)
        close = np.abs(cv - cx) <= ct + 1e-6 * np.abs(cx) + 1e-12
        if np.all(both_nan | close):
            return True
    return False


# ---- Running an intent.py ------------------------------------------------------------


def run_intent(intent_path: Path, candidate: gt.GT, truth: gt.GT) -> list[dict]:
    """Run an intent.py's check(t, truth) and return its results. An exception in the
    intent file is recorded as a failing result, after the results recorded so far."""
    check: Callable = runpy.run_path(str(intent_path))["check"]
    t, ref = Table(candidate, "candidate"), Table(truth, "truth")
    try:
        check(t, ref)
    except Exception as e:  # noqa: BLE001 - recorded as a result
        t._record("intent.py raised", False, f"{type(e).__name__}: {e}")
    return [r.__dict__ for r in t.results]
