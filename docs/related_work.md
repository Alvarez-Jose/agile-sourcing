# Agile Sourcing

## what is this

UCSC procurement handles 20k+ purchases a year with 9 people. the current process sucks — staff have to figure out which policies apply, which forms to fill, which suppliers to use, all on their own. theres like 15+ policy documents, some 66 pages long, and they all override each other depending on the situation.

we're building an AI agent that does all of that for them. you type what you need, it figures out the rules, finds options, and gives you a purchase request ready to go.

## the research angle

this isnt just a product — its a research project. the core question:

**how do you build a retrieval system that understands conditional dependencies across regulatory documents, where the rules that apply depend on variables the user gives you (funding source, dollar amount, purchase type)?**

standard RAG cant do this. it grabs text chunks that look similar to your query. but procurement compliance isnt about similarity — its about logic. a $75K purchase on an NIH grant triggers completely different rules than the same $75K purchase on campus funds, and those rules live in different documents that override each other.

so we're building a custom RAG pipeline from scratch. not wrapping langchain around chromadb — actually building the parser, the graph, the retriever, and the verifier ourselves.

## why off-the-shelf RAG breaks

normal RAG is like ctrl+F on steroids — it finds text that looks similar to your question. that works when the answer lives in one chunk. but procurement policy doesnt work that way:

- the answer to "can I buy this?" is spread across 15+ documents
- those documents conditionally override each other (federal rules beat UC rules beat campus rules)
- which rules apply depends on what the USER tells you (funding source, dollar amount, purchase type), not whats in the documents
- no single chunk contains the complete answer
- the retrieval path changes based on user variables, not just query semantics

so we need retrieval that understands rule hierarchy, conditional overrides, and user-specific context. thats what we're building.

## how it works

```
policy PDFs
    → policy-aware parser (breaks docs into rules, thresholds, exceptions)
    → regulatory knowledge graph (maps which rules override which, conditionally)
    → hybrid index (vector similarity + graph traversal)
    → multi-hop retriever (base rule → overrides → exceptions → required forms)
    → grounded verifier (checks every claim against retrieved policy)
    → response with citations
```

the key insight: use a deterministic rule engine for threshold logic (will never hallucinate on dollar amounts) and RAG for explanations and edge cases. the rule engine gives accuracy, the RAG gives context. use both.

## architecture

two agents:
- **conversation agent** — talks to the user, collects what they need, presents results perplexity-style
- **rules agent** — checks compliance, finds suppliers, fills forms, flags issues

agent 1 never submits anything without agent 2 signing off.

see `docs/architecture.png` for the full diagram.

## research plan

### phase 1 — policy parsing & knowledge graph (weeks 1-4)
**goal:** turn flat policy PDFs into a structured, queryable knowledge graph

- build a policy-aware parser that detects sections, subsections, rules, thresholds, exceptions, and cross-references in BUS-43, SSPR FAQ, UC T&Cs, etc.
- extract individual rules as typed nodes with metadata (document source, section number, conditions, authority level)
- map conditional dependencies between rules across documents ("BUS-43 threshold is overridden by SSPR when funding = federal AND amount > $50K")
- build the regulatory knowledge graph with nodes (rules, thresholds, forms, exceptions) and edges (overrides, requires, cross-references, conditional-on)
- validate graph structure against real procurement buyer knowledge

**deliverable:** a structured knowledge graph from UC procurement policy documents with conditional inter-document dependencies mapped

### phase 2 — custom retrieval pipeline (weeks 5-8)
**goal:** build multi-hop constrained retrieval that navigates the policy graph based on user variables

- build hybrid index combining vector embeddings (for semantic similarity) with graph structure (for rule relationships)
- implement multi-hop retriever: given user inputs (amount, funding source, purchase type), traverse the graph — base rule → funding-source overrides → purchase-type exceptions → required forms → insurance requirements
- add constraint propagation — each hop narrows applicable rules based on user variables
- build reranker that scores retrieved rules by relevance, authority level, and specificity
- implement grounded verification — after LLM generates a compliance determination, check every claim against retrieved policy chunks. flag unsupported claims.

**deliverable:** a working retrieval pipeline that, given a purchase scenario, returns the correct set of applicable rules with citations

### phase 3 — evaluation & benchmark (weeks 9-12)
**goal:** prove the system works and measure it rigorously

- build the procurement compliance benchmark — purchase scenarios with buyer-validated ground truth:
  - low value office supplies (<$10K, non-federal)
  - federal grant equipment ($75K microscope on NIH grant)
  - sole source niche item (lab robot, foreign supplier)
  - service contract (triggers contracting-out / Regents 5402)
  - restricted items (controlled substances, vehicles)
  - mixed funding (federal + non-federal split)
  - foreign supplier with restricted party screening
- run baselines:
  - **naive RAG** — standard chunk + embed + retrieve with chromadb
  - **keyword search** — BM25 / TF-IDF
  - **LLM-only** — no retrieval, just ask GPT-4o
  - **rule engine only** — deterministic rules, no RAG
- measure:
  - **retrieval precision/recall** — did it find ALL applicable rules?
  - **compliance path accuracy** — did it determine the correct compliance requirements?
  - **form identification accuracy** — did it identify the right forms?
  - **citation accuracy** — are policy citations correct and sufficient?
  - **hallucination rate** — what % of compliance claims are unsupported by retrieved policy?
- compare our custom pipeline against all baselines across all scenarios
- have UCSC procurement buyers evaluate system output vs what they would do

**deliverable:** a benchmark dataset, baseline comparisons, and evaluation results showing our approach vs standard methods

### why this evaluation is novel

theres no existing benchmark for this. legal RAG benchmarks test case law reasoning. financial RAG benchmarks test document summarization. nobody has a test set that says "given this purchase scenario, here is the correct compliance path with the correct forms, thresholds, and citations." we're building that benchmark as part of the research contribution — not just the system, but the ground truth to measure it against.

## related work

### tier 1 — peer-reviewed, top venues

**LegalGraphRAG** — Zhang et al. (ACL 2026)
https://arxiv.org/abs/2605.28120
Hierarchical legal graph + multi-agent verification for legal reasoning. closest to what we're doing but focuses on case law, not regulatory compliance with conditional user-variable-driven retrieval.

**MultiDocFusion** — Shin et al. (EMNLP 2025)
https://aclanthology.org/2025.emnlp-main.1062/
LLM-based hierarchical parsing for document structure trees. improved retrieval precision 8-15%. relevant to our policy-aware parser.

**Multi-Agent RAG for Regulatory Compliance** (ACM 2025)
https://dl.acm.org/doi/pdf/10.1145/3785472
Multi-agent RAG for GDPR compliance checking. handles cross-references and conditional structures. they check software requirements, we check purchase requests.

**RAG for Drug Regulatory Compliance** (PubMed 2025)
https://pubmed.ncbi.nlm.nih.gov/41709726/
RAG for FDA compliance in pharma. results aligned with manual expert reviews. proves RAG can work for regulatory domains.

### tier 2 — strong preprints & references

**HiChunk** — Tencent Youtu Research (2025)
https://arxiv.org/pdf/2509.11552
Code: https://github.com/TencentYoutuResearch/HiChunk.git
Dataset: https://huggingface.co/datasets/Youtu-RAG/HiCBench
Multi-level hierarchical chunking with auto-merge retrieval. open source + public benchmark.

**C2RAG** — (March 2026)
https://arxiv.org/pdf/2603.14828
Introduces sufficiency checks before multi-hop propagation. prevents retrieval hallucination. directly relevant to our verifier.

**AGORA Policy QA** — (March 2026)
https://arxiv.org/abs/2603.24580v1
Key finding: better retrieval doesnt guarantee better answers. validates why we need a verification layer on top of retrieval.

**Graph RAG Survey** — Peng et al. (2024)
https://arxiv.org/abs/2408.08921
Comprehensive survey of GraphRAG approaches. good for positioning.

### resource list

**Awesome-GraphRAG**
https://github.com/DEEP-PolyU/Awesome-GraphRAG
Curated list of GraphRAG papers, benchmarks, and open-source projects.

## gaps we're filling

1. **conditional inter-document dependencies** — nobody models "rule A applies UNLESS condition X, then rule B from a different document takes over"
2. **user-variable-driven retrieval** — retrieval path depends on what the user tells you, not just query text
3. **procurement compliance benchmark** — no ground truth dataset exists for this domain
4. **hallucination measurement in regulatory context** — wrong claim = audit finding, nobody measures this specifically
5. **end-to-end system for real use** — tested against real procurement workflows with real buyers

## project structure

```
agile-sourcing/
├── rag_pipeline/              ← the research (custom RAG from scratch)
│   ├── parser/                # policy-aware doc parsing
│   ├── graph/                 # regulatory knowledge graph
│   ├── indexer/               # hybrid vector + graph index
│   ├── retriever/             # multi-hop constrained retrieval
│   ├── verifier/              # hallucination detection for compliance
│   └── generator/             # grounded response + citations
├── backend/                   ← the application layer
│   ├── agents/                # conversation + rules agents
│   ├── rules_engine/          # deterministic threshold logic
│   ├── supplier/              # supplier search
│   ├── forms/                 # SSPR + PR auto-fill
│   └── api/                   # FastAPI routes
├── evaluation/                ← how we prove it works
│   ├── benchmarks/            # test scenarios + ground truth
│   ├── baselines/             # naive RAG, keyword, LLM-only
│   ├── metrics/               # retrieval accuracy, hallucination rate
│   └── scenarios/             # real purchase test cases
├── frontend/                  # Angular app
├── data/policies/             # the actual policy PDFs
├── experiments/               # notebooks + configs
├── paper/                     # LaTeX writeup
└── docs/                      # architecture diagrams, related work
```

## tech stack

| what | prototype | production |
|------|-----------|------------|
| LLM | OpenAI GPT-4o / Claude API | self-hosted Llama 3 (if UC requires) |
| orchestration | raw python API calls | LangGraph |
| vector DB | Chroma | pgvector |
| graph | NetworkX | NetworkX or Neo4j |
| backend | FastAPI | FastAPI |
| frontend | Streamlit | Angular |
| database | SQLite | PostgreSQL |
| auth | none | UC SSO (CruzID) |

heads up — UC T&Cs section 7.1 says AI use with institutional data needs Chancellor approval. we use public policy docs + fake purchase data for the prototype to avoid this blocker.

## setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# add your API keys

# ingest policy docs
cp /path/to/pdfs/* data/policies/
python scripts/ingest_policies.py
python scripts/build_policy_graph.py

# run evaluation
python scripts/run_evaluation.py
python scripts/compare_baselines.py

# run app
uvicorn backend.main:app --reload --port 8000
```

## team

UCSC Procurement + Dev Team — Spring 2026