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

The model preserved the assertion identity, evidence identity, and
support relation, but omitted the `φ` assertion marker and wrapped
the representation in a JSON-like structure.

This artifact is preserved verbatim as historical evidence and must
not be edited retroactively.
