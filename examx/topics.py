"""FIT2014 topic taxonomy and a keyword/regex tagger.

Each topic has a list of regex patterns with weights. A question is tagged with
every topic whose score passes a threshold; the highest-scoring topic is its
primary topic. Patterns are matched case-insensitively against question text
(and solution text when available, at reduced weight).
"""
from __future__ import annotations

import re

# Ordered roughly by where they appear in the unit.
TOPICS: dict[str, list[tuple[str, float]]] = {
    "propositional_logic": [
        (r"\bpropositions?\b", 2), (r"conjunctive normal form|\bCNF\b", 3), (r"truth table", 3),
        (r"disjunctive normal form|\bDNF\b", 3), (r"tautolog", 2), (r"[∧∨¬]", 0.5),
    ],
    "predicate_logic": [
        (r"\bpredicates?\b", 3), (r"predicate logic", 3), (r"[∀∃]", 2), (r"universal statement|existential statement", 3),
        (r"atomic sentence", 2), (r"\bquantifier", 2),
    ],
    "induction": [(r"\binduction\b", 4), (r"inductive (step|hypothesis)|base case", 2)],
    "regular_expressions": [
        (r"regular expressions?|\bregexp?s?\b", 3), (r"match(es)? the regular", 2), (r"\)\^\{∗\}|∗", 0.5),
    ],
    "finite_automata": [
        (r"\bFA\b|\bDFA\b|finite automat", 3), (r"\bstates?\b", 0.5), (r"final state|start state", 1),
    ],
    "nfa": [(r"\bNFAs?\b|nondeterministic finite", 3), (r"ε-?transition|empty transition", 1)],
    "kleenes_theorem": [
        (r"kleene'?s theorem", 4), (r"convert (it|the nfa|an nfa).{0,40}(finite automaton|\bFA\b)", 3),
        (r"subset construction", 3), (r"(NFAs?|FAs?|regular expressions?) to (NFAs?|FAs?|regular expressions?)", 2),
        (r"generali[sz]ed (transition graph|nondeterministic)|\bGTG\b|\bGNFA\b", 3),
    ],
    "minimisation": [(r"minimi[sz]", 4), (r"fewest states|minimum number of states", 4), (r"state[- ]minimi", 4)],
    "regular_closure": [
        (r"closed under|closure propert", 3), (r"prove that .{0,80} is regular\b", 3), (r"complement", 1), (r"cofinite", 2), (r"(union|intersection) of .{0,20}regular", 2),
    ],
    "pumping_lemma_regular": [
        (r"pumping lemma", 2), (r"not regular", 3), (r"pumping lemma for regular", 3), (r"myhill|nerode", 3),
    ],
    "cfg": [
        (r"context[- ]free grammars?|\bCFGs?\b", 3), (r"\bderivation\b", 2), (r"parse tree", 3), (r"→", 0.3),
        (r"chomsky normal form|\bCNF\b for context", 2), (r"ambiguous", 2),
        (r"regular grammar", 3), (r"\bCYK\b|cocke-younger-kasami", 4),
    ],
    "pda": [(r"pushdown automat|\bPDAs?\b", 4), (r"\bstack\b", 1)],
    "pumping_lemma_cfl": [
        (r"not context[- ]free", 4), (r"pumping lemma for context[- ]free", 4), (r"\buvxyz\b|uv\^\{?i", 2),
    ],
    "turing_machines": [
        (r"turing machines?", 3), (r"\bTMs?\b", 1), (r"(draw|write|give) a turing machine|turing machine to (compute|decide|recognise)", 4),
        (r"trace the execution", 2),
        (r"\btape\b", 2), (r"\bhead\b", 1), (r"universal turing machine|\bUTM\b", 2), (r"enumerator", 3),
    ],
    "church_turing": [(r"church[- ]turing", 5), (r"recursive function", 2), (r"lambda calculus|λ", 2)],
    "decidability": [
        (r"\bdecidable\b|\bundecidable\b", 3), (r"halting problem", 2), (r"recursively enumerable|\br\.e\.", 3),
        (r"\bdecider\b", 1), (r"semi-?decidable|recogni[sz]able", 2), (r"rice'?s theorem", 4),
    ],
    "mapping_reductions": [
        (r"mapping reduction|reduction from|reduce[sd]? .{0,30} to", 3), (r"(undecidable|not r\.e\.).{0,200}you may use", 2),
    ],
    "complexity_p": [
        (r"\bclass P\b|in P\b|polynomial[- ]time|polynomial time complexity", 2), (r"time complexity", 2),
        (r"big-?O|O\(n", 2),
    ],
    "np_completeness": [
        (r"\bNP\b", 2), (r"NP-complete", 4), (r"cook-?levin", 4), (r"satisfiab|\bSAT\b", 2),
        (r"polynomial-?time reduction", 3), (r"certificate|verifier", 2),
        (r"vertex cover|clique|hamiltonian|independent set|colou?ring|subset sum|3-?SAT", 1),
    ],
    "language_classes": [(r"venn diagram", 4), (r"which classes it belongs", 4), (r"chomsky hierarchy", 3)],
}

# Human-readable names used in rendered papers and the CLI.
TOPIC_NAMES = {
    "propositional_logic": "Propositional logic",
    "predicate_logic": "Predicate logic",
    "induction": "Proof by induction",
    "regular_expressions": "Regular expressions",
    "finite_automata": "Finite automata",
    "nfa": "Nondeterministic finite automata",
    "kleenes_theorem": "Kleene's theorem / conversions",
    "minimisation": "FA minimisation",
    "regular_closure": "Closure properties of regular languages",
    "pumping_lemma_regular": "Pumping lemma (regular)",
    "cfg": "Context-free grammars",
    "pda": "Pushdown automata",
    "pumping_lemma_cfl": "Pumping lemma (context-free)",
    "turing_machines": "Turing machines",
    "church_turing": "Church-Turing thesis",
    "decidability": "Decidability / undecidability",
    "mapping_reductions": "Reductions (computability)",
    "complexity_p": "Time complexity / class P",
    "np_completeness": "NP and NP-completeness",
    "language_classes": "Classes of languages",
}

_COMPILED = {t: [(re.compile(p, re.I), w) for p, w in pats] for t, pats in TOPICS.items()}
THRESHOLD = 3.0


def score(text: str) -> dict[str, float]:
    text = re.sub(r"\s+", " ", text)
    out: dict[str, float] = {}
    for topic, pats in _COMPILED.items():
        s = 0.0
        for rx, w in pats:
            n = len(rx.findall(text))
            if n:
                s += w * min(n, 3)  # cap repeated hits so long questions don't dominate
        if s:
            out[topic] = s
    return out


def tag(question_text: str, solution_text: str = "") -> tuple[list[str], str | None]:
    """Return (topics sorted by score, primary topic)."""
    sc = score(question_text)
    for t, s in score(solution_text).items():
        sc[t] = sc.get(t, 0) + 0.3 * s
    # "Pumping lemma" + "context-free" means the CFL version, not the regular one.
    if sc.get("pumping_lemma_cfl", 0) >= THRESHOLD and "not regular" not in question_text.lower():
        sc.pop("pumping_lemma_regular", None)
    ranked = sorted((t for t, s in sc.items() if s >= THRESHOLD), key=lambda t: -sc[t])
    return ranked, (ranked[0] if ranked else None)


ANSWER_TYPES = [
    # (answer_type, pattern) — first match wins; drives which grader is used.
    ("tm_trace", r"trace the execution"),
    ("proof", r"prove by induction"),
    ("mcq", r"circl(e|ing) the appropriate|choose one of the answers|tick one box"),
    ("language_classes", r"venn diagram"),
    ("string_list", r"write down all strings|list all (the )?strings"),
    ("fa_minimise", r"fewest states|minimi[sz]|has only \w+ states|minimum number of states"),
    ("fa_table", r"filling in the table|fill in the table"),
    ("regex", r"(give|write|find) (a|the) regular expression"),
    ("nfa", r"(give|draw|construct) an? NFA"),
    ("fa", r"(give|draw|construct) an? (FA|DFA|finite automaton)"),
    ("cfg", r"(give|write|construct) an? (context[- ]free|regular) grammar|give a cfg"),
    ("derivation", r"\bderivation\b|parse tree"),
    ("pda", r"pushdown automaton"),
    ("tm", r"(draw|give|construct|design|write) a turing machine"),
    ("prop_formula", r"write a proposition|conjunctive normal form|boolean expression"),
    ("predicate_formula", r"predicate logic|universal statement|existential statement"),
    ("proof", r"\bprove\b|\bproof\b|show that"),
]
_ANSWER_RX = [(t, re.compile(p, re.I)) for t, p in ANSWER_TYPES]


def answer_type(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    for t, rx in _ANSWER_RX:
        if rx.search(text):
            return t
    return "short_answer"
