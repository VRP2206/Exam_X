"""Model-spec parsing and the Gemini/Claude request formats, with the HTTP layer mocked (no keys or network)."""
import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from examx import llm

MSGS = [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Again"}]


class Resp:
    def __init__(self, code, data, headers=None):
        self.status_code, self._data, self.headers = code, data, headers or {}
        self.text = json.dumps(data)

    def json(self):
        return self._data


@pytest.fixture
def calls(monkeypatch):
    """Record each POST and answer from a queue of responses."""
    log, queue = [], []

    def post(url, headers=None, json=None, timeout=None):
        log.append({"url": url, "headers": headers, "body": dict(json)})
        return queue.pop(0)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-claude")
    return log, queue


@pytest.mark.parametrize("spec,expected", [
    ("qwen3:8b", ("ollama", "qwen3:8b")),
    ("ollama:qwen3:14b", ("ollama", "qwen3:14b")),
    ("gemini", ("gemini", llm.CLOUD_DEFAULTS["gemini"])),
    ("gemini:gemini-2.5-pro", ("gemini", "gemini-2.5-pro")),
    ("claude", ("claude", llm.CLOUD_DEFAULTS["claude"])),
    ("claude:claude-opus-5-5", ("claude", "claude-opus-5-5")),
])
def test_split(spec, expected):
    assert llm.split(spec) == expected


def test_cloud_grader_is_the_selected_model():
    assert llm.grader_model("gemini:gemini-2.5-pro") == "gemini:gemini-2.5-pro"
    assert llm.grader_model("claude") == "claude"


def test_gemini_request(calls):
    log, queue = calls
    queue.append(Resp(200, {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True},
                                                                  {"text": '{"a": 1}'}]}}],
                            "usageMetadata": {"candidatesTokenCount": 5}}))
    assert llm.chat_json(MSGS, model="gemini:gemini-2.5-pro") == {"a": 1}
    req = log[0]
    assert req["url"].endswith("/models/gemini-2.5-pro:generateContent")
    assert req["headers"] == {"x-goog-api-key": "test-gemini"}
    assert req["body"]["systemInstruction"] == {"parts": [{"text": "Be terse."}]}
    assert [c["role"] for c in req["body"]["contents"]] == ["user", "model", "user"]
    assert req["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_claude_request_and_temperature_fallback(calls):
    log, queue = calls
    queue.append(Resp(400, {"error": {"message": "temperature is not supported for this model"}}))
    queue.append(Resp(200, {"content": [{"type": "text", "text": "ok"}], "usage": {"output_tokens": 1}}))
    assert llm.chat(MSGS, model="claude:claude-opus-5-5", temperature=0.2) == "ok"
    first, second = log[0]["body"], log[1]["body"]
    assert log[0]["url"].endswith("/v1/messages")
    assert log[0]["headers"]["x-api-key"] == "test-claude"
    assert first["system"] == "Be terse." and first["model"] == "claude-opus-5-5"
    assert [m["role"] for m in first["messages"]] == ["user", "assistant", "user"]
    assert first["temperature"] == 0.2 and "temperature" not in second


def test_rate_limit_is_retried(calls):
    log, queue = calls
    queue += [Resp(429, {}, {"retry-after": "1"}), Resp(200, {"content": [{"type": "text", "text": "ok"}]})]
    assert llm.chat(MSGS, model="claude") == "ok"
    assert len(log) == 2


def test_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY"):
        llm.chat(MSGS, model="gemini")


def test_web_model_switch_and_procedural_paper(tmp_path, monkeypatch):
    from examx import web
    monkeypatch.setattr(web, "OUT", tmp_path)
    monkeypatch.setattr(web, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(web, "provider_status", lambda refresh=False: {
        p: {"ready": p == "ollama", "models": ["qwen3:8b"] if p == "ollama" else [], "default": d}
        for p, d in (("ollama", "qwen3:8b"), ("gemini", "gemini-2.5-flash"), ("claude", "claude-sonnet-5-5"))})
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "Google Gemini" in urllib.request.urlopen(base + "/settings").read().decode()
        data = b"provider=gemini&model=gemini-2.5-pro&prose=llm"
        urllib.request.urlopen(base + "/settings", data=data)
        assert web.SETTINGS["model"] == "gemini:gemini-2.5-pro" and web.SETTINGS["prose"] == "llm"
        assert "gemini-2.5-pro" in (tmp_path / "settings.json").read_text()
        assert "GEMINI_API_KEY" in urllib.request.urlopen(base + "/").read().decode()
        # No AI: a procedural paper, then a blank attempt marked by the exact checkers.
        urllib.request.urlopen(base + "/generate", data=b"seed=7")
        for _ in range(100):
            if (tmp_path / "practice-7.json").exists():
                break
            time.sleep(0.1)
        body = urllib.request.urlopen(base + "/paper/7").read().decode()
        assert "Submit for marking" in body
    finally:
        server.shutdown()
        web.SETTINGS.update(model=llm.DEFAULT_MODEL, prose="past", review=False)
