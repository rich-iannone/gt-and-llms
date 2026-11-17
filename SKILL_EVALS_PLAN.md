# Great Tables skill + evals: revival plan

> Status: draft v0.1, 2026-10-30. Owner: Rich Iannone.
> Home: `rich-iannone/gt-and-llms` (this repo). The skill itself is proposed to live in
> `posit-dev/great-tables` (see D1).

## 1. Goal

Ship a **human-authored Great Tables skill** and a **reproducible eval** showing whether it
helps a capable model, Sonnet 5, build tables that do what the prompt asked. The eval
runs agent code through **mcp-console** (a hard requirement from its author), drives the
model with **chatlas** + the Anthropic API, and renders tables with **nokap** (the engine
behind `GT.gtsave()`).

The main question is **intent fulfillment**: does the table answer the prompt, with the
right rows, columns, computed values, structure and formatting, and does it read well?
Matching one particular house style is not the target.

## 2. What we have (inventory)

| Source | What's there | Keep | Change or drop |
|---|---|---|---|
| `HrudithL/gt-skill` | 24 prompts (easy/medium/hard) over 10 datasets; ground-truth `.py` + `.png` per prompt with metadata (`LABEL_SYNONYMS`, `REQUIRED_INSTRUCTIONS`, `CANONICAL_MEASURES`, `SEMANTIC_TYPES`); 4 skill variants (prose/scripts/house/creator); a no-skill baseline; a vision judge with 1/3/5 anchors; a convergence report; contact sheets; per-call cost capture; one skill per run | Prompts, data-prep logic in the ground truths, metadata ideas, the baseline-as-control idea, the judge design (separate model, batched call, N/A when it doesn't apply), convergence, contact sheets, cost tracking | **Engine:** Claude Agent SDK becomes chatlas + mcp-console. **Sidecar:** the `.pth` monkeypatch of `nokap._api` becomes a supported nokap API. **Scoring:** the 6.3k-line regex/AST comparator scores house-style conformance (`#08306B` header band, stub tint, stripe colour, hero-not-bold, `force_sign`), and the winning skill teaches exactly those rules, so the reported +72 lift is partly circular. Replace it with intent checks against the GT object (§6). **Writer model:** Haiku 4.5 becomes Sonnet 5. **Datasets:** airquality and islands (3 + 1 prompts) are deprecated in GT and need replacing. **Ground truths** target GT 0.22.0; GT is now 1.1.0 (the pinned GT has `summary_rows`/`grand_summary_rows`, but their `columns=` raises NotImplementedError). **Data:** the 8 datasets gt-skill's truths use are byte-identical between GT 0.22.0 and the pinned GT |
| `rich-iannone/gt-and-llms` (Nov 2025) | 3 "spec-style" prompts (api_latency, tech_salaries, github_repos) + 6 CSVs; an Inspect + chatlas eval of with vs without `llms.txt`; the blog-style write-ups; Inspect `.eval` logs | The spec-style prompts (a useful counterpoint to gt-skill's vague "intent-style" prompts), the docs-in-context arm idea, the write-ups as narrative material | Move the Inspect harness into `archive/2025-llms-txt/`. Its scorer ("code runs") is too weak. |
| `great-tables@feat-claude-skill` | `SKILLS/SKILL.md`: 74 lines on philosophy and principles, written by Rich | The seed for the human-authored skill | Revise by hand for GT 1.1 (§7). Move to its final home (D1). |
| `rich-iannone/skillbuilder` | Skill-eval toolkit: multi-baseline, Bradley-Terry leaderboard, `claude_api` backend | Ideas: the "agent-written skill" baseline, pairwise ranking | Not a dependency for now (D6) |

## 3. Decisions (all confirmed by Rich, 2026-11-05)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Where the skill lives | `great-tables/skills/great-tables/` (like `nokap/skills/`), versioned with the API; gt-and-llms evaluates a pinned commit | The skill has to track API changes; evals reference a SHA |
| D2 | How the skill reaches the model (chatlas has no skill loader) | Put the `SKILL.md` body in the system prompt inside a `<skill>` block. Put `references/` on a path the agent can read through Console. The base prompt is the same in every arm. | Measures the skill's content. Whether the skill *triggers* is a separate, later eval. |
| D3 | Agent sees its own render | On by default; run an ablation with it off | That's how people use Claude Code. It's also where layout and wrapping problems get fixed. |
| D4 | Inspect | Drop it. Use a thin harness: JSONL results + Console recordings. | mcp-console already provides sandboxing, the session and the transcript. Inspect would add a second sandbox and tool model on top. |
| D5 | Judge model | Opus 5 (`claude-opus-5`). Never the writer model. | Separation, plus strong vision |
| D6 | skillbuilder | Don't depend on it now. Maybe port the harness in as a backend later. | Keeps this project unblocked |
| D7 | Comparison arms | Baseline (no skill), `llms.txt` in context, Rich's skill, Hrudith's `prose` skill (ported, unchanged) | Shows the lift and gives a fair comparison with the earlier work |

## 4. Integrity protocol (non-negotiable)

1. **Skills are written without model assistance.** Rich writes them by hand. Each skill
   version is frozen as a git SHA plus a sha256 of the skill tree, and every trial records both.
   `PROVENANCE.md` logs who wrote what, and when.
2. **Prompts, assertions and ground truths are human-authored or human-reviewed.** Harness
   code can be model-assisted. Skill text cannot.
3. **Dev/test split.** About 2/3 of prompts are *dev*: we can look at them while revising the
   skill. About 1/3 are *test*: hidden until the final run. gt-skill's "earn each rule from a
   failure" loop overfits unless the evaluation set is held out.
4. **Freeze the judge rubric and the human-calibration sample** before the main run.
5. **Pin everything:** model IDs, GT version, Console version (recordings capture it), nokap
   version, Chrome version.

## 5. Harness architecture

```
corpus item ──► trial(arm, prompt, repeat)
                 │
                 ├─ fresh workspace dir: data/<csv>, (skill refs if arm has a skill)
                 ├─ fresh mcp-console server (one per trial = one isolated session)
                 │     config: sandbox.profile=workspace (writes only to the trial dir),
                 │             network restricted (nokap's CDP runs over pipes, §5.2),
                 │             python: <uv-locked agent env>, r.resolution=disabled (Phase 0)
                 ├─ chatlas ChatAnthropic(model="claude-sonnet-5", system_prompt=base+arm)
                 │     await mcp_console.chatlas.register(chat, transport_kwargs={cwd, env})
                 │     (register() preserves image results; chatlas.tool() would turn them into placeholders)
                 │     turn and tool-call budget; capture tokens + cost from chatlas
                 └─ deliverable: workspace/table.py that builds `gt_tbl` and calls gt_tbl.gtsave("table.png")
                 
post-trial (outside the agent session):
  re-run table.py in a clean Console session ──► GT object (pickled/introspected),
  as_raw_html(), table.png via nokap ──► scoring (§6) ──► results.jsonl
  copy the Console recording (journal, transcript.md, session QMDs) into the trial dir
```

### 5.1 Layout (this repo)

```
gt-and-llms/
  SKILL_EVALS_PLAN.md
  pyproject.toml            # uv; chatlas, mcp-console[chatlas], great-tables, nokap, polars, pandas
  console/config.yaml       # the Console sandbox + package profile used for every trial
  arms/                     # base_prompt.md, arm definitions (which skill SHA, llms.txt snapshot)
  corpus/{dev,test}/<id>/   # prompt.json, truth.py, intent.py (assertions), notes.md
  data/                     # CSVs (gt datasets + gt-and-llms CSVs)
  harness/                  # run.py (CLI), trial.py, console.py, render.py, score/, judge.py, report.py
  runs/                     # gitignored raw trial dirs
  results/                  # committed, versioned snapshots (results.jsonl + summary)
  report/                   # Quarto write-up (tables built with GT)
  archive/2025-llms-txt/    # the old Inspect work
```

### 5.2 Rendering inside the sandbox (main technical risk)

> **Resolved in Phase 0 (2026-10-30), option 1.** `chrome-headless-shell --single-process` plus
> `sandbox.network.allow_local_binding: true` renders inside Console's sandbox. Full Chrome
> aborts in LaunchServices registration, and multi-process headless-shell is denied
> `mach-register`. Details are in `spikes/phase0/FINDINGS.md`.
>
> **Updated 2026-11-16.** nokap `main` (0273091) talks to Chrome over
> `--remote-debugging-pipe` by default on macOS/Linux, so `allow_local_binding` is gone from
> `console/config.yaml`. `harness/prepare.py` and one Sonnet 5 trial
> (`runs/20261116-pin-bump`) pass without it. The original analysis follows.

gt-skill found that headless Chrome can't start under the macOS Claude Code Seatbelt
profile. Console also uses Seatbelt on macOS, so assume the same problem until a spike
proves otherwise. Options, in order of preference:

1. **Chrome for Testing `chrome-headless-shell`** launched by nokap inside the sandbox. It
   touches fewer mach and GPU services than full Chrome. A spike will show whether it
   starts under Console's profile.
2. **A supported nokap "attach" mode.** For example, `nokap.connect(ws_url)` or a
   `NOKAP_CDP_URL` env var: the harness launches Chrome on the host, and `gtsave()` attaches
   over loopback CDP. Needs `sandbox.network.allow_local_binding: true` in Console config.
   This replaces gt-skill's `.pth` monkeypatch with a real API.
3. **Fallback:** the agent writes the HTML (`gt_tbl.write_raw_html()`), and the harness
   renders it on the host between turns. This is worse for the visual feedback in D3.

**Getting the image back to the model:** Console only captures pyplot figures (plus R plots).
Short term: put a `show_png(path)` helper in the base prompt, the same in every arm, that
draws the PNG with `plt.imshow` so Console returns it. Ask the mcp-console author whether
Python rich display (`IPython.display.Image` / `image/png` MIME) could be captured; that
would make the helper unnecessary.

### 5.3 nokap work items (Rich maintains it)

Revised after Phase 0. The attach API (option 2) is no longer needed.

- Detect or install `chrome-headless-shell` (for example, `nokap install-chrome`); prefer it when present
- A supported way to add Chrome args without code changes (for example, `NOKAP_CHROME_ARGS`),
  or automatic `--single-process` when a sandbox is detected. This replaces the spike's
  `sitecustomize.py` shim.
- ~~Optional: CDP over `--remote-debugging-pipe`, which drops the loopback port and the
  `allow_local_binding` requirement~~ Done on nokap `main` (#2), and the default on POSIX
- Fix: `Chrome.__del__` raises `AttributeError` when `__init__` fails before `_process` is set
- `nokap doctor` reports sandbox-related launch failures clearly (SIGABRT from LaunchServices,
  `bootstrap_check_in ... Permission denied`)
- Then: `gtsave()` passes through unchanged. Check that the GT test suite still passes.

## 6. Scoring: intent first

| Layer | What | How |
|---|---|---|
| L0 Mechanics | `table.py` runs; yields a `GT`; renders to PNG | Re-execution in a clean session |
| L1 Intent assertions (deterministic) | Per-prompt checks written by a human: required columns present, row filter/count, sort order, grouping by X, spanner over {a, b}, stub = X, title present, currency/percent/sep formatting on named columns, conditional highlight on rows meeting a condition, `sub_missing` applied when NAs exist | `corpus/<id>/intent.py` checks the **GT object** (`_boxhead`, `_stub`, `_spanners`, `_styles`, `_formats`) and the rendered cell text, not regex over the source. A shared assertion library keeps each prompt to about 5–15 lines. |
| L2 Data correctness | Displayed values match the ground-truth computation | Compare the GT's underlying frame to `truth.py`'s frame: tolerant numeric match, label synonyms, order-insensitive unless the prompt asks for an order |
| L3 Judge: absolute | Intent fulfillment + readability (1/3/5 anchors): answers the question; labels name the right concepts; sensible hierarchy; appropriate precision; fits the viewport | Opus 5 reads the **prompt + candidate PNG** (+ a data schema summary). It does **not** see the ground-truth PNG as a target, so it can't reward copying one author's style. |
| L3' Judge: pairwise | Skill arm vs baseline (and vs prose) for the same prompt and repeat | Blind A/B, both orders, ties allowed. Gives win rate and Bradley-Terry scores. |
| Process | Turns, cells run, Python errors, **GT API errors** (AttributeError/TypeError on GT calls, a direct measure of what the skill fixes), tokens, cost, wall-clock | Parsed from the Console journal + chatlas |
| Convergence | Agreement across repeats on structure (stub, groups, spanners, formats, visible columns) | Simplified port of gt-skill's convergence fields, read from the GT object |

**Judge calibration:** before the main run, Rich rates a stratified sample of about 50
tables, blind to arm. Report judge vs human agreement (Spearman for absolute scores,
agreement rate for pairwise). If agreement is weak, revise the rubric and recalibrate,
then freeze it.

**Headline metrics:** L1 pass rate, L2 correctness, L3' win rate vs baseline, and GT API
error rate. Each is reported per arm with bootstrap CIs over prompts, on the **test**
split, alongside cost per trial.

## 7. Corpus refresh

- Port gt-skill's 24 prompts. Replace the 4 airquality/islands prompts with prompts on
  current datasets (illness, reactions, photolysis, nuclides, peeps, sza, exibble).
- Add gt-and-llms's 3 spec-style prompts, and add more of that style so both styles are
  represented (tag: `style: intent | spec`).
- Add prompts that exercise features newer than gt-skill: nanoplots, `fmt_icon`/`fmt_image`,
  summary rows, units notation, `cols_merge*`, and locale formatting.
- Regenerate every `truth.py` on GT 1.1.0. These are reference implementations for L2 data
  checks, not style targets.
- Target about 36 prompts, roughly 24 dev / 12 test, stratified by difficulty and style.

## 8. Phases

| Phase | Work | Exit criterion |
|---|---|---|
| **0. Spikes** ✅ 2026-10-30 | (a) chatlas + `mcp_console.chatlas.register` + Sonnet 5: one trial end to end, image returned to the model; (b) nokap/Chrome under the Console sandbox on macOS (§5.2 options 1→2); (c) measure the cost and latency of one trial | A table rendered from inside Console and seen by the model; a cost-per-trial estimate. **Met:** $0.015–0.14 and 10–63s per trial; see `spikes/phase0/FINDINGS.md` |
| **1. nokap** | Attach API and/or headless-shell support; release | `gtsave()` works inside the Console sandbox. **Status 2026-11-05:** `feat-sandboxed-chrome` is merged to nokap `main` (adds `install-chrome`, `NOKAP_CHROME_ARGS`, an automatic `--single-process` retry, and the `__del__` fix). Not yet on PyPI, which is still at 0.1.0. **2026-11-16:** pipe transport merged (#2) and is the default on POSIX; the agent env now pins nokap `main` 0273091. Remaining: a PyPI release. |
| **2. Repo reset** | Archive the 2025 work; uv project; Console config; skeleton harness | `harness/run.py --arm baseline --prompt <id>` produces a trial dir. **Met 2026-11-05:** `runs/phase2-check-deny/baseline/api_latency/r1` (3 tool calls, 1 image, 11s, $0.022). The agent's only tool is Console's `send`. The sandbox denies reads of the repo (corpus, arms, runs, `.env`, `.git`), its sibling projects, `~/py_projects` and `~/.claude`, and `harness/prepare.py` checks this on every setup. The agent env pins GT `main` 9516ea8 and nokap `main` 0273091 (Q4; bumped 2026-11-16 from 024ca9d and c74bd46, together with mcp-console 0.0.6 → 0.0.7, whose `send()` now returns a `ConsoleResult`); Chrome for Testing 156.0.8078.80 is installed into `.browsers/` by `harness/prepare.py`. |
| **3. Corpus** | Port, replace and add prompts; `truth.py` on GT 1.1; human-written `intent.py`; dev/test split | All truths render; all assertions pass on their own truth. **Status 2026-11-05:** 36 items (12 easy / 12 medium / 12 hard; 10 spec, 26 intent), and all 36 truths render. 20 are gt-skill ports in `corpus/unsplit/` (prompts verbatim). The 3 gt-and-llms spec prompts have model-drafted truths, reviewed by Rich. 13 model-drafted items (2 airquality/islands replacements, 4 more intent items, 7 spec items on newer features) have prompts and truths reviewed by Rich. The L1 library (`harness/score/intent.py`, 47 tests) reads every truth correctly. No `intent.py` yet (Rich writes these). `harness/split.py --seed N` makes the split: 24 dev / 12 test in a dry run. Possible GT gaps found: `fmt_chem` leaves `O(^1D)` literal; locale `de` puts € before the amount |
| **4. Scoring** | L0–L2, process metrics, convergence; judge rubric; calibration sample | Judge vs human agreement meets the bar; rubric frozen. **Status 2026-11-05:** L0–L2, structure and process metrics are built (`harness/score_trials.py`, `harness/summarize.py`). Each `table.py` is re-run in a fresh, model-free Console session under the trial sandbox. L2 matches each of the truth's visible columns to a candidate column by values (an `intent.py` can narrow this with `DATA_COLUMNS`). GT API errors are counted from the trial's Console recordings. Checked end to end on 3 baseline trials of `api_latency` (`runs/phase4-check`). The judge's rubric is drafted (`judge/`) and awaits Rich's review. The judge code and the calibration sample are not started |
| **5. Skill authoring** (Rich, by hand) | Revise the `feat-claude-skill` SKILL.md for GT 1.1: API-accurate method guidance, common mistakes, references/ | Skill v1 frozen (SHA + hash in PROVENANCE.md) |
| **6. Pilot** | All arms × dev split × 2 repeats | Numbers look sane; budget for the full run confirmed |
| **7. Iterate** | Rich revises the skill on dev results (by hand); re-run dev only | Skill v-final frozen |
| **8. Final run** | All arms × test split × 5 repeats (+ the D3 ablation) | `results/<date>/` committed |
| **9. Publish** | Quarto report in `report/`; ship the skill in great-tables; blog post | Report and skill PR live |

## 9. Risks

- **Chrome in the sandbox** (§5.2). Phase 0 de-risks it; option 3 always works.
- **Judge bias toward verbose or colourful tables.** The rubric anchors are about intent,
  calibration happens first, and pairwise order is swapped.
- **Cost growth.** Arms × prompts × repeats × (writer + judge). Set the budget after the pilot.
  Use an `--estimate` dry run and a result cache keyed by (arm SHA, prompt hash, model, repeat).
- **mcp-console churn.** It is a development preview. Pin the version and keep the
  integration in `harness/console.py`.
- **Skill format portability.** D2 injects the skill into the system prompt rather than using
  Claude Code's loader. Note this in the report. A later check can run the same skill under
  Claude Code + Console.

## 10. Open questions

1. ~~D1–D7 above.~~ Confirmed 2026-11-05.
2. Should the final run include a second writer model (for example, Haiku 4.5) to show the
   lift on a weaker model? It's cheap to add after the Sonnet 5 run.
3. Is Hrudith involved: as a reviewer of the ported corpus, or credited in the report?
4. Which GT version the eval pins. great-tables `main` is 779 commits past v1.1.0. The
   pandas-int64 nanoplot failure Phase 0 hit (BUGS.md #115 (b)) is already fixed on `main`
   by #1008, so it doesn't need filing. Recommendation: pin the next GT release (or a `main`
   SHA in `agent-env`) so the skill and the eval target the same API. **2026-11-16:** bumped
   to `main` 9516ea8 (1335 commits past v1.1.0, mostly GTI). All 36 truths still pass
   with L2 = 1.00. 16 `truth.png` files came out 2px taller, most likely from the column-label
   padding and footer-order fixes (#1134, #1133), and were regenerated. Re-pin to the latest
   `main` once more before freezing skill v1, so the skill is written against the API it's
   evaluated on.
