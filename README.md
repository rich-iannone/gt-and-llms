# gt-and-llms

How well does GT work with LLMs? This repo evaluates whether a hand-written Great Tables skill
helps a model (Sonnet 5) build tables that do what a prompt asks. The plan is in
[SKILL_EVALS_PLAN.md](SKILL_EVALS_PLAN.md).

The agent writes and runs code through [mcp-console](https://github.com/posit-dev/mcp-console),
driven by [chatlas](https://github.com/posit-dev/chatlas), and renders tables with
[nokap](https://github.com/posit-dev/nokap).

## How the evals work

Each prompt in the corpus asks for a table built from one of GT's datasets. An intent-style
prompt says what the reader should learn, and a spec-style prompt lists the features to use.
For each prompt, Sonnet 5 writes and runs Python through mcp-console, in a sandbox with no
network and no access to this repo, and renders its table with nokap so it can look at the
result and revise it.

There are four arms, which differ only in what's added to a shared system prompt: nothing (the
baseline), GT's `llms.txt`, Rich's hand-written skill, or the `prose` skill from Hrudith L.'s
gt-skill.

Each table is scored in four layers. The first checks that the code runs and renders. The
second runs hand-written checks on the GT object (`intent.py`), and the third compares the
table's values with a reference table (`truth.py`). In the last, Opus 5 grades each render
against its prompt and compares the arms blind, in pairs.

The prompts are split into two sets. About two thirds are dev prompts, and the skill is revised
based on how it does on them. The other third are test prompts, which nobody looks at until the
final run, where each one is run five times. Since the skill was never tuned on the test
prompts, its results on them show how much it helps on prompts it hasn't seen. People write or
review every skill, prompt, check and truth, and `PROVENANCE.md` records who did what.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and an `ANTHROPIC_API_KEY` in `.env`.

```bash
uv sync                      # the harness environment
uv run harness/prepare.py    # the agent's environment, chrome-headless-shell, sandbox checks
```

## Running trials

```bash
uv run harness/run.py --arm baseline --prompt api_latency
uv run harness/run.py --arm baseline --prompt dev --repeats 2 --run-id pilot
```

Each trial gets a fresh workspace and Console session under `runs/<run-id>/<arm>/<prompt>/r<n>/`.
See `harness/trial.py` for what's in a trial directory.

## Scoring

```bash
uv run harness/score_trials.py runs/<run-id>      # L0–L2, structure and process metrics
uv run harness/summarize.py runs/<run-id> --split dev
```

`score_trials.py` re-runs each trial's `table.py` in a fresh Console session with no model
attached. It writes `score.json` and a re-rendered `score/table.png` into the trial directory.
`summarize.py` gives each arm's metrics with bootstrap CIs over prompts, the difference from the
baseline, and convergence across repeats. The judge (L3) isn't built yet.

## The corpus

Each item is a directory, `corpus/<split>/<id>/`, holding:

- `prompt.json`: the prompt, its data files, `style` (`intent` or `spec`), `difficulty`,
  and `source`
- `truth.py`: a reference table, which must assign the GT to `gt_tbl`. It's used for data
  checks, not as a style target. `truth.png` is its render, for reading.
- `intent.py`: the item's checks, written by hand (see below)

Items are in `unsplit/` until `harness/split.py` divides them between `dev/` and `test/`.

```bash
uv run harness/check_corpus.py               # every truth renders; every intent.py passes on its truth
uv run harness/check_corpus.py peeps_tallest
uv run harness/split.py --seed N             # dry run of the stratified dev/test split
VIRTUAL_ENV= uv run --project console/agent-env --with pytest pytest tests -q
```

The tests run in the agent's environment because they need GT. Run them from the repo root.

### Writing an intent.py

An `intent.py` defines `check(t, truth)`. `t` is the candidate's table and `truth` is the
item's `truth.py` table, both as `harness.score.intent.Table`. Each assertion on `t` records
a pass or a fail, so one failure doesn't hide the rest:

```python
from harness.score.intent import INTEGER


def check(t, truth):
    t.title("dashboard")
    t.row_count(6)
    t.stub("endpoint")
    t.order("p99_ms", descending=True)
    t.formatted(["avg_ms", "p95_ms", "p99_ms", "requests", "errors"], INTEGER)
    t.filled(t.col("p99_ms").num > 1000, color="red", light=True)
```

A column can be named by its data name or label (ignoring case). When the prompt doesn't
fix the names, find it by its values: `t.col(like=truth.col("msrp"))`. The checks are:

- **Heading:** `title`, `subtitle`, `source_note`
- **Shape:** `row_count`, `has_columns`, `stub`, `grouped_by`, `spanner`, `summary_row`
- **Values:** `same_values` (at the precision shown, at the usual scalings), `order`
- **Formats:** `formatted` with `number()`, `currency()`, `percent()`, `compact()` or
  `INTEGER`; these take `sep=`/`dec=` for other locales
- **Missing values and plots:** `no_raw_missing`, `nanoplot`
- **Styles:** `filled` (a row highlight), `gradient` (a color scale), `text_styled`

The docstrings in `harness/score/intent.py` give each check's details.

L2 checks that the table shows the truth's data, column by column. By default it uses every
visible column of the truth. If only some of them are what the prompt asks for, name those in
the `intent.py`: `DATA_COLUMNS = ["car", "msrp"]`.

## Layout

| Path | What |
|---|---|
| `arms/` | The base system prompt and the comparison arms (`arms.yaml`) |
| `corpus/<split>/<id>/` | Corpus items (above) |
| `data/` | CSVs the prompts use |
| `console/` | Console config, the agent's locked Python env (`agent-env/`), helpers on its path |
| `harness/` | The trial runner, corpus tools, and scoring (`score/`) |
| `tests/` | Tests of the scoring library |
| `spikes/phase0/` | Phase 0 feasibility spikes and findings |
| `archive/2025-llms-txt/` | The 2025 Inspect eval of `llms.txt` and its write-ups |

`.well-known/llms.txt` stays at the top level because the 2025 write-up links to it.
