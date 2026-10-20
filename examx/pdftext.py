"""Span-level PDF text extraction.

PyMuPDF's plain text output flattens LaTeX maths (a^m b^n becomes "ambn") and
loses the colour coding used in the solution PDFs (answers in blue, comments in
green/purple). This module rebuilds lines from individual spans so we keep both.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

BLACK = 0x000000
FOOTER_Y = 715  # anything below this on a US-letter page is page number / mark tally


@dataclass
class Span:
    text: str
    x0: float
    x1: float
    y: float  # baseline
    size: float
    color: int
    bold: bool


@dataclass
class Line:
    page: int
    y: float
    x0: float
    spans: list[Span] = field(default_factory=list)

    @property
    def colors(self) -> set[int]:
        return {s.color for s in self.spans if s.text.strip()}

    def text(self, keep=None) -> str:
        """Render the line, marking raised/lowered small spans as ^{..}/_{..}."""
        spans = [s for s in self.spans if keep is None or keep(s)]
        if not spans:
            return ""
        main = max(spans, key=lambda s: (s.size, len(s.text.strip())))
        base, size = main.y, main.size
        out: list[str] = []
        prev_x1 = None
        for s in sorted(spans, key=lambda s: s.x0):
            t = s.text
            if prev_x1 is not None and s.x0 - prev_x1 > 0.2 * size and not t.startswith(" "):
                if not (out and out[-1].endswith(" ")):
                    out.append(" ")
            if t.strip() and s.size < 0.85 * size:
                if s.y < base - 1.0:
                    t = "^{" + t.strip() + "}"
                elif s.y > base + 1.0:
                    t = "_{" + t.strip() + "}"
            out.append(t)
            prev_x1 = s.x1
        txt = "".join(out)
        # ^{a}^{b} -> ^{ab}
        txt = txt.replace("}^{", "").replace("}_{", "")
        return clean(txt).rstrip()


LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "̸": "", "\x00": ""}


def clean(t: str) -> str:
    for a, b in LIGATURES.items():
        t = t.replace(a, b)
    t = t.replace("y̸ =", "y ≠").replace("̸ =", " ≠")
    return t


def page_lines(page: pymupdf.Page, pno: int) -> list[Line]:
    spans: list[Span] = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if not s["text"].strip():
                    continue  # whitespace spans sit at odd baselines; gaps are re-derived from x positions
                x0, _, x1, _ = s["bbox"]
                spans.append(Span(s["text"], x0, x1, s["origin"][1], s["size"], s["color"], bool(s["flags"] & 16)))
    # Group full-size spans into rows by baseline; attach small (super/sub) spans afterwards.
    big = sorted([s for s in spans if s.size >= 9.5], key=lambda s: (s.y, s.x0))
    small = [s for s in spans if s.size < 9.5]
    rows: list[Line] = []
    for s in big:
        for r in rows:
            if abs(r.y - s.y) < 2.0:
                r.spans.append(s)
                break
        else:
            rows.append(Line(pno, s.y, s.x0, [s]))
    for s in small:
        best = min(rows, key=lambda r: abs(r.y - s.y), default=None)
        if best is not None and abs(best.y - s.y) < 8:
            best.spans.append(s)
        else:
            rows.append(Line(pno, s.y, s.x0, [s]))
    for r in rows:
        r.x0 = min(s.x0 for s in r.spans)
    rows.sort(key=lambda r: r.y)
    # Drop footers (page numbers, per-page mark tallies).
    return [r for r in rows if not (r.y > FOOTER_Y and r.text().strip().isdigit())]


def extract_lines(path: str) -> list[Line]:
    doc = pymupdf.open(path)
    out: list[Line] = []
    for pno, page in enumerate(doc):
        out.extend(page_lines(page, pno))
    return out
