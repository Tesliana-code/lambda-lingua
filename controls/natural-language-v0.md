# Natural-Language Control v0

Status: FROZEN for Experiment Zero.

This control is used to compare natural-language semantic transport
against ΛLingua v0.

For each task, represent the supplied epistemic state in concise
natural language.

Preserve exactly:

- which items are assertions
- which identifiers are evidence
- which items are unknown
- which items are hypotheses
- which evidence item supports which assertion

Do not add new facts.

Do not convert hypotheses into assertions.

Do not convert unknowns into assertions or hypotheses.

Do not substitute one evidence identifier for another.

Do not remove provenance relations.

The output may use ordinary natural language, but it must preserve
the complete epistemic structure of the source state.

Models must not negotiate or modify these rules during Experiment Zero.
