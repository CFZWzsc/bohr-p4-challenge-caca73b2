# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-caca73b2` (track: `academic-writing`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `results-discussion-writer`
- Summary: Use when a case supplies raw result materials (tables, figure captions, statistics text, draft notes) and asks for a Results and Discussion section; extracts numeric claims with units and error-bar meaning, separates observation from interpretation, audits claim strength against statistics, keeps a source map, and emits /app/output/result.json preserving case_id and every output_contract field. Deterministic standard library only; no network.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
