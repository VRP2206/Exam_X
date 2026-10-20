"""Ingest past FIT2014 papers (and solutions) into structured JSON.

Output layout:
    data/corpus.json            every question from every paper
    data/papers/<paper>.json    one file per paper
    data/figures/*.png          rendered diagrams (question and solution)
    data/stats.json             topic / marks distributions used by the generator
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

from .pdftext import BLACK, Line, extract_lines
from .topics import answer_type, tag

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "papers"
SOLUTIONS_DIR = ROOT / "solution"
DATA_DIR = ROOT / "data"

Q_HEADER = re.compile(r"^Question\s+(\d+)\s*\((.+?)\s*marks?\)\s*$")
PART = re.compile(r"^\(([a-z])\)\s*(.*)$")
SKIP_LINE = re.compile(r"^(Working Space|END OF EXAMINATION|Official\s*use\s*only|Page \d+ of \d+|\d{1,2})$")


@dataclass
class Part:
    label: str
    text: str
    marks: float | None = None
    answer_type: str = "short_answer"
    solution: str = ""
    comments: str = ""


@dataclass
class Question:
    id: str
    paper: str
    year: int
    number: int
    marks: float
    text: str  # full question text, including all parts
    stem: str  # text before the first part
    parts: list[Part] = field(default_factory=list)
    solution: str = ""
    comments: str = ""
    topics: list[str] = field(default_factory=list)
    primary_topic: str | None = None
    answer_type: str = "short_answer"
    has_figure: bool = False
    figures: list[str] = field(default_factory=list)
    solution_figures: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


def paper_id(path: Path) -> str:
    return path.stem.replace("FIT2014-", "").replace("-soln", "").lower()


def paper_year(pid: str) -> int:
    return int(re.search(r"(20\d\d)", pid).group(1))


def parse_marks(s: str) -> tuple[float, list[float] | None]:
    """'7' -> (7, None);  '4 + 6 + 7 + 2 + 2 = 21' -> (21, [4, 6, 7, 2, 2])."""
    if "=" in s:
        lhs, rhs = s.split("=", 1)
        return float(rhs), [float(x) for x in lhs.split("+")]
    return float(s), None


def split_questions(lines: list[Line]) -> list[tuple[re.Match, list[Line]]]:
    """Group lines under their 'Question N (M marks)' header. Front matter is dropped."""
    out: list[tuple[re.Match, list[Line]]] = []
    for ln in lines:
        t = ln.text()
        m = Q_HEADER.match(t)
        if m:
            out.append((m, []))
        elif out and not SKIP_LINE.match(t):
            out[-1][1].append(ln)
    return out


def split_parts(texts: list[str], allow_parts: bool) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Split a question's lines into stem and (a), (b), ... parts.

    Only accept the next letter in sequence, so "(a) Derivation:" answer-space labels
    and option lists like "(a) It doubles" inside one part don't create bogus parts.
    """
    stem: list[str] = []
    parts: list[tuple[str, list[str]]] = []
    for t in texts:
        m = PART.match(t)
        expected = chr(ord("a") + len(parts))
        if allow_parts and m and m.group(1) == expected:
            parts.append((m.group(1), [m.group(2)] if m.group(2) else []))
        elif parts:
            parts[-1][1].append(t)
        else:
            stem.append(t)
    return stem, parts


def join(lines) -> str:
    lines = [re.sub(r"\s*Official\s*use\s*only\s*", " ", l).rstrip() for l in lines]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def render_figures(doc: pymupdf.Document, qlines: list[Line], tops: dict[int, float], bottoms: dict[int, float], dest: Path, stem: str) -> list[str]:
    """Render the band of each page belonging to a question if it contains vector drawings."""
    files = []
    for pno in sorted({ln.page for ln in qlines} | set(tops)):
        page = doc[pno]
        clip = pymupdf.Rect(40, tops.get(pno, 60) - 14, page.rect.width - 40, bottoms.get(pno, 715))
        drawings = [d for d in page.get_drawings() if d["rect"].intersects(clip) and d["rect"].height + d["rect"].width > 15]
        if len(drawings) < 3:
            continue
        name = f"{stem}_p{pno + 1}.png"
        page.get_pixmap(clip=clip, dpi=110).save(dest / name)
        files.append(name)
    return files


def question_bands(groups, all_lines: list[Line]) -> list[tuple[dict[int, float], dict[int, float]]]:
    """For each question, page -> top y (header) and page -> bottom y (next header or footer)."""
    headers = [(ln.page, ln.y) for ln in all_lines if Q_HEADER.match(ln.text())]
    bands = []
    for i, (pg, y) in enumerate(headers):
        nxt = headers[i + 1] if i + 1 < len(headers) else None
        bands.append(({pg: y}, {pg: nxt[1] - 10} if nxt and nxt[0] == pg else {}))
    return bands


def ingest_paper(path: Path, fig_dir: Path) -> list[Question]:
    pid = paper_id(path)
    lines = extract_lines(str(path))
    doc = pymupdf.open(path)
    groups = split_questions(lines)
    bands = question_bands(groups, lines)
    questions = []
    for (m, qlines), (tops, bottoms) in zip(groups, bands):
        num = int(m.group(1))
        marks, part_marks = parse_marks(m.group(2))
        texts = [ln.text() for ln in qlines]
        full = join(texts)
        is_mcq = bool(re.search(r"circl(e|ing) the appropriate|choose one of the answers", full, re.I))
        stem, parts = split_parts(texts, allow_parts=not is_mcq)
        qid = f"{pid}-q{num}"
        q = Question(
            id=qid, paper=pid, year=paper_year(pid), number=num, marks=marks, text=full, stem=join(stem),
            parts=[Part(label=l, text=join(t)) for l, t in parts],
            pages=sorted({ln.page + 1 for ln in qlines} | {p + 1 for p in tops}),
        )
        if part_marks and len(part_marks) == len(q.parts):
            for p, mk in zip(q.parts, part_marks):
                p.marks = mk
        q.figures = render_figures(doc, qlines, tops, bottoms, fig_dir, qid)
        q.has_figure = bool(q.figures)
        questions.append(q)
    return questions


def attach_solutions(questions: list[Question], soln_path: Path, fig_dir: Path) -> None:
    """Solutions PDFs reproduce the question in black; answers are blue, comments another colour."""
    lines = extract_lines(str(soln_path))
    doc = pymupdf.open(soln_path)
    groups = split_questions(lines)
    bands = question_bands(groups, lines)
    by_num = {q.number: q for q in questions}
    for (m, qlines), (tops, bottoms) in zip(groups, bands):
        q = by_num.get(int(m.group(1)))
        if q is None:
            continue
        labels = [p.label for p in q.parts]
        cur = None  # current part label
        ans: dict[str | None, list[str]] = defaultdict(list)
        com: dict[str | None, list[str]] = defaultdict(list)
        for ln in qlines:
            black = ln.text(keep=lambda s: s.color == BLACK)
            pm = PART.match(black)
            if pm and pm.group(1) in labels and labels.index(pm.group(1)) == (labels.index(cur) + 1 if cur else 0):
                cur = pm.group(1)
            blue = ln.text(keep=lambda s: s.color == 0x0000FF)
            other = ln.text(keep=lambda s: s.color not in (BLACK, 0x0000FF))
            if blue:
                ans[cur].append(blue)
            if other:
                com[cur].append(other)
        q.solution = join(ans[None])
        q.comments = join(com[None])
        for p in q.parts:
            p.solution, p.comments = join(ans[p.label]), join(com[p.label])
        if q.parts and not q.solution:
            q.solution = join(f"({p.label}) {p.solution}" for p in q.parts if p.solution)
        q.solution_figures = render_figures(doc, qlines, tops, bottoms, fig_dir, q.id + "_soln")


def ingest_all(papers_dir: Path = PAPERS_DIR, solutions_dir: Path = SOLUTIONS_DIR, out_dir: Path = DATA_DIR) -> list[Question]:
    fig_dir = out_dir / "figures"
    (out_dir / "papers").mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    for old in fig_dir.glob("*.png"):
        old.unlink()
    solutions = {paper_id(p): p for p in solutions_dir.glob("*.pdf")}
    corpus: list[Question] = []
    for path in sorted(papers_dir.glob("*.pdf")):
        qs = ingest_paper(path, fig_dir)
        pid = paper_id(path)
        if pid in solutions:
            attach_solutions(qs, solutions[pid], fig_dir)
        for q in qs:
            q.topics, q.primary_topic = tag(q.text, q.solution)
            q.answer_type = answer_type(q.text)
            for p in q.parts:
                at = answer_type(p.text)
                p.answer_type = q.answer_type if at == "short_answer" else at
        paper = {
            "paper": pid, "year": paper_year(pid), "source": str(path.relative_to(ROOT)),
            "has_solutions": pid in solutions, "total_marks": sum(q.marks for q in qs),
            "questions": [asdict(q) for q in qs],
        }
        (out_dir / "papers" / f"{pid}.json").write_text(json.dumps(paper, indent=1, ensure_ascii=False))
        corpus.extend(qs)
    (out_dir / "corpus.json").write_text(json.dumps([asdict(q) for q in corpus], indent=1, ensure_ascii=False))
    (out_dir / "stats.json").write_text(json.dumps(compute_stats(corpus), indent=1))
    return corpus


def compute_stats(corpus: list[Question]) -> dict:
    by_paper = defaultdict(list)
    for q in corpus:
        by_paper[q.paper].append(q)
    topic_marks = Counter()
    topic_count = Counter()
    for q in corpus:
        if q.primary_topic:
            topic_marks[q.primary_topic] += q.marks
            topic_count[q.primary_topic] += 1
    n = len(by_paper)
    return {
        "papers": {p: {"questions": len(qs), "total_marks": sum(q.marks for q in qs)} for p, qs in by_paper.items()},
        "mean_questions_per_paper": sum(len(v) for v in by_paper.values()) / n,
        "marks_histogram": dict(sorted(Counter(q.marks for q in corpus).items())),
        "topic_question_count": dict(topic_count.most_common()),
        "topic_marks_share": {t: round(m / sum(topic_marks.values()), 4) for t, m in topic_marks.most_common()},
        "answer_types": dict(Counter(q.answer_type for q in corpus).most_common()),
        # Order in which topics appear within a paper (mean position 0..1) so generated papers follow the syllabus.
        "topic_position": {
            t: round(sum(q.number / len(by_paper[q.paper]) for q in corpus if q.primary_topic == t) / c, 3)
            for t, c in topic_count.items()
        },
    }


def load_corpus(path: Path = DATA_DIR / "corpus.json") -> list[dict]:
    return json.loads(path.read_text())
