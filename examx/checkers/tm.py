"""Turing machine and pushdown automaton simulators.

TM text format (one transition per line; FIT2014 edge labels are "read→write,move")::

    start: 1
    accept: ACCEPT          (optional; also "halt:")
    1 a -> 1 b R            current read -> next write move
    1 Δ -> 2 Δ L            Δ, _, B or blank = blank
    1 --a→b,R--> 2          (alternative: label in FIT2014 style)

A machine halts when no transition applies. Moves are L, R or S (stay).
Moving left off cell 0 crashes (FIT2014 convention) unless allow_left_crash=False,
in which case the head stays put.

PDA format (FIT2014 labels "read, pop → push")::

    start: 1
    accept: 4
    1 ε,ε->$ 2
    2 a,ε->a 2
    2 b,a->ε 3
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

BLANK = "Δ"
BLANK_WORDS = {"Δ", "∆", "_", "B", "blank", "□", "#"}
EPS_WORDS = {"ε", "eps", "λ", "e", ""}


def _blank(s: str) -> str:
    return BLANK if s in BLANK_WORDS else s


@dataclass
class TM:
    start: str
    delta: dict[tuple[str, str], tuple[str, str, str]]  # (state, read) -> (next, write, move)
    accept: set[str] = field(default_factory=set)
    reject: set[str] = field(default_factory=set)


@dataclass
class TMResult:
    halted: bool
    accepted: bool
    crashed: bool
    state: str
    tape: str  # tape contents with trailing blanks removed
    steps: int


def parse_tm(text: str) -> TM:
    start, accept, reject, delta = None, set(), set(), {}
    for raw in text.strip().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"(start|initial)\s*[:=]\s*(\S+)", line, re.I)
        if m:
            start = m.group(2)
            continue
        m = re.match(r"(accept|halt|final)\w*\s*[:=]\s*(.+)", line, re.I)
        if m:
            accept |= set(re.split(r"[,\s]+", m.group(2).strip()))
            continue
        m = re.match(r"reject\w*\s*[:=]\s*(.+)", line, re.I)
        if m:
            reject |= set(re.split(r"[,\s]+", m.group(1).strip()))
            continue
        norm = line.replace("→", "->")
        # FIT2014 style:  p --a->b,R--> q   or   p a->b,R q
        m = re.match(r"(\S+)\s+-*\s*(\S+?)\s*->\s*(\S+?)\s*,\s*([LRS])\s*-*>?\s+(\S+)$", norm)
        if m:
            p, a, b, mv, q = m.groups()
        else:
            m = re.match(r"(\S+)\s+(\S+)\s*->\s*(\S+)\s+(\S+)\s+([LRS])$", norm)
            if not m:
                raise ValueError(f"cannot parse TM transition: {raw!r}")
            p, a, q, b, mv = m.groups()
        a, b = _blank(a), _blank(b)
        if (p, a) in delta and delta[(p, a)] != (q, b, mv):
            raise ValueError(f"nondeterministic: two transitions from state {p} on {a}")
        delta[(p, a)] = (q, b, mv)
        start = start or p
    if start is None:
        raise ValueError("empty Turing machine")
    if not accept:
        accept = {s for s in {q for q, _, _ in delta.values()} if s.upper() in {"ACCEPT", "HALT", "YES"}}
    return TM(start, delta, accept, reject)


def run_tm(tm: TM, inp: str, max_steps: int = 10_000, allow_left_crash: bool = True) -> TMResult:
    tape = dict(enumerate(inp))
    pos, state, steps = 0, tm.start, 0
    while steps < max_steps:
        if state in tm.accept or state in tm.reject:
            break
        key = (state, tape.get(pos, BLANK))
        if key not in tm.delta:
            break
        state, write, move = tm.delta[key]
        tape[pos] = write
        steps += 1
        if move == "L":
            if pos == 0:
                if allow_left_crash:
                    return TMResult(True, False, True, state, _tape_str(tape), steps)
            else:
                pos -= 1
        elif move == "R":
            pos += 1
    halted = steps < max_steps
    return TMResult(halted, halted and state in tm.accept, False, state, _tape_str(tape), steps)


def _tape_str(tape: dict[int, str]) -> str:
    if not tape:
        return ""
    cells = [tape.get(i, BLANK) for i in range(max(tape) + 1)]
    return "".join(cells).rstrip(BLANK)


# ------------------------------------------------------------------ PDA

@dataclass
class PDA:
    start: str
    accept: set[str]
    edges: list[tuple[str, str, str, str, str]]  # (p, read, pop, push, q); "" = ε; push is a string, top first


def parse_pda(text: str) -> PDA:
    start, accept, edges = None, set(), []
    for raw in text.strip().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"(start|initial)\s*[:=]\s*(\S+)", line, re.I)
        if m:
            start = m.group(2)
            continue
        m = re.match(r"(accept|final)\w*\s*[:=]\s*(.+)", line, re.I)
        if m:
            accept |= set(re.split(r"[,\s]+", m.group(2).strip()))
            continue
        m = re.match(r"(\S+)\s+(\S*)\s*,\s*(\S*)\s*(?:->|→)\s*(\S*)\s+(\S+)$", line)
        if not m:
            raise ValueError(f"cannot parse PDA transition: {raw!r}")
        p, a, x, y, q = m.groups()
        clean = lambda s: "" if s in EPS_WORDS else s
        edges.append((p, clean(a), clean(x), clean(y), q))
        start = start or p
    if start is None:
        raise ValueError("empty PDA")
    return PDA(start, accept, edges)


def pda_accepts(pda: PDA, w: str, max_configs: int = 200_000, max_stack: int = 64) -> bool:
    """Nondeterministic BFS over configurations; accept by final state once input is consumed."""
    init = (pda.start, 0, "")
    seen, queue = {init}, deque([init])
    while queue and len(seen) < max_configs:
        state, i, stack = queue.popleft()
        if i == len(w) and state in pda.accept:
            return True
        for p, a, x, y, q in pda.edges:
            if p != state:
                continue
            if a and (i >= len(w) or w[i] != a):
                continue
            if x and not stack.startswith(x):
                continue
            ns = y + stack[len(x):]
            if len(ns) > max_stack:
                continue
            cfg = (q, i + (1 if a else 0), ns)
            if cfg not in seen:
                seen.add(cfg)
                queue.append(cfg)
    return False
