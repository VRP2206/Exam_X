"""Context-free grammars: parsing, Earley membership, and bounded language comparison.

Grammar text format (one or more productions per line, "|" for alternatives)::

    S → aSb | X
    X -> aX | ε

Non-terminals are capital letters, optionally followed by digits or primes
(S, A1, B'), or names in angle brackets (<expr>). Everything else is a terminal
symbol, one character each. ε / eps / λ (or an empty right-hand side) is the
empty string. A trailing "(1)" rule number, as in the past papers, is ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product

ARROW = re.compile(r"\s*(?:→|->|::=|=>|⇒)\s*")
NONTERM = re.compile(r"<[^>]+>|[A-Z][0-9']*")


@dataclass
class CFG:
    start: str
    rules: dict[str, list[tuple[str, ...]]]  # A -> list of RHS symbol tuples

    @property
    def nonterminals(self) -> set[str]:
        return set(self.rules)

    @property
    def terminals(self) -> set[str]:
        return {s for rhss in self.rules.values() for rhs in rhss for s in rhs if s not in self.rules}

    def accepts(self, w: str) -> bool:
        return earley(self, w)

    def language_upto(self, alphabet: set[str], n: int) -> set[str]:
        return {"".join(t) for k in range(n + 1) for t in product(sorted(alphabet), repeat=k) if self.accepts("".join(t))}


def _tokenise_rhs(rhs: str) -> tuple[str, ...]:
    rhs = rhs.strip()
    if rhs in {"ε", "eps", "epsilon", "λ", "Λ", ""}:
        return ()
    out, i = [], 0
    while i < len(rhs):
        if rhs[i].isspace():
            i += 1
            continue
        m = NONTERM.match(rhs, i)
        if m:
            out.append(m.group(0))
            i = m.end()
        elif rhs[i] in "ελ":
            i += 1
        else:
            out.append(rhs[i])
            i += 1
    return tuple(out)


def parse_cfg(text: str) -> CFG:
    rules: dict[str, list[tuple[str, ...]]] = {}
    start = None
    for raw in text.strip().splitlines():
        line = re.sub(r"\(\d+\)\s*$", "", raw.split("#", 1)[0]).strip()
        if not line:
            continue
        parts = ARROW.split(line, maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"cannot parse production: {raw!r}")
        lhs, rhs = parts[0].strip(), parts[1]
        if not NONTERM.fullmatch(lhs):
            raise ValueError(f"left-hand side must be a non-terminal: {lhs!r}")
        start = start or lhs
        for alt in rhs.split("|"):
            rules.setdefault(lhs, []).append(_tokenise_rhs(alt))
    if start is None:
        raise ValueError("empty grammar")
    # Non-terminals used but never defined derive nothing.
    for rhss in list(rules.values()):
        for rhs in rhss:
            for s in rhs:
                if NONTERM.fullmatch(s) and s not in rules:
                    rules[s] = []
    return CFG(start, rules)


def _nullable(g: CFG) -> set[str]:
    null, changed = set(), True
    while changed:
        changed = False
        for a, rhss in g.rules.items():
            if a not in null and any(all(s in null for s in rhs) for rhs in rhss):
                null.add(a)
                changed = True
    return null


def earley(g: CFG, w: str) -> bool:
    """Earley recogniser with the Aycock–Horspool fix for nullable non-terminals."""
    nullable = _nullable(g)
    n = len(w)
    chart: list[set] = [set() for _ in range(n + 1)]
    root = ("γ", (g.start,), 0, 0)
    chart[0].add(root)
    for i in range(n + 1):
        agenda = list(chart[i])
        while agenda:
            item = agenda.pop()
            lhs, rhs, dot, origin = item
            if dot < len(rhs):
                sym = rhs[dot]
                if sym in g.rules:  # predict
                    for prod in g.rules[sym]:
                        new = (sym, prod, 0, i)
                        if new not in chart[i]:
                            chart[i].add(new)
                            agenda.append(new)
                    if sym in nullable:
                        new = (lhs, rhs, dot + 1, origin)
                        if new not in chart[i]:
                            chart[i].add(new)
                            agenda.append(new)
                elif i < n and w[i] == sym:  # scan
                    chart[i + 1].add((lhs, rhs, dot + 1, origin))
            else:  # complete
                for l2, r2, d2, o2 in list(chart[origin]):
                    if d2 < len(r2) and r2[d2] == lhs:
                        new = (l2, r2, d2 + 1, o2)
                        if new not in chart[i]:
                            chart[i].add(new)
                            agenda.append(new)
    return ("γ", (g.start,), 1, 0) in chart[n]


def compare(student: CFG, reference, alphabet: set[str], n: int = 8):
    """Compare a grammar against a reference (CFG, or a predicate str -> bool) on all strings up to length n.

    Returns (missing, extra): strings the reference has but the student lacks, and vice versa,
    each sorted shortest-first.
    """
    ref = reference.accepts if isinstance(reference, CFG) else reference
    missing, extra = [], []
    for k in range(n + 1):
        for t in product(sorted(alphabet), repeat=k):
            w = "".join(t)
            r, s = bool(ref(w)), student.accepts(w)
            if r and not s:
                missing.append(w)
            elif s and not r:
                extra.append(w)
    return missing, extra


def check_derivation(g: CFG, steps: list[str]) -> tuple[bool, str]:
    """Check a leftmost-or-any derivation: each step must follow from the previous by one rule application."""
    steps = [re.sub(r"\(\d+\)\s*$", "", s).replace(" ", "").replace("ε", "") for s in steps if s.strip()]
    if not steps:
        return False, "empty derivation"
    if steps[0] != g.start:
        return False, f"derivation must start from {g.start}"
    for a, b in zip(steps, steps[1:]):
        if not _one_step(g, a, b):
            return False, f"'{b}' does not follow from '{a}' by a single rule"
    if any(NONTERM.fullmatch(s) for s in _tokenise_rhs(steps[-1])):
        return False, "derivation ends with non-terminals remaining"
    return True, "ok"


def _one_step(g: CFG, a: str, b: str) -> bool:
    toks = list(_tokenise_rhs(a))
    for i, sym in enumerate(toks):
        if sym in g.rules:
            for rhs in g.rules[sym]:
                if "".join(toks[:i] + list(rhs) + toks[i + 1:]) == b:
                    return True
    return False
