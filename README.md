# Agile Sourcing

AI-powered procurement portal for UCSC. Users describe what they need in plain language, the system determines compliance rules, finds suppliers, and produces a ready-to-submit purchase request.

## Current Status (October 29, 2026)

Policy Q&A pipeline, measured on the 60-question benchmark (October 17 run, across the then-32 UC/UCSC policy documents):

| Metric | Default (`think` off) | With `--think` |
|--------|------|------|
| Correct / partial / wrong (LLM judge, corrected answer key) | **55 / 5 / 0** (91.7%) | 52 / 8 / 0 (86.7%, measured before the ladders) |
| Same, on the 54 questions the corpus can answer (see below) | 51 / 3 / 0 (94%) | 49 / 5 / 0 (91%, before the ladders) |
| Answers citing a policy source | 60 / 60 | 59 / 60 |
| Empty answers / explicit "not found in policy" refusals | 0 / 0 | 0 / 1 |
| Retrieval: expected document at rank 1 / in top 5 (no LLM) | 50 / 60 and 60 / 60 | same |
| Mean / median latency per question | 1.8 s / 1.8 s | 8.0 s / 7.1 s |

- Thresholds follow the **interim BUS-43 (Jan 2026)**, the **SSPR form (Rev. 12-2025)**, and the **Oct 2025 FAR update**. Every rule carries its document, page, and quote, and a test fails if a quote disappears from the current documents.
- The October 17 jump (50 → 55) comes from four policy ladders in the rule engine and from indexing the interim BUS-43 and the official SSPR PDF; seven questions that no model had answered correctly the day before (Q27, 34, 36, 42, 47 among them) are now decided deterministically with a cited quote.
- Six questions were reported separately until October 29, 2026, when both issues were resolved: **Q13–15**'s expected answers now follow the 12-2025 SSPR form's mixed-funding thresholds ($15,000 federal contract / $50,000 federal grant), superseding the 2021 FAQ's flat $10,000 trigger, and **Q46–48** became answerable when the official 48 CFR Part 12 PDF (govinfo.gov) was added to the corpus. Scores dated before October 29 were measured against the older key and without the FAR document.
- The answer key is AI-generated and has been corrected where it contradicted the policy text (13 questions so far, each with the quote and page in `evaluation/results/benchmark_questions_corrected.json`); real buyer questions are pending from the procurement team.
- Single run per configuration; expect about ±3 questions of run-to-run variation (a repeat of the same qwen3:32b configuration scored 47 and 44).
- **The judge matters.** The table above is graded by qwen3:8b. Re-graded by qwen3:32b (`JUDGE_MODEL=qwen3:32b`), the same answers score **41 / 15 / 4** (default) and **46 / 13 / 1** (`--think`): the 8b judge passes about 9 answers the 32b judge calls partial. Use the 32b-judged numbers when comparing models.

### October 29, 2026: corrected key, FAR Part 12, and a fine-tuned embedder

All numbers below are judged by qwen3:32b on the fully corrected answer key (all 60 questions now answerable — see the resolution bullet above), with the official 48 CFR Part 12 PDF added to the corpus (33 documents, 3,216 chunks). They are not comparable to earlier scores, which used the older key and corpus.

| Configuration (qwen3:8b answerer, default mode) | Correct / partial / wrong |
|---|---|
| Base embedder (`all-MiniLM-L6-v2`, public default) | 40 / 13 / 7 |
| **Fine-tuned embedder** (private `EMBED_MODEL` slot) | **41 / 13 / 6** |

- **Embedder fine-tune (adopted).** MiniLM fine-tuned on 12,345 generated (question, chunk) pairs; on a chunk-level held-out split, retrieval accuracy@1 rose from 28.7% to 41.0% and accuracy@5 from 56.7% to 74.6%. The end-to-end gain (+1 correct / −1 wrong) is within run-to-run noise; the held-out gain is the evidence it generalizes to phrasings beyond the benchmark. Details: `evaluation/results/analysis/embedder_finetune_v1_2026-10-29.md`.
- **Private model slots.** Fine-tuned weights live in a private Hugging Face repo and load via `EMBED_MODEL` + `HF_TOKEN`; unset, everything falls back to the public base models, so the repo works for everyone out of the box. Private training data ships in the repo as AES-256 ciphertext (`*.enc`, `scripts/vault.sh`); plaintext stays untracked.
- **Chunk enrichment (tried, not adopted).** Contextual headers + likely questions per chunk scored no better than the baseline in either serving mode (36/60 and 39/60 vs 40/60); the generated questions were instead reused as the fine-tune training set. Details: `evaluation/results/analysis/enrichment_v1_2026-10-29.md`.

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

### Pipeline comparison: rule-engine pipeline vs grounded pipeline (October 29, 2026)

This branch merges the `auth` branch's retrieval stack (SQLite source index, policy
graph, section retriever, span-verified "grounded" answers) alongside the rule-engine
pipeline, and runs both on the same 60 questions, same LLM (qwen3:8b on an A100),
same judge (qwen3:32b). Full analysis: `evaluation/results/analysis/ab_rules_vs_grounded_2026-10-29.md`.

| | rule-engine pipeline (`/api/ask`) | grounded, as shipped | grounded, full corpus |
|---|---|---|---|
| Judge correct | **39 / 60** | 4 / 60 | 14 / 60 |
| Correct + partial | **56 / 60** | 28 / 60 | 32 / 60 |
| Flat wrong | **4** | 32 | 28 |
| Refusals | **0** | 34 | 25 |
| Median latency | **2.6 s** | 5.7 s | 9.5 s |

Why the rule-engine pipeline wins:

1. **Deterministic rules beat retrieval for thresholds.** Known thresholds, forms and
   prohibitions are answered from the provenance-backed rule engine with a cited
   quote — no LLM involved, so an 8B model can't get them wrong. The grounded
   pipeline removed this layer and depends on retrieval + the LLM for everything.
2. **It answers the question.** The grounded pipeline's manifest marks 31 of 33
   documents unreviewed and its chat refuses review scopes, so as shipped it
   retrieves from 2 documents and refuses 34/60 questions. Even over the full corpus
   (`evaluation/benchmarks/build_grounded_index.py`) its span-verification loop
   abstains on 25/60 whenever qwen3:8b fails twice to select valid quote spans.
3. **3.7x faster**, because it ranks pre-built hybrid indexes instead of re-ranking
   1,724 section candidates per question, and skips the JSON claim-repair loop.

What the grounded pipeline does better — kept in the tree for future adoption: when
it does answer it is rarely flat wrong (3 of its 35 real answers), and its citations
carry exact source spans, byte offsets and page locations; its section-level
retrieval and cross-policy reference hops are worth porting into the main retriever.

Reproduce:

```bash
python evaluation/benchmarks/run_benchmark.py --pipeline rules --out a.json
python -m evaluation.benchmarks.build_grounded_index    # one-time, for grounded-full
python evaluation/benchmarks/run_benchmark.py --pipeline grounded-full --out b.json
JUDGE_MODEL=qwen3:32b python evaluation/metrics/score.py a.json b.json --judge
```

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

**How a policy question is answered:** intent classifier → query parser (amount, funding type) → threshold questions go straight to the rule engine with a cited source; four policy ladders (post-employment contracting bans, business-meal documentation, tax-free alcohol permits, BUS-63 risk matrix / certificate of insurance) decide their questions the same way, with a page-cited quote and a test per quote (`rules/policy_ladders.py`); everything else uses query rewriting, hybrid BM25 + semantic retrieval, cross-encoder reranking (8 chunks to the LLM), and a fixed Answer / Rule / Source / Conditions response when the engine decided something. Questions the engine can only annotate (what counts as a sole source reason, that split orders are prohibited) get those facts as background and a free-form answer. Low-confidence retrieval returns "not found in policy." Every chunk is indexed with its policy name and section in the text, so the embedder, BM25 and the reranker all see which document it is from. All LLM calls have token caps, 90 s timeouts, fallbacks, and thinking disabled at the API level (qwen3 ignores the `/no_think` tag often enough to return empty answers otherwise).

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

## Integration status (November 6, 2026)

`cb-integration` combines the authenticated extension and cart helper with the
`rag-v2-hybrid` pipeline. The performance tables above are upstream experiments,
not a rerun of this integrated branch. Google sign-in and server-owned account
approval still gate `/api/ask` and `/api/cart/guide`; the cart helper remains a
separate deterministic two-source check. Document-level filtering is not enabled
on the shared rule-engine chat endpoint.

Model slots `LLM_MODEL`, `EMBED_MODEL`, `RERANKER_MODEL`, and `CHROMA_COLLECTION`
may be configured in `secret/.env` or the process environment. Public defaults work
without private weights. A different embedder requires a matching, rebuilt index;
do not query an index generated by a different embedding model. `HF_TOKEN` is
needed only for authorized private model access. Encrypted upstream artifacts do
not activate themselves; do not commit decrypted files or vault keys.

See [the branch integration report](docs/branch-integration-2026-11-06.md) for
branch-by-branch changes, preserved behavior, and verification limits.

## First-time setup

After completing the setup below, start everything from one terminal:

```sh
./run.sh
```

The launcher starts Ollama if needed, downloads the configured Qwen model if missing,
starts FastAPI, and runs the extension development server/browser. Press Ctrl+C to
stop the services it started; an existing Ollama service is left running. Log paths
are printed in the terminal. It works when invoked from any directory.

Use `./run.sh --check` to check installed tools, configuration, and index presence
without starting services. If the main policy index has not been built, review the
intended PDF/DOCX files in `data/raw_policies`, then use `./run.sh --index` once to
build it and launch the project. This explicitly rebuilds the main index from all
top-level policy PDFs/DOCX, so exclude held documents unless their use is authorized.
The launcher does not install Python/frontend dependencies or configure Firebase;
complete those first-time steps below first.

Install **Git**, **Python 3.12**, **Node.js 22.13+ with Corepack**, and **Ollama**
before starting. The commands below use macOS/Linux shell syntax. Run them from
the repository root unless a step says otherwise.

### 1. Clone the development branch

```sh
git clone --branch cb-integration https://github.com/Alvarez-Jose/agile-sourcing.git
cd agile-sourcing
```

### 2. Create a virtual environment and install dependencies

```sh
python3.12 -m venv venv
./venv/bin/python -m pip install --upgrade pip setuptools wheel
./venv/bin/python -m pip install -r requirements.txt && ./venv/bin/python -m pip check
cd frontend
corepack pnpm install --frozen-lockfile
cd ..
```

Wait for both installations to finish successfully before continuing.

### 3. Configure Firebase authentication

```sh
mkdir -p secret
```

Obtain the team's Firebase configuration and authorized Admin SDK JSON privately,
or configure your own Firebase project using the [auth guide](docs/auth-setup.md).
Place the shared environment file at `secret/.env` and the Admin JSON inside
`secret/`. These files are ignored by Git.

<!-- In `secret/.env`, set `GOOGLE_APPLICATION_CREDENTIALS` to the JSON filename and
`VITE_API_BASE_URL=http://localhost:8000`, alongside the Firebase and Google OAuth
values listed in the auth guide. Register your browser extension's actual redirect
URL in the Google OAuth client as described there. -->

### 4. Start Ollama and download the model

Open the Ollama application, or run this in a separate terminal and leave it running:

```sh
ollama serve
```

If port 11434 is already in use and `ollama list` succeeds, Ollama is already
running. In your setup terminal, download the model:

```sh
ollama pull qwen3:8b
ollama list
```

### 5. Add policy documents and build the index

```sh
mkdir -p data/raw_policies
```

Obtain the team's policy PDFs/DOCX and place them directly in `data/raw_policies/`.
The full document collection is not included in Git. For a small demo corpus,
you can download the reviewed BUS-43 and SSPR starter documents instead:

```sh
./venv/bin/python -m scripts.download_starter_policies
```

Once the documents are present, build the Chroma index:

```sh
./venv/bin/python -m scripts.ingest_policies --ingest
```

The script should report how many chunks it stored in
`data/embeddings/chroma_store`. The first run downloads the embedding model;
the reranking model downloads when chat first loads.

### 6. Run the backend and extension

Keep Ollama running. Open two more terminals and navigate to your cloned
`agile-sourcing` directory in each.

**Backend terminal:**

```sh
./venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

**Extension terminal:**

```sh
cd frontend
corepack pnpm dev
```

WXT should open a development browser. If loading manually in Chrome, enable
Developer mode at `chrome://extensions`, choose **Load unpacked**, and select
`frontend/.output/chrome-mv3-dev`.

Check the API from another terminal:

```sh
curl http://localhost:8000/api/health
```

Expect `{"status":"ok"}`. This checks the API; test chat separately. Sign in with
Google, have an administrator set `users/{uid}.is_approved` to boolean `true` in
Firestore, then click **Sync Session with Backend** in extension settings. Try:
**How should I document price reasonableness on the SSPR form?**

## Testing

For the limited two-source CruzBuy cart-to-SSPR workflow, see the
[cart demo instructions](docs/cart-demo.md). Open **Cart helper** in the extension
popup while viewing your signed-in CruzBuy Simple Shopping Cart. It previews cart
details and asks for funding/charge confirmation before checking SSPR applicability.
It requires the two reviewed PDFs but does not use the general RAG or call Qwen.

```sh
./venv/bin/python -m pytest rules tests -q
cd frontend
corepack pnpm test
corepack pnpm compile
corepack pnpm build
```

The integrated RAG evaluation tools can be run separately:

```sh
./venv/bin/python -m evaluation.benchmarks.run_benchmark
./venv/bin/python -m evaluation.analyze_benchmark evaluation/results/benchmark_results_full.json
./venv/bin/python -m evaluation.check_citation_grounding /path/to/saved-api-responses.json --output data/evaluation/citation_grounding.csv
```

The original `run_benchmark` runner retains its defaults and output format; its
saved rows omit the evidence needed by the citation checker. On `cb-integration`,
the new evidence-preserving runner supports a short smoke evaluation:

```sh
./venv/bin/python -m evaluation.benchmarks.run_grounding_benchmark --limit 5 --out data/evaluation/cb_grounding_responses.json
./venv/bin/python -m evaluation.summarize_grounding data/evaluation/cb_grounding_responses.json --output data/evaluation/cb_grounding_summary.csv
./venv/bin/python -m evaluation.check_citation_grounding data/evaluation/cb_grounding_responses.json --output data/evaluation/cb_grounding_details.csv
```

Ollama, cached/downloaded models, and the main `uc_policies` index from setup step 5
are required. Increase `--limit` to 60 for the full question set. The runner stops
without writing results when that index is missing. These commands run the local
pipeline directly for developer evaluation; the browser-facing `/api/ask` endpoint
still verifies the Firebase token and requires account approval before invoking it.

Grounding checks flag invalid citation numbers, empty cited evidence, and dollar
amounts absent from evidence. They are diagnostics, not correctness grades or
automatic answer blocking. Purchase amounts supplied in a question may legitimately
be flagged for human review. The summary separates execution errors and refusals
from evaluated answers. An unflagged answer is not proof of a correct answer.

For a tool-only smoke check without Ollama, use the deliberately synthetic fixtures:

```sh
./venv/bin/python -m evaluation.summarize_grounding evaluation/results/citation_grounding_test.json --output data/evaluation/cb_fixture_summary.csv
```

Those four fixtures intentionally include three faulty responses; their counts are
not live Qwen benchmark results. See [the integration notes](docs/cb-integration.md)
for imported branch versions and validation limits. The performance table above is
the historical team baseline and was not rerun for these integration changes.

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
