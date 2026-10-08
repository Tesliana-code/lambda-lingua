# ΛLingua v0 — Epistemic Core

Status: FROZEN for Experiment Zero.

ΛLingua v0 is a minimal symbolic protocol for testing whether
heterogeneous, unmodified language models can preserve epistemic
structure and provenance across model-to-model handoffs.

This version is intentionally small.

## Prime Directive

ΛLingua is not successful because models can produce
ΛLingua-looking strings.

It is successful only if information survives translation
across heterogeneous models.

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

### Unknown laundering

    ?:X

must not become:

    φ:X

or:

    ĥ:X

without new information outside the encoded state.

### Provenance loss

    φ:X ∵ ε:E7

must not become merely:

    φ:X

when preservation of the encoded state is required.

### Provenance substitution

    φ:X ∵ ε:E7

must not become:

    φ:X ∵ ε:E9

unless the input state itself contains that relation.

## Experiment Zero Interpretation

Experiment Zero measures whether models preserve:

- assertions
- evidence identity
- unknown state
- hypothesis state
- support relations

The protocol is frozen before testing.

Models may fail to understand ΛLingua v0.

Models may produce protocol violations.

Models must not negotiate, redefine, extend, or repair
the language during Experiment Zero.

## Non-Goals

ΛLingua v0 does not define:

- delegation
- return messages
- authority
- capabilities
- mutation
- encryption
- agent identity
- transport
- protocol negotiation
- language evolution

Those belong to later experiments or to a Wire Lingua dialect.

## Version Rule

For Experiment Zero, this document is immutable.

If the language changes, the new version must receive a new
version identifier and must not replace ΛLingua v0 retroactively.
