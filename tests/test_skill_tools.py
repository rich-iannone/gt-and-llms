"""Tests for the skill tooling: harness/freeze_skill.py, harness/check_skill.py (which needs GT,
so those tests skip outside the agent's environment) and harness/api_errors.py.

    VIRTUAL_ENV= uv run --project console/agent-env --with pytest pytest tests/test_skill_tools.py
"""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import REPO, api_errors, freeze_skill  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def source(tmp_path):
    repo = tmp_path / "great-tables"
    skill = repo / "skills/great-tables"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: great-tables\n---\nBody\n")
    (skill / "references/api.md").write_text("API\n")
    (repo / "README.md").write_text("not part of the skill\n")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=R", "-c", "user.email=r@x", "add", ".")
    _git(repo, "-c", "user.name=R", "-c", "user.email=r@x", "commit", "-qm", "skill")
    # Uncommitted edits are never frozen
    (skill / "SKILL.md").write_text("edited\n")
    (skill / "scratch.md").write_text("untracked\n")
    return repo


def test_tree_sha256_matches_the_recorded_prose_hash():
    # PROVENANCE.md's prose row was hashed the way harness/arms.py hashes a skill
    tree = freeze_skill.tree_sha256(REPO / "arms/prose/skill")
    assert tree in (REPO / "PROVENANCE.md").read_text()


def test_freeze(source, tmp_path, monkeypatch, capsys):
    dest, prov = tmp_path / "arms/rich/skill", tmp_path / "PROVENANCE.md"
    prov.write_text("| Arm | ... |\n|---|---|\n| rich | not yet frozen | Rich Iannone | | |\n")
    monkeypatch.setattr(freeze_skill, "DEST", dest)
    monkeypatch.setattr(freeze_skill, "PROVENANCE", prov)
    monkeypatch.setattr(freeze_skill, "REPO", tmp_path)
    sha = _git(source, "rev-parse", "HEAD")
    monkeypatch.setattr(sys, "argv", ["freeze_skill", str(source), "--rev", sha[:7]])
    freeze_skill.main()

    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert files == ["SKILL.md", "references/api.md"]
    assert (dest / "SKILL.md").read_text().endswith("Body\n")
    tree = freeze_skill.tree_sha256(dest)
    row = [line for line in prov.read_text().splitlines() if line.startswith("| rich |")]
    assert len(row) == 1 and f"@{sha[:7]}" in row[0] and tree in row[0]
    assert "skill" in capsys.readouterr().out

    # An existing skill is only replaced with --replace
    with pytest.raises(SystemExit, match="--replace"):
        freeze_skill.main()
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--replace"])
    freeze_skill.main()
    assert freeze_skill.tree_sha256(dest) == tree


def test_freeze_needs_a_skill(source, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["freeze_skill", str(source), "--rev", "HEAD", "--source", "nope"]
    )
    with pytest.raises(SystemExit, match="SKILL.md doesn't exist"):
        freeze_skill.main()
    monkeypatch.setattr(sys, "argv", ["freeze_skill", str(source), "--rev", "no-such-rev"])
    with pytest.raises(SystemExit, match="rev-parse"):
        freeze_skill.main()


def test_api_errors_pattern():
    e = {"type": "AttributeError", "message": "'GT' object has no attribute 'fmt_numbr'"}
    assert api_errors.pattern(e) == "AttributeError: 'GT' object has no attribute 'fmt_numbr'"
    e = {"type": "ValueError", "message": "can't use 'a b c' at <obj 0x7f3a>"}
    assert api_errors.pattern(e) == "ValueError: can't use '…' at <obj 0x…>"
    assert api_errors.gt_names("fmt_number() got an unexpected keyword 'decimal'") == {"fmt_number"}


def test_api_errors_report(tmp_path):
    def trial(arm, prompt, rep, errors):
        path = tmp_path / "run" / arm / prompt / rep / "score.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"process": {"errors": errors}}))

    typo = {"type": "AttributeError", "message": "'GT' object has no attribute 'fmt_numbr'"}
    other = {"type": "ZeroDivisionError", "message": "division by zero", "gt_api": False}
    trial("baseline", "p1", "r1", [typo | {"gt_api": True}] * 2)
    trial("baseline", "p2", "r1", [typo | {"gt_api": True}, other])
    trial("prose", "p1", "r1", [])
    rows, trials = api_errors.load([tmp_path / "run"], None, every=False)
    out = api_errors.report(rows, trials)
    assert out["arms"] == {
        "baseline": {"trials": 2, "trials_with_errors": 2},
        "prose": {"trials": 1, "trials_with_errors": 0},
    }
    # Counted once per trial
    [p] = out["patterns"]
    assert p["trials"] == 2 and p["arms"] == {"baseline": 2} and p["prompts"] == ["p1", "p2"]
    assert out["names"] == {"fmt_numbr": {"baseline": 2}}
    rows, trials = api_errors.load([tmp_path / "run"], None, every=True)
    assert len(api_errors.report(rows, trials)["patterns"]) == 2


SKILL = """\
---
name: test
---
Use `fmt_number(decimals=2)` and `loc.body()`. Not `fmt_numbr()`, which is a typo.
Never write `opt_row_striping(color="red")`.
`tab_header` takes `title=`; `cols_label(a="A")` too.

```python
from great_tables import GT, loc, style, fmt_number
import polars as pl

df = pl.DataFrame({"a": [1]})
gt = GT(df).fmt_number(columns="a", decimal=2)
(
    gt
    .tab_style(style=style.fill(colour="red"), locations=loc.bdy())
    .tab_header(title="T")
)
df.pipe(print, 1, 2, 3)
gt.pipe(lambda x: x)
```

```bash
fmt_numbr --not-python
```
"""


def test_check_skill(tmp_path):
    pytest.importorskip("great_tables")
    from harness import check_skill

    (tmp_path / "SKILL.md").write_text(SKILL)
    (tmp_path / "ex.py").write_text("from great_tables import GT\nGT(None).cols_hide(colums=1)\n")
    found = {(f.file, f.line, f.problem, f.warned) for f in check_skill.check_skill(tmp_path)}
    assert found == {
        ("SKILL.md", 4, "GT has no method `fmt_numbr`", True),
        ("SKILL.md", 5, "`GT.opt_row_striping`: no parameter `color`", True),
        ("SKILL.md", 9, "`great_tables` has no `fmt_number`", False),
        (
            "SKILL.md",
            13,
            "`GT.fmt_number`: no parameter `decimal` (did you mean `decimals`?)",
            False,
        ),
        ("SKILL.md", 16, "`style.fill`: no parameter `colour` (did you mean `color`?)", False),
        ("SKILL.md", 16, "`loc` has no `bdy`", False),
        ("ex.py", 2, "`GT.cols_hide`: no parameter `colums` (did you mean `columns`?)", False),
    }
    # The bash block isn't read, and `tab_header` without a call is a real method
    assert len(check_skill.check_skill(tmp_path)) == len(found)


def test_check_skill_counts():
    pytest.importorskip("great_tables")
    from harness import check_skill

    api = check_skill.API()
    # Polars' pipe isn't GT's, so isn't checked; on a GT it is
    assert check_skill.check_code(api, "df.pipe(f, 1, x=2)") == []
    assert check_skill.check_code(api, "GT(df).tab_header()") == [
        (1, "`GT.tab_header`: missing a required argument: 'title'")
    ]
    assert check_skill.check_code(api, "def html(x): ...\nhtml(1, 2, 3)") == []
    assert check_skill.check_code(api, ".fmt_percent(decimals=1)") == []
    assert check_skill.check_code(api, "decimals=") is None
    assert Counter(check_skill.check_names(api, "GT.fmt_nmber, loc.body")) == Counter(
        ["GT has no method `fmt_nmber`"]
    )
