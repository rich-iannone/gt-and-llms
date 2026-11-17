"""Write Great Tables' sample datasets to data/<name>.csv, from the GT version pinned in
console/agent-env. Runs in the agent's Python, which has GT:

    console/agent-env/.venv/bin/python harness/export_data.py

Re-run after changing the GT pin; prompts and truths read these CSVs.
"""

from pathlib import Path

import great_tables
import great_tables.data as gt_data
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    names = [
        n
        for n in sorted(dir(gt_data))
        if not n.startswith("_") and isinstance(getattr(gt_data, n), pd.DataFrame)
    ]
    for name in names:
        getattr(gt_data, name).to_csv(DATA / f"{name}.csv", index=False)
    print(f"great-tables {great_tables.__version__}: wrote {', '.join(names)}")


if __name__ == "__main__":
    main()
