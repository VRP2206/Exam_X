"""Command-line interface: examx ingest | stats | generate | grade | check | bench | serve."""
from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path

from .ingest import DATA_DIR, ROOT

log = functools.partial(print, flush=True)  # progress lines appear promptly even when piped


def cmd_ingest(args):
    from .ingest import ingest_all
    corpus = ingest_all()
    papers = sorted({q.paper for q in corpus})
    print(f"Ingested {len(corpus)} questions from {len(papers)} papers into {DATA_DIR.relative_to(ROOT)}/")
    for p in papers:
        qs = [q for q in corpus if q.paper == p]
        print(f"  {p:<16} {len(qs):>2} questions  {sum(q.marks for q in qs):>5g} marks  "
              f"{sum(1 for q in qs if q.solution)} with solutions")


def cmd_stats(args):
    from .topics import TOPIC_NAMES
    stats = json.loads((DATA_DIR / "stats.json").read_text())
    print("Share of marks by primary topic (all papers):")
    for t, s in stats["topic_marks_share"].items():
        print(f"  {TOPIC_NAMES.get(t, t):<42} {100 * s:5.1f}%  {'█' * round(s * 100)}")
    print("\nAnswer types:", ", ".join(f"{k} {v}" for k, v in stats["answer_types"].items()))


def cmd_generate(args):
    from .generate import generate_paper, save_paper
    paper = generate_paper(seed=args.seed, model=args.model, use_llm=not args.no_llm, variation=args.variation, log=log)
    paths = save_paper(paper, Path(args.out))
    print(f"\nTotal marks: {paper['total_marks']}")
    for k, p in paths.items():
        print(f"  {k:<14} {p}")


def cmd_grade(args):
    from .grade import grade_attempt, load_paper, parse_attempt
    from .render import render_report, write_pdf
    paper = load_paper(args.paper)
    attempt = parse_attempt(Path(args.attempt).read_text())
    report = grade_attempt(paper, attempt, use_llm=not args.no_llm, model=args.model, log=log)
    md = render_report(report)
    out = Path(args.out) if args.out else Path(args.attempt).with_suffix(".report.md")
    out.write_text(md)
    out.with_suffix(".json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    if args.pdf:
        write_pdf(md, out.with_suffix(".pdf"))
    print(f"\nTotal: {report['total']:g} / {report['max_total']:g}\nReport: {out}")


def cmd_check(args):
    """Quick one-off checks, e.g. examx check regex '(a∪b)*ab' 'a*b(a∪b)*'."""
    from .checkers import cfg, fa, logic, regex
    if args.kind == "regex":
        cx = fa.counterexample(regex.to_nfa(args.a), regex.to_nfa(args.b))
        print("equivalent" if cx is None else f"differ on {cx!r}")
    elif args.kind == "fa":
        a, b = (fa.parse_automaton(Path(x).read_text()) for x in (args.a, args.b))
        cx = fa.counterexample(a, b)
        print("equivalent" if cx is None else f"differ on {cx!r}")
    elif args.kind == "logic":
        env = logic.counterexample(args.a, args.b)
        print("equivalent" if env is None else f"differ when {env}")
    elif args.kind == "cfg":
        g = cfg.parse_cfg(Path(args.a).read_text())
        print(f"{args.b!r}: {'generated' if g.accepts(args.b) else 'not generated'}")


def cmd_bench(args):
    from .llm import available_models, benchmark
    models = args.models or available_models()
    prompt = ("Write a 6-mark FIT2014 exam question asking students to use the Pumping Lemma to prove a language "
              "over {a,b} is not regular, followed by a complete model solution.")
    for r in benchmark(models, prompt):
        print(f"{r['model']:<22} load {r['load_s']:>5}s  generate {r['wall_s']:>6}s  {r['tok_per_s']:>5} tok/s")


def cmd_serve(args):
    from .web import serve
    serve(args.host, args.port, model=args.model)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="examx", description="FIT2014 practice-paper generator and grader (local LLM)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ingest", help="parse papers/ and solution/ PDFs into data/").set_defaults(func=cmd_ingest)
    sub.add_parser("stats", help="show topic and answer-type statistics of the past papers").set_defaults(func=cmd_stats)

    g = sub.add_parser("generate", help="generate a practice paper with solutions")
    g.add_argument("--seed", type=int)
    g.add_argument("--model", help="Ollama model (default: $EXAMX_MODEL or qwen3:8b)")
    g.add_argument("--no-llm", action="store_true", help="procedural questions only (fast, no Ollama needed)")
    g.add_argument("--variation", type=float, default=0.35, help="fraction of slots swapped from other papers")
    g.add_argument("--out", default="output")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("grade", help="grade a student attempt")
    r.add_argument("paper", help="generated paper JSON, or a past paper id such as exam-2013")
    r.add_argument("attempt", help="attempt file (Markdown or JSON)")
    r.add_argument("--model")
    r.add_argument("--no-llm", action="store_true", help="exact checks only")
    r.add_argument("--out", help="report path (default: <attempt>.report.md)")
    r.add_argument("--pdf", action="store_true", help="also write a PDF report")
    r.set_defaults(func=cmd_grade)

    c = sub.add_parser("check", help="compare two answers exactly")
    c.add_argument("kind", choices=["regex", "fa", "logic", "cfg"])
    c.add_argument("a", help="regex/formula, or a file for fa/cfg")
    c.add_argument("b", help="regex/formula, file (fa) or string to test (cfg)")
    c.set_defaults(func=cmd_check)

    b = sub.add_parser("bench", help="benchmark installed Ollama models")
    b.add_argument("models", nargs="*")
    b.set_defaults(func=cmd_bench)

    s = sub.add_parser("serve", help="run the local web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8014)
    s.add_argument("--model")
    s.set_defaults(func=cmd_serve)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
