"""Hand-checked banks used by the procedural question generators.

Every language carries a Python membership predicate; where it is regular or
context-free it also carries a reference regex / CFG. tests/test_bank.py checks
that all three agree on every string up to a fixed length.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _count(w, c):
    return w.count(c)


def _ab_split(w):
    """(m, n) if w = a^m b^n, else None."""
    m = len(w) - len(w.lstrip("a"))
    rest = w[m:]
    return (m, len(rest)) if set(rest) <= {"b"} else None


@dataclass(frozen=True)
class Language:
    key: str
    description: str  # Markdown, used in question text
    alphabet: tuple[str, ...]
    predicate: Callable[[str], bool]
    regex: str | None = None  # present iff regular
    cfg: str | None = None  # present iff context-free
    regular: bool = False
    context_free: bool = True


LANGUAGES = [
    Language("first_last_differ", "the language of all strings over {a,b} whose first and last letters are different",
             ("a", "b"), lambda w: len(w) >= 2 and w[0] != w[-1],
             regex="a(a∪b)*b ∪ b(a∪b)*a", cfg="S → aXb | bXa\nX → aX | bX | ε", regular=True),
    Language("even_a", "the language of all strings over {a,b} with an even number of a's",
             ("a", "b"), lambda w: _count(w, "a") % 2 == 0,
             regex="b*(ab*ab*)*", cfg="S → bS | aT | ε\nT → bT | aS", regular=True),
    Language("contains_aba", "the language of all strings over {a,b} that contain aba as a substring",
             ("a", "b"), lambda w: "aba" in w,
             regex="(a∪b)*aba(a∪b)*", cfg="S → XabaX\nX → aX | bX | ε", regular=True),
    Language("no_bb", "the language of all strings over {a,b} that do not contain bb as a substring",
             ("a", "b"), lambda w: "bb" not in w,
             regex="(a∪ba)*(ε∪b)", cfg="S → aS | baS | b | ε", regular=True),
    Language("ends_ab", "the language of all strings over {a,b} that end in ab",
             ("a", "b"), lambda w: w.endswith("ab"),
             regex="(a∪b)*ab", cfg="S → aS | bS | ab", regular=True),
    Language("len_mod3", "the language of all strings over {a,b} whose length is a multiple of 3",
             ("a", "b"), lambda w: len(w) % 3 == 0,
             regex="((a∪b)(a∪b)(a∪b))*", cfg="S → XXXS | ε\nX → a | b", regular=True),
    Language("binary_div3", "the language of binary strings (possibly with leading zeros) that represent a multiple of 3",
             ("0", "1"), lambda w: w != "" and int(w, 2) % 3 == 0,
             regex="(0∪1(01*0)*1)(0∪1(01*0)*1)*", cfg="S → 0Z | 1O\nZ → 0Z | 1O | ε\nO → 0T | 1Z\nT → 0O | 1T", regular=True),
    Language("binary_pos_leading1", "the language of positive integers in binary with leading bit 1",
             ("0", "1"), lambda w: w.startswith("1"),
             regex="1(0∪1)*", cfg="S → 1X\nX → 0X | 1X | ε", regular=True),
    Language("anbn", "{ a^n b^n : n ≥ 0 }", ("a", "b"), lambda w: (s := _ab_split(w)) is not None and s[0] == s[1],
             cfg="S → aSb | ε"),
    Language("am_lt_bn", "{ a^m b^n : m < n }", ("a", "b"), lambda w: (s := _ab_split(w)) is not None and s[0] < s[1],
             cfg="S → aSb | Sb | b"),
    Language("am_bn_m_gt_2n", "{ a^m b^n : m > 2n, n ≥ 0 }", ("a", "b"),
             lambda w: (s := _ab_split(w)) is not None and s[0] > 2 * s[1], cfg="S → aX\nX → aaXb | aX | ε"),
    Language("a2n_bn", "{ a^{2n} b^n : n ≥ 1 }", ("a", "b"),
             lambda w: (s := _ab_split(w)) is not None and s[1] >= 1 and s[0] == 2 * s[1], cfg="S → aaSb | aab"),
    Language("palindromes", "the language of palindromes over {a,b}", ("a", "b"), lambda w: w == w[::-1],
             cfg="S → aSa | bSb | a | b | ε"),
    Language("equal_ab", "the language of strings over {a,b} with equal numbers of a's and b's", ("a", "b"),
             lambda w: _count(w, "a") == _count(w, "b"), cfg="S → aSbS | bSaS | ε"),
    Language("more_a", "the language of strings over {a,b} with more a's than b's", ("a", "b"),
             lambda w: _count(w, "a") > _count(w, "b"), cfg="S → TaT\nT → aTbT | bTaT | aT | ε"),
    Language("ww_reverse_c", "{ w c w^R : w ∈ {a,b}^* }, where w^R is the reverse of w", ("a", "b", "c"),
             lambda w: w.count("c") == 1 and (i := w.index("c")) * 2 + 1 == len(w) and w[:i] == w[i + 1:][::-1],
             cfg="S → aSa | bSb | c"),
    Language("anbncn", "{ a^n b^n c^n : n ≥ 0 }", ("a", "b", "c"),
             lambda w: (n := len(w) // 3) * 3 == len(w) and w == "a" * n + "b" * n + "c" * n, context_free=False),
    Language("ww", "{ ww : w ∈ {a,b}^* }", ("a", "b"), lambda w: len(w) % 2 == 0 and w[: len(w) // 2] == w[len(w) // 2:],
             context_free=False),
    Language("a_square", "{ a^{n^2} : n ≥ 0 }", ("a",),
             lambda w: set(w) <= {"a"} and int(len(w) ** 0.5) ** 2 == len(w), context_free=False),
]
LANG = {l.key: l for l in LANGUAGES}


# ------------------------------------------------------------------ TM functions

def _twos(w):
    i = w.rfind("1")
    return w if i < 0 else "".join("1" if c == "0" else "0" for c in w[:i]) + w[i:]


def _incr(w):
    if not w:
        return "1"
    return bin(int(w, 2) + 1)[2:].zfill(len(w)) if "0" in w else "1" + "0" * len(w)


@dataclass(frozen=True)
class TMFunction:
    key: str
    description: str
    alphabet: tuple[str, ...]
    fn: Callable[[str], str]
    example: str
    tm: str  # reference machine in examx.checkers.tm text format


TM_FUNCTIONS = [
    TMFunction("twos_complement", "computes the 2's complement of a binary string: flip each bit up to (but not including) "
               "the last 1, and keep that last 1 and all 0s after it unchanged", ("0", "1"), _twos, "0110100", """
start: 0
halt: H
# mark the first cell (X = 0, Y = 1): the tape has no blank to its left
0 0 -> 1 X R
0 1 -> 1 Y R
0 Δ -> H Δ R
1 0 -> 1 0 R
1 1 -> 1 1 R
1 Δ -> 2 Δ L
# 2: skip trailing 0s leftwards until the last 1
2 0 -> 2 0 L
2 1 -> 3 1 L
2 X -> H 0 R
2 Y -> H 1 R
# 3: flip everything to the left of the last 1
3 0 -> 3 1 L
3 1 -> 3 0 L
3 X -> H 1 R
3 Y -> H 0 R
"""),
    TMFunction("flip_bits", "flips every bit of a binary string (0 becomes 1 and 1 becomes 0)", ("0", "1"),
               lambda w: w.translate(str.maketrans("01", "10")), "01101", """
start: 1
halt: H
1 0 -> 1 1 R
1 1 -> 1 0 R
1 Δ -> H Δ R
"""),
    TMFunction("increment", "adds 1 to a binary number (most significant bit first). If the input is all 1s, the output is "
               "one bit longer, e.g. 111 becomes 1000", ("0", "1"), _incr, "1011", """
start: 0
halt: H
# mark the first cell (X = 0, Y = 1) so the left end can be recognised
0 0 -> 1 X R
0 1 -> 1 Y R
0 Δ -> H 1 R
1 0 -> 1 0 R
1 1 -> 1 1 R
1 Δ -> 2 Δ L
2 1 -> 2 0 L
2 0 -> 5 1 L
2 X -> H 1 R
2 Y -> 4 1 R
4 0 -> 4 0 R
4 Δ -> H 0 R
5 0 -> 5 0 L
5 1 -> 5 1 L
5 X -> H 0 R
5 Y -> H 1 R
"""),
    TMFunction("swap_ab", "replaces every a by b and every b by a", ("a", "b"), lambda w: w.translate(str.maketrans("ab", "ba")),
               "aab", """
start: 1
halt: H
1 a -> 1 b R
1 b -> 1 a R
1 Δ -> H Δ R
"""),
    TMFunction("append_a", "appends one a to the end of its input string", ("a", "b"), lambda w: w + "a", "bab", """
start: 1
halt: H
1 a -> 1 a R
1 b -> 1 b R
1 Δ -> H a R
"""),
    TMFunction("double_last", "duplicates the last letter of a nonempty string (and leaves the empty string unchanged)",
               ("a", "b"), lambda w: w + w[-1:] if w else w, "abb", """
start: 0
halt: H
0 a -> 1 a R
0 b -> 1 b R
0 Δ -> H Δ R
1 a -> 1 a R
1 b -> 1 b R
1 Δ -> 2 Δ L
2 a -> 3 a R
2 b -> 4 b R
3 Δ -> H a R
4 Δ -> H b R
"""),
]
TMF = {f.key: f for f in TM_FUNCTIONS}


# ------------------------------------------------------------------ decision problems

DECISION_PROBLEMS = [
    ("Input: a Turing machine M.\nQuestion: Does M halt when given the empty string as input?", "Undecidable"),
    ("Input: a Turing machine M and a string w.\nQuestion: If M is run on w, does it halt within 100 steps?", "Decidable"),
    ("Input: a Turing machine M.\nQuestion: Does M have more than 10 states?", "Decidable"),
    ("Input: a Turing machine M.\nQuestion: Is the language accepted by M finite?", "Undecidable"),
    ("Input: a Turing machine M.\nQuestion: Does M accept the string abba?", "Undecidable"),
    ("Input: a Turing machine M.\nQuestion: Does M ever move its head left, when run on the empty string, during its first 50 steps?",
     "Decidable"),
    ("Input: a Finite Automaton A.\nQuestion: Is the language accepted by A empty?", "Decidable"),
    ("Input: two Finite Automata A and B.\nQuestion: Do A and B accept the same language?", "Decidable"),
    ("Input: a Context-Free Grammar G and a string w.\nQuestion: Does G generate w?", "Decidable"),
    ("Input: two Context-Free Grammars G and H.\nQuestion: Do G and H generate the same language?", "Undecidable"),
    ("Input: a Context-Free Grammar G.\nQuestion: Does G generate every string over its terminal alphabet?", "Undecidable"),
    ("Input: a Context-Free Grammar G.\nQuestion: Is the language generated by G empty?", "Decidable"),
    ("Input: a Turing machine M.\nQuestion: Is the language accepted by M regular?", "Undecidable"),
    ("Input: two Turing machines M1 and M2.\nQuestion: Do M1 and M2 accept the same language?", "Undecidable"),
    ("Input: a Turing machine M.\nQuestion: Does M ever write the symbol a on its tape, when run on the empty string, "
     "within its first 1000 steps?", "Decidable"),
    ("Input: a Turing machine M.\nQuestion: Does M halt on every input?", "Undecidable"),
    ("Input: a Turing machine M.\nQuestion: Does the description of M (as a string) have even length?", "Decidable"),
    ("Input: a Pushdown Automaton P and a string w.\nQuestion: Does P accept w?", "Decidable"),
]

CLASSES = ["Finite", "Regular", "Context-Free", "P", "NP", "Decidable", "r.e.", "None"]

# (description, smallest class it is known to belong to, assuming P ≠ NP)
CLASS_ITEMS = [
    ("The set of all strings over {a,b} of length at most 3.", "Finite"),
    ("The language {a, ab, abb, abbb}.", "Finite"),
    ("The set of all correctly formed arithmetic expressions using positive integers, +, − and parentheses.",
     "Context-Free"),
    ("The set of all graphs containing a Hamiltonian circuit.", "NP"),
    ("The set of all satisfiable Boolean expressions in Conjunctive Normal Form.", "NP"),
    ("The set of all graphs that can be properly coloured with 3 colours.", "NP"),
    ("The set of all graphs containing no circuit.", "P"),
    ("The set of all connected graphs.", "P"),
    ("The set of binary representations of prime numbers.", "P"),
    ("The set of all Context-Free Grammars that generate the empty language.", "P"),
    ("The set of all (encodings of) Turing machines that halt when given the empty string as input.", "r.e."),
    ("The set of all (encodings of) Turing machines that eventually halt, when given themselves as input.", "r.e."),
    ("The set of all (encodings of) Turing machines that loop forever, when given themselves as input.", "None"),
    ("The set of all (encodings of) Turing machines that accept every string.", "None"),
]

PROP_SCENARIOS = [
    ("You are choosing toppings for a pizza", "You choose {}.", ["mushroom", "olives", "pineapple", "capsicum"]),
    ("Four students are being considered for two scholarships", "{} receives a scholarship.", ["Ada", "Grace", "Kurt", "Emmy"]),
    ("A robot vacuum can be in some of these rooms", "The robot is in the {}.", ["kitchen", "lounge", "study", "hallway"]),
    ("A committee is being formed from four candidates", "{} is on the committee.", ["Alonzo", "Barbara", "Claude", "Dorothy"]),
    ("Your phone is somewhere in your house", "Your phone is in the {}.", ["bedroom", "bathroom", "garage", "laundry"]),
]
