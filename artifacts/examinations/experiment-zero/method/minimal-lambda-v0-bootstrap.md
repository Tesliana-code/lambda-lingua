# ΛLingua v0 — minimal bootstrap

| Symbol | Meaning |
|---|---|
| φ | assertion |
| ε | evidence |
| ? | unknown |
| ĥ | hypothesis |
| ∵ | supported-by relation |

No other operators exist.

    φ:TERM       TERM is an assertion.
    ε:TERM       TERM is an evidence item.
    ?:TERM       TERM is unknown.
    ĥ:TERM       TERM is a hypothesis.
    φ:X ∵ ε:E1   Assertion X is supported by evidence item E1.

An unknown must not become an assertion or hypothesis.
A hypothesis must not become an assertion.
A support relation keeps both endpoints and its direction.
