#!/usr/bin/env python3

import json
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

MODELS = [
    "gemma3:1b",
    "qwen3:1.7b",
    "qwen3.5:2b",
]

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "results" / "raw"
SUMMARY_DIR = ROOT / "results" / "summary"

RAW_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)


def call_model(model: str) -> dict:
    expected = f"READY-{model}"

    payload = {
        "model": model,
        "prompt": f"Return exactly this text and nothing else: {expected}",
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_ctx": 2048,
            "num_predict": 40,
        },
        "keep_alive": 0,
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.time()

    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read()

    finished = time.time()

    data = json.loads(body)
    data["_request"] = payload
    data["_wall_seconds"] = round(finished - started, 3)
    return data


rows = []

for model in MODELS:
    expected = f"READY-{model}"

    print()
    print(f"===== STUDENT: {model} =====")

    try:
        result = call_model(model)
    except Exception as exc:
        row = {
            "model": model,
            "status": "ERROR",
            "error": repr(exc),
        }
        rows.append(row)
        print("ERROR:", repr(exc))
        continue

    safe_name = model.replace(":", "__").replace("/", "_")
    raw_path = RAW_DIR / f"smoke_{safe_name}.json"

    raw_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    response = result.get("response")
    thinking = result.get("thinking")
    exact = response == expected

    row = {
        "model": model,
        "expected": expected,
        "response": response,
        "thinking_present": bool(thinking),
        "done": result.get("done"),
        "done_reason": result.get("done_reason"),
        "prompt_tokens": result.get("prompt_eval_count"),
        "output_tokens": result.get("eval_count"),
        "wall_seconds": result.get("_wall_seconds"),
        "exact_match": exact,
    }

    rows.append(row)

    print("response:", repr(response))
    print("thinking_present:", bool(thinking))
    print("done_reason:", result.get("done_reason"))
    print("prompt_tokens:", result.get("prompt_eval_count"))
    print("output_tokens:", result.get("eval_count"))
    print("wall_seconds:", result.get("_wall_seconds"))
    print("exact_match:", exact)

summary_path = SUMMARY_DIR / "smoke_models.json"
summary_path.write_text(
    json.dumps(rows, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print()
print("===== STATUS =====")

all_ok = True

for row in rows:
    if row.get("status") == "ERROR":
        all_ok = False
        print(f"{row['model']}: ERROR")
        continue

    ok = (
        row["exact_match"] is True
        and row["thinking_present"] is False
        and row["done"] is True
        and row["done_reason"] == "stop"
    )

    if not ok:
        all_ok = False

    print(
        f"{row['model']}: "
        f"exact={row['exact_match']} "
        f"thinking={row['thinking_present']} "
        f"reason={row['done_reason']} "
        f"tokens={row['output_tokens']} "
        f"{'PASS' if ok else 'FAIL'}"
    )

print(f"summary={summary_path.relative_to(ROOT)}")
print(f"overall={'PASS' if all_ok else 'FAIL'}")
print("===== END =====")

raise SystemExit(0 if all_ok else 1)
