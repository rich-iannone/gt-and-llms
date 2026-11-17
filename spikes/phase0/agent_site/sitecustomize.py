# SPIKE-ONLY shim, loaded into the agent's Python via PYTHONPATH.
#
# Inside Console's macOS Seatbelt profile, Chrome can't register its MachPortRendezvousServer, so
# multi-process Chrome aborts. `chrome-headless-shell --single-process` works. nokap has no supported
# way to add Chrome args through GT.gtsave(), so append NOKAP_SPIKE_ARGS to nokap's defaults.
# Phase 1 replaces this with a real nokap option.
import os

_extra = os.environ.get("NOKAP_SPIKE_ARGS", "").split()
if _extra:
    try:
        import nokap._browser as _nb

        _orig = _nb._default_chrome_args

        def _default_chrome_args(port, headless=True):
            return _orig(port, headless) + _extra

        _nb._default_chrome_args = _default_chrome_args
    except ImportError:
        pass
