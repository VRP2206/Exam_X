"""Tests for the exact checkers, mostly using answers from the past-paper solutions."""
from itertools import product

import pytest

from examx.checkers import cfg, fa, logic, regex, tm


def strings(alphabet, n):
    return ["".join(t) for k in range(n + 1) for t in product(alphabet, repeat=k)]


# ------------------------------------------------------------ regex

def test_exam2013_q3_strings_up_to_8():
    nfa = regex.to_nfa("(((ab) ∪(ba))a)^{∗}")
    assert fa.language_upto(nfa, {"a", "b"}, 8) == {"", "aba", "baa", "abaaba", "ababaa", "baaaba", "baabaa"}


def test_sample2013_q4_strings_up_to_8():
    expected = {"", "101", "101101", "00", "10100", "00101", "00101101", "10100101", "10110100", "0000",
                "0000101", "0010100", "1010000", "000000", "00000000"}
    nfa = regex.to_nfa("((101)∗∪(00))∗")
    assert fa.language_upto(nfa, {"0", "1"}, 8) == expected
    # The solution notes the inner star is redundant.
    assert fa.equivalent(nfa, regex.to_nfa("((101)∪(00))∗"))


def test_sample2013_q3_binary_fraction():
    r = "0.(0 ∪1)∗1"
    for w in ["0.1", "0.01", "0.0111"]:
        assert regex.matches(r, w)
    for w in ["0.", "0.0", "0.10", "1.1"]:
        assert not regex.matches(r, w)
    # The "almost right" answer in the solution comments differs, e.g. on 0.0
    assert fa.counterexample(regex.to_nfa(r), regex.to_nfa("0.(0∪1)∗"), {"0", "1", "."}) == "0."


def test_regex_shorthands():
    assert fa.equivalent(regex.to_nfa("0.[01]*1"), regex.to_nfa("0.(0∪1)*1"))
    assert fa.equivalent(regex.to_nfa("a+"), regex.to_nfa("aa*"))
    assert fa.equivalent(regex.to_nfa("a | ε"), regex.to_nfa("(ε ∪ a)"))
    assert regex.matches("∅*", "")
    with pytest.raises(regex.RegexError):
        regex.to_nfa("(ab")


def test_regex_counterexample_is_shortest():
    # first and last letters differ (exam 2014-style question)
    good = "a(a∪b)*b ∪ b(a∪b)*a"
    bad = "a(a∪b)*b"
    assert fa.counterexample(regex.to_nfa(good), regex.to_nfa(bad)) == "ba"


# ------------------------------------------------------------ FA

EXAM2013_Q5_SOLN = """
state        a            b
Start 1      {2,3,4,5,6}  ∅
Final {2,3,4,5,6} {3,6}   {3,5,6}
Final {3,6}  {3,6}        ∅
Final {3,5,6} {3,6}       ∅
      ∅      ∅            ∅
"""


def test_parse_subset_construction_table_and_minimise():
    m = fa.parse_table(EXAM2013_Q5_SOLN)
    d = m.to_dfa()
    assert d.accepts("a") and d.accepts("ab") and d.accepts("abaa")
    assert not d.accepts("b") and not d.accepts("abb")
    # Solution comment: {3,6} and {3,5,6} merge under minimisation -> 3 live states + dead state.
    assert d.minimised().num_states == 4


SAMPLE_Q8_GIVEN = """
state a b
Start 1 2 6
      2 3 6
      3 6 3
      4 5 4
Final 5 4 6
Final 6 3 6
"""
SAMPLE_Q8_ANSWER = """
state a b
Start 1 2 4
      2 3 4
      3 4 3
Final 4 3 4
"""


def test_sample2013_q8_minimisation():
    given, answer = fa.parse_table(SAMPLE_Q8_GIVEN), fa.parse_table(SAMPLE_Q8_ANSWER)
    assert fa.equivalent(given, answer)
    assert given.to_dfa().minimised().num_states == 4 == answer.to_dfa().minimised().num_states


def test_edge_list_nfa_with_epsilon():
    m = fa.parse_edges("""
        start: 1
        final: 3
        1 a 2
        2 ε 3
        3 a,b 3
    """)
    assert fa.equivalent(m, regex.to_nfa("a(a∪b)*"))
    wrong = fa.parse_edges("start: 1\nfinal: 2\n1 a 2\n2 a 2")
    assert fa.counterexample(m, wrong) == "ab"


def test_parse_automaton_dispatch():
    assert fa.parse_automaton(SAMPLE_Q8_ANSWER).accepts("ab")
    assert fa.parse_automaton("start: 1\nfinal: 1\n1 a 1").accepts("aaa")


# ------------------------------------------------------------ CFG

def test_exam2013_q8_cfg():
    g = cfg.parse_cfg("S → aX\nX → aaXb\nX → aX\nX → ε")
    ref = lambda w: (m := len(w) - len(w.lstrip("a"))) and set(w[m:]) <= {"b"} and m > 2 * (len(w) - m)
    assert cfg.compare(g, ref, {"a", "b"}, 9) == ([], [])
    # The solution's near-miss also generates the empty string.
    near = cfg.parse_cfg("S → aaSb | aS | ε")
    missing, extra = cfg.compare(near, ref, {"a", "b"}, 9)
    assert missing == [] and extra[0] == ""


def test_exam2013_q9_grammar_is_astar_bstar():
    g = cfg.parse_cfg("S → a S (1)\nS → S b (2)\nS → ε (3)")
    assert cfg.compare(g, lambda w: regex.matches("a*b*", w), {"a", "b"}, 8) == ([], [])


def test_exam2013_q10_derivation():
    g = cfg.parse_cfg("S → aBa\nB → BB\nB → Q\nB → R\nQ → q\nR → r")
    ok, _ = cfg.check_derivation(g, ["S", "aBa (1)", "aBBa (2)", "aBBBa (2)", "aQBBa (3)", "aqBBa (5)",
                                      "aqRBa (4)", "aqrBa (6)", "aqrQa (3)", "aqrqa (5)"])
    assert ok
    ok, msg = cfg.check_derivation(g, ["S", "aBa", "aqa"])
    assert not ok and "does not follow" in msg


def test_cfg_nullable_and_angle_brackets():
    g = cfg.parse_cfg("<E> -> <E>+<E> | (<E>) | x")
    assert g.accepts("x+(x+x)") and not g.accepts("x+")
    g2 = cfg.parse_cfg("S -> AB\nA -> aA | ε\nB -> bB | ε")
    assert g2.accepts("") and g2.accepts("aab") and not g2.accepts("ba")


# ------------------------------------------------------------ PDA

def test_exam2013_q11_pda_from_grammar():
    # Standard top-down PDA for S -> A, A -> AbA | a (pushes rightmost symbol first).
    pda = tm.parse_pda("""
        start: 1
        accept: 4
        1 ε,ε->$ 2
        2 ε,ε->S 3
        3 ε,S->A 3
        3 ε,A->AbA 3
        3 ε,A->a 3
        3 a,a->ε 3
        3 b,b->ε 3
        3 ε,$->ε 4
    """)
    for w in ["a", "aba", "ababa"]:
        assert tm.pda_accepts(pda, w), w
    for w in ["", "ab", "abba", "b"]:
        assert not tm.pda_accepts(pda, w), w


# ------------------------------------------------------------ TM

TWOS_COMPLEMENT = """
start: 1
halt: H
1 0 -> 1 0 R
1 1 -> 1 1 R
1 Δ -> 2 Δ L
2 0 -> 2 0 L
2 1 -> 3 1 L
3 0 -> 3 1 L
3 1 -> 3 0 L
"""


def twos_complement(w):
    i = w.rfind("1")
    if i < 0:
        return w
    return "".join("1" if c == "0" else "0" for c in w[:i]) + w[i:]


def test_exam2013_q13_twos_complement_tm():
    machine = tm.parse_tm(TWOS_COMPLEMENT)
    # This machine finishes by running off the left end, which halts it (FIT2014 convention).
    assert tm.run_tm(machine, "0110100").tape == "1001100"
    for w in strings("01", 7):
        r = tm.run_tm(machine, w)
        assert r.halted and r.tape == twos_complement(w), w


def test_tm_fit2014_label_syntax_and_crash():
    machine = tm.parse_tm("1 a→b,R 1\n1 Δ→Δ,L 2\n2 b→b,L 2")
    r = tm.run_tm(machine, "aa")
    assert r.crashed and r.tape == "bb"
    loop = tm.parse_tm("1 Δ -> 1 Δ R")
    assert not tm.run_tm(loop, "", max_steps=50).halted


def test_tm_rejects_nondeterminism():
    with pytest.raises(ValueError):
        tm.parse_tm("1 a -> 2 a R\n1 a -> 3 b L")


# ------------------------------------------------------------ logic

def test_exam2013_q1_exactly_one_cnf():
    ans = "(C ∨H ∨S) ∧(¬C ∨¬H) ∧(¬C ∨¬S) ∧(¬H ∨¬S)"
    assert logic.is_cnf(ans)
    for env, v in logic.truth_table(ans):
        assert v == (sum(env.values()) == 1)
    assert logic.counterexample(ans, "C ∨ H ∨ S") is not None


def test_sample2013_q1_exactly_two_cnf():
    ans = ("(A ∨H ∨R) ∧(A ∨H ∨W) ∧(A ∨R ∨W) ∧(H ∨R ∨W) ∧"
           "(¬A ∨¬H ∨¬R) ∧(¬A ∨¬H ∨¬W) ∧(¬A ∨¬R ∨¬W) ∧(¬H ∨¬R ∨¬W)")
    assert logic.is_cnf(ans)
    assert all(v == (sum(env.values()) == 2) for env, v in logic.truth_table(ans))


def test_logic_operators_and_forms():
    assert logic.tautology("¬((P ∧ Q) ∧ (¬P ∧¬Q))")
    assert logic.equivalent("p -> q", "~p | q")
    assert logic.equivalent("p <-> q", "(p => q) & (q => p)")
    assert not logic.is_cnf("(a & b) | c") and logic.is_dnf("(a & b) | c")
    assert logic.satisfiable("x1 & ~x2") and not logic.satisfiable("x & ~x")
    assert logic.evaluate(logic.parse("1 ∧ ¬0"), {})
