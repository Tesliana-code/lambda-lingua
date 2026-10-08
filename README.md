# ΛLingua: a language for AI models

ΛLingua is a small symbolic language for representing epistemic state across different language models.

The experiment asks whether a model can receive a compact specification for a language it has never seen before, acquire enough of that language in context, and preserve meaning when the information moves to another model.

The interesting part is not whether a model can produce strings that *look* like ΛLingua. The interesting part is whether assertions stay assertions, uncertainty stays uncertainty, evidence remains attached to the right claim, and hypotheses do not quietly turn into facts.

That gives us something concrete to measure.

## The core language

The current frozen ΛLingua v0 core has five operators:

    φ   assertion
    ε   evidence
    ?   unknown
    ĥ   hypothesis
    ∵   supported by

Example:

    φ:HTTP503 ∵ ε:E1

This means that `HTTP503` is represented as an assertion supported by evidence `E1`.

The marker `φ` does not certify objective truth. It records the epistemic role assigned to a proposition inside the current state.

Likewise:

    ?:DNS_CAUSED_INCIDENT

means that DNS causality is unresolved.

And:

    ĥ:MEMORY_PRESSURE_CAUSED_RESTART

records a hypothesis.

The point of the language is to keep those distinctions explicit while information moves between models.

## Why this is interesting

A handoff can preserve the vocabulary of an observation while changing its status.

A source may say that a service failed and that DNS is one possible cause. A later model may summarize the same material as a DNS-caused failure.

The subject survived. The epistemic structure did not.

ΛLingua turns that kind of drift into an observable failure.

A successful handoff therefore has to preserve more than terms. It has to preserve the structure that says what is asserted, what supports it, what remains open, and what is still hypothetical.

That is the working criterion behind the project:

> ΛLingua succeeds when information survives translation across heterogeneous models.

## Experiment Zero: zero-training acquisition

Experiment Zero tested whether local models could use a frozen ΛLingua specification without fine-tuning or weight updates.

The initial model set was:

- Gemma 3 1B
- Qwen 3 1.7B
- Qwen 3.5 2B

A later replication added Phi-4 Mini 3.8B.

Each model received frozen tasks under controlled bootstrap conditions. Raw responses were preserved verbatim.

The models developed noticeably different failure profiles.

### Gemma

One early canonical target was:

    φ:HTTP503 ∵ ε:E1

Gemma returned a JSON-like representation that preserved the claim, evidence identifier, and support relation while dropping the canonical `φ` form.

On another task it returned only:

    φ

That was useful. It separated semantic pickup from syntax compliance.

### Qwen

Qwen 3 1.7B generally showed stronger protocol discipline.

Qwen 3.5 2B was especially interesting around provenance. It could preserve evidence relationships even when uncertainty handling was weaker.

Those are different errors. A model can remember which evidence supports a claim and still change the claim's epistemic status.

### Phi

Phi produced one of the clearest examples of why syntax alone is a poor success criterion.

The canonical state was:

    φ:HEALTH_CHECK_FAILED ∵ ε:E7
    ε:E8
    ?:DNS_CAUSED_INCIDENT

Phi returned:

    φ:DNS_LOOKUP ∵ ε:E8
    ?:HEALTH_CHECK_FAILURE
    ĥ:DNS_CAUSE

The output was recognizably ΛLingua, but the roles had moved. The health-check failure became unknown, DNS causality became a hypothesis, and the evidence relation changed.

Across the full replication, Phi performed much better with the complete bootstrap than with the minimal one. That result changed the next question we wanted to ask.

## Experiment One: how much teaching is enough?

Experiment Zero asked whether models could pick up the protocol.

Experiment One measures acquisition.

Every model receives the same frozen curriculum. The experiment tracks how much teaching is required before the model reaches stable competence on unseen material.

The curriculum has five checkpoints:

    C0   specification only
    C1   + 3 worked demonstrations
    C2   + corrective round 1
    C3   + corrective round 2
    C4   + corrective round 3

Teaching uses nine exercises. Corrections are deterministic and generated from the frozen canonical state.

Evaluation uses a separate exam form at every checkpoint:

    C0 → X0
    C1 → X1
    C2 → X2
    C3 → X3
    C4 → X4

Each form contains 24 items built from the same 24 epistemic skeletons with disjoint content. This avoids teaching the model through repeated exposure to the exam while keeping structural difficulty matched.

The current corpus contains:

- 120 checkpoint examination items
- 24 cross-domain transfer items
- 9 teaching exercises
- 3 worked demonstrations

The design is frozen before acquisition inference begins.

## Cross-domain transfer

A model may learn the surface language of incident response without learning ΛLingua itself.

The transfer exam tests the same epistemic structures across infrastructure, science, and logistics settings. The structure stays comparable while the subject matter changes.

If performance survives that shift, the evidence for protocol acquisition becomes much stronger.

## Bootstrap compression

Experiment One also asks how much of the specification can be removed before acquisition breaks.

The frozen compression conditions are:

    CP-100   full specification
    CP-75
    CP-50
    CP-25
    CP-EX    examples only
    CP-SYM   symbols only

The percentage variants are built by controlled deletion from the full specification. They are not rewritten after seeing model behavior.

This gives us a bootstrap compression curve for each model family.

## Metrics

The project uses several complementary measurements.

**SF — Semantic Fidelity**  
How much of the intended semantic state survives?

**PS — Provenance Survival**  
Does evidence stay connected to the right claims?

**US — Uncertainty Survival**  
Does information marked unknown remain unknown?

**PV — Protocol Violations**  
How often does the emitted representation violate the frozen protocol?

**ESF — Epistemic Status Fidelity**  
How often does each canonical node remain under its correct epistemic marker?

**TC — Total Token Cost**  
How expensive was the full interaction?

### ATΛ — Acquisition Tokens

Experiment One adds a direct measure of teaching cost.

`ATΛ_first` is the first checkpoint at which a model reaches the frozen competence threshold.

`ATΛ_stable` is the first checkpoint from which competence persists through every later checkpoint.

The stable value is the primary acquisition measure. It distinguishes a durable acquisition point from a temporary score spike.

ATΛ counts teaching tokens only. Evaluation cost remains part of TC.

## The final experiment: model-to-model transmission

The eventual goal is to move from individual acquisition to communication.

Once the acquisition work is complete, ΛLingua will be placed inside a controlled Agent-Wire relay. A semantic state will pass through heterogeneous models while every handoff is recorded.

For example:

    source
      ↓
    Gemma
      ↓ Λ
    Qwen
      ↓ Λ
    Phi
      ↓ Λ
    Qwen
      ↓
    reconstructed state

The model order can then be changed and the experiment repeated.

This phase will measure semantic drift across handoffs, provenance decay, uncertainty laundering, hypothesis inflation, evidence mutation, error amplification, and repair behavior.

The interesting question becomes:

> Can a group of different models maintain a shared epistemic state while information moves through the chain?

Agent-Wire provides the durable trace needed to locate exactly where a state changed.

At that point ΛLingua becomes more than an output notation. It becomes an experimental semantic transport layer between heterogeneous machine reasoners.

## ΛLingua and Wire Lingua

ΛLingua is the language.

Wire Lingua is the proposed coordination dialect that may eventually extend the same ideas to delegation, return semantics, constraints, and other agent-to-agent operations.

The distinction keeps the epistemic core small enough to study cleanly.

Agent-Wire and Deaddrop remain separate systems with their own contracts. ΛLingua can consume those interfaces during later experiments without becoming part of their core protocol.

## Reproducibility

The project freezes experimental inputs before inference.

Current safeguards include:

- versioned specifications and benchmark files
- SHA-256 manifests
- disjoint checkpoint exam forms
- deterministic exam generation
- automated leakage checks
- pinned model identities and digests
- fresh model context for independent evaluations
- verbatim raw-response preservation
- deterministic scoring definitions
- explicit competence thresholds fixed before results are inspected

Experiment Zero artifacts are preserved separately from later replications. Experiment One has its own frozen acquisition design and runner.

A change to a frozen protocol, benchmark, threshold, or inference condition creates a new experiment version rather than silently rewriting the old one.

## Research direction

The project is moving through three questions.

**Can models acquire ΛLingua from a specification?**

Experiment Zero established the first baseline.

**How much teaching is required for stable acquisition?**

Experiment One measures the acquisition curve.

**Does the language survive communication between heterogeneous models?**

The Agent-Wire relay will test that directly.

The language itself remains tiny:

    φ  ε  ?  ĥ  ∵

The experiment is about how much semantic structure those five symbols can carry.

    φ:Λ ∵ ε:experiment
