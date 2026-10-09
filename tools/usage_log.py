"""Append one JSON line per paid Gemini call to usage.jsonl in the project root.

tools/costs.py prices the log. Token counts are normalised to
{"input": {modality: n}, "output": {modality: n}, "thought": n}, modalities in lower case.
"""
import json
import threading
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "usage.jsonl"
_lock = threading.Lock()


def _by_modality(items, key, total):
    out = {}
    for item in items or []:
        modality = str(item.get("modality") or "unspecified").lower()
        out[modality] = out.get(modality, 0) + (item.get(key) or 0)
    if not out and total:
        out["unspecified"] = total
    return out


def from_interaction(usage):
    """Normalise the `usage` of an Interactions API response (None when absent)."""
    if usage is None:
        return None
    u = usage.model_dump(mode="json", exclude_none=True)
    return {
        "input": _by_modality(u.get("input_tokens_by_modality"), "tokens", u.get("total_input_tokens")),
        "output": _by_modality(u.get("output_tokens_by_modality"), "tokens", u.get("total_output_tokens")),
        "thought": u.get("total_thought_tokens", 0),
    }


def from_generate(meta):
    """Normalise the `usage_metadata` of a generate_content response (None when absent)."""
    if meta is None:
        return None
    u = meta.model_dump(mode="json", exclude_none=True)
    return {
        "input": _by_modality(u.get("prompt_tokens_details"), "token_count", u.get("prompt_token_count")),
        "output": _by_modality(u.get("candidates_tokens_details"), "token_count", u.get("candidates_token_count")),
        "thought": u.get("thoughts_token_count", 0),
    }


def summary(usage):
    """One line for the terminal, e.g. 'tokens in 120 (text 120), out 2,450 (audio 2,450)'."""
    if usage is None:
        return "no usage returned"
    parts = []
    for direction, label in (("input", "in"), ("output", "out")):
        counts = usage[direction]
        detail = ", ".join(f"{m} {n:,}" for m, n in counts.items())
        parts.append(f"{label} {sum(counts.values()):,} ({detail})")
    if usage["thought"]:
        parts.append(f"thought {usage['thought']:,}")
    return "tokens " + ", ".join(parts)


def log(script, model, usage, **extra):
    """Append a call to the log: script name, model, normalised usage, and any extra fields."""
    line = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": script, "model": model,
            "usage": usage, **extra}
    with _lock, LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
