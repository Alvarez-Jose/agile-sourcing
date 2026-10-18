# Authenticated chat on develop

`develop` integrates the team's main-branch RAG, the five open PR branches, and
Firebase/FastAPI authentication. The user requested that RAG and evaluation code
remain exactly as the teammate left it. The pipeline includes PR #7's DOCX citation
fix; the diagnostic scripts from PRs #8 and #9 are included without modifications.

## API boundary

1. Verify the Firebase ID token and retrieve the fresh server-owned Firestore profile.
2. Reject unapproved accounts before importing or invoking the RAG pipeline.
3. Call the team's unchanged `ask(question, think=...)` entry point.
4. Return its answer, sources, citations, rule sources, intent, determination, and
   refusal fields. A transport-only adapter exposes source `ref` as the extension's
   `citation_id` and source `text` as expandable supporting text. It does not modify
   rankings, answer wording, or refusal decisions, or invent section offsets/URLs.

Google sign-in, department, role, clearance, approval, and Firestore profile ownership
remain intact. **By the user's explicit decision, only authentication and approval
are enforced for chat at this stage.** The team's RAG has no per-user scope argument;
approved users share its indexed corpus. Document clearance filtering is deferred to
the RAG teammate. The existing `policy_scope()` helper and reviewed source/graph
index remain available for future integration but are not active retrieval controls.

The team's Chroma collection is `uc_policies`. Their BM25/semantic retrieval, intent
routing, cross-encoder, rules, Qwen prompts, model setup, token caps, timeouts, and
citation formatting remain unchanged. The earlier auth branch's span-ID generator,
full-parent expansion, and graph traversal are not the active chat implementation.

## Startup and testing

See [README](../README.md) and [auth setup](auth-setup.md). Use Python 3.12+ for the
unchanged DOCX citation PR's f-string syntax. Auth/health load no RAG models; optional
`RAG_WARM_UP=1` invokes the existing warm-up at API startup.

```sh
./venv/bin/python -m scripts.ingest_policies --ingest
./venv/bin/python -m uvicorn backend.main:app --reload --port 8000
# Separate terminal, from frontend/:
corepack pnpm dev
```

The policy source/graph tools still support offline inspection. Their versioned Chroma
publisher and the previous `scripts.evaluate_policy_chat` belong to the old auth
pipeline; they are not the team's current ingestion/benchmark entry points.

```sh
./venv/bin/python -m evaluation.benchmarks.run_benchmark
./venv/bin/python -m evaluation.analyze_benchmark evaluation/results/benchmark_results_full.json
./venv/bin/python -m evaluation.check_citation_grounding /path/to/saved-api-responses.json --output data/evaluation/citation_grounding.csv
```

The benchmark runner drops supporting sources from its saved scoring rows. The
citation checker needs complete response objects with `answer`, `sources`, and
`rule_sources`; it cannot validate provenance from those benchmark rows alone.
Known benchmark, routing, source-coverage, blank-answer, and grading issues remain
with the teammate rather than being changed during auth integration.

Previous live tests of a modified intermediate pipeline are not validation of this
final untouched version. Final verification and PR dispositions are recorded in
[the integration review](develop-integration.md).
