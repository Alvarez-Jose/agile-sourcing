# AGENTS.md

Guidance for coding agents working in this repo. `CLAUDE.md` points here.

## What this is

An AI procurement portal for UCSC: a buyer describes a purchase in plain language, and the
system determines which UC/federal policies apply, routes funding and thresholds, retrieves
policy text with citations, and produces a purchase request. The backend is Python
(FastAPI + Ollama + Chroma); the frontend is a WXT browser extension.

`docs/related_work.md` explains the research problem (conditional dependency across
regulatory documents; why plain chunk-similarity RAG is insufficient). Read it before
changing retrieval logic.

## Commands

```bash
# Tests — this exact subset is what CI runs (.github/workflows/tests.yml)
python -m pytest rules tests/integration -q

# Backend (loads embeddings, reranker, and Ollama at startup)
ollama pull qwen3:8b
uvicorn backend.main:app --reload --port 8000

# Build the vector index from policy docs
python scripts/ingest_policies.py --ingest
python scripts/ingest_policies.py --query "what is the bidding threshold?"

# Benchmark (needs Ollama; slow)
python evaluation/benchmarks/run_benchmark.py --out evaluation/results/full.json
python evaluation/metrics/score.py evaluation/results/full.json --judge

# Frontend
cd frontend && pnpm install && pnpm dev
```

No lint or type-check step exists in CI. `ruff` and `black` are listed in
`requirements.txt` but have no config and have never been run over this repo — do not
reformat wholesale, and match the surrounding file instead.

## Architecture

```
backend/api/routes.py    POST /api/ask -> AskResponse (answer, sources, citations,
                         rule_sources, determination, intent, refused)
backend/rag/pipeline.py  ask(): intent -> rule engine -> retrieval -> fixed-format answer
rag_pipeline/            parser (pdf/docx/section/metadata), hybrid index, intent, reranker
rules/                   deterministic threshold engine — pure Python, no heavy deps
evaluation/              benchmark generation, runner, scoring, baselines
training/                QLoRA fine-tuning scripts (not on the request path)
frontend/                WXT + React + Tailwind extension
```

Pipeline order in `ask()` matters: threshold and rule-heavy questions are answered by the
rule engine (often without an LLM call), everything else goes through query rewriting,
hybrid BM25 + semantic retrieval, cross-encoder reranking, then an LLM constrained to a
fixed Answer / Rule / Source / Conditions format. Low confidence returns an explicit
`NOT_FOUND_ANSWER` instead of a vague non-answer.

## Policy correctness rules

These are the invariants that keep the compliance output trustworthy. Breaking one is a
worse outcome than a failing test.

1. **`rules/` is the single source of truth for every dollar threshold.** The README table
   is a summary; if it disagrees with `rules/thresholds.py`, the code wins. Never hardcode a
   threshold, form name, or section list in the prompt, the route, the frontend, or a
   benchmark script — import the constant.
2. **Every threshold constant has a provenance record.** Add or change a number in
   `rules/thresholds.py` and you must update `rules/provenance.py` (`SOURCES`, and
   `TOPIC_SOURCES` if the topic map should cite it) with document, physical PDF page,
   section, and an exact quote. Pages are physical one-based PDF pages, not printed numbers.
3. **`rules/test_provenance.py` verifies quotes against the real documents.** It fails if a
   quote stops appearing on its stated page after a policy update. It skips when the policy
   files (in `data/raw_policies/`, gitignored) are absent, so it passes in CI without
   proving anything — run it locally after touching `rules/`.
4. **Policy documents are not in this repo.** Do not commit PDFs/DOCX from `data/`, and do
   not add verbatim policy text beyond the short citations already in `rules/provenance.py`.
5. **The rule engine's determination is authoritative.** `FIXED_FORMAT_INSTRUCTIONS` tells
   the LLM not to recompute or contradict it. Don't loosen that, and don't let the LLM
   produce the Rule/Source lines — they are filled from the determination and provenance.
6. **Refusals must stay explicit.** Keep `REFUSAL_MIN_RERANK = -8.0` justified by the
   benchmark (comment above it records which floor loses correct answers); don't swap the
   refusal path back to a vague "the excerpts don't specify".
7. **The benchmark answer key is AI-generated and partly hand-corrected.** Original
   expected answers were left unchanged on purpose. Don't "fix" scores by editing expected
   answers silently; record corrections separately as the existing commits do.

## Conventions

- Python 3.13. `rules/` uses stdlib only (`dataclasses`, `typing`) so the rule engine and
  its tests stay importable without torch/chromadb/ollama. Keep it that way.
- Integration tests stub `backend.rag.pipeline` (`tests/integration/test_ask_api.py`)
  because the real module loads models. Add new API-contract tests the same way, and keep
  the response fields the frontend already reads (`answer`, `sources`) backward compatible.
- Module headers use a `# path/to/file.py` line plus a short lowercase explanation,
  including how to run the file when that isn't obvious. Comments explain *why* (source of
  a rule, why a threshold is what it is, what was tried and rejected), not what the code
  does. Match that density; long files legitimately have long comments.
- Data classes and plain functions over frameworks. Frameworks are available
  (langchain/langgraph) but the parser, retriever, and verifier are deliberately
  hand-built — don't wrap them in LangChain abstractions.
- All LLM calls need a token cap and a timeout; a looping local model must not hang a
  request.
- `.env` is gitignored; config keys are documented in `.env.example`. Everything must
  still run with the local Ollama/model setup — no new required cloud API calls.

## Before you finish

- Run `python -m pytest rules tests/integration -q`.
- If you touched `rules/`, also run the provenance and rule tests locally with the policy
  documents present (see `POLICY_SOURCE_DIRS` in `rules/test_provenance.py`), and look at
  any `skipped` count rather than trusting a green run.
- If you changed retrieval, prompting, or thresholds, the benchmark numbers in `README.md`
  and `evaluation/results/analysis/benchmark_results_summary.md` may be stale; say so
  instead of updating them without a rerun.
