"""Regular expressions in FIT2014 notation, compiled to NFAs (Thompson construction).

Syntax accepted:
    union        ∪  |        (also "+" between operands when plus_is_union=True)
    star         *  ∗  ^{∗} ^*
    one-or-more  +  (postfix, default)
    epsilon      ε  λ  eps
    empty set    ∅
    char class   [01]  [a-c]
    grouping     ( )
Whitespace is ignored. Any other character is a literal symbol (so "0.(0∪1)*1" works).
"""
from __future__ import annotations

import re
from itertools import count

from .fa import EPS, NFA

_ids = count()


class RegexError(ValueError):
    pass


def _normalise(s: str) -> str:
    s = s.replace("^{∗}", "*").replace("^{*}", "*").replace("^*", "*").replace("∗", "*")
    s = s.replace("^{+}", "+").replace("∪", "|").replace("λ", "ε")
    s = re.sub(r"\beps(ilon)?\b", "ε", s)
    return re.sub(r"\s+", "", s)


def _expand_class(body: str) -> list[str]:
    out, i = [], 0
    while i < len(body):
        if i + 2 < len(body) and body[i + 1] == "-":
            out += [chr(c) for c in range(ord(body[i]), ord(body[i + 2]) + 1)]
            i += 3
        else:
            out.append(body[i])
            i += 1
    return out


class _Parser:
    """Recursive descent:  union := concat ('|' concat)* ;  concat := postfix* ;  postfix := atom ('*'|'+')*"""

    def __init__(self, s: str, plus_is_union: bool):
        self.s, self.i, self.plus_union = s, 0, plus_is_union

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else None

    def parse(self):
        node = self.union()
        if self.peek() is not None:
            raise RegexError(f"unexpected {self.peek()!r} at position {self.i}")
        return node

    def union(self):
        alts = [self.concat()]
        while self.peek() == "|" or (self.plus_union and self.peek() == "+"):
            self.i += 1
            alts.append(self.concat())
        return alts[0] if len(alts) == 1 else ("union", alts)

    def concat(self):
        items = []
        while self.peek() is not None and self.peek() not in "|)" and not (self.plus_union and self.peek() == "+"):
            items.append(self.postfix())
        if not items:
            return ("eps",)
        return items[0] if len(items) == 1 else ("concat", items)

    def postfix(self):
        node = self.atom()
        while self.peek() in ("*", "+") and not (self.peek() == "+" and self.plus_union):
            op = self.s[self.i]
            self.i += 1
            node = ("star", node) if op == "*" else ("concat", [node, ("star", node)])
        return node

    def atom(self):
        c = self.peek()
        if c == "(":
            self.i += 1
            node = self.union()
            if self.peek() != ")":
                raise RegexError("missing ')'")
            self.i += 1
            return node
        if c == "[":
            j = self.s.find("]", self.i)
            if j < 0:
                raise RegexError("missing ']'")
            chars = _expand_class(self.s[self.i + 1:j])
            self.i = j + 1
            return ("union", [("sym", ch) for ch in chars])
        if c in ("*", "+", ")"):
            raise RegexError(f"unexpected {c!r} at position {self.i}")
        self.i += 1
        if c == "ε":
            return ("eps",)
        if c == "∅":
            return ("empty",)
        return ("sym", c)


def parse(s: str, plus_is_union: bool = False):
    return _Parser(_normalise(s), plus_is_union).parse()


def _build(node, delta, alphabet):
    """Return (start, final) of a Thompson fragment."""
    s, f = next(_ids), next(_ids)
    kind = node[0]

    def edge(p, a, q):
        delta.setdefault((p, a), set()).add(q)

    if kind == "sym":
        alphabet.add(node[1])
        edge(s, node[1], f)
    elif kind == "eps":
        edge(s, EPS, f)
    elif kind == "empty":
        pass
    elif kind == "union":
        for child in node[1]:
            cs, cf = _build(child, delta, alphabet)
            edge(s, EPS, cs)
            edge(cf, EPS, f)
    elif kind == "concat":
        prev = s
        for child in node[1]:
            cs, cf = _build(child, delta, alphabet)
            edge(prev, EPS, cs)
            prev = cf
        edge(prev, EPS, f)
    elif kind == "star":
        cs, cf = _build(node[1], delta, alphabet)
        edge(s, EPS, cs)
        edge(cf, EPS, cs)
        edge(s, EPS, f)
        edge(cf, EPS, f)
    return s, f


def to_nfa(regex: str, plus_is_union: bool = False) -> NFA:
    tree = parse(regex, plus_is_union)
    delta, alphabet = {}, set()
    s, f = _build(tree, delta, alphabet)
    states = {s, f} | {p for p, _ in delta} | {q for qs in delta.values() for q in qs}
    return NFA(states, alphabet, delta, {s}, {f})


def matches(regex: str, w: str) -> bool:
    return to_nfa(regex).accepts(w)
