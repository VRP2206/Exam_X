"""Grade a student's attempt at a generated (or past) paper.

Attempt format (Markdown)::

    ## Q1
    (A ∨ B) ∧ (¬A ∨ ¬B)

    ## Q3
    ### (a)
    ε, ab, ba
    ### (b)
    ```
    start: 1
    final: 2
    1 a 2
    ```

Questions are "## Q<n>" or "## Question <n>"; parts are "### (a)" or a line starting "(a)".
If a part contains a fenced code block, that block is used for automatic checking.
A JSON attempt {"1": "answer", "3": {"a": "...", "b": "..."}} is also accepted.

Parts with a ``check`` spec are marked exactly by examx.checkers; everything else
(proofs, explanations, or answers that do not parse) is marked by the LLM against
the model solution and rubric.
"""
from __future__ import annotations

import json
import re
from itertools import product
from pathlib import Path

from . import bank, llm
from .checkers import cfg as cfgmod
from .checkers import fa, logic, regex, tm
from .ingest import DATA_DIR

Q_HEAD = re.compile(r"^#{1,3}\s*(?:Q|Question)\s*(\d+)\b.*$", re.I | re.M)
P_HEAD = re.compile(r"^(?:#{2,4}\s*)?\(([a-z])\)\s?", re.M)
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)


# ------------------------------------------------------------------ attempt parsing

def parse_attempt(text: str) -> dict[int, dict[str, str]]:
    """-> {question number: {part label ('' if none): answer text}}"""
    stripped = text.strip()
    if stripped.startswith("{"):
        data = json.loads(stripped)
        return {int(k): (v if isinstance(v, dict) else {"": v}) for k, v in data.items()}
    out: dict[int, dict[str, str]] = {}
    heads = list(Q_HEAD.finditer(text))
    for i, h in enumerate(heads):
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        out[int(h.group(1))] = _split_parts(body)
    return out


def _split_parts(body: str) -> dict[str, str]:
    # Ignore part markers inside code blocks.
    masked = FENCE.sub(lambda m: " " * len(m.group(0)), body)
    marks = list(P_HEAD.finditer(masked))
    if not marks:
        return {"": body.strip()}
    parts = {"": body[: marks[0].start()].strip()} if body[: marks[0].start()].strip() else {}
    for i, m in enumerate(marks):
        parts[m.group(1)] = body[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)].strip()
    return parts


def answer_payload(ans: str) -> str:
    m = FENCE.search(ans)
    return (m.group(1) if m else ans).strip()


def round_half(x: float) -> float:
    return round(x * 2) / 2


# ------------------------------------------------------------------ exact checks

def _strings(alphabet, n):
    return ["".join(t) for k in range(n + 1) for t in product(sorted(alphabet), repeat=k)]


def _show(w: str) -> str:
    return f"'{w}'" if w else "ε (the empty string)"


def check_string_list(spec, ans, marks):
    expected = fa.language_upto(regex.to_nfa(spec["regex"]), set(spec["alphabet"]), spec["max_len"])
    toks = [t.strip() for t in re.split(r"[,\s;]+", ans.replace("{", " ").replace("}", " ")) if t.strip()]
    given = {"" if t in {"ε", "λ", "eps", "epsilon", "''", '""'} else t for t in toks}
    hit, extra, missing = given & expected, given - expected, expected - given
    score = marks * max(0.0, (len(hit) - len(extra)) / len(expected))
    fb = []
    if missing:
        fb.append("Missing: " + ", ".join(_show(w) for w in sorted(missing, key=lambda s: (len(s), s))))
    if extra:
        fb.append("Should not be listed: " + ", ".join(_show(w) for w in sorted(extra, key=lambda s: (len(s), s))))
    return round_half(score), ("All strings correct." if not fb else " ".join(fb))


def _parse_language_answer(ans: str, kind: str):
    if kind == "regex":
        return regex.to_nfa(ans.strip().splitlines()[0] if "\n" in ans.strip() else ans)
    if kind == "automaton":
        return fa.parse_automaton(ans)
    try:  # "either"
        return fa.parse_automaton(ans)
    except Exception:
        return regex.to_nfa(ans)


def _is_deterministic(m: fa.NFA) -> bool:
    return len(m.start) == 1 and all(a != fa.EPS and len(qs) <= 1 for (_, a), qs in m.delta.items())


def check_language(spec, ans, marks):
    sigma = set(spec["alphabet"])
    ref = regex.to_nfa(spec["reference_regex"]) if spec.get("reference_regex") else fa.parse_edges(spec["reference_automaton"])
    student = _parse_language_answer(ans, spec.get("answer", "either"))
    cx = fa.counterexample(student, ref, sigma)
    if cx is None:
        score, fb = marks, ["Correct: your answer recognises exactly the required language."]
        if spec.get("deterministic") and not _is_deterministic(student):
            score -= 1
            fb.append("However the question asks for a (deterministic) FA and yours has ε-moves or several "
                      "transitions on the same letter.")
        if spec.get("max_states"):
            n = student.to_dfa(sigma).reachable().num_states if not _is_deterministic(student) else \
                len(_reachable_states(student))
            if n > spec["max_states"]:
                score -= 1
                fb.append(f"It has {n} states but the minimum possible is {spec['max_states']}.")
        return max(0, score), " ".join(fb)
    accepted = student.accepts(cx)
    words = _strings(sigma, 7)
    agree = sum(student.accepts(w) == ref.accepts(w) for w in words) / len(words)
    score = round_half(marks * 0.6 * max(0.0, (agree - 0.5) / 0.5)) if agree < 1 else marks * 0.5
    fb = (f"Not equivalent to the required language: your answer {'accepts' if accepted else 'rejects'} "
          f"{_show(cx)}, which should be {'rejected' if accepted else 'accepted'}. "
          f"It agrees with the correct language on {100 * agree:.0f}% of strings up to length 7.")
    return score, fb


def _reachable_states(m: fa.NFA) -> set:
    seen, stack = set(m.start), list(m.start)
    while stack:
        q = stack.pop()
        for (p, _), qs in m.delta.items():
            if p == q:
                for r in qs - seen:
                    seen.add(r)
                    stack.append(r)
    return seen


def check_cfg(spec, ans, marks):
    lang = bank.LANG[spec["language"]]
    g = cfgmod.parse_cfg(ans)
    missing, extra = cfgmod.compare(g, lang.predicate, set(spec["alphabet"]), spec.get("max_len", 8))
    if not missing and not extra:
        return marks, f"Correct on every string up to length {spec.get('max_len', 8)}."
    fb, score = [], marks
    if missing:
        score -= (marks + 1) // 2
        fb.append(f"Your grammar cannot generate {_show(missing[0])}" +
                  (f" (and {len(missing) - 1} more short strings in the language)" if len(missing) > 1 else "") + ".")
    if extra:
        score -= marks // 2
        fb.append(f"Your grammar generates {_show(extra[0])}, which is not in the language" +
                  (f" (and {len(extra) - 1} more)" if len(extra) > 1 else "") + ".")
    return max(0, score), " ".join(fb)


def check_derivation(spec, ans, marks):
    g = cfgmod.parse_cfg(spec["grammar"])
    steps = [re.sub(r"^\s*(⇒|=>|->|→)\s*", "", l) for l in ans.splitlines() if l.strip()]
    ok, msg = cfgmod.check_derivation(g, steps)
    final = re.sub(r"\(\d+\)\s*$", "", steps[-1]).replace(" ", "") if steps else ""
    if ok and final == spec["target"]:
        return marks, "Valid derivation."
    if ok:
        return max(0, marks - 1), f"Each step is valid, but it derives '{final}' instead of '{spec['target']}'."
    return round_half(marks * 0.3) if len(steps) > 2 else 0, f"Invalid derivation: {msg}."


def check_tm(spec, ans, marks):
    f = bank.TMF[spec["function"]]
    machine = tm.parse_tm(ans)
    words = _strings(f.alphabet, spec.get("max_len", 6))
    fails = []
    for w in words:
        r = tm.run_tm(machine, w, max_steps=5000)
        want = f.fn(w)
        if not r.halted or r.tape != want:
            fails.append((w, want, r))
    if not fails:
        return marks, f"Correct output on all {len(words)} inputs up to length {spec.get('max_len', 6)}."
    frac = 1 - len(fails) / len(words)
    w, want, r = fails[0]
    why = "did not halt (step limit reached)" if not r.halted else \
        (f"crashed off the left end with tape '{r.tape}'" if r.crashed else f"halted with tape '{r.tape}'")
    return round_half((marks - 1) * frac), (f"Wrong on {len(fails)} of {len(words)} test inputs. "
                                            f"For input {_show(w)} the output should be '{want}' but your machine {why}.")


def check_prop(spec, ans, marks):
    ans = ans.strip().splitlines()[0] if ans.strip() else ans
    env = logic.counterexample(ans, spec["reference"])
    if env is None:
        if spec.get("require_cnf") and not logic.is_cnf(ans):
            return marks - 1, "Logically correct, but not in Conjunctive Normal Form."
        return marks, "Correct."
    a, b = logic.parse(ans), logic.parse(spec["reference"])
    vs = sorted(logic.variables(a) | logic.variables(b))
    rows = list(product([False, True], repeat=len(vs)))
    agree = sum(logic.evaluate(a, dict(zip(vs, r))) == logic.evaluate(b, dict(zip(vs, r))) for r in rows) / len(rows)
    assign = ", ".join(f"{k}={'T' if v else 'F'}" for k, v in env.items())
    return round_half((marks - 1) * max(0.0, (agree - 0.5) / 0.5) * 0.5), \
        f"Not equivalent to the required proposition: it gives the wrong truth value when {assign}."


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


ALIASES = {"cf": "contextfree", "cfl": "contextfree", "re": "re", "recursivelyenumerable": "re",
           "notre": "none", "decidable": "decidable", "recursive": "decidable"}


def check_choice(spec, ans, marks):
    a = _norm(ans.strip().splitlines()[0] if ans.strip() else "")
    a = ALIASES.get(a, a)
    opts = {_norm(o): o for o in spec["options"]}
    chosen = [opts[a]] if a in opts else [o for n, o in opts.items() if a.startswith(n) and n]
    chosen.sort(key=len, reverse=True)  # "undecidable..." must not match "decidable" first
    if not chosen:
        return 0, f"No recognisable choice (expected one of: {', '.join(spec['options'])})."
    return (marks, "Correct.") if chosen[0] == spec["answer"] else (0, f"Incorrect: the answer is {spec['answer']}.")


CHECKERS = {"string_list": check_string_list, "language": check_language, "cfg": check_cfg,
            "derivation": check_derivation, "tm_function": check_tm, "prop": check_prop, "choice": check_choice}


# ------------------------------------------------------------------ LLM marking

GRADER_SYSTEM = """You are a fair, careful FIT2014 Theory of Computation marker. Mark the student's answer
against the model solution and rubric. Award marks for correct reasoning even if it differs from the
model solution; do not award marks for statements that are wrong, vague, or missing key steps.
Before deducting marks because a student's claim is wrong, check the claim yourself step by step: the
model solution may itself be imperfect, and a concise argument that is correct deserves the marks.
Do not deduct for not restating a standard theorem in full unless the rubric asks for it.
Be concise and specific in feedback: say what is right, what is wrong, and how to fix it."""


def llm_grade(question: dict, part: dict, answer: str, model: str | None, note: str = "") -> tuple[float, str]:
    rubric = "\n".join(f"- {r['criterion']} ({r['marks']} marks)" for r in part.get("rubric", [])) or \
        f"- Correct and complete answer ({part['marks']} marks)"
    user = (f"QUESTION ({part['marks']} marks):\n{question['text']}\n{part['text']}\n\n"
            f"MODEL SOLUTION:\n{part.get('solution') or '(none available — use your own knowledge)'}\n\n"
            f"RUBRIC:\n{rubric}\n\n" + (f"NOTE FROM AUTOMATIC CHECKER: {note}\n\n" if note else "") +
            f"STUDENT ANSWER:\n{answer}\n\n"
            'Return JSON: {"criteria": [{"criterion": "...", "awarded": <number>, "comment": "..."}], '
            '"feedback": "2-4 sentences for the student"}')
    data = llm.chat_json([{"role": "system", "content": GRADER_SYSTEM}, {"role": "user", "content": user}],
                         model=model or llm.grader_model(), temperature=0.0, num_predict=1200)
    crit = [c for c in data.get("criteria", []) if isinstance(c, dict)]
    total = 0.0
    for c in crit:
        try:
            total += float(c.get("awarded", 0))
        except (TypeError, ValueError):
            pass
    score = round_half(min(max(total, 0.0), part["marks"]))
    detail = "; ".join(f"{c.get('criterion', '')}: {c.get('awarded', 0)} — {c.get('comment', '')}" for c in crit)
    fb = str(data.get("feedback", "")).strip()
    return score, (fb + ("\n\n_Rubric:_ " + detail if detail else "")).strip()


# ------------------------------------------------------------------ driver

def grade_part(question: dict, part: dict, answer: str, use_llm: bool = True, model: str | None = None) -> dict:
    res = {"label": part["label"], "marks": part["marks"]}
    if not answer.strip():
        return {**res, "awarded": 0, "method": "blank", "feedback": "No answer given."}
    spec = part.get("check")
    note = ""
    if spec and spec["kind"] in CHECKERS:
        try:
            score, fb = CHECKERS[spec["kind"]](spec, answer_payload(answer), part["marks"])
            return {**res, "awarded": float(score), "method": "exact", "feedback": fb}
        except Exception as e:  # unparseable answer: let the LLM read it instead
            note = f"the answer could not be parsed for automatic checking ({e})"
    if not use_llm:
        return {**res, "awarded": 0, "method": "needs-llm",
                "feedback": "Not marked: this answer needs the LLM marker." + (f" ({note})" if note else "")}
    try:
        score, fb = llm_grade(question, part, answer, model, note)
        return {**res, "awarded": score, "method": "llm-rubric", "feedback": fb}
    except llm.LLMError as e:
        return {**res, "awarded": 0, "method": "error", "feedback": f"LLM marking failed: {e}"}


def grade_attempt(paper: dict, attempt: dict[int, dict[str, str]], use_llm: bool = True, model: str | None = None,
                  log=print) -> dict:
    questions = []
    for q in paper["questions"]:
        ans = attempt.get(q["number"], {})
        parts = []
        for p in q["parts"]:
            a = ans.get(p["label"], "")
            if not a and len(q["parts"]) == 1:
                a = "\n".join(ans.values())
            r = grade_part(q, p, a, use_llm, model)
            log(f"Q{q['number']}{'(' + p['label'] + ')' if p['label'] else ''}: {r['awarded']:g}/{p['marks']:g} [{r['method']}]")
            parts.append(r)
        questions.append({"number": q["number"], "marks": q["marks"], "awarded": sum(p["awarded"] for p in parts),
                          "parts": parts})
    return {"paper_title": paper["title"], "total": sum(q["awarded"] for q in questions),
            "max_total": sum(q["marks"] for q in questions), "questions": questions}


def past_paper(pid: str) -> dict:
    """Wrap an ingested past paper in the generated-paper schema so attempts at it can be graded."""
    data = json.loads((DATA_DIR / "papers" / f"{pid}.json").read_text())
    qs = []
    for q in data["questions"]:
        parts = q["parts"] or [{"label": "", "text": "", "marks": None, "solution": q["solution"]}]
        n = len(parts)
        marks = [p.get("marks") or 0 for p in parts]
        if not all(marks):
            marks = [int(q["marks"]) // n + (1 if i < int(q["marks"]) % n else 0) for i in range(n)]
        qs.append({"number": q["number"], "marks": q["marks"], "text": q["stem"] if q["parts"] else q["text"],
                   "topic": q["primary_topic"], "parts": [
                       {"label": p["label"], "text": p.get("text", ""), "marks": m,
                        "solution": p.get("solution") or q["solution"],
                        "rubric": [{"criterion": "Correct answer (see official solution)" if data["has_solutions"]
                                    else "Correct and complete answer", "marks": m}], "check": None}
                       for p, m in zip(parts, marks)]})
    return {"title": f"FIT2014 {pid}", "questions": qs}


def load_paper(path_or_id: str) -> dict:
    p = Path(path_or_id)
    if p.exists():
        return json.loads(p.read_text())
    if (DATA_DIR / "papers" / f"{path_or_id}.json").exists():
        return past_paper(path_or_id)
    raise FileNotFoundError(f"no paper JSON at {path_or_id} and no past paper with that id")
