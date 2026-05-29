# Agile Sourcing

AI-powered procurement portal for UCSC. Users describe what they need in plain language, the system determines compliance rules, finds suppliers, and produces a ready-to-submit purchase request.

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

## Project Structure

```
agile-sourcing/
├── backend/
│   ├── api/              # FastAPI routes & middleware
│   ├── agents/           # Conversation + Rules agents
│   ├── rules_engine/     # Deterministic compliance logic
│   ├── rag/              # Policy retrieval (vector DB)
│   ├── supplier/         # Supplier search & catalog
│   ├── forms/            # SSPR & PR auto-fill
│   ├── models/           # Pydantic schemas & DB models
│   ├── utils/            # Config, logging
│   └── main.py           # FastAPI app entry point
├── frontend/             # Angular app (ng new)
├── data/
│   ├── policies/         # Policy PDFs for RAG ingestion
│   ├── raw/              # Raw data exports
│   └── embeddings/       # Cached embeddings
├── tests/
│   ├── unit/             # Unit tests per module
│   ├── integration/      # End-to-end agent tests
│   └── scenarios/        # Real purchase scenario tests
├── scripts/              # Ingestion, seeding, eval scripts
├── docs/                 # Architecture docs, policy notes
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

```bash
# Clone
git clone <repo-url>
cd agile-sourcing

# Python env
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Config
cp .env.example .env
# fill in API keys

# Ingest policy docs
cp /path/to/policy-pdfs/* data/policies/
python scripts/ingest_policies.py

# Run backend
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
ng serve
```

## Key Rules the System Enforces

| Amount | Non-Federal | Federal |
|--------|------------|---------|
| < $10K | Low-value, dept buys | Micro-purchase |
| $10-50K | Procurement, no bid | SSPR @ $15K (contracts) |
| $50-100K | Procurement, no bid | Competitive + SSPR (grants) |
| > $100K | Must competitively bid | Full federal compliance |
| < $250K | Small biz/DVBE ok | Small biz < $100K |

## Tech Stack

- **Backend:** FastAPI (Python) + TypeScript
- **LLM:** OpenAI GPT-4o / Claude (prototype) → self-hosted (production)
- **Orchestration:** Raw API calls (prototype) → LangGraph (production)
- **Vector DB:** Chroma (prototype) → pgvector (production)
- **Frontend:** Streamlit (prototype) → Angular (production)
- **Database:** SQLite (prototype) → PostgreSQL (production)
- **Auth:** UC SSO (Cisco Duo / CruzID) — production only
- **Forms:** PDF fill or HTML → PDF

## Team

UCSC Procurement + Dev Team — Spring 2026
## System Architecture Diagram

![Architecture](docs/updated%20system%20design.drawio.png)
