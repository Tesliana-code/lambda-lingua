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

TERM is represented as an assertion.

This does not mean that TERM is objectively true.

### Evidence

    ε:TERM

TERM denotes an evidence item.

### Unknown

    ?:TERM

The status or value of TERM is unknown.

Unknown must not be silently converted into an assertion
or hypothesis.

### Hypothesis

    ĥ:TERM

TERM is represented as a hypothesis.

A hypothesis must not be interpreted as an assertion.

### Support relation

    φ:X ∵ ε:E1

Assertion X is supported by evidence item E1.

The relation records provenance.

It does not independently establish that X is true.

A support relation must preserve both endpoints, X and E1,
and the directed relation between them.

## Valid Examples

    φ:HTTP503 ∵ ε:E1

Assertion HTTP503 is supported by evidence E1.

    ?:DB_UNAVAILABLE

Whether DB_UNAVAILABLE is true is unknown.

    ĥ:OVERLOAD

OVERLOAD is a hypothesis.

    φ:TIMEOUT ∵ ε:LOG17
    ?:ROOT_CAUSE
    ĥ:NETWORK_FAILURE

These statements represent distinct epistemic states.

## Invalid Transformations

The following transformations are protocol errors.

### Hypothesis laundering

    ĥ:X

must not become:

    φ:X

without new information outside the encoded state.
