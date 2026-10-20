"""Render generated papers and grading reports to Markdown and PDF."""
from __future__ import annotations

import re
from pathlib import Path

import markdown
import pymupdf

from .topics import TOPIC_NAMES


def _maths(s: str) -> str:
    """a^{2n} -> a<sup>2n</sup> for HTML output (Markdown output keeps the caret form)."""
    s = re.sub(r"\^\{([^}]*)\}", r"<sup>\1</sup>", s)
    return re.sub(r"(?<=[A-Za-z0-9)])\^([A-Za-z0-9+\-]+)", r"<sup>\1</sup>", s)


def render_markdown(paper: dict, solutions: bool = False) -> str:
    out = [f"# {paper['title']}" + (" — Solutions" if solutions else ""), "",
           f"FIT2014 Theory of Computation · Total marks: {paper['total_marks']} · Time: 3 hours", ""]
    if not solutions:
        out += ["*Instructions:* answer all questions. Where an answer format is suggested, using it lets your "
                "answer be marked automatically (`examx grade`).", ""]
    for q in paper["questions"]:
        out.append(f"## Question {q['number']} ({q['marks']} marks)")
        if solutions:
            out.append(f"*Topic: {TOPIC_NAMES.get(q['topic'], q['topic'])} · source: {q['source']}"
                       + (f" · modelled on {q['inspired_by']}" if q.get("inspired_by") else "") + "*")
        out.append("")
        if q["text"]:
            out += [q["text"], ""]
        for p in q["parts"]:
            label = f"**({p['label']})** " if p["label"] else ""
            pm = f" *[{p['marks']} marks]*" if len(q["parts"]) > 1 and p["text"] else ""
            if p["text"] or label:
                out += [f"{label}{p['text']}{pm}", ""]
            if p.get("answer_format") and not solutions:
                out += [f"> {p['answer_format']}", ""]
            if solutions:
                out += ["**Model solution:**", "", p["solution"] or "_(none)_", ""]
                if p.get("rubric"):
                    out += ["**Marking rubric:**", ""]
                    out += [f"- {r['criterion']} — {r['marks']}" for r in p["rubric"]]
                    out.append("")
        out.append("")
    return "\n".join(out)


def render_report(report: dict) -> str:
    out = [f"# Grading report: {report['paper_title']}", "",
           f"**Total: {report['total']:g} / {report['max_total']:g}** ({100 * report['total'] / max(report['max_total'], 1):.0f}%)",
           "", "| Question | Marks | Method |", "|---|---|---|"]
    for q in report["questions"]:
        methods = ", ".join(sorted({p["method"] for p in q["parts"]}))
        out.append(f"| {q['number']} | {q['awarded']:g} / {q['marks']:g} | {methods} |")
    out.append("")
    for q in report["questions"]:
        out += [f"## Question {q['number']} — {q['awarded']:g} / {q['marks']:g}", ""]
        for p in q["parts"]:
            lab = f"({p['label']}) " if p["label"] else ""
            out += [f"**{lab}{p['awarded']:g} / {p['marks']:g}** · _{p['method']}_", "", p["feedback"], ""]
    return "\n".join(out)


CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 17pt; } h2 { font-size: 13pt; margin-top: 14pt; border-bottom: 1px solid #999; }
pre, code { font-family: monospace; font-size: 9.5pt; }
pre { background-color: #f3f3f3; padding: 4pt; }
blockquote { color: #555; font-size: 9pt; margin-left: 10pt; }
table { border-collapse: collapse; } td, th { border: 1px solid #aaa; padding: 2pt 6pt; }
"""


def write_pdf(md_text: str, path: Path) -> Path:
    html = markdown.markdown(_maths(md_text), extensions=["fenced_code", "tables"])
    story = pymupdf.Story(html=html, user_css=CSS)
    writer = pymupdf.DocumentWriter(str(path))
    page = pymupdf.paper_rect("a4")
    where = page + (54, 54, -54, -54)
    more = True
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return path
