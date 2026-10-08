# ΛLingua v0 — Epistemic Core

## Vocabulary

| Symbol | Meaning |
|---|---|
| φ | assertion |
| ε | evidence |
| ? | unknown |
| ĥ | hypothesis |
| ∵ | supported-by relation |

No additional operators are part of ΛLingua v0.

## Grammar

### Assertion

    φ:TERM

### Evidence

    ε:TERM

### Unknown

    ?:TERM

Unknown must not be silently converted into an assertion
or hypothesis.

### Hypothesis

    ĥ:TERM

A hypothesis must not be interpreted as an assertion.

### Support relation

    φ:X ∵ ε:E1

Assertion X is supported by evidence item E1.

A support relation must preserve both endpoints, X and E1,
and the directed relation between them.
