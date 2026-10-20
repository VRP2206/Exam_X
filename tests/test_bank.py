"""The language bank's regexes, grammars and predicates must agree."""
from itertools import product

import pytest

from examx import bank
from examx.checkers import cfg, regex


def strings(alphabet, n):
    return ["".join(t) for k in range(n + 1) for t in product(alphabet, repeat=k)]


@pytest.mark.parametrize("lang", [l for l in bank.LANGUAGES if l.regex], ids=lambda l: l.key)
def test_regex_matches_predicate(lang):
    nfa = regex.to_nfa(lang.regex)
    for w in strings(lang.alphabet, 9):
        assert nfa.accepts(w) == lang.predicate(w), w


@pytest.mark.parametrize("lang", [l for l in bank.LANGUAGES if l.cfg], ids=lambda l: l.key)
def test_cfg_matches_predicate(lang):
    g = cfg.parse_cfg(lang.cfg)
    n = 7 if len(lang.alphabet) == 3 else 9
    assert cfg.compare(g, lang.predicate, set(lang.alphabet), n) == ([], [])


def test_flags_consistent():
    for l in bank.LANGUAGES:
        assert bool(l.regex) == l.regular, l.key
        assert bool(l.cfg) == l.context_free, l.key


def test_tm_function_examples():
    assert bank.TMF["twos_complement"].fn("0110100") == "1001100"
    assert bank.TMF["increment"].fn("111") == "1000"
    assert bank.TMF["increment"].fn("1011") == "1100"
    assert bank.TMF["erase_b"].fn("abbab") == "aa"
