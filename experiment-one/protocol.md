# Experiment One (acq-01) — Acquisition Curriculum Protocol

Status: DESIGN FROZEN, acq-01 design v1 (disjoint checkpoint exam forms,
fresh-context rule, teaching-only ATΛ accounting). No inference has been run.

## Question

How many teaching tokens and examples does a previously untrained model need
before it reliably preserves ΛLingua v0 semantics, provenance, uncertainty,
and epistemic status on unseen tasks?

## Invariants

- Language: ΛLingua v0 (`spec/lambda-v0.md`, sha256 `2230db56…7cac`),
  unchanged. Experiment One does not create a new language version.
- Learning is in-context only. No fine-tuning, no LoRA, and no weight changes.
- Experiment Zero, the Replication 01 artifacts, and their branches are
  read-only.
- Exam and transfer items never appear in any teaching context.
- Examples, corrections, compression variants, thresholds, and scoring are
  fixed before inference. Any later change becomes acq-02.

## Models (fixed)

| Model | Ollama digest |
|---|---|
| gemma3:1b | `8648f39daa8fbf5b18c7b4e6a8fb4990c692751d49917417b8842ca5758e7ffc` |
| qwen3:1.7b | `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` |
| qwen3.5:2b | `324d162be6ca5629ae4517c8710434d0bd2d665bc94dbad46e9af8fbf8a2f0df` |
| phi4-mini:3.8b-q4_K_M | `78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753` |

Preflight must verify these digests. A different digest aborts the run.

## Inference options (frozen)

    temperature = 0, seed = 0, num_ctx = 12288, num_predict = 512,
    think = false, keep_alive = 0, stream = false

Calls use stateless `/api/generate`. Every call is a fresh context, so no
model state carries between calls. `num_ctx` is raised from 4096 in
Experiment Zero because the C4 context carries 12 worked examples. Transport
or runtime failures may be retried once, as in Experiment Zero. The same
VRAM and RAM safety guards as Experiment Zero apply.

## Prompt template (frozen)

    SECTION A — ΛLINGUA CURRICULUM

    {curriculum payload}

    SECTION B — TASK

    Source:
    {input}

    Terms: {terms joined with ", "}

    SECTION C — INSTRUCTION

    Represent the epistemic state using ΛLingua v0 only.
    Use the listed term identifiers exactly and evidence identifiers exactly as written in the source.
    Do not explain.
    Do not redefine, extend, or negotiate the protocol.
    Return only the ΛLingua representation.

Curriculum files are inserted byte-for-byte, with trailing newlines stripped.
Concatenated payload parts are joined by exactly one blank line. The NULL
context (token probe only) omits the curriculum payload and keeps the
Section A header line.

## Curriculum stages

| Stage | What | Context (Section A payload) | Feedback |
|---|---|---|---|
| 0 Baseline | Cite Experiment Zero (`artifacts/examinations/experiment-zero/`) and Phi Replication 01 (`rphi01-20261008`). Not re-run. | — | — |
| 1 Demonstration | 3 canonical demonstrations, each with source, ΛLingua, and a short "why" per category. | `compression-100.md` + `stage-1-demonstrations.md` | none |
| 2 Corrective | 3 rounds × 3 exercises (TR01–TR09), each followed by a deterministic correction. | Stage 1 + growing transcript (`stage-2-corrections.md`) | deterministic, fixed |
| 3 Unseen exam | Form X4 (X4-01…X4-24) after the full curriculum. | C4 | none |
| 4 Transfer | 24 items: 8 isomorphic skeletons × {infrastructure, science, logistics}. | C4 | none |

All teaching material is infrastructure-domain. Stage 4 tests whether the
learned behaviour carries beyond incident vocabulary.

## Checkpoints (acquisition ladder)

| Checkpoint | Section A payload | Worked examples |
|---|---|---|
| C0 | `compression-100.md` | 0 |
| C1 | C0 + `stage-1-demonstrations.md` (Stage 1 measurement) | 3 |
| C2 | C1 + transcript of round 1 | 6 |
| C3 | C1 + transcript of rounds 1–2 | 9 |
| C4 | C1 + transcript of rounds 1–3 (Stage 3 measurement) | 12 |

Each checkpoint has its own exam form, and no item is administered at two
checkpoints:

| Checkpoint | Exam form | File |
|---|---|---|
| C0 | X0-01 … X0-24 | `benchmark/unseen-exam-X0.jsonl` |
| C1 | X1-01 … X1-24 | `benchmark/unseen-exam-X1.jsonl` |
| C2 | X2-01 … X2-24 | `benchmark/unseen-exam-X2.jsonl` |
| C3 | X3-01 … X3-24 | `benchmark/unseen-exam-X3.jsonl` |
| C4 | X4-01 … X4-24 | `benchmark/unseen-exam-X4.jsonl` |

### Matched forms

All five forms come from the same 24 epistemic skeletons
(`benchmark/exam-skeletons.json`, K01–K24), rendered by
`tools/build_exam_forms.py`. Item `Xk-nn` is skeleton `Knn` filled with
content set `k`. Every skeleton fixes these properties:

- the sentence frame, including its epistemic cue phrasing;
- the number of assertions, evidence items, unknowns, and hypotheses;
- the support-edge pattern and the order evidence is mentioned in;
- the adversarial subtype, taught or untaught trap type, and cue novelty
  (taught or novel).

Between forms only the content changes: event descriptions, term
identifiers, and evidence identifiers. Evidence identifiers are
`{kind}{1000·(k+1) + 10·skeleton + slot}`, so their ranges are disjoint per
form.

The cue frames are shared across forms on purpose. They are the controlled
"protocol cue vocabulary" that keeps difficulty matched. All content wording
is disjoint. `tools/verify_design.py` enforces each guarantee:

1. Forms are mutually disjoint. No term or evidence identifier, full input,
   or 4-word content (filler) sequence is shared between any two forms.
2. No checkpoint item leaks into teaching. No exam or transfer identifier
   appears in any curriculum file or training item, and no form's content
   shares a 4-word sequence with any demonstration or training input.
3. Every form has the same structure. The per-skeleton structural
   signatures are identical, and so are the aggregate counts of assertions,
   evidence, unknowns, hypotheses, edges, adversarial items, taught and
   untaught traps, and novel cues.
4. No form shares a 4-word sequence with any Experiment Zero input.
5. Every form file matches a fresh render of the skeleton file byte for byte.

Residual risk: content-specific difficulty is controlled only through
matched structure, not calibrated empirically. Per-skeleton IE is reported at
every checkpoint so that difficulty differences between forms can be
inspected after the run. They must never be used to re-weight or drop items.

Exam items never enter a context, and every exam call is independent. C0 is
the within-experiment baseline under the new task format (term identifiers
supplied). It is a new condition on new items, not a re-run of Experiment
Zero.

## Context isolation (normative)

FRESH-CONTEXT RULE. Every checkpoint evaluation and every compression
condition starts from a fresh model conversation/context. Only the
explicitly defined curriculum transcript for that checkpoint may be present.
Teaching history persists. Exam history does not.

- C0 sees only the C0 curriculum state.
- C1 sees only the C1 curriculum state.
- C2 sees only the C2 curriculum state.
- C3 sees only the C3 curriculum state.
- C4 sees only the C4 curriculum state.
- Previous checkpoint exam prompts/responses must never appear in later
  checkpoint contexts.
- Compression conditions CP-100 / CP-75 / CP-50 / CP-25 / CP-EX / CP-SYM are
  independent fresh runs with no teaching, feedback, or hidden state carried
  between them.

Implementation consequences, binding on the runner:

- Every call is a single stateless `/api/generate` request (no `context`
  field, no chat history, `keep_alive = 0`). The prompt is the complete
  input; nothing else reaches the model.
- The Section A payload of a call is exactly the checkpoint's curriculum
  state from §Checkpoints: the compression file, plus the demonstrations
  from C1 on, plus the corrected-exercise transcript of the closed rounds
  from C2 on. Exercise prompts (Stage 2) use the transcript so far.
- Only exercise responses and their corrections enter the transcript. Exam,
  transfer, token-probe, and compression-condition prompts and responses are
  never written into any later prompt.
- Each exam item is its own call; items of the same form do not see each
  other.
- The runner records the sha256 of every Section A payload; all items of one
  checkpoint must share one payload hash, and that payload must be a prefix
  of the next checkpoint's payload (teaching history persists).

## Bootstrap compression sub-experiment

Single-shot conditions with no corrections, all examined on form X0. These
conditions are parallel, not sequential. None of them involves teaching or
feedback, and each call is independent, so using one form across them
gives a paired comparison between compression levels with no exposure
between conditions. CP-100 is the same measurement as C0.

| Condition | File | Construction | Words (ratio to 100) |
|---|---|---|---|
| CP-100 | `compression-100.md` | byte-identical to `spec/lambda-v0.md` | 459 (1.000) |
| CP-75 | `compression-75.md` | deletion-only subset of spec lines | 349 (0.760) |
| CP-50 | `compression-50.md` | deletion-only subset of CP-75 | 219 (0.477) |
| CP-25 | `compression-25.md` | deletion-only subset of CP-50 | 112 (0.244) |
| CP-EX | `compression-examples-only.md` | Stage 1 demonstrations with the "Why" blocks deleted; no spec text | 137 |
| CP-SYM | `compression-symbols-only.md` | title + vocabulary table + "No additional operators" line | 48 (0.105) |

The percentage targets refer to whitespace-delimited words in the spec, with
a ±0.05 tolerance. Variants are produced by deleting lines and never by
rewording, and they are nested (25 ⊂ 50 ⊂ 75 ⊂ 100). Model-native token
counts (BTΛ) are measured at run time. Variants will not be re-tuned after
any model output is seen.

## Benchmark

| File | Items | Adversarial | Domain |
|---|---|---|---|
| `acquisition-train.jsonl` | 9 | 4 (all trap types taught) | infrastructure |
| `exam-skeletons.json` | 24 skeletons × 5 content sets | — | infrastructure |
| `unseen-exam-X0.jsonl` … `-X4.jsonl` | 24 each (120 total) | 8 each (5 taught-type, 3 untaught-type) | infrastructure |
| `transfer-exam.jsonl` | 24 | 9 (3 skeletons × 3 domains) | infra / science / logistics |

Adversarial subtypes target plausible-world reconstruction, the failure mode
seen in Phi T08:

- `plausible_cause`: a causal link that world knowledge suggests but the
  source marks unknown.
- `orphan_evidence`: topical evidence on file that supports nothing. The
  trap is attaching it to an assertion or hypothesis.
- `unsupported_assertion`: an assertion with no evidence next to an
  unrelated evidence-backed assertion.
- `obvious_hypothesis`: a near-certain explanation that the source only
  proposes.
- `lexical_trap`: an asserted term containing UNKNOWN or HYPOTHESIS.
- `crossed_evidence_late_qualifier`: evidence identifiers given out of
  mention order, and a hypothesis qualifier placed after the claim.

Element balance, disjointness, and absence of Experiment Zero wording are
checked by `tools/verify_design.py`. The results are recorded in the frozen
manifest.

## Execution order (per model, models in table order)

1. Preflight: model digests, frozen-manifest hash check, clean tree, and the
   same safety guards as Experiment Zero.
2. Token probe: NULL × all items of X0–X4 (`num_predict = 1`, not scored).
3. CP-100/C0 exam on X0. Then CP-75, CP-50, CP-25, CP-EX, and CP-SYM, each on X0.
4. C1 exam on X1.
5. Round 1 exercises, then the C2 exam on X2. Round 2, then C3 on X3. Round 3, then C4 on X4.
6. Transfer exam at C4.

Planned calls: 393 per model (120 probes + 6 × 24 compression/C0 + 24 C1 + 9
exercises + 3 × 24 C2–C4 + 24 transfer), 1572 in total.

## Records

Each call is recorded as in Experiment Zero: the exact prompt and its sha256,
the raw response, the visible response, token counts, timing, VRAM, and
`done_reason`. Exercise records also store the generated correction text and
its sha256. Raw records are never edited.

## Runner

The Experiment One runner is not part of this design freeze. It must
implement this protocol exactly, reuse the Experiment Zero parser unchanged,
and be reviewed separately. Its sha256 is recorded at preflight, alongside a
check that every file in `frozen-manifest.json` still matches its hash.
