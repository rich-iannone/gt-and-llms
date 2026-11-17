"""Port HrudithL/gt-skill's prompts and ground truths into corpus/unsplit/, which holds
items until the dev/test split. Prompts are copied verbatim. Truths get mechanical
changes only: read data/<name>.csv relative to the working directory, and expose the
table as `gt_tbl` instead of saving a PNG. Fixes for the pinned GT come after, by hand.

    git clone https://github.com/HrudithL/gt-skill /tmp/gt-skill
    git -C /tmp/gt-skill checkout d1ed4e6
    uv run harness/port_gt_skill.py /tmp/gt-skill
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.corpus import CORPUS

# Their datasets are gone from great_tables.data; plan §7 replaces these prompts
DEPRECATED = {
    "airquality_hottest_days",
    "islands_sizes",
    "airquality_monthly_summary",
    "airquality_wind_regime",
}


def _port_truth(src: str, data_file: str) -> str:
    out = re.sub(r"^_HERE = .*\n_ROOT = .*\n", "", src, flags=re.M)
    out = re.sub(r'_ROOT / "data" / "([^"]+)"', r'"data/\1"', out)
    out, n = re.subn(r"^gt\.gtsave\(.*\)\n", "gt_tbl = gt\n", out, flags=re.M)
    assert n == 1, "expected one gtsave() call"
    assert "_ROOT" not in out and "_HERE" not in out, "leftover path variables"
    if not re.search(r"\bPath\b", out.replace("from pathlib import Path\n", "")):
        out = out.replace("from pathlib import Path\n", "")
    assert f'"data/{data_file}"' in out, f"truth doesn't read data/{data_file}"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clone", type=Path, help="a gt-skill checkout")
    args = parser.parse_args()
    sha = subprocess.run(
        ["git", "-C", str(args.clone), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    source = f"HrudithL/gt-skill@{sha} (verbatim)"

    ported = []
    for difficulty in ["easy", "medium", "hard"]:
        for path in sorted((args.clone / "prompts" / difficulty).glob("*.json")):
            pid = path.stem
            if pid in DEPRECATED:
                continue
            spec = json.loads(path.read_text())
            data_file = Path(spec["data"]).name
            truth_src = (path.parent / "ground_truth" / f"{pid}.py").read_text()

            item = CORPUS / "unsplit" / pid
            item.mkdir(parents=True, exist_ok=True)
            prompt = {
                "id": pid,
                "style": "intent",
                "difficulty": difficulty,
                "data": [data_file],
                "source": source,
                "prompt": spec["prompt"],
            }
            (item / "prompt.json").write_text(json.dumps(prompt, indent=2) + "\n")
            header = (
                f"# Ported from {source.replace(' (verbatim)', '')}: "
                f"prompts/{difficulty}/ground_truth/{pid}.py\n"
                "# by harness/port_gt_skill.py (data path, `gt_tbl`); later edits are noted inline.\n"
            )
            (item / "truth.py").write_text(header + _port_truth(truth_src, data_file))
            ported.append(pid)
    print(f"ported {len(ported)} items from gt-skill@{sha}")


if __name__ == "__main__":
    main()
