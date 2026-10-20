"""Propositional logic: parsing, truth tables, equivalence and normal-form checks.

Operators (any spelling):  ¬ ~ ! not   ∧ & and /\\   ∨ | or \\/   ⇒ → -> implies   ⇔ ↔ <-> iff
Precedence (high to low): ¬, ∧, ∨, ⇒ (right-assoc), ⇔. Constants: T/True/1, F/False/0.
"""
from __future__ import annotations

import re
from itertools import product

TOKEN = re.compile(r"\s*(<->|<=>|->|=>|/\\|\\/|[¬~!∧&∨|⇒→⇔↔()]|[A-Za-z_][A-Za-z0-9_]*|[01])")
OPS = {
    "¬": "not", "~": "not", "!": "not", "not": "not",
    "∧": "and", "&": "and", "/\\": "and", "and": "and",
    "∨": "or", "|": "or", "\\/": "or", "or": "or",
    "⇒": "imp", "→": "imp", "->": "imp", "=>": "imp", "implies": "imp",
    "⇔": "iff", "↔": "iff", "<->": "iff", "<=>": "iff", "iff": "iff",
}
CONSTS = {"T": True, "True": True, "true": True, "F": False, "False": False, "false": False, "1": True, "0": False}


def tokenize(s: str) -> list[str]:
    out, i = [], 0
    while i < len(s):
        m = TOKEN.match(s, i)
        if not m:
            if s[i:].strip() == "":
                break
            raise ValueError(f"unexpected character {s[i]!r} in formula")
        tok = m.group(1)
        out.append(OPS.get(tok, tok))
        i = m.end()
    return out


class _P:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, x=None):
        tok = self.peek()
        if x is not None and tok != x:
            raise ValueError(f"expected {x!r}, got {tok!r}")
        self.i += 1
        return tok

    def iff(self):
        n = self.imp()
        while self.peek() == "iff":
            self.eat()
            n = ("iff", n, self.imp())
        return n

    def imp(self):
        n = self.disj()
        if self.peek() == "imp":
            self.eat()
            return ("imp", n, self.imp())
        return n

    def disj(self):
        n = self.conj()
        while self.peek() == "or":
            self.eat()
            n = ("or", n, self.conj())
        return n

    def conj(self):
        n = self.neg()
        while self.peek() == "and":
            self.eat()
            n = ("and", n, self.neg())
        return n

    def neg(self):
        if self.peek() == "not":
            self.eat()
            return ("not", self.neg())
        return self.atom()

    def atom(self):
        tok = self.eat()
        if tok == "(":
            n = self.iff()
            self.eat(")")
            return n
        if tok is None or tok in {"and", "or", "imp", "iff", ")"}:
            raise ValueError(f"unexpected {tok!r}")
        if tok in CONSTS:
            return ("const", CONSTS[tok])
        return ("var", tok)


def parse(s: str):
    p = _P(tokenize(s))
    n = p.iff()
    if p.peek() is not None:
        raise ValueError(f"unexpected {p.peek()!r}")
    return n


def variables(n) -> set[str]:
    if n[0] == "var":
        return {n[1]}
    if n[0] == "const":
        return set()
    return set().union(*(variables(c) for c in n[1:]))


def evaluate(n, env: dict[str, bool]) -> bool:
    k = n[0]
    if k == "var":
        return env[n[1]]
    if k == "const":
        return n[1]
    if k == "not":
        return not evaluate(n[1], env)
    a, b = evaluate(n[1], env), evaluate(n[2], env)
    return {"and": a and b, "or": a or b, "imp": (not a) or b, "iff": a == b}[k]


def truth_table(f, vars_: list[str] | None = None) -> list[tuple[dict, bool]]:
    n = parse(f) if isinstance(f, str) else f
    vs = sorted(vars_ or variables(n))
    return [(dict(zip(vs, vals)), evaluate(n, dict(zip(vs, vals)))) for vals in product([True, False], repeat=len(vs))]


def counterexample(f1: str, f2: str) -> dict | None:
    """An assignment where the formulas differ, or None if equivalent."""
    a, b = parse(f1), parse(f2)
    vs = sorted(variables(a) | variables(b))
    for vals in product([False, True], repeat=len(vs)):
        env = dict(zip(vs, vals))
        if evaluate(a, env) != evaluate(b, env):
            return env
    return None


def equivalent(f1: str, f2: str) -> bool:
    return counterexample(f1, f2) is None


def satisfiable(f: str) -> bool:
    return any(v for _, v in truth_table(f))


def tautology(f: str) -> bool:
    return all(v for _, v in truth_table(f))


def _is_literal(n) -> bool:
    return n[0] in {"var", "const"} or (n[0] == "not" and n[1][0] == "var")


def _flatten(n, op):
    return _flatten(n[1], op) + _flatten(n[2], op) if n[0] == op else [n]


def is_cnf(f: str) -> bool:
    n = parse(f)
    return all(all(_is_literal(l) for l in _flatten(c, "or")) for c in _flatten(n, "and"))


def is_dnf(f: str) -> bool:
    n = parse(f)
    return all(all(_is_literal(l) for l in _flatten(c, "and")) for c in _flatten(n, "or"))
