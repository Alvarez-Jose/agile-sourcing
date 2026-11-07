# Agile Sourcing

AI-powered procurement portal for UCSC. Users describe what they need in plain language, the system determines compliance rules, finds suppliers, and produces a ready-to-submit purchase request.

[Progress updates and experiment history](documentation/prgress.md)

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

**How a policy question is answered:** intent classifier → query parser (amount, funding type) → threshold questions go straight to the rule engine with a cited source; four policy ladders (post-employment contracting bans, business-meal documentation, tax-free alcohol permits, BUS-63 risk matrix / certificate of insurance) decide their questions the same way, with a page-cited quote and a test per quote (`rules/policy_ladders.py`); everything else uses query rewriting, hybrid BM25 + semantic retrieval, cross-encoder reranking (8 chunks to the LLM), and a fixed Answer / Rule / Source / Conditions response when the engine decided something. Questions the engine can only annotate (what counts as a sole source reason, that split orders are prohibited) get those facts as background and a free-form answer. Low-confidence retrieval returns "not found in policy." Every chunk is indexed with its policy name and section in the text, so the embedder, BM25 and the reranker all see which document it is from. All LLM calls have token caps, 90 s timeouts, fallbacks, and thinking disabled at the API level (qwen3 ignores the `/no_think` tag often enough to return empty answers otherwise).

### Tech Stack

- **Backend:** FastAPI (Python)
- **LLM:** qwen3:8b via Ollama (local)
- **Retrieval:** all-MiniLM-L6-v2 embeddings, BM25 + semantic hybrid search, ms-marco-MiniLM-L-6-v2 cross-encoder reranker
- **Vector DB:** Chroma (prototype) → pgvector (production)
- **Frontend:** WXT browser extension (React + Tailwind)
- **Database:** SQLite (prototype) → PostgreSQL (production)
- **Auth:** Google sign-in (prototype) → UC SSO / CruzID (production)

### Project Structure

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
├── docs/                 # Setup guides, policy references, architecture assets
├── documentation/        # Progress history, integration notes, experiment writeups
├── requirements.txt
├── run.sh                # Start local services
├── test.sh               # Run a named test group
├── secret/               # Ignored configuration and Admin credentials
└── README.md
```

## First-time setup

Install **Git**, **Python 3.12**, **Node.js 22.13+**, **pnpm** (or Corepack),
**Google Chrome**, and [Ollama](https://ollama.com/download). These instructions
use macOS/Linux shell commands.

### 1. Clone the repository

```sh
git clone https://github.com/Alvarez-Jose/agile-sourcing.git
```

### 2. Open the repository in your terminal

```sh
cd agile-sourcing
```

### 3. Prepare your environment

If you already have a project environment, activate it (whatever its name or
location) and ensure its project dependencies are installed. Otherwise, `./run.sh`
will create `venv/` and install Python and frontend dependencies automatically.
System prerequisites, Firebase configuration, and policy documents still need to
be supplied separately.

Before launching:

- Place the team's Firebase `.env` and authorized Admin SDK JSON in `secret/`;
  follow the [auth guide](docs/auth-setup.md) for configuration and your browser's
  OAuth callback. These files stay out of Git.
- Put the intended policy PDFs/DOCX directly in `data/raw_policies/`. For a small
  demo corpus, run `python -m scripts.download_starter_policies` in your active environment.
  The full corpus is not included in the repository.

### 4. Run the project

```sh
./run.sh --index   # First launch: build the index and start services
./run.sh           # Later launches
```

The launcher uses your active virtual environment. If none is active, it finds
and activates `venv/`, `.venv/`, `env/`, or `.env/` under the repository root.
The folders are checked in that order; the first usable environment wins.
If none exists, it creates `venv/` and installs dependencies before starting.
An existing environment is reused, not replaced. A custom-named environment must
be activated first to avoid creating an additional one. Activation inside the
script lasts only for that run. `--check` never creates environments or installs packages.

`--index` rebuilds the index from **all top-level PDFs/DOCX** in
`data/raw_policies/`; review that folder first. The launcher starts Ollama if
needed, downloads the configured Qwen model if missing, and starts FastAPI and
WXT's extension development browser. Initial model downloads/indexing take time.
Keep the terminal open; **Ctrl+C** stops services started by the launcher.

Check [API health](http://localhost:8000/api/health), then sign in with Google.
An administrator must approve your account in Firestore before chat works.
Health checks confirm the API is running, not answer quality. Use `--check` in
place of `--index` to check setup without starting services.

Optional model settings and troubleshooting: [auth/setup guide](docs/auth-setup.md).
Changing the embedder requires rebuilding a matching index.

## Testing

Run these commands from the repository root after completing setup. Start with
`./test.sh all` for the normal development checks; long model evaluations are
separate so they do not run accidentally.

| What to check | One command | What it reports / needs |
| --- | --- | --- |
| Quick development suite | `./test.sh all` | Backend tests, frontend tests, TypeScript and extension build. No running API or Ollama needed. |
| Backend, rules and evaluation helpers | `./test.sh backend` | Passed, failed, skipped and test pass rate. Firebase and model calls are simulated in integration tests. |
| Authentication and sessions | `./test.sh auth` | Backend token/approval tests and frontend sign-in/session tests. No live Google login needed. |
| Frontend | `./test.sh frontend` | Test counts, TypeScript check and extension build result. |
| Cart paperwork helper | `./test.sh cart` | API/rule test counts plus eight synthetic cart scenarios. Needs the reviewed BUS-43 and SSPR PDFs. |
| Running API health | `./test.sh health` | HTTP status and response time. Start `./run.sh` first. |
| RAG answer quality | `./test.sh rag` | All 60 questions, corrected-key LLM-judged accuracy, partial/incorrect counts, latency and citation diagnostics. Needs Ollama, models and the policy index. |
| Retrieval quality | `./test.sh retrieval` | Expected-document recall@1, recall@5 and candidate-pool recall over 60 questions. Needs the embedding/reranking models and policy index; no answer generation or running API needed. |

The long RAG check shows a loading indicator, an **Answering** progress bar and a
**Grading** progress bar. Retrieval has its own progress bar. In an interactive
terminal, elapsed time keeps updating during each model call; ETA is an estimate.
RAG answers and grades are saved after each question so completed work survives
interruption. Model logs and reports go to a new, ignored folder under
`data/evaluation/`; the terminal prints its location.

For a short trial before the full 60-question run:

```sh
./test.sh rag --limit 5
```

Use `./test.sh --help` for options such as a different health URL or an installed
judge model. Each command returns a nonzero exit code for test failures, failed
health checks, model execution errors or ungraded answers. A completed quality
benchmark reports its score; an incorrect model answer is not a program crash.

**How to read results:** unit-test pass rates measure code checks. RAG accuracy is
an automated judge's estimate, not Procurement validation. Retrieval recall checks
whether an expected document appears in the results, not whether every passage or
answer is correct. Citation amount flags can include question-supplied amounts or
shorthand parsing issues. Different corpora, model settings and judges produce
results that should not be compared directly.

Automated tests do not open Google sign-in or your private CruzBuy session. For a
manual browser check, follow the [auth guide](docs/auth-setup.md) and
[cart helper instructions](docs/cart-demo.md). Raw benchmark tools remain in
`evaluation/` for experiments; historical measurements are in the
[progress log](documentation/prgress.md).

## Key Rules the System Enforces

| Rule | Threshold | Source |
|------|-----------|--------|
| Competitive bidding required | $100,000 or more | BUS-43 (interim 2026), §C.1 |
| Former employee contracting bans | 2 years (took part in the contract's decision-making); 12 months (policymaking role, same department); retirees exempt | OGC Post-Employment Rules (Oct 2023), p.3 |
| Certificate of insurance | Required for any High-risk exposure C–K; on request only for Low/Moderate (digital-only) risk | BUS-63 Risk Matrix (9.19.2025), pp.1–2 |
| Tax-free alcohol | TTB permit in the Regents' name; vendor holds a signed copy; semiannual inventory | BFB-BUS-2 / UCPS 120031, pp.2–6 |
| Business meal documentation | Type of expense and event, guest list with names/titles, date/location, business purpose, approver signature; itemized receipts at $75+ | BUS-79 IV.B.1, p.17 |
| SSPR form: federal contracts | ≥ $15,000 | SSPR form Rev. 12-2025, p.1 |
| SSPR form: federal grants / cooperative agreements | ≥ $50,000 | SSPR form Rev. 12-2025, p.1 |
| SSPR form: non-federal | ≥ $100,000 | SSPR form Rev. 12-2025, p.1 |
| Mixed funding | Federal rules apply only when the federal portion exceeds the federal thresholds above | SSPR form Rev. 12-2025, p.1 §I |
| Federal micro-purchase | $15,000 (campus grant cap up to $50,000) | FAR (Oct 2025); BUS-43 §B.4 |
| Small business / DVBE | Up to $250,000; 1 quote $10K–$100K, 2 quotes above $100K | BUS-43 §C.1, p.25 |
| Simplified acquisition threshold | $350,000 | FAR (Oct 2025) |

The authoritative values, with page-level quotes, live in `rules/`. If this table and `rules/` ever disagree, `rules/` wins.

## Team

UCSC Procurement + Dev Team — 2026

## System Architecture Diagram

![Architecture](docs/updated%20system%20design.drawio.png)
