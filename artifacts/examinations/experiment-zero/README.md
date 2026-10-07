# ΛLingua Experiment Zero — Examination Archive

Status: COMPLETE

Run ID: `ez0-20261007`

This directory preserves the first full ΛLingua Experiment Zero
examination set.

## Students

- `gemma3:1b`
- `qwen3:1.7b`
- `qwen3.5:2b`

## Conditions

- A — Natural-language control
- B — Full frozen ΛLingua v0 bootstrap
- C — Minimal derived ΛLingua v0 bootstrap

## Tasks

T01 was calibration-only and is not part of official scoring.

T02–T10 comprise the official benchmark.

## Calls

- Dry run: 9
- Official: 81
- Total preserved inference calls: 90

All inference calls were sequential.

Thinking was disabled.

No semantic failure was retried.

Transport failures: 0.

## Preservation Rule

Raw model responses are historical evidence.

They must not be edited, normalized, repaired, or replaced
retroactively.

Scoring and interpretation may evolve, but the submitted model
responses remain immutable.

## Important Method Note

A scoring-only divide-by-zero defect affecting aggregate treatment of
tasks without uncertainty categories was repaired after inference had
completed.

The repair did not alter prompts, model outputs, frozen experimental
inputs, or inference execution.

The preflight runner hash therefore differs from the final scoring
runner hash.

## Historical Note

The first recorded ΛLingua attempt predates this archive and is
preserved separately under:

    artifacts/historical/first-gemma-attempt-T01.json
