#!/usr/bin/env python3
"""Design verification and freeze manifest for ΛLingua Experiment One (acq-01).

Runs no model inference.

    python3 experiment-one/tools/verify_design.py            # checks only
    python3 experiment-one/tools/verify_design.py --freeze   # checks + write frozen-manifest.json
    python3 experiment-one/tools/verify_design.py --check-manifest
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_exam_forms  # noqa: E402
EXP = ROOT / "experiment-one"
MANIFEST = EXP / "frozen-manifest.json"
CUR, BEN, SCO = EXP / "curriculum", EXP / "benchmark", EXP / "scoring"
SPEC = ROOT / "spec/lambda-v0.md"
EZ_BENCH = ROOT / "benchmark/microtasks-v0.jsonl"
EZ_PARSER = ROOT / "runner/experiment_zero.py"
FORMS = 5
FILLER_NGRAM = 4  # content wording: no shared 4-word sequence across forms or with teaching inputs
EZ_NGRAM = 4      # no shared 4-word sequence with Experiment Zero inputs
COMPRESSION_TARGETS = {"75": 0.75, "50": 0.50, "25": 0.25}
TOLERANCE = 0.05
STAGE0_REFERENCES = {
    "experiment_zero_scores": "artifacts/examinations/experiment-zero/summary/scores_official.json",
}
EXTERNAL_REFERENCES = {
    # Untracked on replication/phi-01-20261007 at freeze time; hashed for citation only.
    "replication_phi_01_scores": "/home/superadmin/lambda-lingua-replication-phi-01-20261007/results/summary/replication_phi_01/rphi01-20261008/scores_official.json",
    "replication_phi_01_epistemic_flips": "/home/superadmin/lambda-lingua-replication-phi-01-20261007/results/summary/replication_phi_01/rphi01-20261008/epistemic_flips.json",
}

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()


def load(name):
    return [json.loads(l) for l in (BEN / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def render(cs):
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


def words(text):
    return len(text.split())


def is_line_subsequence(sub, sup):
    it = iter(l for l in sup if l.strip())
    return all(any(l == s for s in it) for l in sub if l.strip())


def demos_from_markdown():
    text = (CUR / "stage-1-demonstrations.md").read_text(encoding="utf-8")
    out = []
    for block in text.split("## Demonstration ")[1:]:
        terms = re.search(r"^Terms: (.+)$", block, re.M).group(1).split(", ")
        lam = [l.strip() for l in block.split("ΛLingua v0:")[1].split("Why:")[0].splitlines() if l.strip()]
        src = re.search(r"Source:\n(.+)\n", block).group(1)
        out.append({"terms": terms, "lambda": lam, "input": src})
    return out


def lambda_ids(lines):
    ids = set()
    for l in lines:
        ids.update(re.findall(r"[φε?ĥ]:([A-Za-z0-9_]+)", l))
    return ids


def ngrams(text, n):
    w = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def composition(items):
    c = Counter()
    for it in items:
        cs = it["canonical_state"]
        for k in ["assertions", "evidence", "unknowns", "hypotheses", "support_edges"]:
            c[k] += len(cs[k])
            c[f"items_with_{k}"] += bool(cs[k])
        c["adversarial"] += bool(it["adversarial"])
        c["adversarial_taught"] += bool(it["adversarial"]) and it.get("adversarial_taught_in_curriculum") is True
        c["adversarial_untaught"] += bool(it["adversarial"]) and it.get("adversarial_taught_in_curriculum") is False
        c["novel_cue"] += it["cue_set"] == "novel"
    c["items"] = len(items)
    return dict(c)


def item_signature(it):
    cs = it["canonical_state"]
    return (it.get("skeleton"), len(cs["assertions"]), len(cs["evidence"]), len(cs["unknowns"]),
            len(cs["hypotheses"]), len(cs["support_edges"]), it["adversarial"],
            it.get("adversarial_taught_in_curriculum"), it["cue_set"])


def item_ids(it):
    cs = it["canonical_state"]
    return set(cs["assertions"]) | set(cs["unknowns"]) | set(cs["hypotheses"]) | set(cs["evidence"])


def verify():
    report = {}
    spec_lines = SPEC.read_text(encoding="utf-8").splitlines()

    # --- compression conditions
    check(sha(CUR / "compression-100.md") == sha(SPEC), "compression-100 not byte-identical to spec")
    full = words(SPEC.read_text(encoding="utf-8"))
    comp = {"100": {"words": full, "ratio": 1.0, "bytes": SPEC.stat().st_size}}
    prev = spec_lines
    for k in ["75", "50", "25"]:
        t = (CUR / f"compression-{k}.md").read_text(encoding="utf-8")
        r = words(t) / full
        comp[k] = {"words": words(t), "ratio": round(r, 3), "bytes": len(t.encode())}
        check(abs(r - COMPRESSION_TARGETS[k]) <= TOLERANCE, f"compression-{k} ratio {r:.3f} outside tolerance")
        check(is_line_subsequence(t.splitlines(), prev), f"compression-{k} is not deletion-only of the next level")
        prev = t.splitlines()
    sym = (CUR / "compression-symbols-only.md").read_text(encoding="utf-8")
    check(is_line_subsequence(sym.splitlines(), (CUR / "compression-25.md").read_text(encoding="utf-8").splitlines()),
          "symbols-only is not deletion-only of compression-25")
    check(not re.search(r"φ:|\?:|ĥ:|ε:", sym), "symbols-only contains grammar forms")
    comp["symbols-only"] = {"words": words(sym), "ratio": round(words(sym) / full, 3), "bytes": len(sym.encode())}
    ex = (CUR / "compression-examples-only.md").read_text(encoding="utf-8")
    demo_md = (CUR / "stage-1-demonstrations.md").read_text(encoding="utf-8")
    check(is_line_subsequence(ex.splitlines(), demo_md.splitlines()), "examples-only is not deletion-only of demonstrations")
    check("Why:" not in ex and "| φ |" not in ex, "examples-only contains explanations or spec text")
    comp["examples-only"] = {"words": words(ex), "bytes": len(ex.encode())}
    report["compression"] = comp

    # --- benchmark items
    forms = {f"X{k}": load(f"unseen-exam-X{k}.jsonl") for k in range(FORMS)}
    splits = {"train": load("acquisition-train.jsonl"), **forms, "transfer": load("transfer-exam.jsonl")}
    expected_split = {"train": "train", "transfer": "transfer", **{f: "unseen" for f in forms}}
    allids = Counter()
    for split, items in splits.items():
        for it in items:
            allids[it["id"]] += 1
            cs = it["canonical_state"]
            check(it["split"] == expected_split[split], f"{it['id']}: split mismatch")
            check(render(cs) == it["canonical_lambda"], f"{it['id']}: canonical_lambda != render(canonical_state)")
            check(it["terms"] == sorted(set(cs["assertions"]) | set(cs["unknowns"]) | set(cs["hypotheses"])),
                  f"{it['id']}: term lexicon mismatch")
            cats = [cs["assertions"], cs["evidence"], cs["unknowns"], cs["hypotheses"]]
            flat = [x for c in cats for x in c]
            check(len(flat) == len(set(flat)), f"{it['id']}: node appears in two categories")
            for a, e in cs["support_edges"]:
                check(a in cs["assertions"] and e in cs["evidence"], f"{it['id']}: bad edge {a}->{e}")
            for e in cs["evidence"]:
                check(re.search(rf"(?<![A-Za-z0-9]){re.escape(e)}(?![A-Za-z0-9])", it["input"]) is not None,
                      f"{it['id']}: evidence {e} not verbatim in input")
            check(not re.search(r"[φεĥ∵]", it["input"]), f"{it['id']}: input contains ΛLingua symbols")
    check(all(v == 1 for v in allids.values()), "duplicate item ids")

    # --- balance
    bal = {}
    for split, items in splits.items():
        bal[split] = composition(items)
        for k in ["assertions", "evidence", "unknowns", "hypotheses", "support_edges"]:
            check(bal[split][f"items_with_{k}"] >= max(3, len(items) // 4), f"{split}: {k} under-represented")
    report["balance"] = {"train": bal["train"], "each_exam_form": bal["X0"], "transfer": bal["transfer"]}
    report["adversarial_subtypes"] = {s: dict(Counter(it["adversarial"] for it in splits[s] if it["adversarial"]))
                                      for s in ["train", "X0", "transfer"]}

    # --- CHECK A: checkpoint forms are regenerated exactly from the frozen skeletons
    nfail = len(failures)
    rendered = build_exam_forms.render_all()
    for k in range(FORMS):
        check(build_exam_forms.serialize(rendered[k]) == (BEN / f"unseen-exam-X{k}.jsonl").read_text(encoding="utf-8"),
              f"X{k}: file differs from render of exam-skeletons.json")
        check(all(i["form"] == f"X{k}" and i["checkpoint"] == f"C{k}" for i in forms[f"X{k}"]),
              f"X{k}: form/checkpoint labels wrong")
    report["forms_regenerate_byte_identical"] = len(failures) == nfail

    # --- CHECK B: identical structural composition across forms
    nfail = len(failures)
    sigs = {f: sorted(item_signature(i) for i in items) for f, items in forms.items()}
    for f in forms:
        check(len(forms[f]) == 24, f"{f}: expected 24 items")
        check(sigs[f] == sigs["X0"], f"{f}: per-skeleton structural signature differs from X0")
        check(bal[f] == bal["X0"], f"{f}: aggregate composition differs from X0")
        check(sum(bool(i["adversarial"]) for i in forms[f]) == 8, f"{f}: expected 8 adversarial items")
    report["forms_structurally_identical"] = len(failures) == nfail

    # --- CHECK C: forms mutually disjoint (identifiers, inputs, filler wording)
    nfail = len(failures)
    skel = json.loads((BEN / "exam-skeletons.json").read_text(encoding="utf-8"))["skeletons"]
    filler_text = {f"X{k}": [" ".join(v if isinstance(v, str) else v[0] for v in sk["fillers"][k].values())
                             for sk in skel] for k in range(FORMS)}
    fnames = list(forms)
    for i, a in enumerate(fnames):
        for b in fnames[i + 1:]:
            ov = set().union(*map(item_ids, forms[a])) & set().union(*map(item_ids, forms[b]))
            check(not ov, f"identifier overlap {a} x {b}: {sorted(ov)}")
            check(not ({x["input"] for x in forms[a]} & {x["input"] for x in forms[b]}), f"input overlap {a} x {b}")
            ga = set().union(*(ngrams(t, FILLER_NGRAM) for t in filler_text[a]))
            gb = set().union(*(ngrams(t, FILLER_NGRAM) for t in filler_text[b]))
            check(not (ga & gb), f"filler wording overlap {a} x {b}: {sorted(' '.join(g) for g in ga & gb)}")
    report["forms_mutually_disjoint"] = len(failures) == nfail

    # --- demonstrations
    demos = demos_from_markdown()
    check(len(demos) == 3, "expected exactly 3 demonstrations")
    demo_ids = set()
    for i, d in enumerate(demos, 1):
        ids = lambda_ids(d["lambda"])
        demo_ids |= ids
        terms = {x for x in ids if not re.search(r"[0-9]$", x)}
        check(sorted(terms) == d["terms"], f"demonstration {i}: terms line does not match ΛLingua block")

    # --- stage-2 readable target table matches the training file
    s2 = (CUR / "stage-2-corrections.md").read_text(encoding="utf-8")
    table = {m.group(1): (int(m.group(2)), [x.strip().strip("`") for x in m.group(3).split(" / ")])
             for m in re.finditer(r"^\| (TR\d\d) \| (\d) \| (.+) \|$", s2, re.M)}
    check(len(table) == len(splits["train"]), "stage-2 target table size mismatch")
    for it in splits["train"]:
        rnd, lines = table.get(it["id"], (None, None))
        check(rnd == it["round"] and lines == it["canonical_lambda"].split("\n"),
              f"{it['id']}: stage-2 target table differs from acquisition-train.jsonl")

    # --- CHECK D: no exam/transfer item leaks into teaching; all identifier sets pairwise disjoint
    ez = [json.loads(l) for l in EZ_BENCH.read_text(encoding="utf-8").splitlines() if l.strip()]
    ez_ids = set().union(*(item_ids(t) for t in ez)) | lambda_ids(spec_lines)
    sets = {"demonstrations": demo_ids, "experiment_zero_and_spec": ez_ids,
            **{s: set().union(*(item_ids(i) for i in items)) for s, items in splits.items()}}
    names = list(sets)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ov = sets[a] & sets[b]
            check(not ov, f"identifier overlap {a} x {b}: {sorted(ov)}")
    nfail = len(failures)
    teaching_text = "\n".join((CUR / f).read_text(encoding="utf-8") for f in sorted(p.name for p in CUR.glob("*.md")))
    teaching_text += "\n" + (BEN / "acquisition-train.jsonl").read_text(encoding="utf-8")
    teach_inputs = [d["input"] for d in demos] + [i["input"] for i in splits["train"]]
    teach_grams = set().union(*(ngrams(t, FILLER_NGRAM) for t in teach_inputs))
    for s in list(forms) + ["transfer"]:
        for it in splits[s]:
            for x in item_ids(it):
                check(re.search(rf"(?<![A-Za-z0-9_]){re.escape(x)}(?![A-Za-z0-9_])", teaching_text) is None,
                      f"{it['id']}: {x} leaks into teaching material")
            check(it["input"] not in teach_inputs, f"{it['id']}: input duplicated in teaching")
    for f in forms:
        for t in filler_text[f]:
            ov = ngrams(t, FILLER_NGRAM) & teach_grams
            check(not ov, f"{f}: filler wording appears in teaching: {sorted(' '.join(g) for g in ov)}")
    report["no_exam_leakage_into_teaching"] = len(failures) == nfail

    # --- CHECK E: wording novelty versus Experiment Zero (every split, every form)
    ez_grams = set().union(*(ngrams(t["input"], EZ_NGRAM) for t in ez))
    per_split = {}
    for s, items in [("demonstrations", demos)] + list(splits.items()):
        hits = sorted({" ".join(g) for it in items for g in ngrams(it["input"], EZ_NGRAM) & ez_grams})
        per_split[s] = len(hits)
        check(not hits, f"{s}: shares {EZ_NGRAM}-word sequence(s) with Experiment Zero: {hits}")
    report["experiment_zero_shared_4grams_per_split"] = per_split

    # --- CHECK F: normative design locks are present in the frozen documents
    nfail = len(failures)
    protocol = (EXP / "protocol.md").read_text(encoding="utf-8")
    flat = " ".join(protocol.split())
    for phrase in (["Every checkpoint evaluation and every compression condition starts from a fresh model "
                   "conversation/context.",
                   "Only the explicitly defined curriculum transcript for that checkpoint may be present.",
                   "Teaching history persists. Exam history does not.",
                   "Previous checkpoint exam prompts/responses must never appear in later checkpoint contexts.",
                   "are independent fresh runs with no teaching, feedback, or hidden state carried between them."]
              + [f"C{k} sees only the C{k} curriculum state." for k in range(FORMS)]):
        check(phrase in flat, f"protocol.md: fresh-context rule missing: {phrase!r}")
    stage2 = " ".join((CUR / "stage-2-corrections.md").read_text(encoding="utf-8").split())
    check("Exam items are never appended to the transcript." in stage2,
          "stage-2-corrections.md: exam history exclusion missing")
    report["fresh_context_rule_locked"] = len(failures) == nfail

    nfail = len(failures)
    thr = json.loads((SCO / "thresholds.json").read_text(encoding="utf-8"))
    iso = thr.get("context_isolation", {})
    check(iso.get("fresh_context_per_call") is True and iso.get("exam_history_persists") is False,
          "thresholds.json: context_isolation not locked")
    check(sorted(iso.get("checkpoint_context", {})) == [f"C{k}" for k in range(FORMS)],
          "thresholds.json: checkpoint_context must cover C0..C4")
    report["teaching_history_only_persistence"] = len(failures) == nfail

    nfail = len(failures)
    acct = thr["acquisition"].get("token_accounting", {})
    excluded = ["unseen-exam prompts", "transfer-exam prompts", "compression-evaluation prompts",
                "scoring output", "checkpoint evaluation overhead"]
    check(acct.get("ATΛ_counts") == "teaching tokens only (TT)", "thresholds.json: ATΛ not teaching-only")
    check(acct.get("excluded") == excluded and acct.get("excluded_costs_reported_in") == "TC",
          "thresholds.json: ATΛ exclusions incomplete")
    check(thr["acquisition"].get("primary_metric") == "ATΛ_stable", "primary metric must be ATΛ_stable")
    defs = (SCO / "definitions.md").read_text(encoding="utf-8")
    check("ATΛ counts teaching tokens only (locked)" in defs, "definitions.md: ATΛ accounting section missing")
    for e in excluded:
        check(e in defs, f"definitions.md: ATΛ exclusion not documented: {e}")
    report["atl_teaching_token_only_accounting"] = len(failures) == nfail
    check(sha(CUR / "compression-100.md") == sha(SPEC), "spec drift")
    return report


def frozen_files():
    files = sorted(p for p in EXP.rglob("*") if p.is_file() and p != MANIFEST and "__pycache__" not in p.parts)
    return {str(p.relative_to(ROOT)): sha(p) for p in files}


def freeze(report):
    tracked_dirty = git("status", "--porcelain", "--untracked-files=no")
    untracked = git("status", "--porcelain", "--untracked-files=all").splitlines()
    outside = [l for l in untracked if not l[3:].startswith("experiment-one/")]
    check(not tracked_dirty, f"tracked tree not clean: {tracked_dirty}")
    check(not outside, f"changes outside experiment-one/: {outside}")
    if failures:
        return None
    m = {
        "experiment": "lambda-lingua-acquisition-01",
        "version": "acq-01",
        "status": "FROZEN — design only; no inference run",
        "frozen_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "git": {
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "base_commit": git("rev-parse", "HEAD"),
            "tracked_tree_clean": not tracked_dirty,
            "untracked_scope": "experiment-one/ only, added by the freeze commit whose parent is base_commit",
        },
        "language": {"spec/lambda-v0.md": sha(SPEC)},
        "reused_parser": {"runner/experiment_zero.py": sha(EZ_PARSER)},
        "experiment_zero_benchmark": {"benchmark/microtasks-v0.jsonl": sha(EZ_BENCH)},
        "stage0_references": {k: {"path": v, "sha256": sha(ROOT / v)} for k, v in STAGE0_REFERENCES.items()},
        "external_references_uncommitted": {k: {"path": v, "sha256": sha(v) if Path(v).exists() else None}
                                            for k, v in EXTERNAL_REFERENCES.items()},
        "files": frozen_files(),
        "verification": report,
    }
    m["files_aggregate_sha256"] = hashlib.sha256(
        "".join(f"{h}  {p}\n" for p, h in m["files"].items()).encode()).hexdigest()
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return m


def check_manifest():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cur = frozen_files()
    bad = sorted(set(cur.items()) ^ set(m["files"].items()))
    check(not bad, f"manifest mismatch: {bad}")
    check(sha(SPEC) == m["language"]["spec/lambda-v0.md"], "spec hash mismatch")
    check(sha(EZ_PARSER) == m["reused_parser"]["runner/experiment_zero.py"], "parser hash mismatch")


def main():
    if "--check-manifest" in sys.argv:
        check_manifest()
        print("MANIFEST OK" if not failures else "\n".join(["MANIFEST FAIL"] + failures))
        return 1 if failures else 0
    report = verify()
    if "--freeze" in sys.argv and not failures:
        m = freeze(report)
        if m:
            print(f"manifest: {MANIFEST.relative_to(ROOT)}  aggregate={m['files_aggregate_sha256']}")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("DESIGN OK" if not failures else "\n".join(["DESIGN FAIL"] + failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
