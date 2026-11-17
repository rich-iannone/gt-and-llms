"""Tests for the judge's offline parts (harness/judge.py), calibration (harness/calibrate.py)
and the judge's place in harness/summarize.py. No model is called. They need the harness
environment, which has chatlas:

    uv run --with pytest pytest tests/test_judge.py
"""

import json
import random
import sys
from pathlib import Path

import pytest

pytest.importorskip("chatlas")
from PIL import Image, ImageDraw  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import calibrate, corpus, judge, summarize  # noqa: E402


def test_data_summary_describes_each_column():
    item = corpus.load("api_latency")
    text = judge.data_summary(item)
    for name in item.data:
        assert f"`{name}`:" in text
    assert "rows," in text and "columns" in text
    assert any(kind in text for kind in ("(number)", "(text)", "(date)"))


def test_kind():
    assert judge._kind([]) == "empty"
    assert judge._kind(["1", "2.5", "-3e2"]) == "number"
    assert judge._kind(["2024-01-01", "2024-02-01 10:30"]) == "date"
    assert judge._kind(["a", "1"]) == "text"


def _striped(path: Path, w: int, h: int, line: int = 40) -> Path:
    """White with a black band of text-like noise every `line` px and blank rows between."""
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    for top in range(0, h, line):
        for x in range(0, w, 7):
            draw.rectangle((x, top + 5, x + 3, top + 30), fill="black")
    img.save(path)
    return path


def test_split_render_keeps_small_renders_whole(tmp_path):
    png = _striped(tmp_path / "small.png", 800, 600)
    assert judge.split_render(png, tmp_path / "parts") == [png]
    assert not (tmp_path / "parts").exists()


def test_split_render_cuts_tall_renders_between_lines(tmp_path):
    png = _striped(tmp_path / "tall.png", 1000, 5000)
    parts = judge.split_render(png, tmp_path / "parts")
    assert len(parts) > 1
    heights = [Image.open(p).height for p in parts]
    assert sum(heights) == 5000
    for p in parts:
        img = Image.open(p)
        assert img.width == 1000 and img.width * img.height <= judge.MAX_PIXELS
        # Each cut falls in a blank gap: the part's last row is white
        assert (
            img.crop((0, img.height - 1, img.width, img.height)).getextrema() == ((255, 255),) * 3
        )
    # Splitting again replaces the parts rather than adding to them
    assert judge.split_render(png, tmp_path / "parts") == parts
    assert len(list((tmp_path / "parts").glob("part-*.png"))) == len(parts)


def test_result_and_pair_record():
    assert judge.result("A", "A") == "win" and judge.result("A", "B") == "loss"
    assert judge.result("tie", "B") == "tie"
    path = judge.pair_record(Path("runs/x"), "rich", "baseline", Path("api_latency/r2"))
    assert path == Path("runs/x/pairwise/rich-vs-baseline/api_latency/r2.json")


def test_spearman():
    assert calibrate._ranks([3, 1, 1, 2]) == [4, 1.5, 1.5, 3]
    assert calibrate.spearman([1, 2, 3], [2, 4, 6]) == pytest.approx(1)
    assert calibrate.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
    assert calibrate.spearman([1, 1, 1], [1, 2, 3]) is None
    assert calibrate.spearman([1], [1]) is None


def test_draw_takes_strata_in_turn():
    units = [("a", "easy", i) for i in range(10)] + [("b", "hard", i + 100) for i in range(2)]
    picked = calibrate.draw(units, 4, random.Random(0))
    assert len(picked) == 4
    # Both of the small stratum's units are taken before the big one is used up
    assert sum(u >= 100 for u in picked) == 2
    assert len(calibrate.draw(units, 50, random.Random(0))) == 12


def test_agree_pairwise_counts_each_order(tmp_path, monkeypatch):
    monkeypatch.setattr(calibrate, "REPO", tmp_path)
    (tmp_path / "rec.json").write_text(json.dumps({"results": ["win", "tie"]}))
    (tmp_path / "ratings.csv").write_text("id,verdict,notes\n01,B,\n02,,\n03,A,\n")
    key = {
        # The arm's table was B and the human chose B: a win, matching one of two orders
        "01": {"arm_side": "B", "judged": "rec.json"},
        "02": {"arm_side": "A", "judged": "rec.json"},
        "03": {"arm_side": "A", "judged": "missing.json"},
    }
    out = calibrate.agree_pairwise(tmp_path, key)
    assert out == {"rated": 1, "not_judged": ["03"], "agreement": 0.5}


def test_summarize_judge_metric():
    score = {
        "l0": {"passed": True},
        "l1": None,
        "l2": None,
        "structure": None,
        "process": {"gt_api_errors": 0, "cost_usd": 0.02},
    }
    assert summarize.trial_metrics(score)["judge"] is None
    assert summarize.trial_metrics(score, {"grades": {"x": 1}, "mean": 4.2})["judge"] == 4.2
    # No render, so no grades: the worst score
    assert summarize.trial_metrics(score, {"grades": None, "mean": None})["judge"] == 1.0


def test_summarize_pairwise(tmp_path):
    comp = tmp_path / "pairwise/rich-vs-baseline"
    records = {"p1/r1": (1.0, True), "p1/r2": (0.5, False), "p2/r1": (0.0, None)}
    for rel, (arm_score, consistent) in records.items():
        rec = {"arm_score": arm_score, "instructions_sha256": "h"}
        if consistent is not None:
            rec["consistent"] = consistent
        (comp / rel).parent.mkdir(parents=True, exist_ok=True)
        (comp / f"{rel}.json").write_text(json.dumps(rec))
    row = summarize.pairwise(tmp_path, None)["rich-vs-baseline"]
    # Prompts weigh equally: mean(0.75, 0.0)
    assert row["mean"] == pytest.approx(0.375) and row["prompts"] == 2 and row["pairs"] == 3
    # The pair decided by a missing render isn't counted for consistency
    assert row["consistent"] == pytest.approx(0.5) and row["instructions"] == 1
