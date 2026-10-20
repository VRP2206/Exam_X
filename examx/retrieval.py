"""BM25 retrieval over the ingested corpus, used to pick few-shot exemplars."""
from __future__ import annotations

import math
import re
from collections import Counter

from .ingest import load_corpus

_TOKEN = re.compile(r"[a-z0-9]+|[^\sa-z0-9]", re.I)


def tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text) if len(t) > 1 or not t.isalnum()]


class Index:
    def __init__(self, corpus: list[dict] | None = None, k1: float = 1.5, b: float = 0.75):
        self.docs = corpus if corpus is not None else load_corpus()
        self.toks = [tokens(d["text"]) for d in self.docs]
        self.k1, self.b = k1, b
        self.avgdl = sum(map(len, self.toks)) / max(len(self.toks), 1)
        df = Counter(t for ts in self.toks for t in set(ts))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(ts) for ts in self.toks]

    def score(self, query: str, i: int) -> float:
        tf, dl = self.tf[i], len(self.toks[i])
        s = 0.0
        for t in set(tokens(query)):
            if t in tf:
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def search(self, query: str = "", topic: str | None = None, answer_type: str | None = None, k: int = 3,
               prefer_solutions: bool = True, exclude: set[str] | None = None) -> list[dict]:
        """Rank by BM25 plus bonuses for matching topic / answer type / having a worked solution."""
        scored = []
        for i, d in enumerate(self.docs):
            if exclude and d["id"] in exclude:
                continue
            s = self.score(query, i) if query else 0.0
            if topic and d["primary_topic"] == topic:
                s += 10
            elif topic and topic in d["topics"]:
                s += 4
            if answer_type and d["answer_type"] == answer_type:
                s += 3
            if prefer_solutions and d["solution"]:
                s += 2
            scored.append((s, i))
        scored.sort(reverse=True)
        return [self.docs[i] for s, i in scored[:k] if s > 0]
