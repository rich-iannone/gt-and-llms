"""Spike (b): can GT.gtsave() (via nokap + Chrome) run in the current process context?

Run on the host as a control, then under `mcp-console sandbox` to test the Seatbelt profile.
"""

import os
import sys
import time
import traceback

from great_tables import GT, exibble

out = sys.argv[1] if len(sys.argv) > 1 else "render_check.png"

t0 = time.perf_counter()
try:
    # Spike-only: nokap has no supported way to pass Chrome args through gtsave(), so pre-seed
    # its browser singleton. SPIKE_CHROME_ARGS is a space-separated list (e.g. "--single-process").
    extra = os.environ.get("SPIKE_CHROME_ARGS", "").split()
    if extra:
        import nokap._api
        from nokap._browser import Chrome

        nokap._api._browser = Chrome(extra_args=extra)
    GT(exibble.head(4)).tab_header(title="Render check").gtsave(out)
    print(f"OK {out} {os.path.getsize(out)} bytes in {time.perf_counter() - t0:.2f}s")
except Exception as e:
    print(f"FAIL after {time.perf_counter() - t0:.2f}s: {type(e).__name__}")
    traceback.print_exc()
    stderr = getattr(e, "stderr", None)
    if stderr:
        print("---- chrome stderr ----")
        print(stderr[-4000:])
    sys.exit(1)
