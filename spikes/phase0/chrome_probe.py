"""Launch a Chrome binary with nokap's default args and report whether DevTools comes up.

Usage: python chrome_probe.py <chrome-path> [extra chrome args...]
"""

import subprocess
import sys
import time

from nokap._browser import _default_chrome_args

path, extra = sys.argv[1], sys.argv[2:]
args = [path] + _default_chrome_args(9333, headless=True) + extra + ["about:blank"]

proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
deadline = time.time() + 15
lines = []
status = "TIMEOUT"
while time.time() < deadline:
    line = proc.stderr.readline()
    if line:
        lines.append(line.rstrip())
        if "DevTools listening on" in line:
            status = "OK"
            break
    elif proc.poll() is not None:
        status = f"EXITED code={proc.returncode}"
        break
proc.kill()
print(status)
print("\n".join(lines[-40:]))
