"""End-to-end tests of procedural generation + exact grading (no LLM needed)."""
import random

import pytest

from examx import grade, procedural as P
from examx.generate import generate_paper


def model_answer(part):
    """Extract a machine-readable answer from a procedural part's model solution."""
    sol = part["solution"]
    kind = part["check"]["kind"]
    if kind in ("language", "derivation", "tm_function"):
        body = grade.answer_payload(sol)
        return body.replace("⇒ ", "") if kind == "derivation" else body
    if kind == "prop":
        return sol.split("\n")[0]
    return sol


GENS = [P.gen_string_list, P.gen_nfa_to_dfa, P.gen_minimise, P.gen_prop_cnf, P.gen_regex, P.gen_fa, P.gen_cfg,
        P.gen_derivation, P.gen_tm, P.gen_decidability, P.gen_language_classes]


@pytest.mark.parametrize("gen", GENS, ids=lambda g: g.__name__)
@pytest.mark.parametrize("seed", range(4))
def test_model_solutions_get_full_marks(gen, seed):
    q = gen(random.Random(seed), 6 if gen is P.gen_regex else 4 if gen is P.gen_decidability else 5)
    assert q["marks"] == sum(p["marks"] for p in q["parts"])
    for p in q["parts"]:
        assert sum(r["marks"] for r in p["rubric"]) == p["marks"]
        if p["check"]:
            r = grade.grade_part(q, p, model_answer(p), use_llm=False)
            assert r["method"] == "exact" and r["awarded"] == p["marks"], (r, p["solution"])


def test_wrong_answers_lose_marks_with_feedback():
    q = P.gen_regex(random.Random(0), 3)
    p = q["parts"][0]
    r = grade.grade_part(q, p, "(a∪b)*", use_llm=False)
    assert r["awarded"] < p["marks"] and "should be" in r["feedback"]

    q = P.gen_prop_cnf(random.Random(1), 4)
    p = q["parts"][0]
    ref = p["check"]["reference"]
    # A correct but non-CNF version loses exactly the CNF mark.
    r = grade.grade_part(q, p, f"¬¬({ref})", use_llm=False)
    assert r["awarded"] == p["marks"] - 1 and "Normal Form" in r["feedback"]

    q = P.gen_tm(random.Random(2), 6)
    r = grade.grade_part(q, q["parts"][0], "start: 1\n1 a -> 1 a R", use_llm=False)
    assert r["awarded"] < 6 and "test inputs" in r["feedback"]


def test_choice_matching():
    spec = {"kind": "choice", "answer": "NP", "options": ["Finite", "Regular", "Context-Free", "P", "NP",
                                                          "Decidable", "r.e.", "None"]}
    assert grade.check_choice(spec, "NP", 1)[0] == 1
    assert grade.check_choice(spec, "None", 1)[0] == 0
    assert grade.check_choice({**spec, "answer": "r.e."}, "recursively enumerable", 1)[0] == 1
    assert grade.check_choice({**spec, "answer": "Context-Free"}, "CF", 1)[0] == 1
    dec = {"kind": "choice", "answer": "Undecidable", "options": ["Decidable", "Undecidable"]}
    assert grade.check_choice(dec, "undecidable", 1)[0] == 1 and grade.check_choice(dec, "Decidable", 1)[0] == 0


def test_unparseable_answer_defers_to_llm():
    q = P.gen_fa(random.Random(0), 4)
    r = grade.grade_part(q, q["parts"][0], "I drew it on paper", use_llm=False)
    assert r["method"] == "needs-llm" and "could not be parsed" in r["feedback"]


def test_parse_attempt_markdown():
    text = """## Q1
(A ∨ B)

## Question 3
### (a)
ε, ab
### (b)
```
start: 1
(a) not a part marker inside code
```
"""
    att = grade.parse_attempt(text)
    assert att[1] == {"": "(A ∨ B)"}
    assert att[3]["a"] == "ε, ab"
    assert "not a part marker" in grade.answer_payload(att[3]["b"])


def test_generated_paper_end_to_end():
    paper = generate_paper(seed=3, use_llm=False, log=lambda *a: None)
    assert paper["total_marks"] == 120
    attempt = {}
    for q in paper["questions"]:
        attempt[q["number"]] = {p["label"]: model_answer(p) for p in q["parts"] if p["check"]}
    report = grade.grade_attempt(paper, attempt, use_llm=False, log=lambda *a: None)
    exact = [p for q in report["questions"] for p in q["parts"] if p["method"] == "exact"]
    assert exact and all(p["awarded"] == p["marks"] for p in exact)


def test_past_paper_wrapper():
    paper = grade.past_paper("exam-2013")
    assert sum(q["marks"] for q in paper["questions"]) == 120
    q22 = next(q for q in paper["questions"] if q["number"] == 22)
    assert [p["marks"] for p in q22["parts"]] == [4, 6, 7, 2, 2]


@pytest.mark.parametrize("marks", [4, 20, 40])
def test_table_generators_handle_large_slots(marks):
    import random
    from examx import procedural
    for gen in (procedural.gen_decidability, procedural.gen_language_classes):
        q = gen(random.Random(1), marks)
        assert sum(p["marks"] for p in q["parts"]) == marks
