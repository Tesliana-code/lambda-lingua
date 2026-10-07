#!/usr/bin/env python3
"""ΛLingua Experiment Zero runner.

Subcommands (all take --run-id):

  preflight  verify worktree, frozen inputs, Ollama, models, GPU/RAM; record config
  dry-run    T01 (calibration, official_score=false) for every model x condition
  official   T02-T10 for every model x condition (requires dry-run PASS)
  score      deterministic re-scoring of raw records into results/summary/

Inference is strictly sequential: one request at a time, keep_alive=0, and the
runner verifies via /api/ps that no model is resident before and after each call.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROOT = "/home/superadmin/lambda-lingua-experiment-zero-20261007"
EXPECTED_BRANCH = "experiment/zero-20261007"

OLLAMA = "http://127.0.0.1:11434"

MODELS = ["gemma3:1b", "qwen3:1.7b", "qwen3.5:2b"]
CONDITIONS = ["A", "B", "C"]
CALIBRATION_TASKS = ["T01"]
OFFICIAL_TASKS = [f"T{i:02d}" for i in range(2, 11)]

FROZEN = [
    "spec/lambda-v0.md",
    "benchmark/schema-v0.json",
    "benchmark/microtasks-v0.jsonl",
    "controls/natural-language-v0.md",
    "artifacts/historical/README.md",
    "artifacts/historical/first-gemma-attempt-T01.json",
]
MINIMAL_BOOTSTRAP = "conditions/minimal-lambda-v0-bootstrap.md"

CONDITION_SOURCES = {
    "A": "controls/natural-language-v0.md",
    "B": "spec/lambda-v0.md",
    "C": MINIMAL_BOOTSTRAP,
}
CONDITION_HEADERS = {
    "A": "SECTION A — FROZEN NATURAL-LANGUAGE CONTROL",
    "B": "SECTION A — FROZEN ΛLINGUA BOOTSTRAP",
    "C": "SECTION A — MINIMAL ΛLINGUA BOOTSTRAP",
}
CONDITION_INSTRUCTIONS = {
    "A": (
        "Represent the epistemic state using the natural-language control only.\n"
        "Do not explain.\n"
        "Do not redefine, extend, or negotiate the protocol.\n"
        "Return only the natural-language representation."
    ),
    # B and C reuse the exact instruction from the historical T01 attempt.
    "B": (
        "Represent the epistemic state using ΛLingua v0 only.\n"
        "Do not explain.\n"
        "Do not redefine, extend, or negotiate the protocol.\n"
        "Return only the ΛLingua representation."
    ),
}
CONDITION_INSTRUCTIONS["C"] = CONDITION_INSTRUCTIONS["B"]

OPTIONS = {"temperature": 0, "num_ctx": 4096, "num_predict": 512, "seed": 0}
KEEP_ALIVE = 0
THINK = False
REQUEST_TIMEOUT_S = 300
MAX_ATTEMPTS = 2  # one documented retry for transport/runtime failure only

# Safety thresholds (RTX 3060 Laptop 6 GiB, ~9.7 GiB RAM WSL2).
VRAM_PEAK_MAX_MIB = 5800
POST_UNLOAD_VRAM_SLACK_MIB = 512
RAM_AVAILABLE_MIN_MIB = 1500
UNLOAD_TIMEOUT_S = 60
SAMPLE_INTERVAL_S = 1.0


# ---------------------------------------------------------------- utilities

def now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def http_json(path, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="GET" if payload is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def loaded_models():
    return [m.get("name") for m in http_json("/api/ps").get("models", [])]


def gpu_state():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True).stdout.strip().splitlines()[0]
    used, total, util = (int(x.strip()) for x in out.split(","))
    return {"vram_used_mib": used, "vram_total_mib": total, "gpu_util_pct": util}


def ram_state():
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) // 1024
    return {"ram_total_mib": info["MemTotal"], "ram_available_mib": info["MemAvailable"],
            "swap_free_mib": info["SwapFree"], "swap_total_mib": info["SwapTotal"]}


def system_state():
    return {"t": now(), "loaded_models": loaded_models(), **gpu_state(), **ram_state()}


def load_tasks():
    tasks = {}
    for line in (ROOT / "benchmark/microtasks-v0.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            t = json.loads(line)
            tasks[t["id"]] = t
    return tasks


def run_dir(run_id):
    return ROOT / "results" / "raw" / "experiment_zero" / run_id


def summary_dir(run_id):
    return ROOT / "results" / "summary" / "experiment_zero" / run_id


class SafetyAbort(Exception):
    pass


# ---------------------------------------------------------------- inputs

def input_hashes():
    h = {p: sha256_file(p) for p in FROZEN}
    h[MINIMAL_BOOTSTRAP] = sha256_file(MINIMAL_BOOTSTRAP)
    return h


def frozen_unchanged_vs_head():
    """Frozen files must be byte-identical to HEAD and have no pending changes."""
    diff = git("status", "--porcelain", "--", *FROZEN)
    return diff == "", diff


def verify_inputs_against(preflight):
    ok, diff = frozen_unchanged_vs_head()
    if not ok:
        raise SafetyAbort(f"frozen inputs modified:\n{diff}")
    current = input_hashes()
    if current != preflight["input_hashes"]:
        raise SafetyAbort("experimental input hashes differ from preflight record")
    if sha256_file("runner/experiment_zero.py") != preflight["runner_sha256"]:
        raise SafetyAbort("runner changed since preflight; start a new run id")


def build_prompt(condition, task_input):
    source = (ROOT / CONDITION_SOURCES[condition]).read_text(encoding="utf-8")
    prompt = (
        f"{CONDITION_HEADERS[condition]}\n\n{source}\n\n"
        f"SECTION B — TASK\n\n{task_input}\n\n"
        f"SECTION C — INSTRUCTION\n\n{CONDITION_INSTRUCTIONS[condition]}\n"
    )
    return prompt, sha256_file(CONDITION_SOURCES[condition])


# ---------------------------------------------------------------- preflight

def cmd_preflight(args):
    checks = {}
    top = git("rev-parse", "--show-toplevel")
    branch = git("branch", "--show-current")
    checks["worktree"] = top == EXPECTED_ROOT
    checks["branch"] = branch == EXPECTED_BRANCH
    guard = subprocess.run(["./runner/lab_guard.sh"], cwd=ROOT, capture_output=True, text=True)
    checks["lab_guard"] = guard.returncode == 0
    frozen_ok, frozen_diff = frozen_unchanged_vs_head()
    checks["frozen_unchanged"] = frozen_ok

    version = http_json("/api/version").get("version")
    tags = [m["name"] for m in http_json("/api/tags").get("models", [])]
    checks["ollama_reachable"] = bool(version)
    checks["models_visible"] = all(m in tags for m in MODELS)
    state = system_state()
    checks["no_model_loaded"] = state["loaded_models"] == []
    checks["ram_ok"] = state["ram_available_mib"] >= RAM_AVAILABLE_MIN_MIB
    checks["vram_baseline_ok"] = state["vram_used_mib"] < 1024

    tasks = load_tasks()
    checks["tasks_present"] = all(t in tasks for t in CALIBRATION_TASKS + OFFICIAL_TASKS)

    record = {
        "run_id": args.run_id,
        "timestamp": now(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_branch": branch,
        "worktree": top,
        "working_tree_status": git("status", "--porcelain").splitlines(),
        "ollama_version": version,
        "ollama_endpoint": OLLAMA,
        "models": MODELS,
        "model_digests": {m["name"]: m.get("digest")
                          for m in http_json("/api/tags")["models"] if m["name"] in MODELS},
        "input_hashes": input_hashes(),
        "minimal_bootstrap_path": MINIMAL_BOOTSTRAP,
        "minimal_bootstrap_sha256": sha256_file(MINIMAL_BOOTSTRAP),
        "minimal_bootstrap_text": (ROOT / MINIMAL_BOOTSTRAP).read_text(encoding="utf-8"),
        "runner_sha256": sha256_file("runner/experiment_zero.py"),
        "config": {
            "conditions": {c: {"source": CONDITION_SOURCES[c], "header": CONDITION_HEADERS[c],
                               "instruction": CONDITION_INSTRUCTIONS[c]} for c in CONDITIONS},
            "calibration_tasks": CALIBRATION_TASKS,
            "official_tasks": OFFICIAL_TASKS,
            "options": OPTIONS, "keep_alive": KEEP_ALIVE, "think": THINK,
            "request_timeout_s": REQUEST_TIMEOUT_S, "max_attempts": MAX_ATTEMPTS,
            "endpoint": "/api/generate", "stream": False,
            "safety": {"vram_peak_max_mib": VRAM_PEAK_MAX_MIB,
                       "post_unload_vram_slack_mib": POST_UNLOAD_VRAM_SLACK_MIB,
                       "ram_available_min_mib": RAM_AVAILABLE_MIN_MIB,
                       "unload_timeout_s": UNLOAD_TIMEOUT_S},
            "order": "model-major, then condition A,B,C, then task id",
        },
        "baseline": state,
        "checks": checks,
        "frozen_diff": frozen_diff,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    write_json(run_dir(args.run_id) / "preflight.json", record)
    write_json(summary_dir(args.run_id) / "preflight.json", record)

    print("===== PREFLIGHT =====")
    for k, v in checks.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")
    print(f"git_commit: {record['git_commit']}")
    print(f"ollama: {version}")
    print(f"vram_used_mib: {state['vram_used_mib']}  ram_available_mib: {state['ram_available_mib']}")
    for p, h in record["input_hashes"].items():
        print(f"{h}  {p}")
    print(f"PREFLIGHT: {record['status']}")
    return 0 if record["status"] == "PASS" else 1


# ---------------------------------------------------------------- inference

class Sampler(threading.Thread):
    """Samples GPU/RAM/loaded-models while a request is in flight."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.samples = []
        self.errors = []

    def run(self):
        while not self.stop.is_set():
            try:
                self.samples.append(system_state())
            except Exception as exc:  # sampling must never kill the call
                self.errors.append(repr(exc))
            self.stop.wait(SAMPLE_INTERVAL_S)


def wait_unloaded():
    t0 = time.time()
    while time.time() - t0 < UNLOAD_TIMEOUT_S:
        models = loaded_models()
        if not models:
            return True, round(time.time() - t0, 2)
        time.sleep(0.5)
    return False, round(time.time() - t0, 2)


def generate(model, prompt):
    payload = {"model": model, "prompt": prompt, "stream": False, "think": THINK,
               "options": OPTIONS, "keep_alive": KEEP_ALIVE}
    req = urllib.request.Request(OLLAMA + "/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        body = resp.read()
    return payload, json.loads(body), round(time.time() - t0, 3)


def attempt_call(model, prompt, baseline_vram):
    pre_unloaded, _ = wait_unloaded()
    pre = system_state()
    if not pre_unloaded or pre["loaded_models"]:
        raise SafetyAbort(f"model still resident before call: {pre['loaded_models']}")
    if pre["ram_available_mib"] < RAM_AVAILABLE_MIN_MIB:
        raise SafetyAbort(f"RAM available {pre['ram_available_mib']} MiB below threshold")

    sampler = Sampler()
    sampler.start()
    attempt = {"started": now(), "pre_state": pre}
    try:
        payload, raw, wall = generate(model, prompt)
        attempt.update(request=payload, raw_response=raw, wall_seconds=wall, transport_ok=True)
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as exc:
        attempt.update(transport_ok=False, transport_error=repr(exc))
    finally:
        sampler.stop.set()
        sampler.join()

    unloaded, unload_s = wait_unloaded()
    post = system_state()
    samples = sampler.samples
    peak_vram = max([s["vram_used_mib"] for s in samples] + [post["vram_used_mib"]])
    min_ram = min([s["ram_available_mib"] for s in samples] + [post["ram_available_mib"]])
    max_resident = max([len(s["loaded_models"]) for s in samples] + [0])
    foreign = sorted({m for s in samples for m in s["loaded_models"] if m != model})

    safety = {
        "unloaded": unloaded, "unload_seconds": unload_s,
        "peak_vram_mib": peak_vram, "min_ram_available_mib": min_ram,
        "max_models_resident": max_resident, "foreign_models_seen": foreign,
        "post_vram_mib": post["vram_used_mib"],
        "samples": len(samples), "sampler_errors": sampler.errors,
    }
    violations = []
    if not unloaded:
        violations.append("model_not_unloaded")
    if peak_vram > VRAM_PEAK_MAX_MIB:
        violations.append("vram_peak_exceeded")
    if min_ram < RAM_AVAILABLE_MIN_MIB:
        violations.append("ram_below_minimum")
    if max_resident > 1 or foreign:
        violations.append("concurrent_models")
    if post["vram_used_mib"] > baseline_vram + POST_UNLOAD_VRAM_SLACK_MIB:
        violations.append("vram_not_released")
    safety["violations"] = violations
    attempt.update(finished=now(), post_state=post, safety=safety)
    return attempt


def run_one(run_id, preflight, phase, model, condition, task):
    official = task["id"] in OFFICIAL_TASKS
    safe = f"{model.replace(':', '__')}__{condition}__{task['id']}"
    out = run_dir(run_id) / phase / f"{safe}.json"
    if out.exists():
        rec = read_json(out)
        if rec.get("status") == "complete":
            print(f"[skip existing] {safe}")
            return rec

    verify_inputs_against(preflight)
    prompt, src_hash = build_prompt(condition, task["input"])
    baseline_vram = preflight["baseline"]["vram_used_mib"]

    attempts = []
    for n in range(1, MAX_ATTEMPTS + 1):
        a = attempt_call(model, prompt, baseline_vram)
        a["attempt"] = n
        attempts.append(a)
        if a["safety"]["violations"]:
            break
        if a["transport_ok"] and "error" not in a["raw_response"]:
            break
        if a["transport_ok"]:  # Ollama returned an error object: runtime failure
            a["transport_ok"] = False
            a["transport_error"] = a["raw_response"].get("error")

    final = attempts[-1]
    raw = final.get("raw_response") or {}
    response = raw.get("response")
    prompt_tokens = raw.get("prompt_eval_count")
    rec = {
        "run_id": run_id,
        "timestamp": final["finished"],
        "git_commit": git("rev-parse", "HEAD"),
        "phase": phase,
        "model": model,
        "condition": condition,
        "task_id": task["id"],
        "official_score": official,
        "task_input": task["input"],
        "canonical_state": task["canonical_state"],
        "exact_bootstrap_or_control_hash": src_hash,
        "bootstrap_or_control_path": CONDITION_SOURCES[condition],
        "exact_prompt": prompt,
        "exact_prompt_sha256": sha256_text(prompt),
        "raw_response": raw,
        "visible_response": response,
        "thinking_present": bool(raw.get("thinking")) or ("<think>" in (response or "")),
        "done": raw.get("done"),
        "done_reason": raw.get("done_reason"),
        "prompt_tokens": prompt_tokens,
        "output_tokens": raw.get("eval_count"),
        "wall_seconds": final.get("wall_seconds"),
        "attempt_count": len(attempts),
        "attempts": attempts,
        "transport_failure": not final["transport_ok"],
        "retried": len(attempts) > 1,
        "safety_violations": final["safety"]["violations"],
        "context_risk": (prompt_tokens or 0) >= OPTIONS["num_ctx"] - OPTIONS["num_predict"],
    }
    rec["infra_pass"] = (not rec["transport_failure"] and not rec["safety_violations"]
                         and rec["done"] is True and not rec["thinking_present"]
                         and not rec["context_risk"])
    rec["status"] = "complete" if not rec["transport_failure"] else "transport_failure"
    write_json(out, rec)

    s = final["safety"]
    print(f"{phase} {model:<11} {condition} {task['id']}  "
          f"reason={rec['done_reason']} in={prompt_tokens} out={rec['output_tokens']} "
          f"wall={rec['wall_seconds']} think={rec['thinking_present']} "
          f"unloaded={s['unloaded']}({s['unload_seconds']}s) peakVRAM={s['peak_vram_mib']} "
          f"postVRAM={s['post_vram_mib']} minRAM={s['min_ram_available_mib']} "
          f"attempts={len(attempts)} infra={'PASS' if rec['infra_pass'] else 'FAIL'}")
    if rec["safety_violations"]:
        raise SafetyAbort(f"{safe}: {rec['safety_violations']}")
    if rec["transport_failure"]:
        raise SafetyAbort(f"{safe}: transport failure after {len(attempts)} attempts")
    return rec


def load_preflight(run_id):
    p = run_dir(run_id) / "preflight.json"
    if not p.exists():
        sys.exit("ABORT: no preflight for this run id")
    pf = read_json(p)
    if pf["status"] != "PASS":
        sys.exit("ABORT: preflight did not pass")
    return pf


def cmd_dry_run(args):
    pf = load_preflight(args.run_id)
    tasks = load_tasks()
    results, abort = {}, None
    try:
        for model in MODELS:
            for cond in CONDITIONS:
                for tid in CALIBRATION_TASKS:
                    rec = run_one(args.run_id, pf, "dry_run", model, cond, tasks[tid])
                    results[f"{model}/{cond}"] = rec["infra_pass"]
    except SafetyAbort as exc:
        abort = str(exc)

    status = "PASS" if abort is None and len(results) == 9 and all(results.values()) else "FAIL"
    write_json(run_dir(args.run_id) / "dry_run_status.json",
               {"status": status, "results": results, "abort": abort, "timestamp": now()})
    write_json(summary_dir(args.run_id) / "dry_run_status.json",
               {"status": status, "results": results, "abort": abort, "timestamp": now()})
    print("\n===== DRY RUN STATUS =====")
    for model in MODELS:
        for cond in CONDITIONS:
            v = results.get(f"{model}/{cond}")
            print(f"{model:<11} {cond}: {'PASS' if v else ('FAIL' if v is False else 'NOT RUN')}")
    if abort:
        print(f"ABORT: {abort}")
    print(f"DRY RUN: {status}")
    return 0 if status == "PASS" else 1


def cmd_official(args):
    pf = load_preflight(args.run_id)
    dr = run_dir(args.run_id) / "dry_run_status.json"
    if not dr.exists() or read_json(dr)["status"] != "PASS":
        sys.exit("ABORT: dry run has not passed; official run refused")
    tasks = load_tasks()
    done, abort = 0, None
    try:
        for model in MODELS:
            for cond in CONDITIONS:
                for tid in OFFICIAL_TASKS:
                    run_one(args.run_id, pf, "official", model, cond, tasks[tid])
                    done += 1
    except SafetyAbort as exc:
        abort = str(exc)
    status = {"status": "COMPLETE" if abort is None else "ABORTED", "completed": done,
              "expected": len(MODELS) * len(CONDITIONS) * len(OFFICIAL_TASKS),
              "abort": abort, "timestamp": now()}
    write_json(run_dir(args.run_id) / "official_status.json", status)
    print(f"\nOFFICIAL: {status['status']} {done}/{status['expected']}")
    if abort:
        print(f"ABORT: {abort}")
    return 0 if abort is None else 1


# ---------------------------------------------------------------- scoring
#
# Term identity:
#   strict  = equal after uppercasing and removing non-alphanumerics
#             (HTTP_503 == HTTP503 == http503)
#   lenient = token-set Jaccard >= 0.5 with a unique best canonical candidate;
#             every lenient-only alignment marks the record scoring_uncertain.
# Evidence identifiers are only ever matched strictly.
#
# Condition A (natural language) cannot be parsed deterministically. Only
# evidence-identifier presence is scored; everything else is null and the
# record is marked manual_review_required.

TERM = r"[A-Za-z0-9_][A-Za-z0-9_.\-]*"
MARK = r"(φ|ε|\?|ĥ)"
STMT = rf"(?:φ:{TERM}(?:\s*∵\s*ε:{TERM})?|ε:{TERM}|\?:{TERM}|ĥ:{TERM})"
LINE_RE = re.compile(rf"^{STMT}(?:\s+{STMT})*$")
ATOM_RE = re.compile(rf"{MARK}\s*:\s*({TERM})")
SUPPORT_RE = re.compile(rf"(?:{MARK}\s*:\s*)?({TERM})[\s\"':,]*∵\s*(?:(ε)\s*:\s*)?({TERM})")
CAT = {"φ": "assertions", "ε": "evidence", "?": "unknowns", "ĥ": "hypotheses"}


def norm(t):
    return re.sub(r"[^A-Z0-9]", "", t.upper())


def toks(t):
    out = set()
    for w in re.findall(r"[A-Z]+|[0-9]+", t.upper()):
        out.add(w[:-1] if len(w) > 3 and w.endswith("S") else w)
    return out


def align(term, canon, lenient):
    """canon: {canonical_term: category}. Returns (canonical_term|None, match_type, note)."""
    for c in canon:
        if norm(c) == norm(term):
            return c, "strict", None
    if not lenient:
        return None, None, None
    tt = toks(term)
    scored = []
    for c in canon:
        ct = toks(c)
        j = len(tt & ct) / len(tt | ct) if tt | ct else 0.0
        if j >= 0.5:
            scored.append((j, c))
    if not scored:
        return None, None, None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, "ambiguous", [c for j, c in scored if j == scored[0][0]]
    return scored[0][1], "lenient", round(scored[0][0], 3)


def parse_lambda(text):
    text = unicodedata.normalize("NFC", text or "")  # h+U+0302 -> ĥ only
    violations = []
    if not text.strip():
        violations.append("empty_output")
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("```"):
            violations.append("code_fence")
        elif not LINE_RE.match(s):
            violations.append(f"non_protocol_line: {s[:120]}")

    items = {k: [] for k in CAT.values()}
    for m in ATOM_RE.finditer(text):
        items[CAT[m.group(1)]].append(m.group(2))
    edges = []
    for m in SUPPORT_RE.finditer(text):
        lmark, left, emark, ev = m.groups()
        edges.append({"left": left, "left_marker": lmark, "evidence": ev,
                      "evidence_marker": emark})
        if lmark is None:
            violations.append(f"missing_assertion_marker: {left}")
            items["assertions"].append(left)  # only assertions take ∵ in v0
        elif lmark != "φ":
            violations.append(f"support_on_non_assertion: {lmark}:{left}")
        if emark is None:
            violations.append(f"missing_evidence_marker: {ev}")
            items["evidence"].append(ev)
    return items, edges, violations


def score_lambda(rec, lenient):
    cs = rec["canonical_state"]
    canon_terms = {**{t: "assertions" for t in cs["assertions"]},
                   **{t: "unknowns" for t in cs["unknowns"]},
                   **{t: "hypotheses" for t in cs["hypotheses"]}}
    canon_ev = {e: "evidence" for e in cs["evidence"]}
    canon_edges = {tuple(e) for e in cs["support_edges"]}
    items, edges, violations = parse_lambda(rec["visible_response"])

    preserved = {k: set() for k in ["assertions", "evidence", "unknowns", "hypotheses"]}
    det = {"hypothesis_laundering": [], "unknown_laundering": [], "status_change": [],
           "provenance_loss": [], "provenance_substitution": [], "extra_unsupported_state": []}
    alignments, present = [], set()

    for cat in ["assertions", "unknowns", "hypotheses"]:
        for t in items[cat]:
            c, mt, note = align(t, canon_terms, lenient)
            alignments.append({"output": t, "as": cat, "canonical": c, "match": mt, "note": note})
            if c is None:
                det["extra_unsupported_state"].append(f"{cat}:{t}")
                continue
            present.add(c)
            truth = canon_terms[c]
            if truth == cat:
                preserved[cat].add(c)
            elif truth == "hypotheses" and cat == "assertions":
                det["hypothesis_laundering"].append(c)
            elif truth == "unknowns" and cat in ("assertions", "hypotheses"):
                det["unknown_laundering"].append(c)
            else:
                det["status_change"].append(f"{c}: {truth}->{cat}")
    for e in items["evidence"]:
        c, _, _ = align(e, canon_ev, False)
        if c is None:
            det["extra_unsupported_state"].append(f"evidence:{e}")
        else:
            preserved["evidence"].add(c)

    edge_hits, out_edges = set(), []
    for e in edges:
        lc, lmt, _ = align(e["left"], canon_terms, lenient)
        ec, _, _ = align(e["evidence"], canon_ev, False)
        out_edges.append((lc, ec))
        if lc is not None and (lc, ec) in canon_edges:
            edge_hits.add((lc, ec))
        elif lc is not None and any(a == lc for a, _ in canon_edges):
            det["provenance_substitution"].append(f"{lc} ∵ {e['evidence']}")
        else:
            det["extra_unsupported_state"].append(f"edge:{e['left']}∵{e['evidence']}")
    for a, ev in sorted(canon_edges - edge_hits):
        if a in present and not any(lc == a for lc, _ in out_edges):
            det["provenance_loss"].append(f"{a} ∵ {ev}")

    def rate(n, d):
        return None if d == 0 else round(n / d, 4)

    counts = {
        "assertions": (len(preserved["assertions"]), len(cs["assertions"])),
        "evidence": (len(preserved["evidence"]), len(cs["evidence"])),
        "unknowns": (len(preserved["unknowns"]), len(cs["unknowns"])),
        "hypotheses": (len(preserved["hypotheses"]), len(cs["hypotheses"])),
        "support_edges": (len(edge_hits), len(canon_edges)),
    }
    extra = len(set(det["extra_unsupported_state"]))
    matched = sum(n for n, _ in counts.values())
    total = sum(d for _, d in counts.values())
    return {
        "scoring_status": "deterministic",
        "counts": {k: {"preserved": n, "canonical": d} for k, (n, d) in counts.items()},
        "assertion_preservation": rate(*counts["assertions"]),
        "evidence_identity_preservation": rate(*counts["evidence"]),
        "unknown_preservation": rate(*counts["unknowns"]),
        "hypothesis_preservation": rate(*counts["hypotheses"]),
        "support_edge_preservation": rate(*counts["support_edges"]),
        "semantic_fidelity": rate(matched, total + extra),
        "matched_items": matched, "canonical_items": total, "extra_items": extra,
        "detections": det,
        "missing_assertion_marker": [v for v in violations if v.startswith("missing_assertion_marker")],
        "protocol_violations": violations,
        "protocol_violation": bool(violations),
        "alignments": alignments,
        "scoring_uncertain": any(a["match"] in ("lenient", "ambiguous") for a in alignments),
        "parsed": {"items": items, "edges": edges},
    }


def score_natural(rec):
    cs = rec["canonical_state"]
    text = rec["visible_response"] or ""
    found = [e for e in cs["evidence"]
             if re.search(rf"(?<![A-Za-z0-9]){re.escape(e)}(?![A-Za-z0-9])", text, re.I)]
    n = len(cs["evidence"])
    return {
        "scoring_status": "manual_review_required",
        "note": "natural-language output; only evidence-identifier presence is deterministic",
        "counts": {"evidence": {"preserved": len(found), "canonical": n}},
        "evidence_identity_preservation": None if n == 0 else round(len(found) / n, 4),
        "assertion_preservation": None, "unknown_preservation": None,
        "hypothesis_preservation": None, "support_edge_preservation": None,
        "semantic_fidelity": None, "protocol_violation": None,
        "scoring_uncertain": True,
    }


def aggregate(scored, mode):
    groups = {}
    for r in scored:
        groups.setdefault((r["model"], r["condition"]), []).append(r)
    out = []
    for (model, cond), rs in sorted(groups.items()):
        tok_in = sum(r["prompt_tokens"] or 0 for r in rs)
        tok_out = sum(r["output_tokens"] or 0 for r in rs)
        row = {"model": model, "condition": cond, "mode": mode, "n": len(rs),
               "TC": {"prompt_tokens": tok_in, "output_tokens": tok_out,
                      "total_tokens": tok_in + tok_out,
                      "mean_output_tokens": round(tok_out / len(rs), 2)},
               "done_reason_counts": {}}
        for r in rs:
            row["done_reason_counts"][r["done_reason"]] = row["done_reason_counts"].get(r["done_reason"], 0) + 1
        sc = [r["scores"][mode] for r in rs]
        if cond == "A":
            ev_n = sum(s["counts"]["evidence"]["preserved"] for s in sc)
            ev_d = sum(s["counts"]["evidence"]["canonical"] for s in sc)
            row.update(scoring_status="manual_review_required",
                       SF=None, PS=None, US=None, PV=None,
                       evidence_identity=round(ev_n / ev_d, 4) if ev_d else None)
        else:
            def tot(k, f):
                return sum(s["counts"][k][f] for s in sc)

            def rate(n, d):
                return None if d == 0 else round(n / d, 4)
            unc_n = tot("unknowns", "preserved") + tot("hypotheses", "preserved")
            unc_d = tot("unknowns", "canonical") + tot("hypotheses", "canonical")
            row.update(
                scoring_status="deterministic",
                SF=rate(sum(s["matched_items"] for s in sc),
                        sum(s["canonical_items"] + s["extra_items"] for s in sc)),
                PS=rate(tot("support_edges", "preserved"), tot("support_edges", "canonical")),
                US=rate(unc_n, unc_d),
                PV={"records_with_violation": sum(s["protocol_violation"] for s in sc),
                    "total_violations": sum(len(s["protocol_violations"]) for s in sc)},
                per_category={k: {"preserved": tot(k, "preserved"), "canonical": tot(k, "canonical")}
                              for k in ["assertions", "evidence", "unknowns", "hypotheses", "support_edges"]},
                detections={k: sum(len(s["detections"][k]) for s in sc)
                            for k in sc[0]["detections"]},
                missing_assertion_marker=sum(len(s["missing_assertion_marker"]) for s in sc),
                records_scoring_uncertain=sum(s["scoring_uncertain"] for s in sc),
            )
        out.append(row)
    return out


def cmd_score(args):
    rd = run_dir(args.run_id)
    sd = summary_dir(args.run_id)
    defs = {
        "strict": "term identity = equality after uppercasing and removing non-alphanumerics",
        "lenient": "strict, plus token-set Jaccard >= 0.5 with unique best candidate (uncertain)",
        "SF": "matched canonical items (assertions+evidence+unknowns+hypotheses+edges) / (canonical items + extra unsupported items), micro-averaged",
        "PS": "canonical support edges preserved with exact endpoints and direction / canonical support edges",
        "US": "(unknowns preserved as ? + hypotheses preserved as ĥ) / (canonical unknowns + hypotheses)",
        "PV": "records with >=1 syntax/protocol violation; total violations",
        "TC": "prompt + output tokens as reported by Ollama",
        "condition_A": "natural language; only evidence-identifier presence scored deterministically, rest manual_review_required",
        "unmarked_support_left": "a term on the left of ∵ without φ counts as an assertion for semantic scoring and is also reported as missing_assertion_marker",
    }
    for phase in ["dry_run", "official"]:
        files = sorted((rd / phase).glob("*.json")) if (rd / phase).exists() else []
        scored = []
        for f in files:
            rec = read_json(f)
            if rec.get("status") != "complete":
                continue
            if rec["condition"] == "A":
                s = score_natural(rec)
                rec["scores"] = {"strict": s, "lenient": s}
            else:
                rec["scores"] = {"strict": score_lambda(rec, False),
                                 "lenient": score_lambda(rec, True)}
            slim = {k: v for k, v in rec.items() if k not in ("attempts",)}
            slim["raw_response"] = {k: v for k, v in rec["raw_response"].items() if k != "context"}
            slim["raw_response_context_omitted"] = "context" in rec["raw_response"]
            slim["raw_record_sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
            slim["attempt_summary"] = [{"attempt": a["attempt"], "transport_ok": a["transport_ok"],
                                        "transport_error": a.get("transport_error"),
                                        "safety": {k: v for k, v in a["safety"].items()}}
                                       for a in rec["attempts"]]
            scored.append(slim)
        if not scored:
            continue
        with (sd / f"records_{phase}.jsonl").open("w", encoding="utf-8") as fh:
            for r in scored:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        write_json(sd / f"scores_{phase}.json", {
            "run_id": args.run_id, "phase": phase,
            "official_score": phase == "official",
            "scorer_sha256": sha256_file("runner/experiment_zero.py"),
            "definitions": defs,
            "strict": aggregate(scored, "strict"),
            "lenient": aggregate(scored, "lenient"),
        })
        print(f"scored {phase}: {len(scored)} records -> {sd.relative_to(ROOT)}")
    for name in ["dry_run_status.json", "official_status.json"]:
        if (rd / name).exists():
            write_json(sd / name, read_json(rd / name))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["preflight", "dry-run", "official", "score"])
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    return {"preflight": cmd_preflight, "dry-run": cmd_dry_run,
            "official": cmd_official, "score": cmd_score}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
