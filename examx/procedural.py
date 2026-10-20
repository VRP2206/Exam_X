"""Procedural generators for question types whose answers can be computed exactly.

Each generator takes (rng, marks) and returns a question dict in the generated-
paper schema (see examx/generate.py). Solutions here are computed, not written by
the LLM, so they are correct by construction; every part with a machine-checkable
answer carries a ``check`` spec that examx/grade.py knows how to mark.
"""
from __future__ import annotations

import random
from collections import deque
from itertools import combinations, product

from . import bank
from .checkers import cfg as cfgmod
from .checkers import fa, regex

FA_FORMAT = ("Answer format for automatic marking: a transition table whose first row is `state a b`, one row per "
             "state, rows prefixed by `Start` and/or `Final`, cells holding a state name (use `∅` for none). "
             "Alternatively an edge list: `start: 1`, `final: 2 3`, then lines like `1 a 2`.")
NFA_FORMAT = ("Answer format for automatic marking: an edge list — `start: 1`, `final: 3`, then one transition per line "
              "such as `1 a 2` or `2 ε 3` (several letters may be comma-separated: `1 a,b 2`).")
REGEX_FORMAT = "Answer format for automatic marking: use `∪` (or `|`) for union, `*` for Kleene star, `ε` for the empty string."
CFG_FORMAT = ("Answer format for automatic marking: one production per line, e.g. `S → aSb | ε`; non-terminals are "
              "capital letters and S is the start symbol.")
TM_FORMAT = ("Answer format for automatic marking: `start: 1`, `halt: H`, then one transition per line written "
             "`state read -> next write move` (move is L, R or S; Δ is the blank), e.g. `1 a -> 2 b R`.")
PROP_FORMAT = "Answer format for automatic marking: use ∧ ∨ ¬ (or & | ~) and parentheses."


def part(label, text, marks, solution, rubric=None, check=None, answer_type="short_answer", answer_format=None):
    return {"label": label, "text": text, "marks": marks, "answer_type": answer_type, "solution": solution,
            "rubric": rubric or [{"criterion": "Correct answer", "marks": marks}], "check": check,
            "answer_format": answer_format}


def question(topic, answer_type, text, parts, source="procedural"):
    return {"topic": topic, "answer_type": answer_type, "text": text, "parts": parts,
            "marks": sum(p["marks"] for p in parts), "source": source}


def lang_phrase(lang) -> str:
    return lang.description if lang.description.startswith("the ") else "the language " + lang.description


def split_marks(total: int, n: int) -> list[int]:
    base = [total // n] * n
    for i in range(total - sum(base)):
        base[-1 - i] += 1
    return base


# ------------------------------------------------------------------ formatting

def _sname(s) -> str:
    if isinstance(s, frozenset):
        return "{" + ",".join(sorted(map(str, s), key=_natkey)) + "}" if s else "∅"
    return str(s)


def _natkey(x: str):
    return (0, int(x)) if x.isdigit() else (1, x)


def dfa_table(d: fa.DFA, names: dict | None = None) -> str:
    sigma = sorted(d.alphabet)
    names = names or {q: _sname(q) for q in d.states}
    order = _bfs_order(d)
    rows = [["", "state"] + sigma]
    for q in order:
        flag = " ".join(x for x, c in (("Start", q == d.start), ("Final", q in d.finals)) if c)
        rows.append([flag, names[q]] + [names[d.delta[(q, a)]] for a in sigma])
    return _align(rows)


def nfa_table(m: fa.NFA) -> str:
    sigma = sorted(m.alphabet) + ["ε"]
    rows = [["", "state"] + sigma]
    for q in sorted(m.states, key=lambda s: _natkey(str(s))):
        flag = " ".join(x for x, c in (("Start", q in m.start), ("Final", q in m.finals)) if c)
        cells = []
        for a in sigma:
            t = m.delta.get((q, fa.EPS if a == "ε" else a), set())
            cells.append("{" + ",".join(sorted(map(str, t), key=_natkey)) + "}" if t else "∅")
        rows.append([flag, str(q)] + cells)
    return _align(rows)


def _align(rows) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def _bfs_order(d: fa.DFA) -> list:
    order, queue = [d.start], deque([d.start])
    while queue:
        q = queue.popleft()
        for a in sorted(d.alphabet):
            r = d.delta[(q, a)]
            if r not in order:
                order.append(r)
                queue.append(r)
    return order + sorted((q for q in d.states if q not in order), key=repr)


def code(s: str) -> str:
    return f"\n```\n{s}\n```\n"


def nfa_edges_text(m: fa.NFA) -> str:
    lines = [f"start: {' '.join(sorted(map(str, m.start)))}", f"final: {' '.join(sorted(map(str, m.finals)))}"]
    for (p, a), qs in sorted(m.delta.items(), key=lambda kv: (repr(kv[0][0]), kv[0][1])):
        for q in sorted(qs, key=repr):
            lines.append(f"{p} {a or 'ε'} {q}")
    return "\n".join(lines)


# ------------------------------------------------------------------ generators

def _random_regex(rng: random.Random) -> str:
    w = lambda: "".join(rng.choice("ab") for _ in range(rng.choice([1, 2, 2, 3])))
    shapes = [
        lambda: f"((({w()})∪({w()})){w()})*",
        lambda: f"(({w()})*∪({w()}))*",
        lambda: f"{w()}({w()}∪{w()})*",
        lambda: f"({w()}∪{w()})*{w()}",
        lambda: f"({w()}∪{w()}*)({w()}∪ε)",
    ]
    return rng.choice(shapes)()


def gen_string_list(rng: random.Random, marks: int = 4) -> dict:
    for _ in range(500):
        r = _random_regex(rng)
        n = rng.choice([6, 7, 8])
        lang = sorted(fa.language_upto(regex.to_nfa(r), {"a", "b"}, n), key=lambda s: (len(s), s))
        if 5 <= len(lang) <= 14 and set("".join(lang)) == {"a", "b"}:
            break
    m1, m2 = split_marks(marks, 2)
    strings_ = ", ".join(s or "ε" for s in lang)
    nfa = regex.to_nfa(r)
    return question("regular_expressions", "string_list",
                    f"Consider the regular expression {r} over the alphabet {{a,b}}.",
                    [part("a", f"Write down all strings of at most {n} letters that match this regular expression.", m1,
                          strings_, [{"criterion": "All strings listed, no extras", "marks": m1}],
                          {"kind": "string_list", "regex": r, "alphabet": ["a", "b"], "max_len": n}, "string_list"),
                     part("b", "Give an NFA that recognises the language described by this regular expression.", m2,
                          "One possibility (any NFA for the same language is equally acceptable):" +
                          code(nfa_edges_text(_compact_nfa(nfa))),
                          [{"criterion": "NFA accepts exactly the language of the regular expression", "marks": m2}],
                          {"kind": "language", "reference_regex": r, "alphabet": ["a", "b"], "answer": "automaton"},
                          "nfa", NFA_FORMAT)])


def _compact_nfa(m: fa.NFA) -> fa.NFA:
    """Present a regex's NFA via its minimal DFA (far easier to read than Thompson's ε-soup)."""
    d = m.to_dfa().minimised()
    dead = [q for q in d.states if q not in d.finals and all(d.delta[(q, a)] == q for a in d.alphabet)]
    delta = {}
    for (p, a), q in d.delta.items():
        if p in dead or q in dead:
            continue
        delta[(p + 1, a)] = {q + 1}
    states = {q + 1 for q in d.states if q not in dead}
    return fa.NFA(states, d.alphabet, delta, {d.start + 1}, {q + 1 for q in d.finals})


def _random_nfa(rng: random.Random, n: int) -> fa.NFA:
    states = list(range(1, n + 1))
    delta: dict = {}
    for p in states:
        for a in "ab":
            for q in rng.sample(states, rng.choice([0, 1, 1, 2])):
                delta.setdefault((p, a), set()).add(q)
    for _ in range(rng.choice([1, 2, 2])):
        p, q = rng.sample(states, 2)
        delta.setdefault((p, fa.EPS), set()).add(q)
    finals = set(rng.sample(states[1:], rng.choice([1, 2])))
    return fa.NFA(set(states), {"a", "b"}, delta, {1}, finals)


def gen_nfa_to_dfa(rng: random.Random, marks: int = 7) -> dict:
    for _ in range(2000):
        m = _random_nfa(rng, rng.choice([4, 5]))
        d = m.to_dfa()
        if 4 <= len(d.states) <= 7 and d.finals and len(d.finals) < len(d.states):
            break
    text = ("The following table describes an NFA with ε-transitions (each cell lists the set of possible next states). "
            "Convert it to a Finite Automaton that recognises the same language, using the subset construction. "
            "Represent your FA as a transition table." + code(nfa_table(m)))
    sol = ("Subset construction (each FA state is the ε-closure of a set of NFA states):" + code(dfa_table(d)) +
           "Merging equivalent states (state minimisation) is also acceptable.")
    rubric = [{"criterion": "Correct Start state (ε-closure of the NFA start state)", "marks": 1},
              {"criterion": "Correct transitions for every state", "marks": marks - 2},
              {"criterion": "Correct Final states", "marks": 1}]
    return question("kleenes_theorem", "fa_table", text,
                    [part("", "", marks, sol, rubric,
                          {"kind": "language", "reference_automaton": nfa_edges_text(m), "alphabet": ["a", "b"],
                           "answer": "automaton", "deterministic": True}, "fa_table", FA_FORMAT)])


def _random_min_dfa(rng: random.Random, k: int) -> fa.DFA:
    while True:
        delta = {(q, a): rng.randrange(k) for q in range(k) for a in "ab"}
        finals = set(rng.sample(range(k), rng.choice(range(1, k))))
        d = fa.DFA(set(range(k)), {"a", "b"}, delta, 0, finals)
        if d.reachable().num_states == k and d.minimised().num_states == k:
            return d


def gen_minimise(rng: random.Random, marks: int = 4) -> dict:
    k = rng.choice([3, 4])
    for _ in range(1000):
        d = _random_min_dfa(rng, k)
        # Split some states into copies; redirect a random subset of incoming edges to the copies.
        copies = {q: q + k for q in rng.sample(range(k), rng.choice([1, 2]))}
        delta = {}
        for (q, a), r in d.delta.items():
            delta[(q, a)] = copies[r] if r in copies and rng.random() < 0.5 else r
        for q, c in copies.items():
            for a in "ab":
                delta[(c, a)] = d.delta[(q, a)] if rng.random() < 0.5 else copies.get(d.delta[(q, a)], d.delta[(q, a)])
        finals = d.finals | {c for q, c in copies.items() if q in d.finals}
        big = fa.DFA(set(range(k)) | set(copies.values()), {"a", "b"}, delta, 0, finals)
        if big.reachable().num_states == k + len(copies) and fa.equivalent(big, d):
            break
    # Rename states 1..n in a shuffled order (start stays 1).
    rest = [q for q in big.states if q != 0]
    rng.shuffle(rest)
    names = {0: "1", **{q: str(i + 2) for i, q in enumerate(rest)}}
    minimal = big.minimised()
    text = ("Given the Finite Automaton described by the following table, find an FA with the fewest possible states "
            "that recognises the same language." + code(dfa_table(big, names)) + "Write your new FA as a table.")
    sol = (f"The minimum FA has {minimal.num_states} states:" +
           code(dfa_table(minimal, {q: str(q + 1) for q in minimal.states})))
    return question("minimisation", "fa_minimise", text,
                    [part("", "", marks, sol,
                          [{"criterion": "FA recognises the same language", "marks": marks - 1},
                           {"criterion": f"Has the minimum number of states ({minimal.num_states})", "marks": 1}],
                          {"kind": "language", "reference_automaton": _dfa_edges(big), "alphabet": ["a", "b"],
                           "answer": "automaton", "deterministic": True, "max_states": minimal.num_states},
                          "fa_minimise", FA_FORMAT)])


def _dfa_edges(d: fa.DFA) -> str:
    lines = [f"start: {d.start}", "final: " + " ".join(map(str, sorted(d.finals)))]
    lines += [f"{p} {a} {q}" for (p, a), q in sorted(d.delta.items())]
    return "\n".join(lines)


def _at_least(vs, k):
    """CNF clauses: at least k of vs true <=> every (n-k+1)-subset contains a true variable."""
    return [list(c) for c in combinations(vs, len(vs) - k + 1)] if k > 0 else []


def _at_most(vs, k):
    return [["¬" + v for v in c] for c in combinations(vs, k + 1)] if k < len(vs) else []


def _cnf(clauses) -> str:
    return " ∧ ".join("(" + " ∨ ".join(c) + ")" if len(c) > 1 else c[0] for c in clauses)


def gen_prop_cnf(rng: random.Random, marks: int = 4) -> dict:
    intro, fmt, items = rng.choice(bank.PROP_SCENARIOS)
    n = rng.choice([3, 4])
    items = rng.sample(items, n)
    letters = []
    for it in items:
        c = it[0].upper()
        while c in letters:
            c = chr(ord(c) + 1)
        letters.append(c)
    kind = rng.choice(["exactly", "at_least", "at_most"]) if n == 4 else rng.choice(["exactly", "at_most"])
    k = rng.choice([1, 2]) if kind != "at_most" else rng.choice([1, 2][: n - 2])
    clauses = (_at_least(letters, k) if kind in ("exactly", "at_least") else []) + \
              (_at_most(letters, k) if kind in ("exactly", "at_most") else [])
    words = {"exactly": "exactly", "at_least": "at least", "at_most": "at most"}[kind]
    defs = "\n".join(f"- {L}: {fmt.format(it)}" for L, it in zip(letters, items))
    text = (f"{intro}. Suppose we have propositions {', '.join(letters)} with the following meanings.\n\n{defs}\n\n"
            f"Use {', '.join(letters)} to write a proposition, in Conjunctive Normal Form, that is True precisely when "
            f"{words} {['one', 'two'][k - 1]} of these {n} propositions {'is' if k == 1 else 'are'} True.")
    sol = _cnf(clauses)
    expl = []
    if kind in ("exactly", "at_least"):
        expl.append(f"the clauses of size {n - k + 1} ensure at least {k} are true")
    if kind in ("exactly", "at_most"):
        expl.append(f"the negated clauses of size {k + 1} ensure at most {k} are true")
    return question("propositional_logic", "prop_formula", text,
                    [part("", "", marks, f"{sol}\n\nHere " + " and ".join(expl) + ".",
                          [{"criterion": "Logically correct (same truth table)", "marks": marks - 1},
                           {"criterion": "In Conjunctive Normal Form", "marks": 1}],
                          {"kind": "prop", "reference": sol, "require_cnf": True}, "prop_formula", PROP_FORMAT)])


def gen_regex(rng: random.Random, marks: int = 3) -> dict:
    lang = rng.choice([l for l in bank.LANGUAGES if l.regular])
    if marks >= 5:
        m1, m2 = split_marks(marks, 2)
        return question("regular_expressions", "regex", f"Let L be {lang.description}.", [
            part("a", "Give a regular expression for L.", m1, lang.regex, None,
                 {"kind": "language", "reference_regex": lang.regex, "alphabet": list(lang.alphabet), "answer": "regex"},
                 "regex", REGEX_FORMAT),
            part("b", "Give a Finite Automaton that recognises L.", m2,
                 "One possibility:" + code(dfa_table(_named_min(lang.regex))), None,
                 {"kind": "language", "reference_regex": lang.regex, "alphabet": list(lang.alphabet), "answer": "automaton",
                  "deterministic": True}, "fa", FA_FORMAT)])
    return question("regular_expressions", "regex", "", [
        part("", f"Give a regular expression for {lang.description}.", marks, lang.regex, None,
             {"kind": "language", "reference_regex": lang.regex, "alphabet": list(lang.alphabet), "answer": "regex"},
             "regex", REGEX_FORMAT)])


def _named_min(r: str) -> fa.DFA:
    d = regex.to_nfa(r).to_dfa().minimised()
    return fa.DFA({q + 1 for q in d.states}, d.alphabet, {(p + 1, a): q + 1 for (p, a), q in d.delta.items()},
                  d.start + 1, {q + 1 for q in d.finals})


def gen_fa(rng: random.Random, marks: int = 4) -> dict:
    lang = rng.choice([l for l in bank.LANGUAGES if l.regular])
    return question("finite_automata", "fa", "", [
        part("", f"Draw a Finite Automaton (deterministic) that recognises {lang.description}.", marks,
             "One possibility (the minimum FA):" + code(dfa_table(_named_min(lang.regex))),
             [{"criterion": "Accepts exactly the language", "marks": marks - 1}, {"criterion": "Deterministic and complete", "marks": 1}],
             {"kind": "language", "reference_regex": lang.regex, "alphabet": list(lang.alphabet), "answer": "automaton",
              "deterministic": True}, "fa", FA_FORMAT)])


def gen_cfg(rng: random.Random, marks: int = 3) -> dict:
    lang = rng.choice([l for l in bank.LANGUAGES if l.context_free and not l.regular])
    return question("cfg", "cfg", "", [
        part("", f"Give a Context-Free Grammar for {lang_phrase(lang)}.", marks, lang.cfg,
             [{"criterion": "Generates every string in the language", "marks": (marks + 1) // 2},
              {"criterion": "Generates no strings outside the language", "marks": marks // 2}],
             {"kind": "cfg", "language": lang.key, "alphabet": list(lang.alphabet), "max_len": 8}, "cfg", CFG_FORMAT)])


DERIVATION_GRAMMARS = [
    "S → aBa\nB → BB | Q | R\nQ → q\nR → r",
    "S → AB\nA → aA | a\nB → bB | c",
    "S → aSb | T\nT → cT | ε",
    "S → XY\nX → aXb | ε\nY → cY | c",
    "S → 0S1 | 0A\nA → 1A | 1",
]


def leftmost_derivation(g: cfgmod.CFG, target: str, limit: int = 200_000) -> list[str] | None:
    start = (g.start,)
    prev = {start: None}
    queue = deque([start])
    while queue and len(prev) < limit:
        form = queue.popleft()
        if all(s not in g.rules for s in form):
            if "".join(form) == target:
                out, f = [], form
                while f is not None:
                    out.append("".join(f))
                    f = prev[f]
                return out[::-1]
            continue
        i = next(j for j, s in enumerate(form) if s in g.rules)
        if "".join(form[:i]) != target[:i] or sum(s not in g.rules for s in form) > len(target):
            continue
        for rhs in g.rules[form[i]]:
            nf = form[:i] + rhs + form[i + 1:]
            if nf not in prev:
                prev[nf] = form
                queue.append(nf)
    return None


def _parse_tree(g: cfgmod.CFG, steps: list[str]) -> str:
    """Rebuild an indented parse tree from a leftmost derivation."""
    tree = [g.start, []]
    frontier = [tree]  # non-terminal leaves, left to right
    for a, b in zip(steps, steps[1:]):
        node = frontier.pop(0)
        toks_a = cfgmod._tokenise_rhs(a)
        i = next(j for j, s in enumerate(toks_a) if s in g.rules)
        toks_b = cfgmod._tokenise_rhs(b)
        rhs = toks_b[i: len(toks_b) - (len(toks_a) - i - 1)]
        kids = [[s, []] for s in rhs] or [["ε", []]]
        node[1].extend(kids)
        frontier = [k for k in kids if k[0] in g.rules] + frontier
    lines = []

    def walk(n, d):
        lines.append("  " * d + n[0])
        for c in n[1]:
            walk(c, d + 1)
    walk(tree, 0)
    return "\n".join(lines)


def gen_derivation(rng: random.Random, marks: int = 5) -> dict:
    gtext = rng.choice(DERIVATION_GRAMMARS)
    g = cfgmod.parse_cfg(gtext)
    alphabet = sorted(g.terminals)
    candidates = [w for n in range(4, 7) for w in ("".join(t) for t in product(alphabet, repeat=n)) if g.accepts(w)]
    w = rng.choice(candidates)
    steps = leftmost_derivation(g, w)
    m1, m2 = split_marks(marks, 2)
    numbered = "\n".join(f"{l}    ({i + 1})" for i, l in enumerate(
        f"{lhs} → {''.join(r) or 'ε'}" for lhs, rs in g.rules.items() for r in rs))
    return question("cfg", "derivation",
                    "Consider the following Context-Free Grammar." + code(numbered), [
                        part("a", f"Give a derivation of the string {w}.", m1, code("\n⇒ ".join(steps)),
                             [{"criterion": "Each step applies one production correctly", "marks": m1 - 1},
                              {"criterion": "Ends with the target string", "marks": 1}],
                             {"kind": "derivation", "grammar": gtext, "target": w}, "derivation",
                             "Answer format for automatic marking: one sentential form per line, starting with S."),
                        part("b", f"Give a parse tree for {w}.", m2, "Indented parse tree (children below parents):" +
                             code(_parse_tree(g, steps)), [{"criterion": "Correct parse tree", "marks": m2}], None,
                             "derivation")])


def gen_tm(rng: random.Random, marks: int = 6) -> dict:
    f = rng.choice(bank.TM_FUNCTIONS)
    text = (f"Draw a Turing machine that {f.description}. The input is a string over {{{','.join(f.alphabet)}}}, "
            f"starting in the leftmost cell with the head on it. For example, on input {f.example} the output is "
            f"{f.fn(f.example) or 'empty'}.")
    return question("turing_machines", "tm", text, [
        part("", "", marks, "One possible machine:" + code(f.tm.strip()),
             [{"criterion": "Produces the correct output on all inputs", "marks": marks - 1},
              {"criterion": "Halts properly (does not crash or loop)", "marks": 1}],
             {"kind": "tm_function", "function": f.key, "alphabet": list(f.alphabet), "max_len": 6}, "tm", TM_FORMAT)])


def gen_decidability(rng: random.Random, marks: int = 4) -> dict:
    probs = rng.sample(bank.DECISION_PROBLEMS, marks)
    rows = "\n\n".join(f"**({chr(97 + i)})** " + p.replace("\n", "  \n") for i, (p, _) in enumerate(probs))
    return question("decidability", "mcq",
                    "For each of the following decision problems, indicate whether it is Decidable or Undecidable.\n\n" + rows,
                    [part(chr(97 + i), "", 1, ans, [{"criterion": "Correct classification", "marks": 1}],
                          {"kind": "choice", "answer": ans, "options": ["Decidable", "Undecidable"]}, "mcq")
                     for i, (_, ans) in enumerate(probs)])


def gen_language_classes(rng: random.Random, marks: int = 10) -> dict:
    """The past papers' Venn-diagram question, asked as 'smallest class' since we cannot draw the diagram."""
    items = [(f"{lang_phrase(l)[0].upper()}{lang_phrase(l)[1:]}",
              "Regular" if l.regular else "Context-Free" if l.context_free else "P") for l in bank.LANGUAGES]
    items += bank.CLASS_ITEMS
    chosen = rng.sample(items, min(marks, len(items)))
    rows = "\n".join(f"**({chr(97 + i)})** {d}  " for i, (d, _) in enumerate(chosen))
    text = ("Consider the classes of languages Finite ⊂ Regular ⊂ Context-Free ⊂ P ⊆ NP ⊂ Decidable ⊂ "
            "Recursively Enumerable (r.e.). For each language below, state the **smallest** of these classes "
            "that it is known to belong to, or **None** if it is not r.e. (Assume P ≠ NP.)\n\n" + rows)
    return question("language_classes", "language_classes", text,
                    [part(chr(97 + i), "", 1, ans, [{"criterion": "Correct class", "marks": 1}],
                          {"kind": "choice", "answer": ans, "options": bank.CLASSES}, "mcq")
                     for i, (_, ans) in enumerate(chosen)])


def gen_pumping(rng: random.Random, marks: int = 6) -> dict:
    """Question text only; the LLM writes the proof (see generate.solve_with_llm)."""
    lang = rng.choice([l for l in bank.LANGUAGES if l.context_free and not l.regular])
    q = question("pumping_lemma_regular", "proof", "", [
        part("", f"Use the Pumping Lemma to prove that {lang_phrase(lang)} is not regular.", marks, None,
             None, None, "proof")])
    q["needs_solution"] = True
    return q


def gen_pumping_cfl(rng: random.Random, marks: int = 6) -> dict:
    lang = rng.choice([l for l in bank.LANGUAGES if not l.context_free])
    q = question("pumping_lemma_cfl", "proof", "", [
        part("", f"Use the Pumping Lemma for Context-Free Languages to prove that {lang_phrase(lang)} "
                 f"is not context-free.", marks, None, None, None, "proof")])
    q["needs_solution"] = True
    return q


# answer_type / topic -> generator. Looked up by answer type first, then topic.
BY_ANSWER_TYPE = {
    "string_list": gen_string_list, "fa_table": gen_nfa_to_dfa, "fa_minimise": gen_minimise,
    "prop_formula": gen_prop_cnf, "regex": gen_regex, "fa": gen_fa, "cfg": gen_cfg, "derivation": gen_derivation,
    "tm": gen_tm, "mcq": gen_decidability, "language_classes": gen_language_classes,
}
BY_TOPIC = {
    "minimisation": gen_minimise, "kleenes_theorem": gen_nfa_to_dfa, "pumping_lemma_regular": gen_pumping,
    "pumping_lemma_cfl": gen_pumping_cfl, "propositional_logic": gen_prop_cnf,
    "language_classes": gen_language_classes,
}
# Topics a generator legitimately covers, so a slot is only filled procedurally if topics agree.
GEN_TOPICS = {
    gen_string_list: {"regular_expressions", "nfa"}, gen_nfa_to_dfa: {"kleenes_theorem", "nfa", "finite_automata"},
    gen_minimise: {"minimisation", "finite_automata"}, gen_prop_cnf: {"propositional_logic"},
    gen_regex: {"regular_expressions", "finite_automata"}, gen_fa: {"finite_automata", "regular_expressions"},
    gen_cfg: {"cfg"}, gen_derivation: {"cfg"}, gen_tm: {"turing_machines"},
    gen_decidability: {"decidability", "turing_machines", "language_classes"},
    gen_language_classes: {"decidability", "turing_machines", "language_classes", "np_completeness"},
    gen_pumping: {"pumping_lemma_regular"}, gen_pumping_cfl: {"pumping_lemma_cfl"},
}


def generator_for(topic: str | None, answer_type: str | None):
    g = BY_ANSWER_TYPE.get(answer_type)
    if g and topic in GEN_TOPICS[g]:
        return g
    return BY_TOPIC.get(topic)
