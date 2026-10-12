# Agile Sourcing

AI-powered procurement portal for UCSC. Users describe what they need in plain language, the system determines compliance rules, finds suppliers, and produces a ready-to-submit purchase request.

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
│   └── policies/         # Policy documents for ingestion
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

# Ingest policy docs
cp /path/to/policy-docs/* data/policies/
python scripts/ingest_policies.py

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