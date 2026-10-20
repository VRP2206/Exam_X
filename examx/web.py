"""Local web front end (stdlib only): pick the AI model, generate papers, answer them in the browser, get marked.

Run with `examx serve` and open http://127.0.0.1:8014. The model switcher chooses between the local Ollama
models, Google Gemini and Anthropic Claude. API keys are read from the environment only; the page shows
whether a key is set, never its value. Long jobs (LLM generation and marking) run in a background thread and
the job page refreshes until they finish.
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import markdown

from . import llm
from .ingest import DATA_DIR, ROOT
from .render import _maths, render_markdown, render_report

OUT = ROOT / "output"
SETTINGS_FILE = OUT / "settings.json"  # model choice and options only: never keys
JOBS: dict[str, dict] = {}
SETTINGS = {"model": llm.DEFAULT_MODEL, "prose": "past", "review": False}
PROVIDER_LABELS = {"ollama": "Local (Ollama)", "gemini": "Google Gemini", "claude": "Anthropic Claude"}
KEY_HELP = {
    "ollama": "Start Ollama with <code>ollama serve</code> and pull a model, e.g. <code>ollama pull qwen3:8b</code>.",
    "gemini": "Set <code>GEMINI_API_KEY</code> in the environment of <code>examx serve</code> (for the website: in "
              "<code>~/.examx.env</code>, then restart the container). Free key: aistudio.google.com/apikey.",
    "claude": "Set <code>ANTHROPIC_API_KEY</code> in the environment of <code>examx serve</code> (for the website: in "
              "<code>~/.examx.env</code>, then restart the container). Key: console.anthropic.com.",
}
_status_cache: dict = {"at": 0.0, "data": None}
# Public deployment (see deploy/): with EXAMX_REQUIRE_ACCESS=1 every request must carry the identity header that
# Cloudflare Access adds after login, so the site fails closed if Access is not set up. Running AI jobs cost
# API quota, so their number is capped per day and at any one time.
REQUIRE_ACCESS = os.environ.get("EXAMX_REQUIRE_ACCESS") == "1"
ACCESS_HEADER = "Cf-Access-Authenticated-User-Email"
DAILY_AI_JOBS = int(os.environ.get("EXAMX_DAILY_AI_JOBS", "0"))  # 0 = unlimited
MAX_RUNNING = int(os.environ.get("EXAMX_MAX_JOBS", "2"))
MAX_BODY = 1_000_000
_ai_jobs: dict[str, int] = {}

STYLE = """<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--muted:#606a7b;--line:#dde1e8;--accent:#2f5bd3;--accent-fg:#fff;
--ok:#1f8a4c;--warn:#b26a00;--code:#f0f2f5}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1c2027;--fg:#e4e7ec;--muted:#9aa3b2;--line:#2e343e;
--accent:#7c9cff;--accent-fg:#0d1220;--ok:#4cc27e;--warn:#e0a040;--code:#252a33}}
*{box-sizing:border-box}
body{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:var(--bg);color:var(--fg)}
header{background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:16px;
align-items:center;flex-wrap:wrap}
header a.brand{font-weight:700;font-size:17px;color:var(--fg);text-decoration:none}
header nav{display:flex;gap:14px;flex:1} header nav a{color:var(--muted);text-decoration:none}
.chip{font-size:12.5px;padding:3px 10px;border-radius:99px;border:1px solid var(--line);color:var(--muted);
text-decoration:none;white-space:nowrap}
main{max-width:900px;margin:0 auto;padding:20px 16px 60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:0 0 18px}
.card h2{margin:0 0 10px;font-size:17px;border:0}
h1{font-size:22px;margin:4px 0 14px} h2{font-size:18px;margin-top:30px;padding-bottom:4px;border-bottom:1px solid var(--line)}
a{color:var(--accent)} .muted{color:var(--muted);font-size:13.5px}
pre,code{background:var(--code);border-radius:5px} pre{padding:8px 10px;overflow-x:auto} code{padding:1px 4px}
pre code{padding:0}
textarea{width:100%;min-height:110px;font:13.5px/1.4 ui-monospace,Menlo,monospace;padding:8px;border-radius:6px;
border:1px solid var(--line);background:var(--bg);color:var(--fg)}
input[type=text],input:not([type]),select{padding:6px 8px;border-radius:6px;border:1px solid var(--line);
background:var(--bg);color:var(--fg);font:inherit}
button,.btn{background:var(--accent);color:var(--accent-fg);border:0;border-radius:6px;padding:8px 16px;font:inherit;
font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
.providers{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:12px}
.prov{border:1px solid var(--line);border-radius:8px;padding:10px 12px;cursor:pointer;display:block}
.prov:has(input:checked){border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.prov b{display:block} .ok{color:var(--ok)} .warn{color:var(--warn)}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:8px 0}
.log{white-space:pre-wrap;font:13px/1.45 ui-monospace,monospace;background:var(--code);padding:10px;border-radius:6px;
max-height:60vh;overflow:auto}
table{border-collapse:collapse} td,th{border:1px solid var(--line);padding:4px 9px}
.tablewrap{overflow-x:auto} blockquote{color:var(--muted);margin:6px 0;padding-left:10px;border-left:3px solid var(--line)}
ul.papers{list-style:none;padding:0;margin:0} ul.papers li{padding:8px 0;border-top:1px solid var(--line);display:flex;
gap:12px;flex-wrap:wrap;align-items:baseline} ul.papers li:first-child{border-top:0}
img.fig{max-width:100%;border:1px solid var(--line);border-radius:6px;background:#fff;margin:6px 0}
.saved{font-size:12.5px;color:var(--muted)}
</style>"""


def load_settings() -> None:
    try:
        SETTINGS.update({k: v for k, v in json.loads(SETTINGS_FILE.read_text()).items() if k in SETTINGS})
    except (OSError, ValueError):
        pass


def save_settings() -> None:
    OUT.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(SETTINGS, indent=1))


def provider_status(refresh: bool = False) -> dict:
    if refresh or not _status_cache["data"] or time.time() - _status_cache["at"] > 60:
        _status_cache.update(at=time.time(), data=llm.status())
    return _status_cache["data"]


def page(title: str, body: str, refresh: bool = False) -> bytes:
    meta = '<meta http-equiv="refresh" content="3">' if refresh else ""
    provider, name = llm.split(SETTINGS["model"])
    chip = f"{PROVIDER_LABELS[provider].split(' (')[0]} · {name}"
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>{meta}{STYLE}</head>"
            f"<body><header><a class='brand' href='/'>ExamX</a><nav><a href='/'>Papers</a><a href='/settings'>AI model</a>"
            f"</nav><a class='chip' href='/settings' title='Change AI model'>{html.escape(chip)}</a></header>"
            f"<main>{body}</main></body></html>").encode()


def md(text: str) -> str:
    out = markdown.markdown(_maths(text), extensions=["fenced_code", "tables"])
    out = out.replace("<table>", "<div class='tablewrap'><table>").replace("</table>", "</table></div>")
    # Past questions with diagrams name their rendered figures: show them inline.
    return re.sub(r"data/figures/([\w.\-]+\.png)",
                  r"<br><img class='fig' src='/figures/\1' alt='diagram \1'><br>", out)


def papers() -> list[Path]:
    found = [p for p in OUT.glob("practice-*.json") if re.fullmatch(r"practice-\d+", p.stem)] if OUT.exists() else []
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def job_refusal(uses_ai: bool) -> str | None:
    """Why a new job cannot start now, or None."""
    if sum(not j["done"] for j in JOBS.values()) >= MAX_RUNNING:
        return f"{MAX_RUNNING} jobs are already running; try again when one finishes."
    day = time.strftime("%Y-%m-%d")
    if uses_ai and DAILY_AI_JOBS and _ai_jobs.get(day, 0) >= DAILY_AI_JOBS:
        return f"The daily limit of {DAILY_AI_JOBS} AI jobs on this site is reached; it resets at midnight."
    if uses_ai:
        _ai_jobs[day] = _ai_jobs.get(day, 0) + 1
    return None


def run_job(kind: str, fn, *args) -> str:
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"kind": kind, "log": [], "done": False, "result": None, "start": time.time()}

    def log(msg):
        JOBS[jid]["log"].append(str(msg))

    def target():
        try:
            JOBS[jid]["result"] = fn(*args, log=log)
        except Exception:
            log(traceback.format_exc())
        JOBS[jid]["done"] = True
    threading.Thread(target=target, daemon=True).start()
    return jid


def _generate(use_llm: bool, seed, model: str, prose: str, review: bool, log):
    from .generate import generate_paper, save_paper
    log(f"Model: {model if use_llm else 'none (procedural only)'} · prose: {prose}")
    paper = generate_paper(seed=seed, model=model, use_llm=use_llm, prose=prose, review=review, log=log)
    save_paper(paper, OUT)
    return f"/paper/{paper['seed']}"


def _grade(seed: str, answers: dict, use_llm: bool, model: str, log):
    from .grade import grade_attempt
    paper = json.loads((OUT / f"practice-{seed}.json").read_text())
    if use_llm:
        log(f"Proofs and explanations marked by {model}")
    report = grade_attempt(paper, answers, use_llm=use_llm, model=model, log=log)
    rid = uuid.uuid4().hex[:6]
    (OUT / f"practice-{seed}-report-{rid}.md").write_text(render_report(report))
    (OUT / f"practice-{seed}-report-{rid}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return f"/report/{seed}/{rid}"


def settings_form(status: dict, compact: bool = False) -> str:
    provider, name = llm.split(SETTINGS["model"])
    cards, lists = [], []
    for p in llm.PROVIDERS:
        st = status[p]
        state = ("<span class='ok'>● ready</span>" if st["ready"] else
                 "<span class='warn'>● not running</span>" if p == "ollama" else "<span class='warn'>● no API key</span>")
        extra = "" if st["ready"] else f"<div class='muted'>{KEY_HELP[p]}</div>"
        cards.append(f"<label class='prov'><input type='radio' name='provider' value='{p}'"
                     f"{' checked' if p == provider else ''}> <b>{PROVIDER_LABELS[p]}</b> {state}{extra}</label>")
        opts = "".join(f"<option value='{html.escape(m)}'>" for m in st["models"] or [st["default"]])
        lists.append(f"<datalist id='models-{p}' data-default='{html.escape(st['default'])}'>{opts}</datalist>")
    prose_opts = "".join(f"<option value='{v}'{' selected' if SETTINGS['prose'] == v else ''}>{t}</option>" for v, t in
                         (("past", "real past questions with official solutions"),
                          ("llm", "new questions written by the AI model")))
    return f"""<form method='post' action='/settings'>
<div class='providers'>{''.join(cards)}</div>{''.join(lists)}
<div class='row'><label>Model <input name='model' id='model' list='models-{provider}' size='28'
 value='{html.escape(name)}'></label>
<span class='muted'>leave blank for the provider's default</span></div>
<div class='row'><label>Proof / explanation slots: <select name='prose'>{prose_opts}</select></label>
<label><input type='checkbox' name='review'{' checked' if SETTINGS['review'] else ''}> AI self-review of new questions</label></div>
<p class='muted'>Automata, grammars, Turing machines, logic and decidability questions are always generated and marked by
exact code, whichever model is selected. The model writes proofs and new prose questions, and marks proofs and
explanations. With the local model, keep "real past questions": in testing qwen3:8b often wrote false questions.
Cloud models send the question text and your answers to Google or Anthropic.</p>
<button>Save</button> <a href='/settings?refresh=1' class='muted'>re-check status</a></form>
<script>
(function(){{var m=document.getElementById('model');
document.querySelectorAll('input[name=provider]').forEach(function(r){{r.addEventListener('change',function(){{
var dl=document.getElementById('models-'+r.value);m.setAttribute('list','models-'+r.value);
m.value=dl?dl.dataset.default:'';}});}});}})();
</script>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, body: bytes, code=200, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, to: str):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def log_message(self, *a):
        pass

    def denied(self) -> bool:
        if REQUIRE_ACCESS and not self.headers.get(ACCESS_HEADER):
            self.send(page("Sign-in required", "<h1>Sign-in required</h1><p>This site only accepts requests that come "
                           "through Cloudflare Access. Ask the owner for access.</p>"), 403)
            return True
        return False

    def do_GET(self):
        if self.denied():
            return
        url = urlparse(self.path)
        path = url.path.strip("/").split("/")
        if path == [""]:
            return self.send(page("ExamX", self.home()))
        if path == ["settings"]:
            status = provider_status(refresh="refresh" in parse_qs(url.query))
            body = f"<h1>AI model</h1><div class='card'>{settings_form(status)}</div>"
            return self.send(page("AI model", body))
        if path[0] == "figures" and len(path) == 2 and re.fullmatch(r"[\w.\-]+\.png", path[1]):
            f = DATA_DIR / "figures" / path[1]
            if f.exists():
                return self.send(f.read_bytes(), ctype="image/png")
        if path[0] == "job" and len(path) == 2 and path[1] in JOBS:
            j = JOBS[path[1]]
            if j["done"] and j["result"]:
                return self.redirect(j["result"])
            secs = int(time.time() - j["start"])
            status = "finished with errors" if j["done"] else f"running… {secs // 60}:{secs % 60:02d}"
            body = (f"<h1>{j['kind']}</h1><p class='muted'>{status}</p>"
                    f"<div class='log'>{html.escape(chr(10).join(j['log'])) or 'starting…'}</div>")
            return self.send(page("Job", body, refresh=not j["done"]))
        if path[0] in ("paper", "solutions", "report") and (len(path) < 2 or not path[1].isdigit()):
            return self.send(page("Not found", "<p>Not found.</p>"), 404)
        if path[0] in ("paper", "solutions") and len(path) == 2:
            f = OUT / f"practice-{path[1]}.json"
            if not f.exists():
                return self.send(page("Not found", "<p>No such paper.</p>"), 404)
            paper = json.loads(f.read_text())
            if path[0] == "solutions":
                body = (f"<p><a href='/paper/{path[1]}'>← back to the paper</a></p>"
                        + md(render_markdown(paper, solutions=True)))
                return self.send(page(paper["title"], body))
            return self.send(page(paper["title"], self.answer_form(paper)))
        if path[0] == "report" and len(path) == 3 and re.fullmatch(r"\w+", path[2]):
            f = OUT / f"practice-{path[1]}-report-{path[2]}.md"
            if f.exists():
                body = (md(f.read_text()) + f"<p><a class='btn' href='/solutions/{path[1]}'>Model solutions</a> "
                        f"<a href='/paper/{path[1]}'>back to the paper</a></p>")
                return self.send(page("Report", body))
        self.send(page("Not found", "<p>Not found.</p>"), 404)

    def home(self) -> str:
        status = provider_status()
        provider, name = llm.split(SETTINGS["model"])
        ready = status[provider]["ready"]
        warn = "" if ready else (f"<p class='warn'>{PROVIDER_LABELS[provider]} is not available: "
                                 f"{KEY_HELP[provider]} <a href='/settings'>Change model</a></p>")
        items = []
        for p in papers():
            seed = p.stem.split("-")[1]
            try:
                meta = json.loads(p.read_text())
            except ValueError:
                continue
            reports = sorted(OUT.glob(f"practice-{seed}-report-*.md"), key=lambda r: r.stat().st_mtime)
            rep = "".join(f" <a href='/report/{seed}/{r.stem.rsplit('-', 1)[1]}'>report {i}</a>"
                          for i, r in enumerate(reports, 1))
            items.append(f"<li><a href='/paper/{seed}'><b>Seed {seed}</b></a>"
                         f"<span class='muted'>{html.escape(str(meta.get('model', '')))} · "
                         f"{time.strftime('%d %b %H:%M', time.localtime(p.stat().st_mtime))}</span>"
                         f"<a href='/solutions/{seed}'>solutions</a>{rep}</li>")
        return f"""<h1>FIT2014 practice papers</h1>
<div class='card'><h2>New paper</h2>{warn}
<form method='post' action='/generate'><div class='row'>
<label>Seed <input name='seed' size='8' placeholder='random'></label>
<label><input type='checkbox' name='llm' checked> use {html.escape(name)} for AI-written parts</label></div>
<p class='muted'>Proof slots: {'real past questions' if SETTINGS['prose'] == 'past' else 'new AI-written questions'}
· <a href='/settings'>change model or options</a>. Without the AI it takes about a second; with a local model,
several minutes.</p>
<button>Generate paper</button></form></div>
<div class='card'><h2>Papers</h2><ul class='papers'>{''.join(items) or '<li class=muted>none yet</li>'}</ul></div>"""

    def answer_form(self, paper: dict) -> str:
        seed = paper["seed"]
        _, grader = llm.split(llm.grader_model(SETTINGS["model"]))
        out = [f"<h1>{html.escape(paper['title'])}</h1><p class='muted'>Total marks: {paper['total_marks']} · "
               f"generated with {html.escape(str(paper.get('model', '?')))} · "
               f"<a href='/solutions/{seed}'>solutions</a></p>",
               "<p class='muted'>Put machine-checkable answers (automata, grammars, TMs, formulas) in the suggested "
               "format. Answers are kept in this browser as you type.</p>",
               f"<form method='post' action='/grade/{seed}' id='attempt'>"]
        for q in paper["questions"]:
            out.append(f"<h2>Question {q['number']} <span class='muted'>({q['marks']} marks)</span></h2>{md(q['text'])}")
            for p in q["parts"]:
                lab = f"<b>({p['label']})</b> " if p["label"] else ""
                out.append(md(f"{lab}{p['text']}") if p["text"] or lab else "")
                if p.get("answer_format"):
                    out.append(f"<blockquote>{md(p['answer_format'])}</blockquote>")
                out.append(f"<textarea name='q{q['number']}_{p['label']}'></textarea>")
        out.append(f"""<div class='card' style='margin-top:24px'><div class='row'>
<label><input type='checkbox' name='llm' checked> mark proofs and explanations with {html.escape(grader)}</label></div>
<button>Submit for marking</button> <span class='saved' id='saved'></span></div></form>
<script>
(function(){{var k='examx-attempt-{seed}',f=document.getElementById('attempt'),s=document.getElementById('saved'),d={{}};
try{{d=JSON.parse(localStorage.getItem(k)||'{{}}')}}catch(e){{}}
f.querySelectorAll('textarea').forEach(function(t){{if(d[t.name])t.value=d[t.name];
t.addEventListener('input',function(){{d[t.name]=t.value;try{{localStorage.setItem(k,JSON.stringify(d));
s.textContent='draft saved'}}catch(e){{}}}});}});}})();
</script>""")
        return "".join(out)

    def do_POST(self):
        if self.denied():
            return
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > MAX_BODY:
            return self.send(page("Too large", "<p>Request too large.</p>"), 413)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
        path = urlparse(self.path).path.strip("/").split("/")
        if path == ["settings"]:
            provider = form.get("provider") if form.get("provider") in llm.PROVIDERS else "ollama"
            name = re.sub(r"[^\w.:\-/]", "", form.get("model", "").strip())
            if provider == "ollama":
                name = name.removeprefix("ollama:") or provider_status()["ollama"]["default"]
                SETTINGS["model"] = name
            else:
                name = name.removeprefix(provider + ":")
                SETTINGS["model"] = f"{provider}:{name}" if name else provider
            SETTINGS["prose"] = "llm" if form.get("prose") == "llm" else "past"
            SETTINGS["review"] = "review" in form
            save_settings()
            return self.redirect("/")
        if path == ["generate"]:
            seed = int(form["seed"]) if form.get("seed", "").strip().isdigit() else None
            if why := job_refusal("llm" in form):
                return self.send(page("Busy", f"<h1>Not now</h1><p>{why}</p><p><a href='/'>Back</a></p>"), 429)
            return self.redirect("/job/" + run_job("Generating paper", _generate, "llm" in form, seed,
                                                   SETTINGS["model"], SETTINGS["prose"], SETTINGS["review"]))
        if path[0] == "grade" and len(path) == 2 and (OUT / f"practice-{path[1]}.json").exists():
            answers: dict[int, dict[str, str]] = {}
            for k, v in form.items():
                if k.startswith("q") and "_" in k and k[1:].split("_", 1)[0].isdigit():
                    num, label = k[1:].split("_", 1)
                    answers.setdefault(int(num), {})[label] = v
            if why := job_refusal("llm" in form):
                return self.send(page("Busy", f"<h1>Not now</h1><p>{why}</p><p>Your answers are still saved in "
                                      "this browser.</p>"), 429)
            return self.redirect("/job/" + run_job("Marking", _grade, path[1], answers, "llm" in form,
                                                   llm.grader_model(SETTINGS["model"])))
        self.send(page("Not found", "<p>Not found.</p>"), 404)


def serve(host: str = "127.0.0.1", port: int = 8014, model: str | None = None):
    load_settings()
    if model:
        SETTINGS["model"] = model
    print(f"ExamX web UI on http://{host}:{port}  (model {SETTINGS['model']}; "
          f"{'Cloudflare Access required; ' if REQUIRE_ACCESS else ''}Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
