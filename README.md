# Agile Sourcing

AI-powered procurement portal for UCSC. Users describe what they need in plain language, the system determines compliance rules, finds suppliers, and produces a ready-to-submit purchase request.

## Develop integration

`develop` combines `auth`, main, and all five open PR branches for team testing.
The team's RAG, ingestion, rules, and evaluation code is preserved unchanged,
including the DOCX citation fix and the two evaluation scripts from PRs #7–#9.
FastAPI still verifies Firebase identity and account approval. Department, role,
and clearance remain server-owned profile fields; **document filtering is deferred
to the RAG teammate**. Approved accounts currently share the same indexed corpus.

See [the branch/PR review](docs/develop-integration.md),
[authentication setup](docs/auth-setup.md), and [chat integration](docs/policy-chat.md).
The figures below are main's historical baseline, not a new develop evaluation.

## Current Status (October 12, 2026)

Policy Q&A pipeline, measured on the 60-question benchmark across 32 UC/UCSC policy documents:

| Metric | Result |
|--------|--------|
| Correct (LLM judge, corrected answer key) | 48 / 60 (80.0%) |
| Numeric accuracy (thresholds and amounts) | 95.0% |
| Answers citing a policy source | 55 / 60 |
| Explicit "not found in policy" refusals | 1 |
| Mean / median latency | 6.9 s / 6.0 s (threshold questions ~0 s via rule engine) |

- Thresholds follow the **interim BUS-43 (Jan 2026)**, the **SSPR form (Rev. 12-2025)**, and the **Oct 2025 FAR update**. Every rule carries its document, page, and quote, and a test fails if a quote disappears from the current documents.
- Single run per configuration; expect about ±3 questions of run-to-run variation.
- Benchmark is AI-generated; real buyer questions are pending from the procurement team.

Reproduce:

```bash
python evaluation/benchmarks/run_benchmark.py
python evaluation/metrics/score.py <results.json> --judge
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

**How a policy question is answered:** intent classifier → query parser (amount, funding type) → threshold questions go straight to the rule engine with a cited source; everything else uses query rewriting, hybrid BM25 + semantic retrieval, cross-encoder reranking, and a fixed Answer / Rule / Source / Conditions response. Low-confidence retrieval returns "not found in policy." All LLM calls have token caps, 90 s timeouts, and fallbacks.

## Project Structure

```
agile-sourcing/
├── backend/
│   ├── api/              # FastAPI routes & middleware
│   ├── rag/              # Policy retrieval pipeline
│   ├── auth/             # Sign-in and access control
│   └── main.py           # FastAPI app entry point
├── rules/                # Deterministic threshold engine + tests
├── rag_pipeline/         # Parsing, chunking, indexing, retrieval
├── evaluation/           # Benchmark, scoring, results
├── training/             # Fine-tuning data and scripts
├── frontend/             # WXT browser extension (React + Tailwind)
├── data/
│   └── raw_policies/     # Policy documents for the team ingestion script
├── tests/                # Unit and integration tests
├── scripts/              # Ingestion and evaluation scripts
├── docs/                 # Architecture docs, policy notes
├── requirements.txt
├── secret/               # Ignored configuration and Admin credentials
└── README.md
```

## Setup

Use Python **3.12 or 3.13** for the team's unchanged pipeline (the DOCX citation
PR uses Python 3.12 f-string syntax); CI uses 3.13. Use Node 22.13+ and Corepack/pnpm.
Commands below assume macOS/Linux and start at the repository root.

```sh
git clone --branch develop https://github.com/Alvarez-Jose/agile-sourcing.git
cd agile-sourcing
python3.13 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
mkdir -p secret
```

Configure `secret/.env` and authorized backend Firebase Admin credentials using
[the auth guide](docs/auth-setup.md). This directory is excluded from Git.
Google OAuth must authorize the extension's actual redirect URL.

```sh
ollama pull qwen3:8b
# Put the team's policy PDFs/DOCX in data/raw_policies/.
# Then use their original ingestion entry point from the repository root:
./venv/bin/python -m scripts.ingest_policies --ingest
```

The main pipeline reads the collection named `uc_policies`. The older source-index
publisher's versioned collections are separate and do not replace this ingestion
step. Source/graph review tools remain available but are not used for chat filtering.

Run in separate terminals:

```sh
# Terminal 1; unnecessary if Ollama is already running
ollama serve
# Terminal 2, repository root
./venv/bin/python -m uvicorn backend.main:app --reload --port 8000
# Terminal 3, repository root
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Sign in with Google, have an administrator approve `users/{uid}` in Firestore, and
sync the session in extension settings. `GET /api/health` is public. Auth/health do
not import the RAG stack; optional `RAG_WARM_UP=1` invokes the team's warm-up at
startup. Launch the server from the repository root because the team pipeline uses
relative data paths.

## Testing

```sh
./venv/bin/python -m pytest rules tests -q
cd frontend
corepack pnpm test
corepack pnpm compile
corepack pnpm build
```

The team's RAG tools remain unchanged:

```sh
./venv/bin/python -m evaluation.benchmarks.run_benchmark
./venv/bin/python -m evaluation.analyze_benchmark evaluation/results/benchmark_results_full.json
./venv/bin/python -m evaluation.check_citation_grounding /path/to/saved-api-responses.json --output data/evaluation/citation_grounding.csv
```

The existing benchmark runner retains its own defaults and output format. Its saved
rows omit the `sources`/`rule_sources` needed by the citation checker; supply saved
complete `/api/ask` responses to that checker. These scripts and their known gaps
remain owned by the RAG teammate. See [the integration review](docs/develop-integration.md).

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