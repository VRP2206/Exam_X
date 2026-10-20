"""LLM client with three interchangeable back ends: a local Ollama server, Google Gemini and Anthropic Claude.

A model is named by a spec string "provider:model", where the provider is ollama, gemini or claude:

    qwen3:8b                  local Ollama model (a bare name means Ollama)
    ollama:qwen3:14b          the same, explicitly
    gemini                    Gemini with the default model ($EXAMX_GEMINI_MODEL or gemini-2.5-flash)
    gemini:gemini-3.8-flash   a specific Gemini model
    claude                    Claude with the default model ($EXAMX_CLAUDE_MODEL or claude-sonnet-5-5)
    claude:claude-opus-5-5    a specific Claude model

The default spec is $EXAMX_MODEL (default qwen3:8b). API keys are read only from the environment
(GEMINI_API_KEY or GOOGLE_API_KEY, and ANTHROPIC_API_KEY) and are never written anywhere.
The Ollama server is $OLLAMA_HOST (default localhost:11434).
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

PROVIDERS = ("ollama", "gemini", "claude")
DEFAULT_MODEL = os.environ.get("EXAMX_MODEL", "qwen3:8b")
CLOUD_DEFAULTS = {
    # gemini-2.5-* is closed to new keys and the free tier has no Pro quota; 3.5-flash answered fastest in testing.
    "gemini": os.environ.get("EXAMX_GEMINI_MODEL", "gemini-3.5-flash"),
    "claude": os.environ.get("EXAMX_CLAUDE_MODEL", "claude-sonnet-5-5"),
}
# Marking proofs locally needs more careful reasoning than writing questions, and is a smaller job.
# qwen3:14b runs mostly on CPU (~2 min per proof) but, unlike the 8B model, did not invent errors in a
# correct proof and still gave 0 to a bogus one (see README). Falls back to DEFAULT_MODEL if not pulled.
# Cloud models mark with the same model that is selected for generation.
GRADER_MODEL = os.environ.get("EXAMX_GRADER_MODEL", "qwen3:14b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not HOST.startswith("http"):
    HOST = "http://" + HOST
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
CLAUDE_URL = "https://api.anthropic.com/v1"


def split(spec: str | None) -> tuple[str, str]:
    """"gemini:gemini-3.8-flash" -> ("gemini", "gemini-3.8-flash"); "qwen3:8b" -> ("ollama", "qwen3:8b")."""
    spec = (spec or DEFAULT_MODEL).strip()
    provider, _, name = spec.partition(":")
    if provider not in PROVIDERS:
        return "ollama", spec
    return provider, name or CLOUD_DEFAULTS.get(provider, "qwen3:8b")


def is_cloud(spec: str | None) -> bool:
    return split(spec)[0] != "ollama"


def grader_model(spec: str | None = None) -> str:
    spec = spec or DEFAULT_MODEL
    if is_cloud(spec):
        return spec
    if "EXAMX_GRADER_MODEL" in os.environ or GRADER_MODEL in available_models():
        return GRADER_MODEL
    return spec


def api_key(provider: str) -> str | None:
    names = {"gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "claude": ("ANTHROPIC_API_KEY",)}[provider]
    return next((os.environ[n] for n in names if os.environ.get(n)), None)


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.7, json_mode: bool = False,
         num_ctx: int = 8192, num_predict: int = 2048, think: bool = False, timeout: int = 900) -> str:
    """Send OpenAI-style messages (system/user/assistant) to the provider named by the model spec."""
    provider, name = split(model)
    t0 = time.time()
    if provider == "gemini":
        out = _gemini(messages, name, temperature, json_mode, num_predict, timeout)
    elif provider == "claude":
        out = _claude(messages, name, temperature, num_predict, timeout)
    else:
        return _ollama(messages, name, temperature, json_mode, num_ctx, num_predict, think, timeout)
    chat.last_stats.setdefault("eval_duration", (time.time() - t0) * 1e9)
    return out


def _ollama(messages, model, temperature, json_mode, num_ctx, num_predict, think, timeout) -> str:
    body = {
        "model": model,
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


class QuotaError(LLMError):
    """The provider's quota is used up for longer than is worth waiting (e.g. a free-tier daily limit)."""


EXHAUSTED: dict[str, tuple[float, str]] = {}  # url -> (time the quota resets, message): skip calls until then


def _retry_delay(r) -> float | None:
    """Seconds the API asks us to wait, from Retry-After or Gemini's RetryInfo ("48017s")."""
    wait = r.headers.get("retry-after", "")
    if wait.replace(".", "", 1).isdigit():
        return float(wait)
    try:
        for d in r.json().get("error", {}).get("details", []):
            if str(d.get("retryDelay", "")).endswith("s"):
                return float(d["retryDelay"][:-1])
    except (ValueError, AttributeError):
        pass
    return None


def _message(r) -> str:
    try:
        err = r.json().get("error", {})
        return (err.get("message") if isinstance(err, dict) else str(err)) or r.text[:300]
    except ValueError:
        return r.text[:300]


def _post(name: str, url: str, headers: dict, body: dict, timeout: int, retries: int = 4) -> dict:
    """POST to a cloud API, waiting and retrying on short rate limits and transient overloads.

    A quota that resets later than MAX_WAIT seconds from now fails at once, and later calls to the same
    model fail immediately too, so a run falls back instead of stalling for minutes per question."""
    if url in EXHAUSTED and EXHAUSTED[url][0] > time.time():
        raise QuotaError(EXHAUSTED[url][1])
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            if attempt == retries:
                raise LLMError(f"cannot reach the {name} API: {e}") from e
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        msg = _message(r).strip()
        if r.status_code == 429:
            delay = _retry_delay(r)
            if delay is not None and delay > MAX_WAIT or "PerDay" in r.text:
                hours = f"; resets in about {delay / 3600:.1f} h" if delay else ""
                text = (f"{name} quota used up{hours}. {msg.splitlines()[0]} "
                        f"{(msg.splitlines() + [''])[1].strip()} Choose another model or a local one.")
                EXHAUSTED[url] = (time.time() + (delay or 3600), text)
                raise QuotaError(text)
        if r.status_code in (429, 500, 502, 503, 504, 529) and attempt < retries:
            delay = _retry_delay(r)
            time.sleep(min(delay, MAX_WAIT) if delay else 15 * (attempt + 1))
            continue
        raise LLMError(f"{name} API error {r.status_code}: {msg[:300]}")
    raise LLMError(f"{name} API: too many retries")


MAX_WAIT = 120


def _gemini(messages, model, temperature, json_mode, num_predict, timeout) -> str:
    key = api_key("gemini")
    if not key:
        raise LLMError("GEMINI_API_KEY is not set (get a free key at https://aistudio.google.com/apikey)")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages if m["role"] != "system"]
    # Gemini 2.5 models think before answering, and thinking tokens count towards maxOutputTokens.
    config = {"temperature": temperature, "maxOutputTokens": num_predict + 8192}
    if json_mode:
        config["responseMimeType"] = "application/json"
    body = {"contents": contents, "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post("Gemini", f"{GEMINI_URL}/models/{model}:generateContent", {"x-goog-api-key": key}, body, timeout)
    usage = data.get("usageMetadata", {})
    chat.last_stats = {"eval_count": usage.get("candidatesTokenCount"), "prompt_eval_count": usage.get("promptTokenCount")}
    cands = data.get("candidates") or []
    if not cands:
        raise LLMError(f"Gemini returned no answer: {json.dumps(data.get('promptFeedback', data))[:300]}")
    text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []) if not p.get("thought"))
    if not text:
        raise LLMError(f"Gemini returned an empty answer (finishReason {cands[0].get('finishReason')})")
    return text.strip()


def _claude(messages, model, temperature, num_predict, timeout) -> str:
    key = api_key("claude")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set (create a key at https://console.anthropic.com)")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    body = {"model": model, "max_tokens": max(num_predict, 4096), "temperature": temperature,
            "messages": [m for m in messages if m["role"] != "system"]}
    if system:
        body["system"] = system
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    try:
        data = _post("Claude", f"{CLAUDE_URL}/messages", headers, body, timeout)
    except LLMError as e:
        if "temperature" not in str(e):
            raise
        body.pop("temperature")  # some models only accept their default sampling settings
        data = _post("Claude", f"{CLAUDE_URL}/messages", headers, body, timeout)
    usage = data.get("usage", {})
    chat.last_stats = {"eval_count": usage.get("output_tokens"), "prompt_eval_count": usage.get("input_tokens")}
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if not text:
        raise LLMError(f"Claude returned an empty answer (stop_reason {data.get('stop_reason')})")
    return text.strip()


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


def available_models(provider: str = "ollama") -> list[str]:
    """Model names the provider offers (Ollama: pulled models). Empty if unreachable or no key is set."""
    try:
        if provider == "ollama":
            r = requests.get(f"{HOST}/api/tags", timeout=10)
            return [m["name"] for m in r.json().get("models", [])]
        key = api_key(provider)
        if not key:
            return []
        if provider == "gemini":
            r = requests.get(f"{GEMINI_URL}/models", headers={"x-goog-api-key": key},
                             params={"pageSize": 200}, timeout=10)
            return sorted(m["name"].removeprefix("models/") for m in r.json().get("models", [])
                          if "generateContent" in m.get("supportedGenerationMethods", [])
                          and m["name"].startswith("models/gemini"))
        r = requests.get(f"{CLAUDE_URL}/models", headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                         params={"limit": 100}, timeout=10)
        return [m["id"] for m in r.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError):
        return []


def status() -> dict:
    """Which back ends are usable right now, for the CLI and web UI (never includes key values)."""
    out = {}
    for p in PROVIDERS:
        models = available_models(p)
        ready = bool(models) if p == "ollama" else bool(api_key(p))
        out[p] = {"ready": ready, "models": models,
                  "default": CLOUD_DEFAULTS.get(p) or (DEFAULT_MODEL if not is_cloud(DEFAULT_MODEL) else "qwen3:8b")}
    return out


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
        tps = st["eval_count"] / (st["eval_duration"] / 1e9) if st.get("eval_duration") and st.get("eval_count") else 0
        rows.append({"model": m, "load_s": round(load, 1), "wall_s": round(wall, 1), "tokens": st.get("eval_count"),
                     "tok_per_s": round(tps, 1), "output": out})
    return rows
