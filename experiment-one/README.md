# ΛLingua Experiment One — Acquisition (acq-01)

Measures how efficiently heterogeneous, unmodified local models acquire
ΛLingua v0 from explicit in-context teaching. Teaching runs in stages:
demonstrations, then deterministic corrections, then an unseen exam, then
cross-domain transfer. A bootstrap-compression sub-experiment runs
alongside.

Status: design frozen, acq-01 design v1 (five disjoint, structurally matched
checkpoint exam forms; fresh-context rule; teaching-only ATΛ accounting).
**No inference has been run.**

- `protocol.md`: stages, checkpoints, prompt template, inference options, execution order
- `curriculum/`: Stage 1 demonstrations, the Stage 2 correction protocol, and the six compression conditions
- `benchmark/`: training exercises, the exam skeletons, checkpoint exam forms X0–X4, the transfer exam, and the schema
- `scoring/`: metric definitions (SF, PS, US, PV, TC, ESF, IE, AR, TT, ATΛ_first, ATΛ_stable, BTΛ) and frozen thresholds
- `tools/build_exam_forms.py`: deterministic rendering of X0–X4 from the skeletons
- `tools/verify_design.py`: design checks (form disjointness, leakage, structural identity, Experiment Zero wording) plus the frozen manifest
- `frozen-manifest.json`: sha256 of every frozen file, the base commit, and the tree state

Experiment Zero and Replication 01 are not modified. Changing any frozen file
requires a new experiment version (acq-02).
