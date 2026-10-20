"""Model-spec parsing and the Gemini/Claude request formats, with the HTTP layer mocked (no keys or network)."""
import json
import re
import threading
import time
import urllib.error
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
    ("gemini:gemini-3.8-flash", ("gemini", "gemini-3.8-flash")),
    ("claude", ("claude", llm.CLOUD_DEFAULTS["claude"])),
    ("claude:claude-opus-5-5", ("claude", "claude-opus-5-5")),
])
def test_split(spec, expected):
    assert llm.split(spec) == expected


def test_cloud_grader_is_the_selected_model():
    assert llm.grader_model("gemini:gemini-3.8-flash") == "gemini:gemini-3.8-flash"
    assert llm.grader_model("claude") == "claude"


def test_gemini_request(calls):
    log, queue = calls
    queue.append(Resp(200, {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True},
                                                                  {"text": '{"a": 1}'}]}}],
                            "usageMetadata": {"candidatesTokenCount": 5}}))
    assert llm.chat_json(MSGS, model="gemini:gemini-3.8-flash") == {"a": 1}
    req = log[0]
    assert req["url"].endswith("/models/gemini-3.8-flash:generateContent")
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
    monkeypatch.setattr(web, "provider_status", lambda refresh=False, keys=None: {
        p: {"ready": p == "ollama", "models": ["qwen3:8b"] if p == "ollama" else [], "default": d}
        for p, d in (("ollama", "qwen3:8b"), ("gemini", "gemini-2.5-flash"), ("claude", "claude-sonnet-5-5"))})
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "Google Gemini" in urllib.request.urlopen(base + "/settings").read().decode()
        data = b"provider=gemini&model=gemini-3.8-flash&prose=llm"
        urllib.request.urlopen(base + "/settings", data=data)
        assert web.SETTINGS["model"] == "gemini:gemini-3.8-flash" and web.SETTINGS["prose"] == "llm"
        assert "gemini-3.8-flash" in (tmp_path / "settings.json").read_text()
        assert "/settings#keys" in urllib.request.urlopen(base + "/").read().decode()
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


def test_daily_quota_fails_fast_and_is_remembered(calls):
    log, queue = calls
    llm.EXHAUSTED.clear()
    body = {"error": {"message": "You exceeded your current quota.\n* Quota exceeded for metric: free_tier_requests, "
                                 "limit: 20", "details": [{"retryDelay": "48017s"}]}}
    queue.append(Resp(429, body))
    with pytest.raises(llm.QuotaError, match="limit: 20"):
        llm.chat(MSGS, model="gemini")
    with pytest.raises(llm.QuotaError):
        llm.chat(MSGS, model="gemini")
    assert len(log) == 1  # the second call never reached the API
    llm.EXHAUSTED.clear()


def test_web_key_is_kept_in_the_browser_only(tmp_path, monkeypatch):
    from examx import web
    monkeypatch.setattr(web, "OUT", tmp_path)
    monkeypatch.setattr(web, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(llm, "check_key", lambda provider, key: key.startswith("sk-ant-good"))
    seen = {}
    monkeypatch.setattr(llm, "status", lambda: {p: {"ready": bool(llm.api_key(p)) if p != "ollama" else False,
                                                     "models": [], "default": "x"} for p in llm.PROVIDERS})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    key = "sk-ant-good-" + "x" * 30
    try:
        with pytest.raises(urllib.error.HTTPError) as bad:
            opener.open(base + "/keys", data=b"provider=claude&key=sk-ant-bad-" + b"x" * 30)
        assert "key=bad" in bad.value.headers["Location"] and not bad.value.headers.get("Set-Cookie")
        with pytest.raises(urllib.error.HTTPError) as ok:
            opener.open(base + "/keys", data=f"provider=claude&key={key}".encode())
        cookie = ok.value.headers["Set-Cookie"]
        assert key in cookie and "HttpOnly" in cookie and "Secure" in cookie and "Max-Age" not in cookie
        req = urllib.request.Request(base + "/settings", headers={"Cookie": cookie.split(";")[0]})
        body = urllib.request.urlopen(req).read().decode()
        assert "key saved in this browser" in body and key not in body

        def job(uid, log):
            seen["key"] = llm.api_key("claude")
        jid = web.run_job("t", job, keys={"claude": key})
        for _ in range(50):
            if web.JOBS[jid]["done"]:
                break
            time.sleep(0.05)
        assert seen["key"] == key and llm.api_key("claude") is None  # only inside the job's thread
        assert not any(key in f.read_text() for f in tmp_path.rglob("*") if f.is_file())
    finally:
        server.shutdown()


def test_public_visitors_are_isolated_and_cannot_use_server_resources(tmp_path, monkeypatch):
    from examx import web
    monkeypatch.setattr(web, "OUT", tmp_path)
    monkeypatch.setattr(web, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(web, "OWNERS_FILE", tmp_path / "owners.json")
    monkeypatch.setattr(web, "_public_jobs", {})
    monkeypatch.setattr(web, "PUBLIC_DAILY_JOBS", 2)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-key-" + "x" * 20)
    monkeypatch.setattr(llm, "status", lambda: {p: {"ready": p == "ollama" or bool(llm.api_key(p)), "models": [],
                                                     "default": "qwen3:8b" if p == "ollama" else p}
                                                 for p in llm.PROVIDERS})
    monkeypatch.setattr(web, "_status_cache", {})
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)

    def visit(path, ip, uid=None, data=None):
        headers = {"Cf-Connecting-IP": ip} if ip else {}
        if uid:
            headers["Cookie"] = f"examx_uid={uid}"
        try:
            r = opener.open(urllib.request.Request(base + path, data=data, headers=headers))
            return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def wait(seed):
        for _ in range(100):
            if (tmp_path / f"practice-{seed}.json").exists() and (tmp_path / "owners.json").exists():
                return
            time.sleep(0.05)
    try:
        # The server's own key is not offered to public visitors; local models are owner-only.
        code, headers, body = visit("/", "1.2.3.4")
        alice = re.search(r"examx_uid=([0-9a-f]{32})", headers["Set-Cookie"]).group(1)
        body = visit("/settings", "1.2.3.4", alice)[2]
        assert "server owner only" in body and "no API key" in body
        code, _, body = visit("/generate", "1.2.3.4", alice, b"seed=11&llm=on")
        assert code == 429 and "not available" in body
        # Without AI: allowed, and only Alice sees it in her list.
        code, headers, _ = visit("/generate", "1.2.3.4", alice, b"seed=11")
        assert code == 303
        wait(11)
        assert "Seed 11" in visit("/", "1.2.3.4", alice)[2]
        bob = "b" * 32
        assert "Seed 11" not in visit("/", "5.6.7.8", bob)[2]
        # Bob cannot overwrite Alice's paper by reusing its seed: he is sent to it instead.
        code, headers, _ = visit("/generate", "5.6.7.8", bob, b"seed=11")
        assert code == 303 and headers["Location"] == "/paper/11"
        # Per-IP daily limit (2 here).
        while any(not j["done"] for j in web.JOBS.values()):
            time.sleep(0.05)
        assert visit("/generate", "1.2.3.4", alice, b"seed=12")[0] == 303
        while any(not j["done"] for j in web.JOBS.values()):
            time.sleep(0.05)
        code, _, body = visit("/generate", "1.2.3.4", alice, b"seed=13")
        assert code == 429 and "limit" in body
        # The owner on localhost sees everything and may use local models and server keys.
        body = visit("/settings", None)[2]
        assert "server owner only" not in body
        assert "Seed 11" in visit("/", None)[2] and "Seed 12" in visit("/", None)[2]
    finally:
        server.shutdown()
