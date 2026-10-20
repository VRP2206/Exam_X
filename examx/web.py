"""A small local web UI (stdlib only): generate papers, answer them in the browser, get them graded.

Run with `examx serve` and open http://127.0.0.1:8014. Long jobs (LLM generation
and marking) run in a background thread; the job page refreshes until done.
"""
from __future__ import annotations

import html
import json
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import markdown

from .ingest import ROOT
from .render import _maths, render_markdown, render_report

OUT = ROOT / "output"
JOBS: dict[str, dict] = {}
MODEL: str | None = None

STYLE = """<style>
body{font-family:system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;line-height:1.45;color:#222;background:#fff}
pre{background:#f4f4f4;padding:8px;overflow-x:auto} textarea{width:100%;min-height:90px;font-family:monospace}
h2{border-bottom:1px solid #ccc;margin-top:28px} .btn{padding:6px 14px;margin:4px 0}
.log{white-space:pre-wrap;font-family:monospace;background:#f4f4f4;padding:8px} table{border-collapse:collapse}
td,th{border:1px solid #bbb;padding:3px 8px} blockquote{color:#666;font-size:90%}
</style>"""


def page(title: str, body: str, refresh: bool = False) -> bytes:
    meta = '<meta http-equiv="refresh" content="3">' if refresh else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>{meta}{STYLE}"
            f"</head><body><p><a href='/'>ExamX</a></p>{body}</body></html>").encode()


def md(text: str) -> str:
    return markdown.markdown(_maths(text), extensions=["fenced_code", "tables"])


def papers() -> list[Path]:
    return sorted(OUT.glob("practice-*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if OUT.exists() else []


def run_job(kind: str, fn, *args) -> str:
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"kind": kind, "log": [], "done": False, "result": None}

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


def _generate(use_llm: bool, seed, log):
    from .generate import generate_paper, save_paper
    paper = generate_paper(seed=seed, model=MODEL, use_llm=use_llm, log=log)
    save_paper(paper, OUT)
    return f"/paper/{paper['seed']}"


def _grade(seed: str, answers: dict, use_llm: bool, log):
    from .grade import grade_attempt
    paper = json.loads((OUT / f"practice-{seed}.json").read_text())
    report = grade_attempt(paper, answers, use_llm=use_llm, model=MODEL, log=log)
    rid = uuid.uuid4().hex[:6]
    (OUT / f"practice-{seed}-report-{rid}.md").write_text(render_report(report))
    return f"/report/{seed}/{rid}"


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

    def do_GET(self):
        path = urlparse(self.path).path.strip("/").split("/")
        if path == [""]:
            items = "".join(f"<li><a href='/paper/{p.stem.split('-')[1]}'>{p.stem}</a> · "
                            f"<a href='/solutions/{p.stem.split('-')[1]}'>solutions</a></li>" for p in papers())
            body = ("<h1>ExamX — FIT2014 practice papers</h1>"
                    "<form method='post' action='/generate'>Seed (optional): <input name='seed' size='8'> "
                    "<label><input type='checkbox' name='llm' checked> use local LLM (slow, richer questions)</label><br>"
                    "<button class='btn'>Generate a new paper</button></form>"
                    f"<h2>Papers</h2><ul>{items or '<li>none yet</li>'}</ul>")
            return self.send(page("ExamX", body))
        if path[0] == "job" and len(path) == 2 and path[1] in JOBS:
            j = JOBS[path[1]]
            if j["done"] and j["result"]:
                return self.redirect(j["result"])
            status = "finished with errors" if j["done"] else "running…"
            return self.send(page("Job", f"<h1>{j['kind']} {status}</h1><div class='log'>{html.escape(chr(10).join(j['log']))}</div>",
                                  refresh=not j["done"]))
        if path[0] in ("paper", "solutions") and len(path) == 2:
            f = OUT / f"practice-{path[1]}.json"
            if not f.exists():
                return self.send(page("Not found", "<p>No such paper.</p>"), 404)
            paper = json.loads(f.read_text())
            if path[0] == "solutions":
                return self.send(page(paper["title"], md(render_markdown(paper, solutions=True))))
            return self.send(page(paper["title"], self.answer_form(paper)))
        if path[0] == "report" and len(path) == 3:
            f = OUT / f"practice-{path[1]}-report-{path[2]}.md"
            if f.exists():
                return self.send(page("Report", md(f.read_text()) + f"<p><a href='/solutions/{path[1]}'>Model solutions</a></p>"))
        self.send(page("Not found", "<p>Not found.</p>"), 404)

    def answer_form(self, paper: dict) -> str:
        out = [f"<h1>{html.escape(paper['title'])}</h1><p>Total marks: {paper['total_marks']}</p>",
               f"<form method='post' action='/grade/{paper['seed']}'>"]
        for q in paper["questions"]:
            out.append(f"<h2>Question {q['number']} ({q['marks']} marks)</h2>{md(q['text'])}")
            for p in q["parts"]:
                lab = f"<b>({p['label']})</b> " if p["label"] else ""
                out.append(md(f"{lab}{p['text']}") if p["text"] or lab else "")
                if p.get("answer_format"):
                    out.append(f"<blockquote>{md(p['answer_format'])}</blockquote>")
                out.append(f"<textarea name='q{q['number']}_{p['label']}'></textarea>")
        out.append("<p><label><input type='checkbox' name='llm' checked> use LLM for proofs/explanations</label></p>"
                   "<button class='btn'>Submit for marking</button></form>")
        return "".join(out)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
        path = urlparse(self.path).path.strip("/").split("/")
        if path == ["generate"]:
            seed = int(form["seed"]) if form.get("seed", "").strip().isdigit() else None
            return self.redirect("/job/" + run_job("Generating paper", _generate, "llm" in form, seed))
        if path[0] == "grade" and len(path) == 2:
            answers: dict[int, dict[str, str]] = {}
            for k, v in form.items():
                if k.startswith("q") and "_" in k:
                    num, label = k[1:].split("_", 1)
                    answers.setdefault(int(num), {})[label] = v
            return self.redirect("/job/" + run_job("Marking", _grade, path[1], answers, "llm" in form))
        self.send(page("Not found", "<p>Not found.</p>"), 404)


def serve(host: str = "127.0.0.1", port: int = 8014, model: str | None = None):
    global MODEL
    MODEL = model
    print(f"ExamX web UI on http://{host}:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
