# ExamX — FIT2014 practice-paper generator and grader

A free system that runs locally (with an optional cloud AI model) and

1. **generates new FIT2014 Theory of Computation practice papers** with full worked solutions and marking
   rubrics, in the style and topic mix of the past papers, and
2. **grades a student's attempt**, giving marks per question and feedback.

There are only five past papers (two with solutions), far too few to train a model. ExamX instead combines:

- **exact, code-based generation and marking** for everything that can be computed: regular expressions,
  finite automata (subset construction, minimisation, equivalence), context-free grammars, derivations,
  Turing machines, CNF formulas and decidability classifications;
- **real past questions with their official solutions** for proof and explanation slots (undecidability,
  NP-completeness, induction, ...), placed by a blueprint that follows the past papers' topic mix;
- an **AI model** to write pumping-lemma proofs and to mark proofs and explanations against the model solution
  and rubric. It can be a local open model via Ollama (the default), **Google Gemini** or **Anthropic Claude**,
  switchable in the web UI or with `--model`. AI-invented questions are available but experimental: see
  "Known limitations".

## Setup

Requirements: Python ≥ 3.10, plus at least one AI back end: [Ollama](https://ollama.com) (free, local), a
Gemini API key (free tier) or an Anthropic API key (paid). Without any of them, `--no-llm` still generates and
exactly marks procedural papers. Everything else installs into a virtual environment inside the repo (`.venv/`,
git-ignored).

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
ollama pull qwen3:8b            # default model
ollama pull qwen3:14b           # proof marker (optional but recommended)
ollama pull qwen3:4b-instruct   # optional faster model
```

**Cloud API keys.** In the web UI, paste your key on the **AI model** page (see "Web UI"). For the CLI, put it in
your shell environment (never in a file in the repo; ExamX never writes keys anywhere):

```bash
export GEMINI_API_KEY=...       # free key from https://aistudio.google.com/apikey
export ANTHROPIC_API_KEY=...    # from https://console.anthropic.com
examx models                    # shows which back ends are ready
```

Activate with `source .venv/bin/activate`, or call `.venv/bin/examx` directly.
`data/` is committed, so you only need to re-run ingestion if you add papers.

## Usage

```bash
examx ingest                      # parse papers/ + solution/ PDFs into data/
examx stats                       # topic / answer-type mix of the past papers
examx generate --seed 42          # new paper + solutions in output/ (.md, .pdf, .json)
examx generate --prose llm        # EXPERIMENTAL: LLM writes new proof/explanation questions (see limitations)
examx generate --prose llm --review   # ... plus an LLM self-review pass
examx generate --no-llm           # procedural-only paper in about a second (no Ollama needed)
examx generate --model gemini --prose llm  # Gemini writes new proof/explanation questions
examx generate --model claude:claude-opus-5-5   # a specific cloud model
examx generate --model qwen3:4b-instruct   # faster, lower-quality local LLM
examx grade output/practice-42.json my-attempt.md     # marks + feedback -> my-attempt.report.md/.json
examx grade exam-2013 my-attempt.md                   # grade an attempt at a past paper
examx check regex '(a∪b)*ab' '(a∪b)*a(a∪b)'           # quick exact comparison
examx bench                       # time the installed Ollama models (or: examx bench gemini claude)
examx models                      # which AI back ends are ready
examx serve                       # web UI at http://127.0.0.1:8014
```

### Choosing the AI model

A model is named `provider:model`; a bare name is an Ollama model.

| spec | back end |
|---|---|
| `qwen3:8b` (default), `qwen3:14b`, ... | local Ollama |
| `gemini`, `gemini:gemini-3.8-flash` | Google Gemini (default `gemini-3.5-flash`; on a free key, `gemini-2.5-*` is no longer offered and Pro models have no quota) |
| `claude`, `claude:claude-opus-5-5` | Anthropic Claude (default `claude-sonnet-5-5`) |

Set `EXAMX_MODEL` to change the default, `EXAMX_GEMINI_MODEL` / `EXAMX_CLAUDE_MODEL` to change the provider
defaults, and `OLLAMA_HOST` if Ollama is not on `localhost:11434`. With a local model, proofs are marked by
`EXAMX_GRADER_MODEL` (default `qwen3:14b`); with a cloud model, the selected model marks them too. Short rate limits
(HTTP 429) and overloads (503) are retried with back-off. A quota that resets hours later fails at once, and
later calls to that model are skipped, so the run falls back to procedural questions instead of stalling.

**Gemini free tier in practice (tested October 2026):** `gemini-3.5-flash` allows only **20 requests per day**
per model. An AI-written paper needs about 15–25 requests, and marking an attempt needs one per proof or
explanation, so a free key gives roughly one paper or one marked attempt a day. Peak-time 503 "high demand"
errors were also common. `gemini-flash-lite-latest` has a separate quota, but it is a weaker model. A paid
Gemini or Claude key removes these limits. Note that a cloud model receives the question text and the student's answers, and
Google may use free-tier prompts to improve its products.

### Web UI

`examx serve` opens a front end at http://127.0.0.1:8014:

- **AI model** page: choose Local / Gemini / Claude and the model (installed or offered models are suggested),
  see whether each back end is ready (Ollama running, key set), and choose whether proof slots use real past
  questions or new AI-written ones. The choice is saved in `output/settings.json` (no keys).
- **API keys** (on the same page): paste a Claude or Gemini key. The server checks it once by listing the
  provider's models (no tokens used). It then keeps it **only in your browser**, as an `HttpOnly; Secure;
  SameSite=Strict` cookie that page scripts cannot read. The browser sends it with your requests, and it is used
  only inside your own generation and marking jobs; the server never writes or logs it. By default it is
  forgotten when the browser closes; tick "remember on this device" to keep it for 30 days. **Remove** deletes
  it. Each visitor uses their own key. A key in the server's environment, if any, is the fallback.
- **Papers**: generate a paper (with or without the AI), open it, view solutions and earlier reports.
- **Paper**: answer each part in the browser (drafts are kept in the browser as you type) and submit for
  marking; the report shows marks and feedback per part.

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
             otherwise a past question with an official solution (default), or with --prose llm the LLM
             writes a new question + solution + rubric from retrieved exemplars (examx/retrieval.py, BM25)
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

**Marking proofs uses `qwen3:14b` by default** (`ollama pull qwen3:14b`; override it with `EXAMX_GRADER_MODEL`.
If it isn't installed, marking falls back to the generation model). It runs about 76% on the CPU and takes
about 2 minutes per proof. On the sample attempt's correct-but-terse CFL pumping-lemma proof, qwen3:8b gave
1–3/7 and asserted a true step was false, while qwen3:14b gave 5/7 with accurate feedback. Both gave 0/7 to a
bogus proof that picks one fixed decomposition. Thinking mode made the 8B marker slower without making it
more accurate.

### Known limitations: honest results

A full LLM-mode paper (seed 42, qwen3:8b, before the quality controls) took 19 minutes. Its procedural
questions were all correct. Of its LLM-written questions, about half were poor: near-duplicate questions,
a "prove that ..." of a false statement, wrong decidability and multiple-choice answers, and a meaningless
graph in the NP question. In response:

- decidability tables and Venn/language-class questions are now procedural;
- near-duplicate drafts are rejected, and an optional self-review pass (`--review`) is available;
- every LLM-written question carries a "check before relying on it" note in the solutions.

A second run with those controls (39 minutes) was **not better**. The self-review "fixed" one correct
decidability answer into a wrong one. Several questions fixated on one grammar and claimed false properties
of it. Topics also drifted (the Church–Turing slot produced a CFG question). The local 8B model cannot be
trusted to invent exam content. So the **default is now `--prose past`**: slots with no procedural generator
are filled with **real past questions and their official solutions** (preferring questions that have
solutions and no diagram). The LLM is used only to write proofs for the procedurally worded pumping-lemma
questions, and those are flagged too. `--prose llm` remains available as an experiment.
`examples/practice-42*` was generated in the default mode.

LLM marks for proofs are advisory. The exact marks (automata, grammars, TMs, logic, choices) are reliable.

`examples/` contains a generated paper, a deliberately mixed `sample-attempt.md` and its
`sample-attempt.report.md` (26.5/120, about 3.5 minutes to mark).

## Deploying the website

The site at **https://exam-x.vrp2206.com** runs on this server as two Docker containers: the app, and a
Cloudflare Tunnel connector for it. No ports are opened:

```
browser ─► Cloudflare ─► tunnel ─► Caddy :80 ─► examx 127.0.0.1:8014
```

One-time setup:

1. In the Cloudflare dashboard, give the tunnel a public hostname `exam-x.vrp2206.com` → `HTTP` →
   `localhost:80` (Caddy; `localhost:8014` also works).
2. Put the tunnel token in a private file outside the repo (the prompt hides what you paste):
   ```bash
   umask 077; read -rs T && printf 'TUNNEL_TOKEN=%s\n' "$T" > ~/.examx-tunnel.env && unset T
   ```

```bash
docker compose -f deploy/compose.yaml up -d --build    # start app + tunnel, or rebuild after code changes
docker compose -f deploy/compose.yaml logs -f          # logs
docker compose -f deploy/compose.yaml up -d --force-recreate   # after editing ~/.examx.env
```

**The site is public.** Requests that come through Cloudflare carry a `Cf-Connecting-IP` header and are
treated as public visitors:

- **API keys:** visitors use only their own Claude/Gemini key, entered on the AI model page and kept in their
  browser (see "Web UI"). Server-side keys (`~/.examx.env`, optional) and **local Ollama models are for the owner
  only**, so visitors cannot spend the owner's quota or use the GPU. Without a key, visitors can still generate
  procedural papers and get exact marking.
- **Privacy:** each browser gets an anonymous id cookie. Visitors see only their own papers and reports in
  their list. A report (which contains the student's answers) opens only for its owner. A paper opens for
  anyone with its link, and a visitor cannot overwrite another visitor's paper by reusing its seed.
- **Model choice** is per browser (a cookie) for visitors. The owner's choice is the site default.
- **Limits:** 20 jobs per visitor IP per day, one running job per IP, 300 public jobs per day in total, and 2
  jobs at a time on the server (`EXAMX_PUBLIC_DAILY_JOBS`, `EXAMX_PUBLIC_DAILY_TOTAL`, `EXAMX_MAX_JOBS`).
- **The owner** uses http://127.0.0.1:8014 on the server (or an SSH tunnel to it), which has no limits and
  can see everything. Requests reaching Caddy directly from the LAN also count as the owner.
- To restrict the site to signed-in users later, put a Cloudflare Access application in front and set
  `EXAMX_REQUIRE_ACCESS=1`. Every request must then carry Access's identity header.
- **Content:** proof questions and official solutions from the Monash past papers appear on the public site.
  Check that this is permitted before sharing the link widely.
- Papers, reports and settings live in `output/` on the host.

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
