#!/usr/bin/env python3
"""Render checkpoint exam forms X0..X4 from benchmark/exam-skeletons.json.

Deterministic. No model inference.

    python3 experiment-one/tools/build_exam_forms.py          # write benchmark/unseen-exam-X{0..4}.jsonl
    python3 experiment-one/tools/build_exam_forms.py --check  # verify files equal a fresh render
"""
import json
import re
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
BEN = EXP / "benchmark"
SKELETONS = BEN / "exam-skeletons.json"
FORMS = 5  # X0..X4 -> checkpoints C0..C4


def form_path(k):
    return BEN / f"unseen-exam-X{k}.jsonl"


def render_lambda(cs):
    lines, used = [], set()
    for a in cs["assertions"]:
        es = [e for x, e in cs["support_edges"] if x == a]
        for e in es:
            lines.append(f"φ:{a} ∵ ε:{e}")
            used.add(e)
        if not es:
            lines.append(f"φ:{a}")
    lines += [f"ε:{e}" for e in cs["evidence"] if e not in used]
    lines += [f"?:{u}" for u in cs["unknowns"]]
    lines += [f"ĥ:{h}" for h in cs["hypotheses"]]
    return "\n".join(lines)


def capitalize_sentences(text):
    return re.sub(r"(^|\. )([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def evidence_id(sk, form, slot):
    n = int(sk["id"][1:])
    return f"{sk['evidence_kind']}{1000 * (form + 1) + 10 * n + int(slot[1:])}"


def render_item(sk, form):
    fill = sk["fillers"][form]
    ev = {s: evidence_id(sk, form, s) for s in sk["evidence"]}
    values = {s: v[0] for s, v in fill.items() if s != "k"}
    if "k" in fill:
        values["k"] = fill["k"]
    values.update(ev)
    term = {s: v[1] for s, v in fill.items() if s != "k"}
    cs = {
        "assertions": [term[s] for s in sk["assertions"]],
        "evidence": [ev[s] for s in sk["evidence"]],
        "unknowns": [term[s] for s in sk["unknowns"]],
        "hypotheses": [term[s] for s in sk["hypotheses"]],
        "support_edges": [[term[a], ev[e]] for a, e in sk["support_edges"]],
    }
    item = {
        "id": f"X{form}-{sk['id'][1:]}",
        "split": "unseen",
        "form": f"X{form}",
        "checkpoint": f"C{form}",
        "skeleton": sk["id"],
        "domain": "infrastructure",
        "input": capitalize_sentences(sk["frame"].format(**values)),
        "terms": sorted(term.values()),
        "canonical_state": cs,
        "canonical_lambda": render_lambda(cs),
        "adversarial": sk["adversarial"],
        "cue_set": sk["cue_set"],
    }
    if sk["adversarial"]:
        item["adversarial_taught_in_curriculum"] = sk["adversarial_taught_in_curriculum"]
    return item


def render_all():
    doc = json.loads(SKELETONS.read_text(encoding="utf-8"))
    return {k: [render_item(sk, k) for sk in doc["skeletons"]] for k in range(FORMS)}


def serialize(items):
    return "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items)


def main():
    forms = render_all()
    if "--check" in sys.argv:
        bad = [k for k, items in forms.items()
               if not form_path(k).exists() or form_path(k).read_text(encoding="utf-8") != serialize(items)]
        print("FORMS OK" if not bad else f"FORMS DIFFER: {bad}")
        return 1 if bad else 0
    for k, items in forms.items():
        form_path(k).write_text(serialize(items), encoding="utf-8")
    print(f"wrote {FORMS} forms x {len(forms[0])} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
