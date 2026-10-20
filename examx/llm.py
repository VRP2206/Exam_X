"""Minimal client for a local Ollama server.

The model is chosen with EXAMX_MODEL (default qwen3:8b: it runs split between
the GTX 1650 and system RAM at ~8 tok/s but writes markedly better proofs than
the 4B models, see README) and the server with OLLAMA_HOST (default localhost:11434).
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

DEFAULT_MODEL = os.environ.get("EXAMX_MODEL", "qwen3:8b")
# Marking proofs needs more careful reasoning than writing questions, and is a smaller job.
GRADER_MODEL = os.environ.get("EXAMX_GRADER_MODEL", DEFAULT_MODEL)
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not HOST.startswith("http"):
    HOST = "http://" + HOST


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.7, json_mode: bool = False,
         num_ctx: int = 8192, num_predict: int = 2048, think: bool = False, timeout: int = 900) -> str:
    body = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict},
    }
    if json_mode:
        body["format"] = "json"
    try:
        r = requests.post(f"{HOST}/api/chat", json=body, timeout=timeout)
    except requests.ConnectionError as e:
        raise LLMError(f"cannot reach Ollama at {HOST} (is `ollama serve` running?)") from e
    if r.status_code != 200:
        raise LLMError(f"Ollama error {r.status_code}: {r.text[:300]}")
    data = r.json()
    chat.last_stats = {k: data.get(k) for k in ("eval_count", "eval_duration", "prompt_eval_count", "total_duration")}
    return strip_think(data["message"]["content"])


chat.last_stats = {}


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def chat_json(messages: list[dict], retries: int = 2, **kw) -> dict:
    """Ask for a JSON object; retry with the parse error appended if the model returns invalid JSON."""
    last = ""
    for attempt in range(retries + 1):
        out = chat(messages, json_mode=True, **kw)
        try:
            return parse_json(out)
        except ValueError as e:
            last = out
            messages = messages + [
                {"role": "assistant", "content": out},
                {"role": "user", "content": f"That was not valid JSON ({e}). Reply with only the corrected JSON object."},
            ]
    raise LLMError(f"model did not return valid JSON: {last[:300]}")


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ValueError(str(e)) from e
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    return obj


def available_models() -> list[str]:
    try:
        r = requests.get(f"{HOST}/api/tags", timeout=10)
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def benchmark(models: list[str], prompt: str) -> list[dict]:
    """Time each model on the same prompt (after a warm-up call so load time is reported separately)."""
    rows = []
    for m in models:
        t0 = time.time()
        chat([{"role": "user", "content": "Say OK."}], model=m, num_predict=5)
        load = time.time() - t0
        t0 = time.time()
        out = chat([{"role": "user", "content": prompt}], model=m, temperature=0.2, num_predict=700)
        wall = time.time() - t0
        st = chat.last_stats
        tps = st["eval_count"] / (st["eval_duration"] / 1e9) if st.get("eval_duration") else 0
        rows.append({"model": m, "load_s": round(load, 1), "wall_s": round(wall, 1), "tokens": st.get("eval_count"),
                     "tok_per_s": round(tps, 1), "output": out})
    return rows
