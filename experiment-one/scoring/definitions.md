# Experiment One (acq-01) — Scoring Definitions

Status: FROZEN before any Experiment One inference. Numeric thresholds live in
`thresholds.json`. Any change after inspecting model output creates a new
experiment version.

## Parsing and alignment

- Parser: Experiment Zero `parse_lambda` (`runner/experiment_zero.py`, hash in
  frozen manifest), unchanged.
- Alignment: **strict only** for all reported Experiment One metrics. Every
  task supplies its term identifiers, so naming is not under test. Strict
  means `norm(output) == norm(canonical)`, where `norm` upper-cases and
  removes non-alphanumerics. Evidence identifiers are always strict.
- Lenient alignment (Experiment Zero Jaccard ≥ 0.5) may be computed as a
  diagnostic. It never enters a competence, ATΛ_first, ATΛ_stable, or transfer decision.
- Ground truth: `canonical_state` of each benchmark item.

Definitions per item:

- Canonical nodes `N` = assertions ∪ evidence ∪ unknowns ∪ hypotheses.
  Each node has one canonical marker: φ, ε, ?, or ĥ.
- Canonical edges `G` = `support_edges`, as ordered pairs (assertion, evidence).
- Output markers of a node = the set of markers under which the node appears
  in the output. A node that appears as the left side of `∵` counts as φ.
- Extras = output nodes or edges that do not align to the canonical state
  (Experiment Zero `extra_unsupported_state`, deduplicated).

## Preserved metrics (Experiment Zero definitions, strict mode)

| Metric | Definition |
|---|---|
| SF — Semantic Fidelity | matched canonical items (nodes preserved under the correct marker + exact edges) / (canonical items + distinct extras). Micro-averaged over items. |
| PS — Provenance Survival | canonical edges reproduced with exact endpoints and direction / canonical edges. |
| US — Uncertainty Survival | (unknowns preserved as `?` + hypotheses preserved as `ĥ`) / (canonical unknowns + hypotheses). |
| PV — Protocol Violations | records with at least one parser violation, and the total violation count. |
| TC — Total Token Cost | Ollama `prompt_eval_count` + `eval_count`, summed. Reported per call, per checkpoint, and per model. |

## New metrics

### ESF — Epistemic Status Fidelity

For each canonical node `n`, the node is **status-correct** if and only if its
set of output markers is exactly `{canonical marker of n}`. It must appear,
under the right marker, and under no other marker.

    ESF = Σ status-correct nodes / Σ |N|        (micro-averaged over items)

ESF includes evidence nodes. Edges are excluded; PS measures them. A
node that appears under both the right and a wrong marker is not
status-correct.

Reported together with ESF:

- **ESF_terms**: the same calculation restricted to φ/?/ĥ nodes.
- **Status confusion matrix**: canonical marker × output outcome, with outcomes
  {φ, ε, ?, ĥ, conflict, absent}.
- **Laundering events**: the count of hypothesis→φ and unknown→{φ, ĥ}
  (the Experiment Zero `hypothesis_laundering` and `unknown_laundering`
  detections).

ESF differs from SF in two ways. Extras do not dilute ESF, and edges do not
enter it. ESF answers one question: did each item keep its epistemic status?

### IE — Item Exact

A response is item-exact if and only if all of the following hold:

1. it is a valid record (see §Validity);
2. the parser reports zero protocol violations;
3. every canonical node is status-correct (item ESF = 1);
4. the set of output edges equals `G` exactly;
5. there are zero extras.

IE is the unit used for competence. Partial credit never counts toward
competence.

### AR — Adversarial Resistance

AR is the IE rate on items with a non-null `adversarial` tag. It is reported
overall, per adversarial subtype, and split by
`adversarial_taught_in_curriculum` (taught versus untaught trap types).

### TT — Teaching Tokens

For a model `m`, a curriculum context `k`, and an exam item `i`:

    TT(m, k, i) = prompt_eval_count(prompt(k, i)) − prompt_eval_count(prompt(NULL, i))
    TT(m, k)    = median over the items i of checkpoint k's exam form

`prompt(NULL, i)` is the standard template with an empty Section A payload.
It is measured by a token probe: one call per item with `num_predict = 1`,
output discarded, never scored. TT counts every token of the teaching
context in the model's own tokenizer. From C2 onward this includes the
model's own transcript responses. TT_bytes, the UTF-8 byte length of the
Section A payload, is reported alongside TT as a model-independent measure.

### Token accounting: ATΛ counts teaching tokens only (locked)

ATΛ_first, ATΛ_stable and BTΛ are computed from TT and therefore count only
the tokens of the teaching context (the checkpoint's Section A payload in the
model's tokenizer). They exclude:

- unseen-exam prompts (Sections B and C of every exam call are cancelled by
  the NULL difference);
- transfer-exam prompts;
- compression-evaluation prompts;
- scoring output (corrections are generated offline and never cost model
  tokens; only their text inside the transcript counts, as teaching);
- checkpoint evaluation overhead (exam generations, token probes, retries).

These costs are still reported in TC, per call, per checkpoint and per
model. TC never enters ATΛ, and ATΛ never enters TC.

### Competence

A model is **competent** at a context `k` if and only if, on that context's
full exam form, all of the thresholds in `thresholds.json` `competence` hold
simultaneously:

- every one of the 24 exam records is valid;
- IE count ≥ `min_item_exact` (20 of 24);
- ESF ≥ `min_ESF`, PS ≥ `min_PS`, US ≥ `min_US` (all 0.90);
- adversarial IE count ≥ `min_adversarial_item_exact` (6 of 8);
- laundering events ≤ `max_laundering_events` (1).

Exam form per context: C0 uses X0, C1 X1, C2 X2, C3 X3, C4 X4, and every
compression condition uses X0. All forms are structurally identical; see
`protocol.md` §Matched forms. Competence is never judged on a single
response or a subset of items.

### ATΛ_first and ATΛ_stable — Acquisition Tokens to competence

Curriculum ladder (frozen order): C0 → C1 → C2 → C3 → C4
(`protocol.md` §Checkpoints).

    k_first  = the first checkpoint at which the model is competent
    k_stable = the first checkpoint k such that the model is competent at k
               and at every later checkpoint through C4

    ATΛ_first(m)  = TT(m, k_first)
    ATΛ_stable(m) = TT(m, k_stable)          ← primary acquisition metric

- **ATΛ_stable** is the primary metric. If the model is not competent at C4,
  it is right-censored, `ATΛ_stable(m) > TT(m, C4)`, and reported as **not
  acquired**.
- **ATΛ_first** is always reported. If the model is never competent, it is
  null.
- If ATΛ_first < ATΛ_stable, the model is flagged **unstable**: it reached
  competence and then lost it at a later checkpoint.
- Also reported for each metric: the checkpoint label and **worked examples
  in context** (C0 = 0, C1 = 3, C2 = 6, C3 = 9, C4 = 12, counting
  demonstrations and corrected exercises).
- Per-skeleton IE at every checkpoint is reported as a form-difficulty
  diagnostic. It never alters a competence decision.

### BTΛ — Bootstrap compression (sub-experiment)

For each compression condition `v` ∈ {CP-100, CP-75, CP-50, CP-25, CP-EX,
CP-SYM}:

- report SF, PS, US, PV, TC, ESF, IE, AR, and competence on the unseen exam;
- BTΛ(m, v) = TT(m, v).
- **Minimal sufficient bootstrap** for a model = the condition with the
  smallest BTΛ at which the model is competent, or "none".

Compression conditions are single-shot. They contain no demonstrations,
except CP-EX, which consists only of demonstrations. They contain no
corrections. CP-100 is the same context as C0, so it is measured once and
reported in both places.

### Transfer

Transfer is evaluated at C4 on `transfer-exam.jsonl`: 8 isomorphic skeletons
× 3 domains (infrastructure, science, logistics).

- Report the full metric set per domain.
- **TΔ(d)** = IE_rate(infrastructure) − IE_rate(d), and the same for ESF. TΔ
  measures how much performance depends on vocabulary.
- **Transfer demonstrated** for a model if and only if the model is competent
  at C4 and, for each d in {science, logistics}: IE count ≥ 6 of 8 and
  ESF ≥ 0.90 (`thresholds.json` `transfer`).
- Skeleton-level paired table: for each skeleton, IE in each of the 3 domains.

## Validity

A record is **invalid** if any of the following holds:

- transport or runtime failure after the one permitted retry;
- `prompt_eval_count + num_predict > num_ctx` (context-overflow risk);
- the frozen-input hash check fails.

Invalid records are retained and reported. An invalid exam record counts as
not-IE, and it makes its checkpoint non-competent.

## Stage 0 references (not re-scored)

Experiment Zero and Phi Replication 01 used free term naming and different
items. Their scores are cited only as context and are not directly comparable.
C0 is the within-experiment baseline: the frozen full specification alone,
with no demonstrations.
