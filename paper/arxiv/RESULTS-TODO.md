# Results required before paper freeze

This file separates completed evidence from future work so the manuscript does not accidentally narrate planned results as observed results.

## Already available

### Experiment Zero

- Zero-training baseline across Gemma 3 1B, Qwen 3 1.7B, and Qwen 3.5 2B.
- Frozen bootstrap conditions and archived raw outputs.
- Strict and lenient semantic scoring.
- Provenance, uncertainty, protocol-violation, and token-cost measurements.

### Phi replication

- Phi-4 Mini 3.8B replication complete.
- Full-bootstrap and minimal-bootstrap behavior archived.
- Epistemic-role reassignment examples available.

## Required next

### Experiment One

- Official acquisition run for all four model families.
- C0 through C4 checkpoint results.
- ATΛ_first.
- ATΛ_stable.
- ESF.
- Cross-domain transfer results.
- Bootstrap-compression curve.
- Competence-threshold outcomes.
- Model-family comparison table.

### Agent-Wire relay

- Final relay topology.
- Model ordering.
- Number of hops.
- Semantic drift after each hop.
- Provenance survival by hop.
- Uncertainty survival by hop.
- Epistemic-status transitions.
- Repair behavior.
- Error amplification or recovery patterns.

## Paper freeze gate

The manuscript should not be called final until every quantitative claim in the abstract, results, discussion, and conclusion has a direct artifact or reproducible derivation in the repository.
