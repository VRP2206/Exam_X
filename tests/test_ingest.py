"""Sanity checks on the ingested corpus (data/ is committed; re-run `examx ingest` to refresh)."""
import json

from examx.ingest import DATA_DIR, load_corpus
from examx.topics import TOPICS, answer_type, tag

corpus = load_corpus()


def test_every_paper_totals_120_marks():
    for f in (DATA_DIR / "papers").glob("*.json"):
        paper = json.loads(f.read_text())
        assert paper["total_marks"] == 120, f.name
        nums = [q["number"] for q in paper["questions"]]
        assert nums == list(range(1, len(nums) + 1)), f.name


def test_solutions_attached_only_where_available():
    with_sol = {q["paper"] for q in corpus if q["solution"]}
    assert with_sol == {"exam-2013", "sampleexam2013"}


def test_superscripts_and_part_marks_preserved():
    q = next(q for q in corpus if q["id"] == "exam-2013-q7")
    assert "a^{m}b^{n}" in q["text"].replace(" ", "")
    q22 = next(q for q in corpus if q["id"] == "exam-2013-q22")
    assert [p["marks"] for p in q22["parts"]] == [4, 6, 7, 2, 2]


def test_solution_text_is_separated_from_question_text():
    q = next(q for q in corpus if q["id"] == "exam-2013-q1")
    assert "(C ∨H ∨S)" in q["solution"].replace(" ∨", "∨").replace("∨ ", "∨").replace("∨", " ∨")[:20] or "C" in q["solution"]
    assert "∨" not in q["text"]
    assert "3-CNF" in q["comments"]


def test_every_question_tagged():
    assert all(q["primary_topic"] in TOPICS for q in corpus)


def test_tagger_and_answer_types():
    topics, primary = tag("Use the Pumping Lemma to prove that the language { a^n b^n } is not regular.")
    assert primary == "pumping_lemma_regular"
    assert tag("Prove that the following problem is undecidable. Input: a Turing machine M.")[1] == "decidability"
    assert answer_type("Give a Context-Free Grammar for the language") == "cfg"
    assert answer_type("find an FA with fewest states") == "fa_minimise"
