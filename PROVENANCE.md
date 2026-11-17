# Provenance

Who wrote what, and when (plan §4). Skill text is written by Rich without model assistance.
Prompts, assertions and ground truths are human-authored or human-reviewed. Harness code can
be model-assisted.

## Skills

| Arm | Version (SHA + tree sha256) | Author | Date | Notes |
|---|---|---|---|---|
| rich | not yet frozen | Rich Iannone | | |
| prose | HrudithL/gt-skill@d1ed4e6, `.claude/skills/great-tables/`; tree sha256 `978f0dd97f92f9eff94231c31bd0465a649b260531d37038f5a913fa63a5a2e9` | Hrudith L. (HrudithL/gt-skill) | 2026-08-14 (commit); ported 2026-11-16 | ported unchanged (`diff -r` against the source is clean); MIT licence in `arms/prose/LICENSE` |

## Corpus

Items are named by id; their split directory changes when `harness/split.py` runs, and
`corpus/split.json` then records each item's files by hash. Each `prompt.json` has a `source`
field, and each `truth.py` starts with a header saying where it came from.

| Items | Prompt | `truth.py` | `intent.py` | Reviewed by Rich |
|---|---|---|---|---|
| api_latency, tech_salaries, github_repos (spec) | Rich, 2025 (`archive/2025-llms-txt/eval_dataset_no_docs.jsonl`), copied verbatim 2026-11-05 | Model-drafted 2026-11-05 | Model-drafted 2026-11-16 | prompts: yes (original author); truths: yes, 2026-11-05; `intent.py`: yes, 2026-11-16 |
| The 20 gt-skill items (intent) | Hrudith L., HrudithL/gt-skill@d1ed4e6, verbatim | gt-skill's ground truths, ported by `harness/port_gt_skill.py` (data path and `gt_tbl` only) | Model-drafted 2026-11-16; row counts, grouping and sorts from each truth's `REQUIRED_INSTRUCTIONS` (Hrudith L.) | prompts and truths: yes, 2026-11-05; `intent.py`: yes, 2026-11-16 |
| The 13 proposed items (`source: proposed …`) | Model-drafted 2026-11-05 | Model-drafted 2026-11-05 | Model-drafted 2026-11-16 | prompts and truths: yes, 2026-11-05; `intent.py`: yes, 2026-11-16 |

gt-skill's 4 airquality/islands items aren't ported (plan §7). The datasets come from GT
0.22.0 (`harness/export_data.py`); the 8 that gt-skill's truths use are byte-identical to the
pinned GT's, so the ported truths' values and source notes still hold.

## Harness text

| Item | Origin | Reviewed by Rich |
|---|---|---|
| `arms/base_prompt.md` | Model-drafted for the Phase 0 spike (2026-10-30), unchanged since | yes, 2026-11-05 ("The system prompt looks good") |
| Skill/docs wrapper sentences in `harness/arms.py` | Model-drafted, 2026-11-05 | yes, 2026-11-05 |
| The judge's rubric and instructions (`judge/rubric.md`, `absolute.md`, `pairwise.md`) | Model-drafted 2026-11-05 from plan §6, with gt-skill's `runner/judge_rubric.py` as a reference for format | not yet |

## Harness code

Model-assisted (allowed by §4): `harness/` (including `score/`, the L1 assertion library),
`tests/`, `console/agent_site/`.
