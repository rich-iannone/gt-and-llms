# Phase 0 spike findings (2026-10-30)

Host: macOS (Darwin 25.6, arm64). Versions: mcp-console 0.0.6, chatlas 0.23.0, great-tables
1.1.0, nokap 0.1.0, polars 2.1.0, Chrome 156.0.8078.79, chrome-headless-shell 156.0.8078.80.
Writer model: `claude-sonnet-5`.

**Result: all three spikes pass.** Sonnet 5, driven by chatlas, built a table in Console's sandbox,
rendered it with `gtsave()`, and got the PNG back as an image it could check.

## (b) Rendering inside the Console sandbox

Each blocker in the order we hit it, under `sandbox.profile: workspace`:

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `PermissionError` in `nokap._utils.find_open_port()` | Workers can't bind loopback by default | `sandbox.network.allow_local_binding: true` (needs a `network.proxy` mapping alongside it) |
| 2 | Google Chrome exits with SIGABRT (code -6), no stderr | Full Chrome calls `TransformProcessType` → HIServices `_RegisterApplication` (LaunchServices/WindowServer), which Seatbelt denies. `--no-sandbox`, `--user-data-dir` and crashpad flags don't help. | Use Chrome for Testing `chrome-headless-shell`, which doesn't register as a GUI app |
| 3 | headless-shell exits with code -5: `bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer: Permission denied (1100)` | Seatbelt denies `mach-register`. Multi-process Chrome needs it to hand ports to child processes. | `--single-process` |

With headless-shell, `--single-process` and local binding, `gtsave()` works in the sandbox. Output
is byte-identical in size to the host render. It's also much faster: about 0.5s per render with
headless-shell, against 6.3s for a cold start of full Chrome on the host.

So option 1 in plan §5.2 works. Options 2 (CDP attach) and 3 (host-side render) aren't needed.

Also found:
- **nokap bug:** when `Chrome.__init__` fails before `self._process` is set, `Chrome.__del__`
  raises `AttributeError: 'Chrome' object has no attribute '_process'`.
- **Possible nokap improvement:** `--remote-debugging-pipe` would drop the loopback TCP port, and
  with it the `allow_local_binding` requirement. It needs a pipe transport in `_cdp.py`.
- The spike passes `--single-process` through a `sitecustomize.py` shim
  (`agent_site/sitecustomize.py`), because `gtsave()` has no way to pass Chrome args. Phase 1
  replaces the shim with a supported nokap option.

## (a) End-to-end loop

- `mcp_console.chatlas.register(chat, command=..., args=["serve", "--config-file", cfg],
  transport_kwargs={"cwd": trial_dir})` works. The image from `show_png()` reaches the model as
  `ContentToolResult[ContentImageInline]`.
- Recordings land in the trial dir when `<trial>/.agents/console/` exists before launch (journal,
  `transcript.md`, session QMDs, `capture/` PNGs).
- **Python environment:** managed Python preparation fails on this host. With R installed, Console
  prepares through R's `ir`, which errors on R 4.2.3 (`the condition has length > 1` in
  `ir_resolve_main`). Python-only sessions still prepare R bridge packages. Workaround: point
  `python:` at a uv-locked venv (`agent-env/`) and set `r.resolution: disabled`. A locked env pins
  versions more tightly than `python.packages` anyway, so this is the better default for evals.
  It's worth reporting to the mcp-console author, or checking whether a newer R/ir avoids it.
- Console server startup took about 0.6s with warm caches.

## (c) Cost and latency (baseline arm, no skill)

| Prompt | Tool calls | Images seen | Wall | Cost |
|---|---|---|---|---|
| api_latency (simple) | 3 | 1 | 10.4s | $0.015 |
| github_repos (complex) | 13 | 2 | 62.7s | $0.140 |

chatlas `get_cost()` matches a hand calculation from raw usage. chatlas's per-turn `tokens` field
goes negative with prompt caching; totals and cost are fine. Rough extrapolation: $0.02–0.15 per
writer trial. A skill in the system prompt adds mostly cached input ($0.20/M for Sonnet 5). Pilot
(4 arms × 24 dev × 2 reps = 192 trials): about $10–30. Final (4 × 12 × 5 = 240, plus ablation):
about $15–40 before judge costs.

## Observations relevant to later phases

- In github_repos the model hit `fmt_number(scale_values=...)` (not a GT parameter), then twice hit
  `NotImplementedError: The input data values must be a string` from `fmt_nanoplot()`. That one is
  a **GT bug**: nanoplots fail on a pandas int64 column (numpy integer scalars aren't handled in
  `_generate_data_vals`) but work on polars Int64. The model fixed it by casting to float. Process
  metrics should count these, and the GT bug should be filed.
- In api_latency, the row highlight skips the stub cell (`loc.body()` excludes the stub). The model
  reported success. That's the kind of detail an L1 intent check (does the "row" highlight include
  the stub?) and the skill text could cover.

## Files

- `render_check.py`: `gtsave()` smoke test (host or `mcp-console sandbox`)
- `chrome_probe.py`: launches a Chrome binary with nokap's args and reports whether DevTools came up
- `console_check.py`: renders and returns an image through a real Console session, no model
- `trial.py`: one chatlas + Console + Sonnet 5 trial; `--prompt-index` picks from `eval_dataset_no_docs.jsonl`
- `agent_site/`: `evalhelpers.show_png` (same in every arm) and the spike-only nokap shim
- `agent-env/`: the agent's locked Python environment
- `.browsers/` (gitignored): chrome-headless-shell, from the Chrome for Testing
  `last-known-good-versions-with-downloads.json` Stable channel
