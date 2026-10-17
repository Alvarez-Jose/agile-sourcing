# Agile Sourcing

AI-powered procurement portal for UCSC. Users describe what they need in plain language, the system determines compliance rules, finds suppliers, and produces a ready-to-submit purchase request.

## Current Status (October 16, 2026)

Policy Q&A pipeline, measured on the 60-question benchmark across 32 UC/UCSC policy documents:

| Metric | Default (`think` off) | With `--think` |
|--------|------|------|
| Correct / partial / wrong (LLM judge, corrected answer key) | **50 / 9 / 1** (83.3%) | **52 / 8 / 0** (86.7%) |
| Same, on the 54 questions the corpus can answer (see below) | 47 / 7 / 0 (87%) | 49 / 5 / 0 (91%) |
| Answers citing a policy source | 60 / 60 | 59 / 60 |
| Empty answers / explicit "not found in policy" refusals | 0 / 0 | 0 / 1 |
| Retrieval: expected document at rank 1 / in top 5 (no LLM) | 49 / 60 and 60 / 60 | same |
| Mean / median latency per question | 1.8 s / 1.8 s | 8.0 s / 7.1 s |

- Thresholds follow the **interim BUS-43 (Jan 2026)**, the **SSPR form (Rev. 12-2025)**, and the **Oct 2025 FAR update**. Every rule carries its document, page, and quote, and a test fails if a quote disappears from the current documents.
- Six questions are reported separately: **Q13–15** use a mixed-funding rule that conflicts with the 12-2025 SSPR form (pending a Procurement decision), and **Q46–48** ask about FAR Part 12, which no indexed document covers. The one wrong answer above is Q46.
- The answer key is AI-generated and has been corrected where it contradicted the policy text (13 questions so far, each with the quote and page in `evaluation/results/benchmark_questions_corrected.json`); real buyer questions are pending from the procurement team.
- Single run per configuration; expect about ±3 questions of run-to-run variation (a repeat of the same qwen3:32b configuration scored 47 and 44).
- **The judge matters.** The table above is graded by qwen3:8b. Re-graded by qwen3:32b (`JUDGE_MODEL=qwen3:32b`), the same answers score **41 / 15 / 4** (default) and **46 / 13 / 1** (`--think`): the 8b judge passes about 9 answers the 32b judge calls partial. Use the 32b-judged numbers when comparing models.

### Model comparison (October 16, 2026; rented A100, judge = qwen3:32b, default mode unless noted)

| Model | Correct / partial / wrong | Per-question latency |
|---|---|---|
| llama3.3:70b | 47 / 12 / 1 | 10.0 s |
| qwen3:32b `--think` | 47 / 11 / 2 | 21.6 s |
| qwen3:30b-a3b | 46 / 10 / 4 | 11.8 s |
| **qwen3:8b `--think` (local)** | **46 / 13 / 1** | 8.0 s |
| qwen3:32b | 44 / 14 / 2 (repeat: 47) | 7.8 s |
| qwen3.5:35b | 44 / 15 / 1 | 6.7 s |
| qwen3:8b (local, default) | 41 / 15 / 4 | 1.8 s |
| gemma3:27b | 40 / 19 / 1 | 6.6 s |

Nine questions are answered correctly by none of the six default-mode models: four are the flagged disputed/not-in-corpus ones (Q13, 15, 46, 47); the other five (Q27, 34, 42, 49, 58) are benchmark or retrieval problems, not model problems. Remote results are in `evaluation/results/remote/`.

Reproduce:

```bash
python evaluation/benchmarks/run_benchmark.py                 # add --think for the slower, more accurate mode
python evaluation/metrics/score.py <results.json> --judge
python evaluation/metrics/retrieval_recall.py                 # retrieval only, ~10 s, no LLM
```

## Architecture

```
User (plain language request)
  │
  ▼
┌─────────────────────┐     ┌─────────────────────┐
│  CONVERSATION AGENT │◄───►│    RULES AGENT      │
│  (Agent 1)          │     │    (Agent 2)         │
│                     │     │                      │
│  - NL understanding │     │  - Compliance check  │
│  - Follow-up Q's    │     │  - Supplier search   │
│  - Present results  │     │  - Form generation   │
│  - Policy citations │     │  - Flag issues       │
└─────────────────────┘     └──────┬───────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
             ┌───────────┐ ┌───────────┐ ┌───────────┐
             │  RULE     │ │  RAG      │ │ SUPPLIER  │
             │  ENGINE   │ │ RETRIEVAL │ │ SEARCH    │
             │           │ │           │ │           │
             │ thresholds│ │ BUS-43    │ │ catalogs  │
             │ forms     │ │ SSPR      │ │ contracts │
             │ routing   │ │ T&Cs      │ │ history   │
             └───────────┘ └───────────┘ └───────────┘
```

**How a policy question is answered:** intent classifier → query parser (amount, funding type) → threshold questions go straight to the rule engine with a cited source; everything else uses query rewriting, hybrid BM25 + semantic retrieval, cross-encoder reranking (8 chunks to the LLM), and a fixed Answer / Rule / Source / Conditions response when the engine decided something. Questions the engine can only annotate (what counts as a sole source reason, that split orders are prohibited) get those facts as background and a free-form answer. Low-confidence retrieval returns "not found in policy." Every chunk is indexed with its policy name and section in the text, so the embedder, BM25 and the reranker all see which document it is from. All LLM calls have token caps, 90 s timeouts, fallbacks, and thinking disabled at the API level (qwen3 ignores the `/no_think` tag often enough to return empty answers otherwise).

## Project Structure

```
agile-sourcing/
├── backend/
│   ├── api/              # FastAPI routes & middleware
│   ├── agents/           # Conversation + Rules agents
│   ├── rag/              # Policy retrieval pipeline
│   ├── auth/             # Sign-in and access control
│   └── main.py           # FastAPI app entry point
├── rules/                # Deterministic threshold engine + tests
├── rag_pipeline/         # Parsing, chunking, indexing, retrieval
├── evaluation/           # Benchmark, scoring, results
├── training/             # Fine-tuning data and scripts
├── frontend/             # WXT browser extension (React + Tailwind)
├── data/
│   ├── raw_policies/     # Policy documents for ingestion
│   └── embeddings/       # Chroma index (built by scripts/ingest_policies.py)
├── tests/                # Unit and integration tests
├── scripts/              # Ingestion and evaluation scripts
├── docs/                 # Architecture docs, policy notes
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

```bash
# Clone
git clone https://github.com/Alvarez-Jose/agile-sourcing
cd agile-sourcing

# Python env
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Local model
ollama pull qwen3:8b

# Config
cp .env.example .env

# Ingest policy docs (the 32 UC/UCSC documents)
cp /path/to/policy-docs/* data/raw_policies/
python scripts/ingest_policies.py --ingest

# Run backend
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev
```

## Key Rules the System Enforces

| Rule | Threshold | Source |
|------|-----------|--------|
| Competitive bidding required | $100,000 or more | BUS-43 (interim 2026), §C.1 |
| SSPR form: federal contracts | ≥ $15,000 | SSPR form Rev. 12-2025, p.1 |
| SSPR form: federal grants / cooperative agreements | ≥ $50,000 | SSPR form Rev. 12-2025, p.1 |
| SSPR form: non-federal | ≥ $100,000 | SSPR form Rev. 12-2025, p.1 |
| Mixed funding | Federal rules apply only when the federal portion exceeds the federal thresholds above | SSPR form Rev. 12-2025, p.1 §I |
| Federal micro-purchase | $15,000 (campus grant cap up to $50,000) | FAR (Oct 2025); BUS-43 §B.4 |
| Small business / DVBE | Up to $250,000; 1 quote $10K–$100K, 2 quotes above $100K | BUS-43 §C.1, p.25 |
| Simplified acquisition threshold | $350,000 | FAR (Oct 2025) |

The authoritative values, with page-level quotes, live in `rules/`. If this table and `rules/` ever disagree, `rules/` wins.

## Tech Stack

- **Backend:** FastAPI (Python)
- **LLM:** qwen3:8b via Ollama (local)
- **Retrieval:** all-MiniLM-L6-v2 embeddings, BM25 + semantic hybrid search, ms-marco-MiniLM-L-6-v2 cross-encoder reranker
- **Vector DB:** Chroma (prototype) → pgvector (production)
- **Frontend:** WXT browser extension (React + Tailwind)
- **Database:** SQLite (prototype) → PostgreSQL (production)
- **Auth:** Google sign-in (prototype) → UC SSO / CruzID (production)

## Team

UCSC Procurement + Dev Team — 2026

## System Architecture Diagram

![Architecture](docs/updated%20system%20design.drawio.png)