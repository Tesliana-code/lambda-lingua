# Historical Artifacts

## First ΛLingua model attempt

Model: `gemma3:1b`
Task: `T01`
Protocol: `ΛLingua v0`
Date: 2026-10-07

This is the first recorded model attempt in ΛLingua Experiment Zero.

Canonical target:

    φ:HTTP503 ∵ ε:E1

Gemma returned:

    {
      "HTTP503": "∵ ε:E1"
    }

Interpretation:

- assertion identity preserved
- evidence identity preserved
- support relation preserved
- assertion marker `φ` omitted
- output reformatted into a JSON-like structure

The model preserved much of the semantic state while violating
the canonical ΛLingua representation.

This artifact is preserved verbatim and must not be edited
retroactively.
