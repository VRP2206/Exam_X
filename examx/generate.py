"""Generate a new FIT2014 practice paper with model solutions and marking rubrics.

1. Blueprint: take a random past paper as a template (so the paper keeps the real
   topic order and the 120-mark total) and swap some slots for same-marks
   questions from other papers at a similar position.
2. Each slot is filled procedurally when a generator exists for its topic and
   answer type (exact solutions), otherwise by the LLM with retrieved past
   questions as few-shot exemplars.
3. Pumping-lemma style procedural questions get their proofs from the LLM.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from . import llm, procedural
from .ingest import load_corpus
from .retrieval import Index
from .topics import TOPIC_NAMES

SYSTEM = """You are an experienced examiner for FIT2014 Theory of Computation at Monash University.
You write exam questions in the exact style of past FIT2014 papers: precise, self-contained, with
marks that reflect the work required. Use plain text with Unicode maths (∪ ∗ ε → ∀ ∃ ¬ ∧ ∨ ≤ ≥ ∈),
writing exponents as a^n or a^{2n}. Never refer to diagrams or figures: give automata as transition
tables, grammars as productions, and graphs as vertex/edge lists. Model solutions must be complete
and correct, written as a strong student would write them in the exam."""


def blueprint(rng: random.Random, corpus: list[dict], variation: float = 0.35) -> list[dict]:
    papers: dict[str, list[dict]] = {}
    for q in corpus:
        papers.setdefault(q["paper"], []).append(q)
    template = papers[rng.choice(sorted(papers))]
    slots = []
    for q in template:
        pos = q["number"] / len(template)
        src = q
        if rng.random() < variation:
            alts = [o for p, qs in papers.items() if p != q["paper"] for o in qs
                    if o["marks"] == q["marks"] and abs(o["number"] / len(qs) - pos) < 0.15 and o["primary_topic"]]
            if alts:
                src = rng.choice(alts)
        slots.append({"marks": int(q["marks"]), "topic": src["primary_topic"], "answer_type": src["answer_type"],
                      "inspired_by": src["id"]})
    return slots


def exemplar_block(ex: list[dict]) -> str:
    out = []
    for i, e in enumerate(ex, 1):
        s = f"--- Past question {i} ({e['id']}, {int(e['marks'])} marks) ---\n{e['text']}\n"
        if e["solution"]:
            s += f"--- Official solution ---\n{e['solution'][:1800]}\n"
        if e["comments"]:
            s += f"--- Marker comments ---\n{e['comments'][:600]}\n"
        out.append(s)
    return "\n".join(out)


QUESTION_SCHEMA = """Return a JSON object:
{"text": "question stem (may be empty if there is only one part)",
 "parts": [{"label": "a", "text": "part question", "marks": <int>,
            "solution": "complete model answer",
            "rubric": [{"criterion": "what earns the marks", "marks": <int>}]}]}
Use a single part with label "" if the question has no sub-parts. Part marks must sum to the total
and each part's rubric marks must sum to that part's marks."""


def llm_question(slot: dict, index: Index, corpus_by_id: dict, model: str | None, avoid: list[str]) -> dict:
    inspired = corpus_by_id.get(slot["inspired_by"])
    ex = [inspired] if inspired else []
    ex += index.search(inspired["text"] if inspired else "", topic=slot["topic"], answer_type=slot["answer_type"], k=3,
                       exclude={slot["inspired_by"]})
    ex = ex[:3]
    topic = TOPIC_NAMES.get(slot["topic"], slot["topic"] or "any FIT2014 topic")
    user = (f"Here are past FIT2014 exam questions on this topic:\n\n{exemplar_block(ex)}\n\n"
            f"Write ONE NEW exam question worth exactly {slot['marks']} marks on the topic: {topic}. "
            f"It must test the same skills as past question 1 but must not copy it: change the language, "
            f"machine, scenario or problem. ")
    if avoid:
        user += "Do not reuse these ideas already in the paper: " + "; ".join(avoid[-6:]) + ". "
    user += "\n\n" + QUESTION_SCHEMA
    data = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                         model=model, temperature=0.8, num_predict=2500)
    return normalise_llm_question(data, slot)


def normalise_llm_question(data: dict, slot: dict) -> dict:
    parts = data.get("parts") or [{"label": "", "text": data.get("text", ""), "marks": slot["marks"]}]
    clean = []
    for i, p in enumerate(parts):
        clean.append({
            "label": str(p.get("label", chr(97 + i) if len(parts) > 1 else "")).strip("() "),
            "text": str(p.get("text", "")).strip(),
            "marks": _int(p.get("marks"), 1),
            "answer_type": "proof" if slot["answer_type"] == "proof" else slot["answer_type"],
            "solution": _text(p.get("solution", "")),
            "rubric": [{"criterion": str(r.get("criterion", "")), "marks": _int(r.get("marks"), 1)}
                       for r in (p.get("rubric") or []) if isinstance(r, dict)],
            "check": None,
            "answer_format": None,
        })
    _rescale(clean, slot["marks"])
    for p in clean:
        if not p["rubric"]:
            p["rubric"] = [{"criterion": "Correct and complete answer", "marks": p["marks"]}]
        _rescale(p["rubric"], p["marks"])
    return {"topic": slot["topic"], "answer_type": slot["answer_type"], "text": str(data.get("text", "")).strip(),
            "parts": clean, "marks": slot["marks"], "source": "llm"}


def _text(v) -> str:
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, indent=1) if isinstance(v, dict) else "\n".join(map(str, v))
    return str(v).strip()


def _int(v, default: int) -> int:
    try:
        return max(0, round(float(v)))
    except (TypeError, ValueError):
        return default


def _rescale(items: list[dict], total: int) -> None:
    """Scale integer 'marks' fields so they sum to total (largest-remainder rounding)."""
    s = sum(i["marks"] for i in items)
    if s == total or not items:
        return
    if s == 0:
        for i in items:
            i["marks"] = 0
        items[-1]["marks"] = total
        return
    raw = [i["marks"] * total / s for i in items]
    floors = [int(x) for x in raw]
    for j in sorted(range(len(items)), key=lambda j: raw[j] - floors[j], reverse=True)[: total - sum(floors)]:
        floors[j] += 1
    for i, m in zip(items, floors):
        i["marks"] = m


def solve_with_llm(q: dict, index: Index, model: str | None) -> None:
    """Fill in model solutions and rubrics for procedurally-worded questions."""
    for p in q["parts"]:
        if p["solution"]:
            continue
        ex = index.search(p["text"], topic=q["topic"], k=2)
        user = (f"Past FIT2014 questions with official solutions, showing the expected style:\n\n{exemplar_block(ex)}\n\n"
                f"Now write the model solution for this {p['marks']}-mark question, and a marking rubric.\n\n"
                f"QUESTION:\n{q['text']}\n{p['text']}\n\n"
                'Return JSON: {"solution": "...", "rubric": [{"criterion": "...", "marks": <int>}]} '
                f"with rubric marks summing to {p['marks']}.")
        data = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                             model=model, temperature=0.3, num_predict=2000)
        p["solution"] = _text(data.get("solution", ""))
        p["rubric"] = [{"criterion": str(r.get("criterion", "")), "marks": _int(r.get("marks"), 1)}
                       for r in data.get("rubric", []) if isinstance(r, dict)] or \
                      [{"criterion": "Correct and complete proof", "marks": p["marks"]}]
        _rescale(p["rubric"], p["marks"])
    q.pop("needs_solution", None)


def generate_paper(seed: int | None = None, model: str | None = None, use_llm: bool = True,
                   procedural_only: bool = False, variation: float = 0.35, log=print) -> dict:
    seed = seed if seed is not None else random.randrange(10**6)
    rng = random.Random(seed)
    corpus = load_corpus()
    by_id = {q["id"]: q for q in corpus}
    index = Index(corpus)
    slots = blueprint(rng, corpus, variation)
    questions, avoid, seen = [], [], set()

    def fresh(gen, marks):
        """Call a procedural generator, retrying so the paper never repeats a question."""
        for _ in range(30):
            q = gen(rng, marks)
            key = q["text"] + "|".join(p["text"] for p in q["parts"])
            if key not in seen:
                break
        seen.add(key)
        return q

    for n, slot in enumerate(slots, 1):
        gen = procedural.generator_for(slot["topic"], slot["answer_type"])
        if procedural_only and not gen:
            gen = _closest_generator(slot)
        if gen:
            q = fresh(gen, slot["marks"])
            log(f"Q{n:>2} ({slot['marks']:>2} marks) procedural  {gen.__name__}")
        elif use_llm:
            log(f"Q{n:>2} ({slot['marks']:>2} marks) LLM         {slot['topic']} / {slot['answer_type']} ...")
            try:
                q = llm_question(slot, index, by_id, model, avoid)
            except llm.LLMError as e:
                log(f"     LLM failed ({e}); falling back to a procedural question")
                q = fresh(_closest_generator(slot), slot["marks"])
        else:
            q = fresh(_closest_generator(slot), slot["marks"])
            log(f"Q{n:>2} ({slot['marks']:>2} marks) procedural  (no LLM) {q['answer_type']}")
        if q.get("needs_solution"):
            if use_llm:
                log("     writing model solution with LLM ...")
                try:
                    solve_with_llm(q, index, model)
                except llm.LLMError as e:
                    log(f"     LLM failed ({e})")
            for p in q["parts"]:
                p["solution"] = p["solution"] or "(model solution not generated: run with the LLM enabled)"
                p["rubric"] = p["rubric"] or [{"criterion": "Correct and complete proof", "marks": p["marks"]}]
        q["number"] = n
        q["inspired_by"] = slot["inspired_by"]
        questions.append(q)
        avoid.append((q["text"] + " " + " ".join(p["text"] for p in q["parts"]))[:120])
    return {"title": f"FIT2014 Practice Exam (seed {seed})", "seed": seed, "model": model or llm.DEFAULT_MODEL,
            "total_marks": sum(q["marks"] for q in questions), "questions": questions}


def _closest_generator(slot: dict):
    """When no LLM is available, pick a procedural generator from the same part of the syllabus."""
    fallback = {"propositional_logic": procedural.gen_prop_cnf, "predicate_logic": procedural.gen_prop_cnf,
                "induction": procedural.gen_derivation, "regular_expressions": procedural.gen_regex,
                "finite_automata": procedural.gen_fa, "nfa": procedural.gen_nfa_to_dfa,
                "kleenes_theorem": procedural.gen_nfa_to_dfa, "minimisation": procedural.gen_minimise,
                "regular_closure": procedural.gen_regex, "pumping_lemma_regular": procedural.gen_pumping,
                "cfg": procedural.gen_cfg, "pda": procedural.gen_cfg, "pumping_lemma_cfl": procedural.gen_pumping_cfl,
                "turing_machines": procedural.gen_tm, "church_turing": procedural.gen_decidability,
                "decidability": procedural.gen_decidability, "mapping_reductions": procedural.gen_decidability,
                "complexity_p": procedural.gen_decidability, "np_completeness": procedural.gen_decidability,
                "language_classes": procedural.gen_decidability}
    return fallback.get(slot["topic"] or "", procedural.gen_regex)


def save_paper(paper: dict, out_dir: Path) -> dict[str, Path]:
    from .render import render_markdown, write_pdf
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"practice-{paper['seed']}"
    paths = {"json": out_dir / f"{stem}.json", "paper_md": out_dir / f"{stem}.md",
             "solutions_md": out_dir / f"{stem}-solutions.md"}
    paths["json"].write_text(json.dumps(paper, indent=1, ensure_ascii=False))
    paths["paper_md"].write_text(render_markdown(paper, solutions=False))
    paths["solutions_md"].write_text(render_markdown(paper, solutions=True))
    try:
        paths["paper_pdf"] = write_pdf(paths["paper_md"].read_text(), out_dir / f"{stem}.pdf")
        paths["solutions_pdf"] = write_pdf(paths["solutions_md"].read_text(), out_dir / f"{stem}-solutions.pdf")
    except Exception as e:  # PDF is a convenience; Markdown is the primary output
        print(f"PDF rendering failed: {e}", file=sys.stderr)
    return paths
