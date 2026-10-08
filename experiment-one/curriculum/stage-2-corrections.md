# Stage 2 — Corrective Teaching Protocol

Status: FROZEN for Experiment One (acq-01). Any change creates a new experiment version.

This file defines how corrective exercises are presented and how corrections
are generated. It is not itself inserted into model prompts; only the
transcript blocks defined below are.

## Exercises

- Source: `benchmark/acquisition-train.jsonl` (TR01–TR09), infrastructure domain only.
- Rounds: exactly 3, presented in file order.
  - Round 1: TR01, TR02, TR03
  - Round 2: TR04, TR05, TR06
  - Round 3: TR07, TR08, TR09
- No item from `unseen-exam-X0.jsonl` … `unseen-exam-X4.jsonl` or `transfer-exam.jsonl` ever appears in a
  teaching context. Exam and transfer terms and evidence identifiers are
  disjoint from all teaching material (verified by `tools/verify_design.py`).

## Procedure per exercise

1. Build the exercise prompt with the standard template (`protocol.md` §Prompt
   template). Its Section A curriculum payload is:
   `compression-100.md` + `stage-1-demonstrations.md` + the transcript so far.
2. Generate once, with the frozen inference options.
3. Preserve the full raw response unedited in the run record.
4. Append one transcript block (below) containing the visible response
   verbatim and the deterministic correction.
5. Continue with the next exercise. Corrections are never negotiated,
   discussed, or extended. The model is never asked to revise its answer.

Every model sees the same exercises and the same correction rules. The
transcript differs between models only because each model's own responses
are embedded verbatim.

## Transcript block (exact format)

The transcript starts with this header line, then a blank line, and is placed
after the demonstrations in Section A:

    # ΛLingua v0 — Corrected Exercises

Each exercise appends:

    ## Exercise {n}

    Source:
    {input}

    Terms: {terms joined with ", "}

    Your response:

    {visible response, verbatim; each line indented by 4 spaces; "(empty)" if empty}

    Correction:
    Result: {EXACT | NOT EXACT}

    Canonical ΛLingua v0:

    {canonical_lambda; each line indented by 4 spaces}

    Differences:
    {difference lines, or "- none"}

`{n}` runs from 1 to 9 across the three rounds. Blocks are separated by one
blank line.

## Correction generation (deterministic)

Responses are parsed with the Experiment Zero ΛLingua parser
(`runner/experiment_zero.py`, `parse_lambda` and `align`, **strict** mode
only; sha256 recorded in the frozen manifest). Term identity is strict
normalized match (case and non-alphanumerics ignored). Evidence identity is
strict.

`Result: EXACT` if and only if the response passes the item-exact criterion
(IE) defined in `scoring/definitions.md`. Otherwise `NOT EXACT`.

Difference lines are emitted in the group order below. Within each group,
lines follow canonical render order (assertions, standalone evidence,
unknowns, hypotheses), then lexicographic order for non-canonical items.
At most 3 FORMAT lines are emitted; offending line text is truncated to 80
characters.

| Group | Condition | Line (exact text) |
|---|---|---|
| 1 FORMAT | empty output | `- FORMAT: the response was empty.` |
| 1 FORMAT | code fence line | `- FORMAT: code fences are not ΛLingua v0 lines.` |
| 1 FORMAT | other non-protocol line | `- FORMAT: "{line}" is not a ΛLingua v0 line.` |
| 2 STATUS | canonical node absent | `- MISSING: {m}:{T} is required.` |
| 2 STATUS | node present only under wrong marker(s) | `- WRONG STATUS: {T} must be {m}:{T}, not {m'}:{T}.` |
| 2 STATUS | node present under correct and other marker | `- CONFLICT: {T} must appear only as {m}:{T}; it also appears as {m'}:{T}.` |
| 3 SUPPORT | canonical edge absent, other edge on same assertion | `- WRONG SUPPORT: φ:{X} ∵ ε:{E'} is not in the source; the source gives φ:{X} ∵ ε:{E}.` |
| 3 SUPPORT | canonical edge absent, no edge on that assertion | `- MISSING SUPPORT: φ:{X} ∵ ε:{E} is required.` |
| 3 SUPPORT | output edge not canonical (not covered above) | `- EXTRA SUPPORT: {left} ∵ {right} is not in the source.` |
| 4 EXTRA | output node not in the source state | `- EXTRA: {m}:{T} is not in the source state.` |

`{m}` is the canonical marker, `{m'}` the marker found in the output, `{T}`
the canonical term spelling. Multiple wrong markers are listed in the order
φ, ε, ?, ĥ, joined with ", ".

### Rule lines

Rule lines quote the frozen specification verbatim and add nothing. Each is
emitted at most once per correction, directly after the first difference
line that triggers it:

| Trigger | Rule line |
|---|---|
| hypothesis written as φ | `  Rule: A hypothesis must not be interpreted as an assertion.` |
| unknown written as φ or ĥ | `  Rule: Unknown must not be silently converted into an assertion or hypothesis.` |
| any SUPPORT group line | `  Rule: A support relation must preserve both endpoints, X and E1, and the directed relation between them.` |

No other explanatory text is permitted. In particular, corrections must not
paraphrase the source, introduce new vocabulary, give hints about later
items, or comment on the model.

## Canonical targets

| Item | Round | Canonical ΛLingua v0 |
|---|---|---|
| TR01 | 1 | `φ:QUEUE_SIZE_LIMIT_REACHED ∵ ε:LOG201` |
| TR02 | 1 | `?:REPLICA_FELL_BEHIND` / `ĥ:REPLICA_SLOW_DISK_WRITES` |
| TR03 | 1 | `φ:DEPLOYMENT_ROLLED_BACK` / `ε:METRIC203` |
| TR04 | 2 | `φ:GATEWAY_DROPPED_CONNECTIONS ∵ ε:TRACE204` / `φ:GATEWAY_RESTARTED ∵ ε:LOG205` / `?:RESTART_CAUSED_DROPS` |
| TR05 | 2 | `φ:SCHEDULER_SKIPPED_JOBS ∵ ε:LOG206` / `φ:SCHEDULER_OUT_OF_MEMORY ∵ ε:LOG206` / `ĥ:SCHEDULER_MEMORY_LEAK` |
| TR06 | 2 | `φ:INBOUND_TRAFFIC_BLOCKED ∵ ε:LOG207` / `?:FIREWALL_RULE_CHANGED` / `ĥ:FIREWALL_CHANGE_BLOCKED_TRAFFIC` |
| TR07 | 3 | `φ:N3_MARKED_UNHEALTHY ∵ ε:E208` / `ε:E209` / `?:N3_OVERLOADED` |
| TR08 | 3 | `φ:H7_DISK_FULL` / `φ:H7_LOG_ROTATION_DISABLED ∵ ε:LOG210` / `ĥ:LOG_ROTATION_CAUSED_FULL_DISK` |
| TR09 | 3 | `φ:ZONE_FILE_TYPO ∵ ε:E211` / `φ:PAYMENTS_RESOLUTION_FAILED ∵ ε:E212` / `?:TYPO_AFFECTED_PAYMENTS` / `ĥ:STALE_RESOLVER_CACHE` |

The authoritative target is the `canonical_lambda` field in
`benchmark/acquisition-train.jsonl`; this table is a readable copy and is
checked against it by `tools/verify_design.py`.

## Checkpoints

After each round closes, that checkpoint's own exam form is administered
with the curriculum prefix frozen at that point: C2 on X2 after round 1, C3 on
X3 after round 2, and C4 on X4 after round 3. Exam items are never appended
to the transcript.
