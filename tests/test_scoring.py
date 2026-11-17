"""Tests for L2 (score/data.py), structure (score/structure.py), process metrics
(score/process.py) and the runner. Run like tests/test_intent.py."""

import json
import sys
from functools import partial
from pathlib import Path

import polars as pl
import pytest
from great_tables import GT, vals

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.score import process, runner  # noqa: E402
from harness.score.data import data_check  # noqa: E402
from harness.score.intent import Table  # noqa: E402
from harness.score.structure import signature  # noqa: E402

CARS = pl.DataFrame(
    {
        "car": ["Aston", "Bentley", "Cadillac"],
        "hp": [503.0, 621.0, 420.0],
        "share": [0.25, 0.5, 0.25],
        "trend": [[1, 2], [2, 1], [1, 1]],
    }
)


def test_data_check_matches_columns_by_values():
    truth = Table(GT(CARS.drop("trend"), rowname_col="car").fmt_percent("share"))
    # Renamed, reordered, rescaled and shown at less precision: still the same data
    cand = Table(
        GT(
            CARS.select(
                pl.col("hp").alias("Horsepower"),
                pl.col("car").alias("Model"),
                (pl.col("share") * 100).alias("pct"),
            ).reverse()
        ).fmt_number("Horsepower", decimals=0)
    )
    r = data_check(cand, truth)
    assert r["score"] == 1 and r["matched"] == {"car": "Model", "hp": "Horsepower", "share": "pct"}

    wrong = Table(GT(CARS.with_columns(pl.col("hp") + 1).drop("trend")))
    r = data_check(wrong, truth)
    assert r["unmatched"] == ["hp"] and r["score"] == pytest.approx(2 / 3)
    assert data_check(Table(GT(CARS.head(2))), truth)["score"] == 0


def test_data_check_one_column_per_match_and_data_columns():
    truth = Table(GT(pl.DataFrame({"a": [1, 2], "b": [1, 2]})))
    cand = Table(GT(pl.DataFrame({"x": [1, 2]})))
    assert data_check(cand, truth)["score"] == 0.5
    assert data_check(cand, truth, ["b"])["score"] == 1
    with pytest.raises(ValueError, match="not in the truth"):
        data_check(cand, truth, ["nope"])


def test_data_check_skips_nanoplots():
    truth = Table(GT(CARS).fmt_nanoplot("trend"))
    r = data_check(Table(GT(CARS.drop("trend"))), truth)
    assert r["skipped"] == ["trend"] and r["score"] == 1


def test_signature():
    df = pl.DataFrame({"g": ["a", "a", "b"], "k": ["x", "y", "z"], "v": [1.0, 2.0, 3.0]})
    tbl = (
        GT(df.with_columns(w=pl.col("v")), rowname_col="k", groupname_col="g")
        .tab_header(title="T")
        .tab_spanner("Both", ["v", "w"])
        .fmt_number("v", decimals=1)
        .fmt_integer("v")
        .fmt(lambda x: f"<{x}>", columns="w")
        .grand_summary_rows(fns={"Total": pl.col("v").sum()}, fmt=partial(vals.fmt_number))
    )
    s = signature(tbl)
    assert s["columns"] == ["v", "w"] and s["stub"] == "k" and s["groups"] == "g"
    assert s["spanners"] == [["v", "w"]]
    assert s["formats"] == {"v": "fmt_integer", "w": "fmt"}
    assert s["heading"] == [True, False, 0] and s["summary_rows"] == [[], ["total"]]
    assert signature(GT(CARS).fmt_nanoplot("trend"))["formats"] == {"trend": "nanoplot"}


# Console's output for these errors, as a trial records them
GT_ERRORS = [
    'Traceback (most recent call last):\n  File "<mcp-console:python:e1>", line 3, in <module>\n'
    '  File "/x/site-packages/great_tables/gt.py", line 552, in __getattr__\n'
    "    raise AttributeError(\nAttributeError: 'GT' object has no attribute 'fmt_numbr'. "
    "Did you mean: 'fmt_number'?\n",
    'Traceback (most recent call last):\n  File "<mcp-console:python:e2>", line 1, in <module>\n'
    "TypeError: fmt_number() got an unexpected keyword argument 'decimal'\n",
    'Traceback (most recent call last):\n  File "<mcp-console:python:e3>", line 1, in <module>\n'
    "ImportError: cannot import name 'fmt_thing' from 'great_tables' (/x/__init__.py)\n",
]
OTHER_ERRORS = [
    'Traceback (most recent call last):\n  File "<mcp-console:python:e5>", line 1, in <module>\n'
    "PermissionError: [Errno 1] Operation not permitted: '/x/.env'\n",
    'Traceback (most recent call last):\n  File "<mcp-console:python:e1>", line 1, in <module>\n'
    'polars.exceptions.ColumnNotFoundError: unable to find column "hp"\n',
    'Traceback (most recent call last):\n  File "<mcp-console:python:e1>", line 1, in <module>\n'
    "TypeError: unsupported operand type(s) for +: 'int' and 'str'\n",
]


def test_process_errors():
    for out in GT_ERRORS:
        (e,) = process.errors(out)
        assert e["gt_api"], out
    for out in OTHER_ERRORS:
        (e,) = process.errors(out)
        assert not e["gt_api"], out
    assert process.errors("shape: (6, 7)\n") == []
    assert [e["type"] for e in process.errors("ok\n" + GT_ERRORS[1] + OTHER_ERRORS[0])] == [
        "TypeError",
        "PermissionError",
    ]
    assert process.errors(OTHER_ERRORS[1])[0]["type"] == "ColumnNotFoundError"


def test_process_metrics(tmp_path: Path):
    cells = tmp_path / "workspace/.agents/console/sessions/s1/capture/sessions/001"
    cells.mkdir(parents=True)
    for i, out in enumerate(["fine\n", GT_ERRORS[0], OTHER_ERRORS[0]], start=1):
        (cells / f"cell-{i:03d}.txt").write_text(out)
    (cells / "cell-002-001.png").write_bytes(b"")
    trial = {"tool_calls": 3, "images_returned": 0, "wall_s": 1.0, "cost_usd": 0.01, "error": None}
    (tmp_path / "trial.json").write_text(json.dumps(trial))
    m = process.metrics(tmp_path)
    assert (m["cells"], m["python_errors"], m["gt_api_errors"]) == (3, 2, 1)


def test_runner_scores_a_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    data.mkdir()
    CARS.drop("trend").write_csv(data / "cars.csv")
    truth = tmp_path / "truth.py"
    truth.write_text(
        "import polars as pl\nfrom great_tables import GT\n"
        "gt_tbl = GT(pl.read_csv('data/cars.csv'), rowname_col='car')\n"
    )
    cand = tmp_path / "table.py"
    cand.write_text(
        "import polars as pl\nfrom great_tables import GT\n"
        "df = pl.read_csv('data/cars.csv').sort('hp', descending=True)\n"
        "gt_tbl = GT(df.select('car', 'hp')).fmt_number('hp', decimals=0)\n"
        "gt_tbl.gtsave('elsewhere.png')\n"
    )
    intent = tmp_path / "intent.py"
    intent.write_text(
        "DATA_COLUMNS = ['car', 'hp']\n"
        "def check(t, truth):\n"
        "    t.order('hp', descending=True)\n"
        "    t.stub('car')\n"
    )
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.chdir(tmp_path)
    r = runner.run(cand, out, truth, intent)
    bad = runner.run(tmp_path / "missing.py", out, truth, intent)
    assert r["error"] is None and (out / "table.png").is_file()
    assert not (tmp_path / "elsewhere.png").exists()
    assert r["data"]["score"] == 1 and r["structure"]["formats"] == {"hp": "fmt_number"}
    assert [c["passed"] for c in r["intent"]] == [True, False]
    assert bad["error"] and bad["data"] is None and bad["intent"] is None


def _score(l0: bool, l2: float, structure: dict | None, gt_errors: int = 0) -> dict:
    return {
        "l0": {"passed": l0},
        "l1": None,
        "l2": {"score": l2},
        "structure": structure,
        "process": {"gt_api_errors": gt_errors, "cost_usd": 0.02},
    }


def test_summarize():
    from harness import summarize

    a, b = {"stub": "x", "formats": {"v": "fmt_number"}}, {"stub": "x", "formats": {}}
    # 3 pairs: (a, a) agrees on both fields, (a, b) twice on stub only -> (3/3 + 1/3) / 2
    assert summarize.convergence([a, a, b]) == pytest.approx(2 / 3)
    assert summarize.convergence([a, None]) == 0 and summarize.convergence([a]) is None

    def trial(arm: str, prompt: str, l2: float, errors: int = 0) -> dict:
        return {"trial": {"arm": arm, "prompt_id": prompt}, "score": _score(True, l2, a, errors)}

    trials = [
        trial("baseline", "p1", 0.5, errors=1),
        trial("baseline", "p1", 1.0),
        trial("baseline", "p2", 0.0),
        trial("rich", "p1", 1.0),
        trial("rich", "p2", 1.0),
    ]
    s = summarize.summarize(trials)
    # Prompts weigh equally: baseline is mean(0.75, 0.0)
    assert s["baseline"]["l2"]["mean"] == pytest.approx(0.375)
    assert s["baseline"]["gt_api"]["mean"] == pytest.approx(0.25)
    assert s["rich"]["l2"]["vs_baseline"]["mean"] == pytest.approx(0.625)
    assert s["baseline"]["convergence"]["mean"] == 1 and s["rich"]["convergence"]["prompts"] == 0
