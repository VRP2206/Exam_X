# ExamX — FIT2014 practice-paper generator and grader

A free, locally-run system that

1. **generates new FIT2014 Theory of Computation practice papers** with full worked solutions and marking
   rubrics, in the style and topic mix of the past papers, and
2. **grades a student's attempt**, giving marks per question and feedback.

There are only five past papers (two with solutions), far too few to train a model. ExamX instead combines:

- **exact, code-based generation and marking** for everything that can be computed: regular expressions,
  finite automata (subset construction, minimisation, equivalence), context-free grammars, derivations,
  Turing machines, CNF formulas and decidability classifications;
- a **local open LLM (via Ollama)**, prompted with past questions retrieved from the parsed papers, for
  proofs and explanations (pumping lemmas, undecidability, NP-completeness, induction, ...).

## Setup

Requirements: Python ≥ 3.10 and [Ollama](https://ollama.com) (both free). Everything else installs into a
virtual environment inside the repo (`.venv/`, git-ignored).

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
ollama pull qwen3:8b            # default model
ollama pull qwen3:4b-instruct   # optional faster model
```

Activate with `source .venv/bin/activate`, or call `.venv/bin/examx` directly.
`data/` is committed, so you only need to re-run ingestion if you add papers.

## Usage

```bash
examx ingest                      # parse papers/ + solution/ PDFs into data/
examx stats                       # topic / answer-type mix of the past papers
examx generate --seed 42          # new paper + solutions in output/ (.md, .pdf, .json)
examx generate --no-llm           # procedural-only paper in about a second (no Ollama needed)
examx generate --model qwen3:4b-instruct   # faster, lower-quality LLM
examx grade output/practice-42.json my-attempt.md     # marks + feedback -> my-attempt.report.md/.json
examx grade exam-2013 my-attempt.md                   # grade an attempt at a past paper
examx check regex '(a∪b)*ab' '(a∪b)*a(a∪b)'           # quick exact comparison
examx bench                       # time the installed Ollama models
examx serve                       # web UI at http://127.0.0.1:8014
```

Set `EXAMX_MODEL` to change the default model, and `OLLAMA_HOST` if Ollama is not on `localhost:11434`.

### Writing an attempt

An attempt is a Markdown file with one `## Q<n>` heading per question and `### (a)` (or a line beginning
`(a)`) per part. Put machine-checkable answers in a fenced code block, using the answer format printed under
the question:

````markdown
## Q1
(A ∨ B ∨ C) ∧ (¬A ∨ ¬B) ∧ (¬A ∨ ¬C) ∧ (¬B ∨ ¬C)

## Q3
### (a)
ε, aba, baa, abaaba
### (b)
```
start: 1
final: 1
1 a 2
2 b 3
3 a 1
```

## Q7
Suppose L is regular. Let N be the number of states of an FA recognising L ...
````

| Answer type | Format |
|---|---|
| regular expression | `∪` or `\|` for union, `*` star, `ε` empty string, `[01]` classes |
| FA / NFA | table (`state a b` header; rows prefixed `Start`/`Final`; `{2,3}` and `∅` cells) or edge list (`start: 1`, `final: 2 3`, `1 a 2`, `2 ε 3`) |
| CFG | `S → aSb \| ε` (also `->`); capitals are non-terminals |
| derivation | one sentential form per line, starting with `S` |
| Turing machine | `start: 1`, `halt: H`, then `state read -> next write move` (Δ = blank), or `1 a→b,R 2` |
| PDA | `start: 1`, `accept: 4`, then `1 a,ε->a 2` (read, pop → push) |
| propositional logic | `∧ ∨ ¬ ⇒ ⇔` or `& \| ~ -> <->` |

An answer that does not parse is not penalised for that: it is passed to the LLM marker with a note.

## How it works

```
papers/*.pdf, solution/*.pdf
        │  examx/pdftext.py   span-level PyMuPDF extraction (keeps a^{n} superscripts and solution colours)
        ▼
examx/ingest.py ──► data/corpus.json, data/papers/*.json, data/figures/*.png, data/stats.json
        │  questions, parts, marks (incl. "4 + 6 + 7 = 17" part marks), topics, answer types, official
        │  solutions (blue text) and marker comments (green/purple text), rendered diagrams
        ▼
examx/generate.py
  blueprint: a random past paper as template (topic order, 120 marks), ~35% of slots swapped for
             same-mark questions at a similar position in other papers
  each slot: procedural generator (examx/procedural.py) when one exists for the topic/answer type,
             otherwise the LLM writes a new question + solution + rubric from retrieved exemplars
             (examx/retrieval.py, BM25)
        ▼
output/practice-<seed>.{md,pdf,json}  + -solutions.{md,pdf}
        ▼
examx/grade.py
  exact checks (examx/checkers/): string lists, regex/FA equivalence via product construction
  (shortest counterexample in the feedback), determinism and minimality, CFG vs reference language
  (Earley parser on all strings up to length 8), derivations, TM simulation on all inputs up to length 6,
  CNF truth tables, multiple choice.  Proofs/explanations: LLM marks against model solution + rubric.
```

### Ingestion

`examx ingest` extracts all five papers. Every paper's question marks sum to exactly 120, which is checked
in the tests. Topics are tagged with weighted regexes (`examx/topics.py`) into 20 topics, from propositional
logic through to NP-completeness. Each question and part also gets an *answer type* (regex, fa_table,
fa_minimise, cfg, derivation, tm, proof, mcq, ...), which drives generation and grading. Diagrams cannot be
turned into text reliably, so they are rendered to PNG in `data/figures/` and linked from the JSON.

### Procedural questions

These are generated with computed, verified solutions: string listing for a random regex plus an NFA; NFA →
FA by subset construction; FA minimisation; regex / FA / CFG for a language from a hand-checked bank
(`examx/bank.py`, where each regex and grammar is tested against a Python predicate); derivations and parse
trees; Turing machines for a function, with a reference TM that is also tested; CNF for "exactly / at
least / at most k" scenarios; decidable/undecidable tables. Pumping-lemma questions are worded procedurally
and the LLM writes the proof.

### Model choice (GTX 1650 4 GB, 8 cores, 31 GB RAM)

Benchmark from `examx bench`, using the same 700-token prompt (write a pumping-lemma question and solution):

| model | speed | placement | quality |
|---|---|---|---|
| `qwen3:4b` | 20 tok/s | GPU | thinking variant: ignores `think: false`, and its proof was wrong |
| `qwen3:4b-instruct` | 20 tok/s | 77% GPU | readable, but chose a language that makes the proof fragile |
| **`qwen3:8b`** (default) | 8 tok/s | split GPU/RAM | correct, well-structured proof |

The default favours quality, because wrong model solutions are worse than slow ones. Use
`--model qwen3:4b-instruct` when speed matters.

## Tests

```bash
.venv/bin/pytest
```

The tests cover the checkers (largely using answers taken from the official past-paper solutions), the
consistency of the language bank and reference TMs, ingestion totals, and end-to-end procedural
generation and exact grading, where every model solution must score full marks. None of them need Ollama.

## Layout

```
examx/            package: pdftext, ingest, topics, retrieval, llm, bank, procedural, generate, render, grade, web, cli
examx/checkers/   fa.py, regex.py, cfg.py, tm.py (TM + PDA), logic.py
data/             ingested corpus (JSON), stats and figures
papers/ solution/ source PDFs
tests/            pytest suite
output/           generated papers and reports (git-ignored)
```
