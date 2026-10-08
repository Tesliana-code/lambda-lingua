#!/usr/bin/env python3
"""ΛLingua Experiment One (acq-01) — acquisition runner.

Implements experiment-one/protocol.md exactly. The ΛLingua parser, strict
alignment, Experiment Zero scorer and the inference safety harness are
imported unchanged from runner/experiment_zero.py.

Subcommands (all inference subcommands take --run-id):

  selftest   offline checks: prompt construction, context isolation, correction
             generator, scorer, call plan. No Ollama calls.
  plan       print the per-model call plan (no Ollama calls)
  preflight  manifest + design verification, worktree/branch/HEAD, clean tree,
             pinned model digests, Ollama, GPU/RAM baseline
  smoke      hardware/context smoke (2 calls per model, training item TR01 only,
             never scored): NULL probe + worst-case C4-sized context
  official   the 393 planned calls per model, models in protocol order;
             resumable, stoppable between calls/batches (see --stop-after, STOP file)
  score      deterministic scoring of raw records into results/summary/acquisition_01/
  stop       create the STOP file for a run; the runner halts before its next call

Context isolation (protocol.md §Context isolation, normative):
  * every call is one stateless /api/generate request (no `context`, no chat
    history, keep_alive=0); the runner checks no model is resident before a call;
  * the Section A payload is built only by curriculum_payload(), whose inputs are
    the frozen curriculum files and the stored *exercise* records of closed rounds;
    exam, transfer, probe, compression and smoke records are never read back into
    any prompt;
  * every item of a checkpoint shares one payload sha256, and C(k) is a prefix of
    C(k+1); both are asserted before each batch.
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import experiment_zero as ez  # noqa: E402  (parser, scorer, safety harness; unchanged)

ROOT = ez.ROOT
EXPECTED_ROOT = "/home/superadmin/lambda-lingua-acquisition-01-20261008"
EXPECTED_BRANCH = "experiment/acquisition-01-20261008"
FREEZE_COMMIT = "e7b7a46b589770f1bed09020aabddf49a9e5c444"
MANIFEST_REL = "experiment-one/frozen-manifest.json"
MANIFEST_SHA256 = "a92ca89a160b3074274a2c71fb273efd63fc35fb4025a0aecd3e1e5abd5d6136"
RUNNER_REL = "runner/acquisition_01.py"
EZ_PARSER_REL = "runner/experiment_zero.py"

EXP = ROOT / "experiment-one"
CUR, BEN, SCO = EXP / "curriculum", EXP / "benchmark", EXP / "scoring"
RAW_BASE = ROOT / "results" / "raw" / "acquisition_01"
SUMMARY_BASE = ROOT / "results" / "summary" / "acquisition_01"

MODELS = {  # protocol.md §Models (fixed), table order = execution order
    "gemma3:1b": "8648f39daa8fbf5b18c7b4e6a8fb4990c692751d49917417b8842ca5758e7ffc",
    "qwen3:1.7b": "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7",
    "qwen3.5:2b": "324d162be6ca5629ae4517c8710434d0bd2d665bc94dbad46e9af8fbf8a2f0df",
    "phi4-mini:3.8b-q4_K_M": "78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753",
}

OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 12288, "num_predict": 512}
PROBE_OPTIONS = {**OPTIONS, "num_predict": 1}
THINK = False
KEEP_ALIVE = 0
REQUEST_KEYS = {"model", "prompt", "stream", "think", "options", "keep_alive"}

HEADER_A = "SECTION A — ΛLINGUA CURRICULUM"
INSTRUCTION = (
    "Represent the epistemic state using ΛLingua v0 only.\n"
    "Use the listed term identifiers exactly and evidence identifiers exactly as written in the source.\n"
    "Do not explain.\n"
    "Do not redefine, extend, or negotiate the protocol.\n"
    "Return only the ΛLingua representation."
)
TRANSCRIPT_HEADER = "# ΛLingua v0 — Corrected Exercises"

CHECKPOINTS = ["C0", "C1", "C2", "C3", "C4"]
FORM_OF = {f"C{k}": f"X{k}" for k in range(5)}
ROUNDS = {1: ["TR01", "TR02", "TR03"], 2: ["TR04", "TR05", "TR06"], 3: ["TR07", "TR08", "TR09"]}
CLOSED_ROUNDS = {"C0": 0, "C1": 0, "C2": 1, "C3": 2, "C4": 3}
WORKED_EXAMPLES = {"C0": 0, "C1": 3, "C2": 6, "C3": 9, "C4": 12}
COMPRESSION = {  # condition -> curriculum file; all evaluated on X0; CP-100 == C0
    "CP-100": "compression-100.md", "CP-75": "compression-75.md", "CP-50": "compression-50.md",
    "CP-25": "compression-25.md", "CP-EX": "compression-examples-only.md",
    "CP-SYM": "compression-symbols-only.md",
}
MARKERS = ["φ", "ε", "?", "ĥ"]
CAT_MARK = {"assertions": "φ", "evidence": "ε", "unknowns": "?", "hypotheses": "ĥ"}
STOP_FILE = "STOP"


class SafetyAbort(Exception):
    pass


class HistoryUnavailable(SafetyAbort):
    """A needed exercise record does not exist yet (not a tampering condition)."""


# ---------------------------------------------------------------- frozen inputs

def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def write_json_atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def curriculum_text(name):
    """Curriculum files are inserted byte-for-byte with trailing newlines stripped."""
    return (CUR / name).read_text(encoding="utf-8").rstrip("\n")


def load_benchmark():
    b = {"train": {i["id"]: i for i in read_jsonl(BEN / "acquisition-train.jsonl")},
         "transfer": read_jsonl(BEN / "transfer-exam.jsonl")}
    for k in range(5):
        items = read_jsonl(BEN / f"unseen-exam-X{k}.jsonl")
        if [i["id"] for i in items] != [f"X{k}-{n:02d}" for n in range(1, 25)]:
            raise SafetyAbort(f"X{k}: item ids differ from frozen form")
        if any(i["form"] != f"X{k}" or i["checkpoint"] != f"C{k}" for i in items):
            raise SafetyAbort(f"X{k}: form/checkpoint labels differ from frozen form")
        b[f"X{k}"] = items
    return b


def exam_identifiers(bench):
    """Every term and evidence identifier of X0–X4 and the transfer exam (normalized)."""
    ids = set()
    for split in [f"X{k}" for k in range(5)] + ["transfer"]:
        for it in bench[split]:
            cs = it["canonical_state"]
            for cat in ["assertions", "evidence", "unknowns", "hypotheses"]:
                ids.update(ez.norm(t) for t in cs[cat])
    return ids


def verify_manifest():
    """Return list of failures. Pinned manifest hash + every file hash + verifier PASS."""
    fails = []
    if sha_file(ROOT / MANIFEST_REL) != MANIFEST_SHA256:
        fails.append("frozen-manifest.json sha256 differs from the pinned freeze value")
    m = json.loads((ROOT / MANIFEST_REL).read_text(encoding="utf-8"))
    for rel, h in m["files"].items():
        if not (ROOT / rel).exists() or sha_file(ROOT / rel) != h:
            fails.append(f"frozen file hash mismatch: {rel}")
    if sha_file(ROOT / "spec/lambda-v0.md") != m["language"]["spec/lambda-v0.md"]:
        fails.append("spec hash mismatch")
    if sha_file(ROOT / EZ_PARSER_REL) != m["reused_parser"][EZ_PARSER_REL]:
        fails.append("Experiment Zero parser hash mismatch")
    if not all(v is True for k, v in m["verification"].items() if isinstance(v, bool)):
        fails.append("manifest verification flags not all true")
    for args in (["--check-manifest"], []):
        r = subprocess.run([sys.executable, "experiment-one/tools/verify_design.py", *args],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            fails.append(f"verify_design.py {' '.join(args)} failed: {r.stdout.strip().splitlines()[-1:]}")
    return fails


def frozen_paths():
    m = json.loads((ROOT / MANIFEST_REL).read_text(encoding="utf-8"))
    return sorted(m["files"]) + [MANIFEST_REL, "spec/lambda-v0.md", EZ_PARSER_REL, RUNNER_REL]


def verify_inputs_unchanged(pf):
    """Before every call: frozen files and runner identical to HEAD and to preflight."""
    dirty = ez.git("status", "--porcelain", "--", *frozen_paths())
    if dirty:
        raise SafetyAbort(f"frozen inputs or runner modified:\n{dirty}")
    if ez.git("rev-parse", "HEAD") != pf["git_commit"]:
        raise SafetyAbort("HEAD moved since preflight; start a new run id")
    if sha_file(ROOT / RUNNER_REL) != pf["runner_sha256"]:
        raise SafetyAbort("runner changed since preflight; start a new run id")
    if sha_file(ROOT / MANIFEST_REL) != MANIFEST_SHA256:
        raise SafetyAbort("frozen manifest changed")


# ---------------------------------------------------------------- prompts and contexts

def task_section(item):
    return f"Source:\n{item['input']}\n\nTerms: {', '.join(item['terms'])}"


def build_prompt(payload, item):
    """protocol.md §Prompt template. payload None = NULL context (token probe only):
    the Section A header line is kept and the payload omitted."""
    parts = [HEADER_A] + ([payload] if payload is not None else [])
    parts += ["SECTION B — TASK", task_section(item), "SECTION C — INSTRUCTION", INSTRUCTION]
    return "\n\n".join(parts) + "\n"


def indent4(text):
    return "\n".join("    " + l for l in text.split("\n"))


def transcript_block(n, item, response, correction):
    shown = "(empty)" if not (response or "").strip() else (response or "").rstrip("\n")
    return (f"## Exercise {n}\n\nSource:\n{item['input']}\n\nTerms: {', '.join(item['terms'])}\n\n"
            f"Your response:\n\n{indent4(shown)}\n\n"
            f"Correction:\nResult: {correction['result']}\n\n"
            f"Canonical ΛLingua v0:\n\n{indent4(item['canonical_lambda'])}\n\n"
            f"Differences:\n" + ("\n".join(correction["lines"]) if correction["lines"] else "- none"))


def transcript(blocks):
    """Header + blocks separated by one blank line; absent until the first block exists
    (so the TR01 exercise context equals C1)."""
    return None if not blocks else TRANSCRIPT_HEADER + "\n\n" + "\n\n".join(blocks)


def curriculum_payload(kind, blocks=()):
    """The ONLY constructor of Section A payloads.

    kind: a checkpoint C0..C4, a compression condition CP-*, or "exercise".
    blocks: corrected-exercise transcript blocks (teaching history). Callers pass
    exactly the blocks of the closed rounds; no other history exists in this API.
    Returns (payload_text, parts) where parts documents the composition.
    """
    if kind in COMPRESSION:
        if blocks:
            raise SafetyAbort("compression conditions carry no teaching history")
        parts = [COMPRESSION[kind]]
        return curriculum_text(COMPRESSION[kind]), parts
    parts = ["compression-100.md"]
    texts = [curriculum_text("compression-100.md")]
    if kind != "C0":
        parts.append("stage-1-demonstrations.md")
        texts.append(curriculum_text("stage-1-demonstrations.md"))
    elif blocks:
        raise SafetyAbort("C0 carries no teaching history")
    t = transcript(list(blocks))
    if t is not None:
        if kind == "C1":
            raise SafetyAbort("C1 carries no corrected exercises")
        parts.append(f"transcript[{len(blocks)} blocks]")
        texts.append(t)
    return "\n\n".join(texts), parts


def assert_payload_clean(payload, exam_ids):
    """Guard: no exam/transfer identifier may occur in any teaching payload."""
    words = {ez.norm(w) for w in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*", payload)}
    leaked = sorted(words & exam_ids)
    if leaked:
        raise SafetyAbort(f"exam identifier(s) in teaching payload: {leaked[:5]}")


# ---------------------------------------------------------------- scoring (strict, frozen definitions)

def canonical_nodes(item):
    """{node: canonical marker} in canonical render order (order of first mention in canonical_lambda)."""
    cs = item["canonical_state"]
    mark = {**{t: "φ" for t in cs["assertions"]}, **{e: "ε" for e in cs["evidence"]},
            **{t: "?" for t in cs["unknowns"]}, **{t: "ĥ" for t in cs["hypotheses"]}}
    order = []
    for m in ez.ATOM_RE.finditer(item["canonical_lambda"]):
        if m.group(2) not in order:
            order.append(m.group(2))
    assert sorted(order) == sorted(mark), item["id"]
    return {n: mark[n] for n in order}


def node_lookup(nodes):
    lut = {}
    for n in nodes:
        if ez.norm(n) in lut:
            raise SafetyAbort(f"canonical node collision under norm(): {n}")
        lut[ez.norm(n)] = n
    return lut


def analyse(item, text):
    """Strict structural analysis of one response against one item.

    Output markers of a node = markers under which it appears; the left side of ∵ counts as φ.
    """
    nodes = canonical_nodes(item)
    lut = node_lookup(nodes)
    items, edges, violations = ez.parse_lambda(text)
    out_marks = {n: set() for n in nodes}
    extra_nodes = set()
    for cat, terms in items.items():
        for t in terms:
            c = lut.get(ez.norm(t))
            if c is None:
                extra_nodes.add((CAT_MARK[cat], t))
            else:
                out_marks[c].add(CAT_MARK[cat])
    out_edges = set()
    for e in edges:
        lc = lut.get(ez.norm(e["left"]))
        ec = lut.get(ez.norm(e["evidence"]))
        if lc is not None:
            out_marks[lc].add("φ")
        out_edges.add((lc if lc is not None else e["left"], ec if ec is not None else e["evidence"],
                       e["left_marker"], e["evidence_marker"], lc is not None, ec is not None))
    canon_edges = [tuple(x) for x in item["canonical_state"]["support_edges"]]
    return {"nodes": nodes, "out_marks": out_marks, "extra_nodes": extra_nodes,
            "out_edges": out_edges, "canon_edges": canon_edges, "violations": violations}


def status_outcome(marks):
    if not marks:
        return "absent"
    if len(marks) > 1:
        return "conflict"
    return next(iter(marks))


def item_scores(item, text, valid):
    """Experiment Zero strict scores + ESF/IE for one record."""
    ezs = ez.score_lambda({"canonical_state": item["canonical_state"], "visible_response": text}, False)
    a = analyse(item, text)
    status_ok = {n: a["out_marks"][n] == {m} for n, m in a["nodes"].items()}
    term_nodes = [n for n, m in a["nodes"].items() if m != "ε"]
    edge_pairs = {(l, e) for l, e, *_ in a["out_edges"]}
    extras = len(set(ezs["detections"]["extra_unsupported_state"]))
    ie = (valid and not ezs["protocol_violations"] and all(status_ok.values())
          and edge_pairs == set(a["canon_edges"]) and extras == 0)
    det = ezs["detections"]
    return {
        "ez": {k: ezs[k] for k in ["counts", "semantic_fidelity", "matched_items", "canonical_items",
                                    "extra_items", "detections", "protocol_violations", "protocol_violation"]},
        "esf_correct": sum(status_ok.values()), "esf_total": len(status_ok),
        "esf_terms_correct": sum(status_ok[n] for n in term_nodes), "esf_terms_total": len(term_nodes),
        "status_outcomes": {n: {"canonical": a["nodes"][n], "outcome": status_outcome(a["out_marks"][n])}
                            for n in a["nodes"]},
        "laundering_events": len(det["hypothesis_laundering"]) + len(det["unknown_laundering"]),
        "output_edges_equal_G": edge_pairs == set(a["canon_edges"]),
        "item_exact": ie,
    }


# ---------------------------------------------------------------- deterministic corrections

RULE_HYP = "  Rule: A hypothesis must not be interpreted as an assertion."
RULE_UNK = "  Rule: Unknown must not be silently converted into an assertion or hypothesis."
RULE_SUP = "  Rule: A support relation must preserve both endpoints, X and E1, and the directed relation between them."


def correction(item, text, valid=True):
    """curriculum/stage-2-corrections.md §Correction generation, exactly."""
    a = analyse(item, text)
    lines, rules_done = [], set()

    def emit(line, rule=None):
        lines.append(line)
        if rule and rule not in rules_done:
            rules_done.add(rule)
            lines.append(rule)

    # group 1 FORMAT (at most 3; identical lines emitted once)
    fmt = []
    norm_text = unicodedata.normalize("NFC", text or "")
    if not norm_text.strip():
        fmt.append("- FORMAT: the response was empty.")
    for line in norm_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("```"):
            f = "- FORMAT: code fences are not ΛLingua v0 lines."
        elif not ez.LINE_RE.match(s):
            f = f'- FORMAT: "{s[:80]}" is not a ΛLingua v0 line.'
        else:
            continue
        if f not in fmt:
            fmt.append(f)
    for f in fmt[:3]:
        emit(f)

    # group 2 STATUS (canonical render order)
    for n, m in a["nodes"].items():
        got = a["out_marks"][n]
        wrong = [x for x in MARKERS if x in got and x != m]
        if not got:
            emit(f"- MISSING: {m}:{n} is required.")
            continue
        if not wrong:
            continue
        rule = RULE_HYP if (m == "ĥ" and "φ" in got) else RULE_UNK if (m == "?" and ({"φ", "ĥ"} & got)) else None
        others = ", ".join(f"{x}:{n}" for x in wrong)
        if m in got:
            emit(f"- CONFLICT: {n} must appear only as {m}:{n}; it also appears as {others}.", rule)
        else:
            emit(f"- WRONG STATUS: {n} must be {m}:{n}, not {others}.", rule)

    # group 3 SUPPORT
    out_pairs = sorted({(l, e, lm, em, la, ea) for l, e, lm, em, la, ea in a["out_edges"]},
                       key=lambda x: (x[0], x[1]))
    canon = a["canon_edges"]
    noncanon = [x for x in out_pairs if (x[0], x[1]) not in set(canon)]
    covered = set()
    for x, e in canon:
        if any((l, ev) == (x, e) for l, ev, *_ in out_pairs):
            continue
        cand = [w for w in noncanon if w[4] and w[0] == x and w not in covered]
        if cand:
            covered.add(cand[0])
            emit(f"- WRONG SUPPORT: φ:{x} ∵ ε:{cand[0][1]} is not in the source; the source gives φ:{x} ∵ ε:{e}.",
                 RULE_SUP)
        else:
            emit(f"- MISSING SUPPORT: φ:{x} ∵ ε:{e} is required.", RULE_SUP)
    for w in noncanon:
        if w in covered:
            continue
        l, e, lm, em = w[:4]
        left = f"{lm}:{l}" if lm else l
        right = f"{em}:{e}" if em else e
        emit(f"- EXTRA SUPPORT: {left} ∵ {right} is not in the source.", RULE_SUP)

    # group 4 EXTRA (lexicographic)
    for m, t in sorted(a["extra_nodes"], key=lambda x: (x[1], MARKERS.index(x[0]))):
        emit(f"- EXTRA: {m}:{t} is not in the source state.")

    exact = item_scores(item, text, valid)["item_exact"]
    if exact and lines:
        raise SafetyAbort(f"{item['id']}: EXACT with difference lines (correction generator defect)")
    if not exact and not lines:
        raise SafetyAbort(f"{item['id']}: NOT EXACT without difference lines (correction generator defect)")
    return {"result": "EXACT" if exact else "NOT EXACT", "lines": lines}


# ---------------------------------------------------------------- inference

def generate(model, prompt, options):
    payload = {"model": model, "prompt": prompt, "stream": False, "think": THINK,
               "options": options, "keep_alive": KEEP_ALIVE}
    if set(payload) != REQUEST_KEYS:  # no `context`, no `system`, no chat history
        raise SafetyAbort("request carries non-stateless fields")
    req = urllib.request.Request(ez.OLLAMA + "/api/generate", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=ez.REQUEST_TIMEOUT_S) as resp:
        body = resp.read()
    return payload, json.loads(body), round(time.time() - t0, 3)


def attempt_call(model, prompt, options, baseline_vram):
    """Experiment Zero attempt_call with this experiment's options; same safety guards."""
    pre_unloaded, _ = ez.wait_unloaded()
    pre = ez.system_state()
    if not pre_unloaded or pre["loaded_models"]:
        raise SafetyAbort(f"model still resident before call (fresh context not guaranteed): {pre['loaded_models']}")
    if pre["ram_available_mib"] < ez.RAM_AVAILABLE_MIN_MIB:
        raise SafetyAbort(f"RAM available {pre['ram_available_mib']} MiB below threshold")
    sampler = ez.Sampler()
    sampler.start()
    attempt = {"started": ez.now(), "pre_state": pre}
    try:
        payload, raw, wall = generate(model, prompt, options)
        attempt.update(request=payload, raw_response=raw, wall_seconds=wall, transport_ok=True)
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as exc:
        attempt.update(transport_ok=False, transport_error=repr(exc))
    finally:
        sampler.stop.set()
        sampler.join()
    unloaded, unload_s = ez.wait_unloaded()
    post = ez.system_state()
    samples = sampler.samples
    peak = max([s["vram_used_mib"] for s in samples] + [post["vram_used_mib"]])
    min_ram = min([s["ram_available_mib"] for s in samples] + [post["ram_available_mib"]])
    max_res = max([len(s["loaded_models"]) for s in samples] + [0])
    foreign = sorted({m for s in samples for m in s["loaded_models"] if m != model})
    v = []
    if not unloaded:
        v.append("model_not_unloaded")
    if peak > ez.VRAM_PEAK_MAX_MIB:
        v.append("vram_peak_exceeded")
    if min_ram < ez.RAM_AVAILABLE_MIN_MIB:
        v.append("ram_below_minimum")
    if max_res > 1 or foreign:
        v.append("concurrent_models")
    if post["vram_used_mib"] > baseline_vram + ez.POST_UNLOAD_VRAM_SLACK_MIB:
        v.append("vram_not_released")
    attempt.update(finished=ez.now(), post_state=post, safety={
        "unloaded": unloaded, "unload_seconds": unload_s, "peak_vram_mib": peak,
        "min_ram_available_mib": min_ram, "max_models_resident": max_res, "foreign_models_seen": foreign,
        "post_vram_mib": post["vram_used_mib"], "samples": len(samples),
        "sampler_errors": sampler.errors, "violations": v})
    return attempt


def call(pf, model, prompt, options):
    """At most one retry, for transport/runtime failure only. Any model output is final."""
    verify_inputs_unchanged(pf)
    attempts = []
    for n in range(1, ez.MAX_ATTEMPTS + 1):
        a = attempt_call(model, prompt, options, pf["baseline"]["vram_used_mib"])
        a["attempt"] = n
        attempts.append(a)
        if a["safety"]["violations"]:
            break
        if a["transport_ok"] and "error" not in a["raw_response"]:
            break
        if a["transport_ok"]:
            a["transport_ok"] = False
            a["transport_error"] = a["raw_response"].get("error")
    return attempts


def make_record(run_id, model, batch, kind, item, prompt, payload_info, options, attempts):
    final = attempts[-1]
    raw = final.get("raw_response") or {}
    resp = raw.get("response")
    pin = raw.get("prompt_eval_count")
    transport_failure = not final["transport_ok"]
    overflow = pin is None or pin + options["num_predict"] > options["num_ctx"]
    rec = {
        "run_id": run_id, "experiment": "acq-01", "git_commit": ez.git("rev-parse", "HEAD"),
        "timestamp": final["finished"], "model": model, "model_digest": MODELS[model],
        "batch": batch, "call_kind": kind, "item_id": item["id"], "split": item.get("split"),
        "form": item.get("form"), "skeleton": item.get("skeleton"), "domain": item.get("domain"),
        "adversarial": item.get("adversarial"),
        "adversarial_taught_in_curriculum": item.get("adversarial_taught_in_curriculum"),
        "canonical_state": item["canonical_state"], "canonical_lambda": item["canonical_lambda"],
        "payload": payload_info, "options": options, "think": THINK, "keep_alive": KEEP_ALIVE,
        "exact_prompt": prompt, "exact_prompt_sha256": sha_text(prompt),
        "raw_response": raw, "visible_response": resp,
        "thinking_present": bool(raw.get("thinking")) or ("<think>" in (resp or "")),
        "done": raw.get("done"), "done_reason": raw.get("done_reason"),
        "prompt_tokens": pin, "output_tokens": raw.get("eval_count"),
        "tokens_all_attempts": sum((a.get("raw_response") or {}).get("prompt_eval_count", 0) or 0
                                   for a in attempts) + sum((a.get("raw_response") or {}).get("eval_count", 0) or 0
                                                            for a in attempts),
        "wall_seconds": final.get("wall_seconds"), "attempt_count": len(attempts), "attempts": attempts,
        "transport_failure": transport_failure, "context_overflow_risk": overflow,
        "safety_violations": final["safety"]["violations"],
    }
    rec["valid"] = not transport_failure and not overflow
    rec["status"] = "complete"
    return rec


# ---------------------------------------------------------------- run layout and plan

def model_slug(model):
    return model.replace(":", "__")


def run_dir(run_id):
    return RAW_BASE / run_id


def rec_path(run_id, model, batch, item_id):
    return run_dir(run_id) / model_slug(model) / batch / f"{item_id}.json"


def load_rec(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def batches(bench):
    """Per-model batch list, protocol.md §Execution order."""
    out = [("probe", "probe", None, [i for k in range(5) for i in bench[f"X{k}"]])]
    out.append(("C0", "exam", "C0", bench["X0"]))
    for cp in ["CP-75", "CP-50", "CP-25", "CP-EX", "CP-SYM"]:
        out.append((cp, "compression", cp, bench["X0"]))
    out.append(("C1", "exam", "C1", bench["X1"]))
    for r in (1, 2, 3):
        out.append((f"R{r}", "exercise", r, [bench["train"][t] for t in ROUNDS[r]]))
        out.append((f"C{r + 1}", "exam", f"C{r + 1}", bench[f"X{r + 1}"]))
    out.append(("transfer", "transfer", "C4", bench["transfer"]))
    return out


def exercise_blocks(run_id, model, bench, n_rounds):
    """Teaching history: transcript blocks of the first n_rounds closed rounds, rebuilt from
    stored exercise records only. Raises if a needed exercise is missing or tampered."""
    blocks, n = [], 0
    for r in range(1, n_rounds + 1):
        for tid in ROUNDS[r]:
            n += 1
            rec = load_rec(rec_path(run_id, model, f"R{r}", tid))
            if rec is None or rec.get("status") != "complete":
                raise HistoryUnavailable(f"{model}: exercise {tid} not complete; teaching history unavailable")
            item = bench["train"][tid]
            corr = correction(item, rec["visible_response"], rec["valid"])
            if corr != rec["correction"]:
                raise SafetyAbort(f"{model}: stored correction for {tid} does not regenerate")
            block = transcript_block(n, item, rec["visible_response"], corr)
            if sha_text(block) != rec["transcript_block_sha256"]:
                raise SafetyAbort(f"{model}: transcript block for {tid} does not regenerate")
            blocks.append(block)
    return blocks


def batch_payload(run_id, model, bench, kind, ctx):
    if kind == "probe":
        return None, ["NULL"], 0
    if kind == "compression":
        p, parts = curriculum_payload(ctx)
        return p, parts, 0
    if kind == "exercise":
        return None, None, None  # per exercise, see run_exercise_batch
    blocks = exercise_blocks(run_id, model, bench, CLOSED_ROUNDS[ctx])
    p, parts = curriculum_payload(ctx, blocks)
    return p, parts, len(blocks)


def check_prefix_chain(run_id, model, bench):
    """Teaching history persists: C(k) payload is a prefix of C(k+1) for every available k."""
    prev = None
    for k in CHECKPOINTS:
        try:
            p, _, _ = batch_payload(run_id, model, bench, "exam", k)
        except HistoryUnavailable:
            break
        if prev is not None and not p.startswith(prev):
            raise SafetyAbort(f"{model}: {k} payload does not extend the previous checkpoint payload")
        prev = p


# ---------------------------------------------------------------- commands

def cmd_plan(args):
    bench = load_benchmark()
    total = 0
    for name, kind, ctx, items in batches(bench):
        print(f"{name:<9} {kind:<12} context={ctx!s:<7} calls={len(items)}")
        total += len(items)
    print(f"per model: {total}   models: {len(MODELS)}   total: {total * len(MODELS)}")
    return 0 if total == 393 else 1


def checks_common():
    c = {}
    c["worktree"] = ez.git("rev-parse", "--show-toplevel") == EXPECTED_ROOT
    c["branch"] = ez.git("branch", "--show-current") == EXPECTED_BRANCH
    c["head_descends_from_freeze"] = subprocess.run(
        ["git", "merge-base", "--is-ancestor", FREEZE_COMMIT, "HEAD"], cwd=ROOT).returncode == 0
    c["tree_clean"] = ez.git("status", "--porcelain", "--untracked-files=all") == ""
    c["runner_committed"] = ez.git("ls-files", RUNNER_REL) == RUNNER_REL
    fails = verify_manifest()
    c["manifest_verified"] = not fails
    return c, fails


def cmd_preflight(args):
    c, fails = checks_common()
    tags = {m["name"]: m.get("digest") for m in ez.http_json("/api/tags").get("models", [])}
    version = ez.http_json("/api/version").get("version")
    c["models_pinned"] = all(tags.get(m) == d for m, d in MODELS.items())
    state = ez.system_state()
    c["no_model_loaded"] = state["loaded_models"] == []
    c["ram_ok"] = state["ram_available_mib"] >= ez.RAM_AVAILABLE_MIN_MIB
    c["vram_baseline_ok"] = state["vram_used_mib"] < 1024
    bench = load_benchmark()
    c["plan_393_per_model"] = sum(len(b[3]) for b in batches(bench)) == 393
    rec = {"run_id": args.run_id, "timestamp": ez.now(), "git_commit": ez.git("rev-parse", "HEAD"),
           "git_branch": ez.git("branch", "--show-current"), "worktree": str(ROOT),
           "ollama_version": version, "model_digests_observed": {m: tags.get(m) for m in MODELS},
           "model_digests_pinned": MODELS, "manifest_sha256": sha_file(ROOT / MANIFEST_REL),
           "manifest_failures": fails, "runner_sha256": sha_file(ROOT / RUNNER_REL),
           "options": OPTIONS, "probe_options": PROBE_OPTIONS, "think": THINK, "keep_alive": KEEP_ALIVE,
           "safety": {"vram_peak_max_mib": ez.VRAM_PEAK_MAX_MIB, "ram_available_min_mib": ez.RAM_AVAILABLE_MIN_MIB,
                      "post_unload_vram_slack_mib": ez.POST_UNLOAD_VRAM_SLACK_MIB},
           "baseline": state, "checks": c, "status": "PASS" if all(c.values()) else "FAIL"}
    write_json_atomic(run_dir(args.run_id) / "preflight.json", rec)
    for k, v in c.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")
    for f in fails:
        print(f"  {f}")
    print(f"PREFLIGHT: {rec['status']}")
    return 0 if rec["status"] == "PASS" else 1


def load_preflight(run_id):
    p = run_dir(run_id) / "preflight.json"
    if not p.exists():
        sys.exit("ABORT: no preflight for this run id")
    pf = json.loads(p.read_text(encoding="utf-8"))
    if pf["status"] != "PASS":
        sys.exit("ABORT: preflight did not pass")
    fails = verify_manifest()
    if fails:
        sys.exit("ABORT: frozen manifest does not verify: " + "; ".join(fails))
    return pf


def smoke_payload(bench):
    """Worst-case C4-sized teaching context from training items only: each of the 9
    'responses' is the canonical answer repeated to >= 2560 bytes (≈ the 512-token cap)."""
    blocks = []
    for n, tid in enumerate([t for r in (1, 2, 3) for t in ROUNDS[r]], 1):
        it = bench["train"][tid]
        pad = it["canonical_lambda"]
        while len(pad.encode()) < 2560:
            pad += "\n" + it["canonical_lambda"]
        blocks.append(transcript_block(n, it, pad, {"result": "NOT EXACT", "lines": []}))
    return curriculum_payload("C4", blocks)[0]


def cmd_smoke(args):
    pf = load_preflight(args.run_id)
    bench = load_benchmark()
    task = bench["train"]["TR01"]  # never an exam or transfer item
    worst = smoke_payload(bench)
    results, abort = {}, None
    try:
        for model in MODELS:
            for name, payload, opts in [("null_probe", None, PROBE_OPTIONS), ("worst_case_c4", worst, OPTIONS)]:
                prompt = build_prompt(payload, task)
                attempts = call(pf, model, prompt, opts)
                rec = make_record(args.run_id, model, "smoke", name, task, prompt,
                                  {"sha256": sha_text(payload) if payload else None,
                                   "parts": ["synthetic worst-case C4"] if payload else ["NULL"]}, opts, attempts)
                rec["official"] = False
                write_json_atomic(run_dir(args.run_id) / "smoke" / model_slug(model) / f"{name}.json", rec)
                pin = rec["prompt_tokens"] or 0
                ok = (rec["valid"] and rec["done"] is True and not rec["thinking_present"]
                      and not rec["safety_violations"] and rec["model_digest"] == pf["model_digests_observed"][model])
                results[f"{model}/{name}"] = {
                    "pass": ok, "prompt_tokens": pin, "output_tokens": rec["output_tokens"],
                    "headroom_tokens": OPTIONS["num_ctx"] - pin - opts["num_predict"],
                    "peak_vram_mib": rec["attempts"][-1]["safety"]["peak_vram_mib"],
                    "unload_seconds": rec["attempts"][-1]["safety"]["unload_seconds"],
                    "done_reason": rec["done_reason"]}
                print(f"smoke {model:<22} {name:<14} {results[f'{model}/{name}']}")
                if rec["safety_violations"]:
                    raise SafetyAbort(f"{model} {name}: {rec['safety_violations']}")
    except SafetyAbort as exc:
        abort = str(exc)
    status = "PASS" if abort is None and len(results) == 2 * len(MODELS) and all(
        r["pass"] for r in results.values()) else "FAIL"
    write_json_atomic(run_dir(args.run_id) / "smoke_status.json",
                      {"status": status, "results": results, "abort": abort, "timestamp": ez.now(),
                       "note": "smoke calls are not official and never scored"})
    print(f"SMOKE: {status}" + (f"  ABORT: {abort}" if abort else ""))
    return 0 if status == "PASS" else 1


def stop_requested(run_id):
    return (run_dir(run_id) / STOP_FILE).exists()


def finish(rec, path):
    write_json_atomic(path, rec)
    s = rec["attempts"][-1]["safety"]
    print(f"{rec['model']:<22} {rec['batch']:<8} {rec['item_id']:<6} in={rec['prompt_tokens']} "
          f"out={rec['output_tokens']} reason={rec['done_reason']} valid={rec['valid']} "
          f"peakVRAM={s['peak_vram_mib']} unload={s['unload_seconds']}s")
    if rec["safety_violations"]:
        raise SafetyAbort(f"{rec['model']} {rec['batch']} {rec['item_id']}: {rec['safety_violations']}")


def run_item_batch(args, pf, bench, exam_ids, model, name, kind, ctx, items):
    payload, parts, nblocks = batch_payload(args.run_id, model, bench, kind, ctx)
    if payload is not None:
        assert_payload_clean(payload, exam_ids)
    info = {"context": ctx, "parts": parts, "transcript_blocks": nblocks,
            "sha256": sha_text(payload) if payload is not None else None,
            "bytes": len(payload.encode()) if payload is not None else 0}
    opts = PROBE_OPTIONS if kind == "probe" else OPTIONS
    for item in items:
        path = rec_path(args.run_id, model, name, item["id"])
        old = load_rec(path)
        if old and old.get("status") == "complete":
            if old["payload"]["sha256"] != info["sha256"]:
                raise SafetyAbort(f"{model} {name}: stored payload hash differs; context not reproducible")
            continue
        if stop_requested(args.run_id):
            return False
        prompt = build_prompt(payload, item)
        rec = make_record(args.run_id, model, name, kind, item, prompt, info, opts, call(pf, model, prompt, opts))
        rec["scored"] = kind != "probe"
        finish(rec, path)
    return True


def run_exercise_batch(args, pf, bench, exam_ids, model, rnd):
    blocks = exercise_blocks(args.run_id, model, bench, rnd - 1)
    n = len(blocks)
    for tid in ROUNDS[rnd]:
        n += 1
        item = bench["train"][tid]
        payload, parts = curriculum_payload("exercise", blocks)
        assert_payload_clean(payload, exam_ids)
        path = rec_path(args.run_id, model, f"R{rnd}", tid)
        old = load_rec(path)
        if old and old.get("status") == "complete":
            blocks.append(transcript_block(n, item, old["visible_response"], old["correction"]))
            continue
        if old and old.get("status") == "transport_failure":
            raise SafetyAbort(f"{model} {tid}: exercise transport failure recorded; professor decision required")
        if stop_requested(args.run_id):
            return False
        prompt = build_prompt(payload, item)
        attempts = call(pf, model, prompt, OPTIONS)
        rec = make_record(args.run_id, model, f"R{rnd}", "exercise", item, prompt,
                          {"context": f"exercise R{rnd}", "parts": parts, "transcript_blocks": len(blocks),
                           "sha256": sha_text(payload), "bytes": len(payload.encode())}, OPTIONS, attempts)
        if rec["transport_failure"]:
            rec["status"] = "transport_failure"
            write_json_atomic(path, rec)
            raise SafetyAbort(f"{model} {tid}: exercise transport failure; teaching halted for review")
        corr = correction(item, rec["visible_response"], rec["valid"])
        block = transcript_block(n, item, rec["visible_response"], corr)
        rec.update(correction=corr, correction_text="Result: " + corr["result"] + "\n" + "\n".join(corr["lines"]),
                   correction_sha256=sha_text(json.dumps(corr, ensure_ascii=False, sort_keys=True)),
                   transcript_block=block, transcript_block_sha256=sha_text(block), scored=False)
        finish(rec, path)
        blocks.append(block)
    return True


def cmd_official(args):
    pf = load_preflight(args.run_id)
    sm = run_dir(args.run_id) / "smoke_status.json"
    if not sm.exists() or json.loads(sm.read_text(encoding="utf-8"))["status"] != "PASS":
        sys.exit("ABORT: hardware/context smoke has not passed for this run id; official run refused")
    bench = load_benchmark()
    exam_ids = exam_identifiers(bench)
    abort, stopped, done = None, False, []
    try:
        for model in MODELS:
            if args.model and model != args.model:
                continue
            for name, kind, ctx, items in batches(bench):
                check_prefix_chain(args.run_id, model, bench)
                ok = (run_exercise_batch(args, pf, bench, exam_ids, model, ctx) if kind == "exercise"
                      else run_item_batch(args, pf, bench, exam_ids, model, name, kind, ctx, items))
                if not ok:
                    stopped = True
                    break
                done.append(f"{model}/{name}")
                if args.stop_after and name == args.stop_after:
                    stopped = True
                    break
            if stopped:
                break
    except SafetyAbort as exc:
        abort = str(exc)
    status = "ABORTED" if abort else "STOPPED" if stopped else "COMPLETE"
    write_json_atomic(run_dir(args.run_id) / "official_status.json",
                      {"status": status, "batches_completed": done, "abort": abort, "timestamp": ez.now()})
    print(f"OFFICIAL: {status}" + (f"  ABORT: {abort}" if abort else ""))
    return 0 if not abort else 1


def cmd_stop(args):
    p = run_dir(args.run_id) / STOP_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ez.now() + "\n", encoding="utf-8")
    print(f"stop requested: {p.relative_to(ROOT)} (remove it to resume)")
    return 0


# ---------------------------------------------------------------- aggregate scoring

def group_metrics(recs, bench_by_id, thr):
    sc = [r["s"] for r in recs]

    def tot(k, f):
        return sum(s["ez"]["counts"][k][f] for s in sc)

    def rate(n, d):
        return None if d == 0 else round(n / d, 4)
    adv = [r for r in recs if r["adversarial"]]
    out = {
        "n": len(recs), "valid": sum(r["valid"] for r in recs),
        "SF": rate(sum(s["ez"]["matched_items"] for s in sc),
                   sum(s["ez"]["canonical_items"] + s["ez"]["extra_items"] for s in sc)),
        "PS": rate(tot("support_edges", "preserved"), tot("support_edges", "canonical")),
        "US": rate(tot("unknowns", "preserved") + tot("hypotheses", "preserved"),
                   tot("unknowns", "canonical") + tot("hypotheses", "canonical")),
        "PV": {"records_with_violation": sum(s["ez"]["protocol_violation"] for s in sc),
               "total_violations": sum(len(s["ez"]["protocol_violations"]) for s in sc)},
        "ESF": rate(sum(s["esf_correct"] for s in sc), sum(s["esf_total"] for s in sc)),
        "ESF_terms": rate(sum(s["esf_terms_correct"] for s in sc), sum(s["esf_terms_total"] for s in sc)),
        "IE": sum(s["item_exact"] for s in sc), "IE_rate": rate(sum(s["item_exact"] for s in sc), len(sc)),
        "AR": {"IE": sum(r["s"]["item_exact"] for r in adv), "n": len(adv),
               "rate": rate(sum(r["s"]["item_exact"] for r in adv), len(adv)),
               "by_subtype": {}, "taught": {}, "untaught": {}},
        "laundering_events": sum(s["laundering_events"] for s in sc),
        "confusion": {},
        "per_skeleton_IE": {r["skeleton"]: r["s"]["item_exact"] for r in recs if r.get("skeleton")},
    }
    for sub in sorted({r["adversarial"] for r in adv}):
        rs = [r for r in adv if r["adversarial"] == sub]
        out["AR"]["by_subtype"][sub] = {"IE": sum(r["s"]["item_exact"] for r in rs), "n": len(rs)}
    for key, flag in [("taught", True), ("untaught", False)]:
        rs = [r for r in adv if r["adversarial_taught_in_curriculum"] is flag]
        out["AR"][key] = {"IE": sum(r["s"]["item_exact"] for r in rs), "n": len(rs)}
    conf = Counter()
    for s in sc:
        for o in s["status_outcomes"].values():
            conf[(o["canonical"], o["outcome"])] += 1
    out["confusion"] = {m: {o: conf[(m, o)] for o in MARKERS + ["conflict", "absent"]} for m in MARKERS}
    c = thr["competence"]
    out["competent"] = (len(recs) == c["exam_items"] and out["valid"] == len(recs)
                        and out["IE"] >= c["min_item_exact"]
                        and (out["ESF"] or 0) >= c["min_ESF"] and (out["PS"] or 0) >= c["min_PS"]
                        and (out["US"] or 0) >= c["min_US"]
                        and len(adv) == c["adversarial_items"]
                        and out["AR"]["IE"] >= c["min_adversarial_item_exact"]
                        and out["laundering_events"] <= c["max_laundering_events"])
    return out


def atl(comp, tt):
    """scoring/definitions.md §ATΛ_first and ATΛ_stable. comp: {Ck: bool|None}; tt: {Ck: TT}.
    Teaching tokens only: TT(k) is the median NULL-differenced prompt size of checkpoint k."""
    k_first = next((k for k in CHECKPOINTS if comp.get(k)), None)
    k_stable = next((k for i, k in enumerate(CHECKPOINTS) if all(comp.get(j) for j in CHECKPOINTS[i:])), None)
    return {
        "ATΛ_first": {"checkpoint": k_first, "tokens": tt.get(k_first) if k_first else None,
                      "worked_examples": WORKED_EXAMPLES.get(k_first)},
        "ATΛ_stable": ({"checkpoint": k_stable, "tokens": tt.get(k_stable), "censored": False,
                        "worked_examples": WORKED_EXAMPLES[k_stable]} if k_stable else
                       {"checkpoint": None, "tokens": None, "censored": True, "not_acquired": True,
                        "tokens_greater_than": tt.get("C4")}),
        "unstable": bool(k_first) and k_first != k_stable,
        "token_accounting": "teaching tokens only: TT = prompt_eval_count(k,i) - prompt_eval_count(NULL,i); "
                            "unseen-exam, transfer, compression, probe, scoring, exercise-generation and "
                            "retry tokens are excluded and reported in TC",
    }


def tokens(r):
    return r.get("tokens_all_attempts") or 0


def cmd_score(args):
    bench = load_benchmark()
    thr = json.loads((SCO / "thresholds.json").read_text(encoding="utf-8"))
    by_id = {i["id"]: i for s in [f"X{k}" for k in range(5)] + ["transfer"] for i in bench[s]}
    by_id.update(bench["train"])
    summary = {"run_id": args.run_id, "experiment": "acq-01", "alignment_mode": "strict",
               "thresholds_version": thr["version"], "models": {}}
    for model in MODELS:
        base = run_dir(args.run_id) / model_slug(model)
        if not base.exists():
            continue
        recs = {}
        for p in sorted(base.glob("*/*.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("status") != "complete" and r.get("status") != "transport_failure":
                continue
            if r["call_kind"] in ("exam", "compression", "transfer"):
                r["s"] = item_scores(by_id[r["item_id"]], r["visible_response"], r["valid"])
            recs.setdefault(r["batch"], []).append(r)
        null = {r["item_id"]: r["prompt_tokens"] for r in recs.get("probe", [])}

        def tt(batch):
            d = [r["prompt_tokens"] - null[r["item_id"]] for r in recs.get(batch, [])
                 if r["prompt_tokens"] is not None and null.get(r["item_id"]) is not None]
            full = len(d) == 24
            b = recs[batch][0]["payload"]["bytes"] if recs.get(batch) else None
            return {"TT": statistics.median(d) if full else None, "TT_bytes": b, "n": len(d)}
        m = {"checkpoints": {}, "compression": {}, "transfer": {}, "TC": {}}
        for k in CHECKPOINTS:
            if k in recs:
                m["checkpoints"][k] = {**group_metrics(recs[k], by_id, thr), **tt(k),
                                       "form": FORM_OF[k], "worked_examples": WORKED_EXAMPLES[k]}
        for cp in COMPRESSION:
            b = "C0" if cp == "CP-100" else cp
            if b in recs:
                g = group_metrics(recs[b], by_id, thr)
                m["compression"][cp] = {**g, "BTΛ": tt(b)["TT"], "TT_bytes": tt(b)["TT_bytes"]}
        comp_ok = [(v["BTΛ"], cp) for cp, v in m["compression"].items() if v["competent"] and v["BTΛ"] is not None]
        m["minimal_sufficient_bootstrap"] = min(comp_ok)[1] if comp_ok else "none"
        # ATΛ: teaching tokens only (TT of the checkpoint); evaluation costs live in TC.
        ladder = [(k, m["checkpoints"].get(k)) for k in CHECKPOINTS]
        complete = all(v is not None and v["n"] == 24 for _, v in ladder)
        comp = {k: (v["competent"] if v else None) for k, v in ladder}
        m["acquisition"] = {"ladder_complete": complete, "competent": comp,
                            **atl(comp, {k: (v or {}).get("TT") for k, v in ladder})}
        if not complete:
            m["acquisition"]["note"] = "ladder incomplete; ATΛ provisional"
        if "transfer" in recs:
            dom = {d: group_metrics([r for r in recs["transfer"] if r["domain"] == d], by_id, thr)
                   for d in ["infrastructure", "science", "logistics"]}
            for d in dom.values():
                d.pop("competent")
            td = {d: {"IE_rate": round(dom["infrastructure"]["IE_rate"] - dom[d]["IE_rate"], 4),
                      "ESF": round(dom["infrastructure"]["ESF"] - dom[d]["ESF"], 4)} for d in ["science", "logistics"]}
            t = thr["transfer"]
            m["transfer"] = {"per_domain": dom, "TΔ": td,
                             "per_skeleton": {}, "transfer_demonstrated": bool(
                                 comp.get("C4") and all(dom[d]["IE"] >= t["min_item_exact_per_domain"]
                                                        and dom[d]["ESF"] >= t["min_ESF_per_domain"]
                                                        for d in t["domains_required"]))}
            for r in recs["transfer"]:
                m["transfer"]["per_skeleton"].setdefault(by_id[r["item_id"]].get("skeleton", r["item_id"][2:]), {})[
                    r["domain"]] = r["s"]["item_exact"]
        tc_cat = Counter()
        for b, rs in recs.items():
            kind = rs[0]["call_kind"]
            for r in rs:
                tc_cat[kind] += tokens(r)
                tc_cat[f"batch:{b}"] += tokens(r)
        m["TC"] = {"total": sum(v for k, v in tc_cat.items() if not k.startswith("batch:")), **dict(tc_cat)}
        summary["models"][model] = m
    out = SUMMARY_BASE / args.run_id / "scores_official.json"
    write_json_atomic(out, summary)
    print(f"wrote {out}")
    return 0


# ---------------------------------------------------------------- selftest (offline)

def cmd_selftest(args):
    fails = []

    def chk(c, msg):
        if not c:
            fails.append(msg)
    bench = load_benchmark()
    exam_ids = exam_identifiers(bench)
    # 1. plan
    chk(sum(len(b[3]) for b in batches(bench)) == 393, "plan is not 393 calls per model")
    # 2. corrections and scoring: canonical answers are EXACT with "- none"; every item
    for it in list(bench["train"].values()) + [i for k in range(5) for i in bench[f"X{k}"]] + bench["transfer"]:
        c = correction(it, it["canonical_lambda"])
        chk(c == {"result": "EXACT", "lines": []}, f"{it['id']}: canonical answer not EXACT")
        s = item_scores(it, it["canonical_lambda"], True)
        chk(s["item_exact"] and s["esf_correct"] == s["esf_total"], f"{it['id']}: canonical answer not IE/ESF=1")
        chk(correction(it, "")["lines"][0] == "- FORMAT: the response was empty.", f"{it['id']}: empty answer")
    tr = bench["train"]
    cases = {
        "TR02": ("?:REPLICA_FELL_BEHIND\nφ:REPLICA_SLOW_DISK_WRITES",
                 ["- WRONG STATUS: REPLICA_SLOW_DISK_WRITES must be ĥ:REPLICA_SLOW_DISK_WRITES, "
                  "not φ:REPLICA_SLOW_DISK_WRITES.", RULE_HYP]),
        "TR01": ("```\nφ:QUEUE_SIZE_LIMIT_REACHED ∵ ε:LOG999\n```",
                 ["- FORMAT: code fences are not ΛLingua v0 lines.", "- MISSING: ε:LOG201 is required.",
                  "- WRONG SUPPORT: φ:QUEUE_SIZE_LIMIT_REACHED ∵ ε:LOG999 is not in the source; "
                  "the source gives φ:QUEUE_SIZE_LIMIT_REACHED ∵ ε:LOG201.", RULE_SUP,
                  "- EXTRA: ε:LOG999 is not in the source state."]),
        "TR06": ("φ:INBOUND_TRAFFIC_BLOCKED ∵ ε:LOG207\nφ:FIREWALL_RULE_CHANGED\n?:FIREWALL_RULE_CHANGED\n"
                 "ĥ:FIREWALL_CHANGE_BLOCKED_TRAFFIC",
                 ["- CONFLICT: FIREWALL_RULE_CHANGED must appear only as ?:FIREWALL_RULE_CHANGED; "
                  "it also appears as φ:FIREWALL_RULE_CHANGED.", RULE_UNK]),
    }
    for tid, (resp, want) in cases.items():
        got = correction(tr[tid], resp)
        chk(got == {"result": "NOT EXACT", "lines": want}, f"{tid}: correction {got['lines']} != {want}")
    # 3. context isolation
    c0, _ = curriculum_payload("C0")
    c1, _ = curriculum_payload("C1")
    chk(c0 == curriculum_text("compression-100.md"), "C0 payload is not the spec alone")
    chk(c1.startswith(c0 + "\n\n"), "C1 does not extend C0")
    fake = [transcript_block(n, tr[t], tr[t]["canonical_lambda"], correction(tr[t], tr[t]["canonical_lambda"]))
            for n, t in enumerate([t for r in (1, 2, 3) for t in ROUNDS[r]], 1)]
    prev = c1
    for k, nb in [("C2", 3), ("C3", 6), ("C4", 9)]:
        p, parts = curriculum_payload(k, fake[:nb])
        chk(p.startswith(prev + "\n\n"), f"{k} does not extend the previous checkpoint")
        chk(parts[-1] == f"transcript[{nb} blocks]", f"{k}: parts {parts}")
        assert_payload_clean(p, exam_ids)
        for x in [i for k2 in range(5) for i in bench[f"X{k2}"]] + bench["transfer"]:
            if x["input"] in p:
                fails.append(f"{k}: exam input {x['id']} in teaching payload")
                break
        prev = p
    for bad in [lambda: curriculum_payload("C0", fake[:1]), lambda: curriculum_payload("C1", fake[:1]),
                lambda: curriculum_payload("CP-50", fake[:1])]:
        try:
            bad()
            fails.append("history accepted where none is allowed")
        except SafetyAbort:
            pass
    for cp in COMPRESSION:
        p, _ = curriculum_payload(cp)
        chk(p == curriculum_text(COMPRESSION[cp]), f"{cp} payload is not its file alone")
    chk(curriculum_payload("CP-100")[0] == c0, "CP-100 != C0")
    nullp = build_prompt(None, bench["X0"][0])
    chk(nullp.startswith(HEADER_A + "\n\nSECTION B — TASK\n\n"), "NULL prompt layout")
    chk(build_prompt(c0, bench["X0"][0]).replace(c0 + "\n\n", "", 1) == nullp, "prompt(k,i) != prompt(NULL,i) + payload")
    try:
        assert_payload_clean(c1 + "\n" + bench["X3"][0]["canonical_lambda"], exam_ids)
        fails.append("leak guard missed an exam identifier")
    except SafetyAbort:
        pass
    # 4. ATΛ on synthetic ladders (teaching tokens only)
    tt = {"C0": 0, "C1": 100, "C2": 200, "C3": 300, "C4": 400}
    a = atl({"C0": False, "C1": True, "C2": False, "C3": True, "C4": True}, tt)
    chk((a["ATΛ_first"]["tokens"], a["ATΛ_stable"]["tokens"], a["unstable"]) == (100, 300, True), f"ATΛ {a}")
    a = atl({"C0": False, "C1": False, "C2": True, "C3": True, "C4": True}, tt)
    chk((a["ATΛ_first"]["checkpoint"], a["ATΛ_stable"]["checkpoint"], a["unstable"]) == ("C2", "C2", False), f"{a}")
    a = atl({"C0": True, "C1": True, "C2": True, "C3": True, "C4": False}, tt)
    chk(a["ATΛ_stable"]["censored"] and a["ATΛ_stable"]["tokens_greater_than"] == 400 and a["unstable"], f"{a}")
    a = atl({k: False for k in CHECKPOINTS}, tt)
    chk(a["ATΛ_first"]["tokens"] is None and a["ATΛ_stable"]["not_acquired"] and not a["unstable"], f"{a}")
    print("SELFTEST:", "PASS" if not fails else "FAIL")
    for f in fails:
        print("  " + f)
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ["selftest", "plan"]:
        sub.add_parser(name)
    for name in ["preflight", "smoke", "score", "stop"]:
        sub.add_parser(name).add_argument("--run-id", required=True)
    o = sub.add_parser("official")
    o.add_argument("--run-id", required=True)
    o.add_argument("--model", choices=list(MODELS), help="restrict to one model (still in protocol order)")
    o.add_argument("--stop-after", help="stop cleanly after this batch name (e.g. C1, R2, transfer)")
    args = ap.parse_args()
    if args.cmd not in ("selftest", "plan"):
        if ez.git("rev-parse", "--show-toplevel") != EXPECTED_ROOT or ez.git("branch", "--show-current") != EXPECTED_BRANCH:
            sys.exit(f"ABORT: must run in {EXPECTED_ROOT} on {EXPECTED_BRANCH}")
    return {"selftest": cmd_selftest, "plan": cmd_plan, "preflight": cmd_preflight, "smoke": cmd_smoke,
            "official": cmd_official, "score": cmd_score, "stop": cmd_stop}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
