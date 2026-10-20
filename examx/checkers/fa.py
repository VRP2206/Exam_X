"""Finite automata: NFA/DFA representation, parsing, subset construction,
minimisation and equivalence checking with counterexamples.

Accepted text formats (student answers or reference solutions):

1. Transition table, as used in FIT2014 papers::

       state  a        b
       Start  1        {2,3}
       Final  {2,3}    3
              3        ∅

   A row may be labelled Start, Final, or "Start Final"; cells may be a single
   state, a set "{2,3}", or ∅ / - for no transition.

2. Edge list::

       start: 1
       final: 3, 4
       1 a 2
       2 ε 3        (also eps / epsilon / λ / e)
       3 a,b 4
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from itertools import product

EPS = ""  # epsilon label inside automata
EPS_WORDS = {"ε", "eps", "epsilon", "λ", "lambda", "e", "Λ"}
EMPTY_WORDS = {"∅", "-", "—", "{}", "Ø", "ø", "empty"}


@dataclass
class NFA:
    states: set
    alphabet: set[str]
    delta: dict[tuple, set]  # (state, symbol or EPS) -> set of states
    start: set
    finals: set

    def eps_closure(self, S) -> frozenset:
        stack, seen = list(S), set(S)
        while stack:
            q = stack.pop()
            for r in self.delta.get((q, EPS), ()):
                if r not in seen:
                    seen.add(r)
                    stack.append(r)
        return frozenset(seen)

    def step(self, S, a) -> frozenset:
        out = set()
        for q in S:
            out |= self.delta.get((q, a), set())
        return self.eps_closure(out)

    def accepts(self, w: str) -> bool:
        S = self.eps_closure(self.start)
        for a in w:
            S = self.step(S, a)
            if not S:
                return False
        return bool(S & self.finals)

    def to_dfa(self, alphabet: set[str] | None = None) -> "DFA":
        """Subset construction. The empty set becomes an explicit dead state."""
        sigma = sorted(alphabet or self.alphabet)
        s0 = self.eps_closure(self.start)
        trans, seen, queue = {}, {s0}, deque([s0])
        while queue:
            S = queue.popleft()
            for a in sigma:
                T = self.step(S, a)
                trans[(S, a)] = T
                if T not in seen:
                    seen.add(T)
                    queue.append(T)
        return DFA(seen, set(sigma), trans, s0, {S for S in seen if S & self.finals})


@dataclass
class DFA:
    states: set
    alphabet: set[str]
    delta: dict[tuple, object]  # total: (state, symbol) -> state
    start: object
    finals: set = field(default_factory=set)

    def accepts(self, w: str) -> bool:
        q = self.start
        for a in w:
            if (q, a) not in self.delta:
                return False
            q = self.delta[(q, a)]
        return q in self.finals

    def completed(self, alphabet: set[str] | None = None) -> "DFA":
        sigma = set(alphabet or self.alphabet) | self.alphabet
        dead = ("__dead__",)
        delta = dict(self.delta)
        states = set(self.states)
        need_dead = False
        for q, a in product(list(states), sigma):
            if (q, a) not in delta:
                delta[(q, a)] = dead
                need_dead = True
        if need_dead:
            states.add(dead)
            for a in sigma:
                delta[(dead, a)] = dead
        return DFA(states, sigma, delta, self.start, set(self.finals))

    def reachable(self) -> "DFA":
        seen, queue = {self.start}, deque([self.start])
        while queue:
            q = queue.popleft()
            for a in self.alphabet:
                r = self.delta.get((q, a))
                if r is not None and r not in seen:
                    seen.add(r)
                    queue.append(r)
        return DFA(seen, set(self.alphabet), {k: v for k, v in self.delta.items() if k[0] in seen}, self.start, self.finals & seen)

    def minimised(self) -> "DFA":
        """Moore partition refinement on the reachable, completed DFA. States are renamed 0..n-1 (start = 0)."""
        d = self.completed().reachable()
        sigma = sorted(d.alphabet)
        block = {q: int(q in d.finals) for q in d.states}
        while True:
            sig = {q: (block[q],) + tuple(block[d.delta[(q, a)]] for a in sigma) for q in d.states}
            ids: dict[tuple, int] = {}
            new = {q: ids.setdefault(sig[q], len(ids)) for q in sorted(d.states, key=repr)}
            if len(ids) == len(set(block.values())):
                break
            block = new
        # Renumber in BFS order from the start state for a canonical form.
        order, queue = {block[d.start]: 0}, deque([d.start])
        reps = {}
        for q in d.states:
            reps.setdefault(block[q], q)
        while queue:
            q = queue.popleft()
            for a in sigma:
                b = block[d.delta[(q, a)]]
                if b not in order:
                    order[b] = len(order)
                    queue.append(reps[b])
        delta = {(order[block[q]], a): order[block[d.delta[(q, a)]]] for q in d.states for a in sigma}
        return DFA(set(order.values()), set(sigma), delta, 0, {order[block[q]] for q in d.finals})

    @property
    def num_states(self) -> int:
        return len(self.states)


def as_dfa(m, alphabet: set[str] | None = None) -> DFA:
    if isinstance(m, NFA):
        return m.to_dfa(alphabet)
    return m.completed(alphabet)


def counterexample(m1, m2, alphabet: set[str] | None = None) -> str | None:
    """Shortest string accepted by exactly one machine, or None if they are equivalent."""
    sigma = set(alphabet or set()) | m1.alphabet | m2.alphabet
    d1, d2 = as_dfa(m1, sigma).completed(sigma), as_dfa(m2, sigma).completed(sigma)
    start = (d1.start, d2.start)
    seen, queue = {start: ""}, deque([start])
    while queue:
        p, q = queue.popleft()
        w = seen[(p, q)]
        if (p in d1.finals) != (q in d2.finals):
            return w
        for a in sorted(sigma):
            nxt = (d1.delta[(p, a)], d2.delta[(q, a)])
            if nxt not in seen:
                seen[nxt] = w + a
                queue.append(nxt)
    return None


def equivalent(m1, m2, alphabet=None) -> bool:
    return counterexample(m1, m2, alphabet) is None


def language_upto(m, alphabet: set[str], n: int) -> set[str]:
    sigma = sorted(alphabet)
    return {"".join(w) for k in range(n + 1) for w in product(sigma, repeat=k) if m.accepts("".join(w))}


# ---------------------------------------------------------------- parsing

def _cell_states(cell: str) -> set[str]:
    cell = cell.strip()
    if cell in EMPTY_WORDS:
        return set()
    cell = cell.strip("{}")
    return {s.strip() for s in re.split(r"[,\s]+", cell) if s.strip()}


def _split_row(line: str) -> list[str]:
    # Split on whitespace but keep {..} groups together.
    return re.findall(r"\{[^}]*\}|[^\s]+", line)


def parse_table(text: str) -> NFA:
    lines = [l for l in (x.strip() for x in text.strip().splitlines()) if l]
    header = _split_row(lines[0])
    if header[0].lower() != "state":
        raise ValueError("table must start with a header row like: state a b")
    symbols = header[1:]
    delta: dict[tuple, set] = {}
    start, finals, states = set(), set(), set()
    dfa_style = _looks_like_dfa_table(lines)
    for line in lines[1:]:
        cells = _split_row(line)
        flags = set()
        while cells and cells[0].lower() in {"start", "final", "start,final", "accept", "->", "*"}:
            flags.add(cells.pop(0).lower())
        if len(cells) != len(symbols) + 1:
            raise ValueError(f"row has {len(cells)} cells, expected {len(symbols) + 1}: {line!r}")
        q = _state_name(cells[0])
        states.add(q)
        if flags & {"start", "start,final", "->"}:
            start.add(q)
        if flags & {"final", "start,final", "accept", "*"}:
            finals.add(q)
        for sym, cell in zip(symbols, cells[1:]):
            sym = EPS if sym in EPS_WORDS else sym
            if dfa_style:
                targets = {_state_name(cell)}  # "{2,3}" names one DFA state; ∅ is the dead state
            else:
                targets = {_state_name(t) for t in _cell_states(cell)}
            delta[(q, sym)] = targets
            states |= targets
    if not start:
        raise ValueError("no Start row in table")
    alphabet = {s if s not in EPS_WORDS else EPS for s in symbols} - {EPS}
    return NFA(states, alphabet, delta, start, finals)


def _looks_like_dfa_table(lines: list[str]) -> bool:
    """True if any row label is a set {..} or ∅: the table is a subset-construction DFA."""
    for line in lines[1:]:
        cells = _split_row(line)
        while cells and cells[0].lower() in {"start", "final"}:
            cells.pop(0)
        if cells and (cells[0].startswith("{") or cells[0] in EMPTY_WORDS):
            return True
    return False


def _state_name(s: str) -> str:
    s = s.strip()
    if s in EMPTY_WORDS:
        return "∅"
    if s.startswith("{"):
        inner = sorted(x for x in _cell_states(s))
        return "{" + ",".join(inner) + "}" if inner else "∅"
    return s


def parse_edges(text: str) -> NFA:
    start, finals, delta, states, alphabet = set(), set(), {}, set(), set()
    for raw in text.strip().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"(start|initial)\s*[:=]\s*(.+)", line, re.I)
        if m:
            start |= {s.strip() for s in re.split(r"[,\s]+", m.group(2)) if s.strip()}
            continue
        m = re.match(r"(finals?|accept(ing)?)\s*[:=]\s*(.*)", line, re.I)
        if m:
            finals |= {s.strip() for s in re.split(r"[,\s]+", m.group(3)) if s.strip()}
            continue
        m = re.match(r"(\S+)\s*(?:-+\s*)?(\S+?)\s*(?:-*>)?\s+(\S+)$", line)
        if not m:
            raise ValueError(f"cannot parse edge: {raw!r}")
        p, labels, q = m.groups()
        states |= {p, q}
        for a in labels.split(","):
            a = EPS if a in EPS_WORDS else a
            if a:
                alphabet.add(a)
            delta.setdefault((p, a), set()).add(q)
    states |= start | finals
    if not start:
        raise ValueError("no start state given (add a line like 'start: 1')")
    return NFA(states, alphabet, delta, start, finals)


def parse_automaton(text: str) -> NFA:
    first = next(l for l in text.strip().splitlines() if l.strip())
    return parse_table(text) if first.split()[0].lower() == "state" else parse_edges(text)
