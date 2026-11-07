# Develop integration — November 6, 2026

## Result and scope

`develop` now includes the tested integration from `cb-integration`, the latest
fetched `main`, `rag-v2-hybrid`, `chore/api-grounding-ingest-guards`, and
`rules/provenance-derived-constants`. Other fetched branch tips were already
ancestors of the combined history. No remote branch was pushed or changed.

The default chat endpoint uses the teammate's rule-engine Hybrid-RAG. The older
section/graph/claim-verification implementation remains available for experiments,
not as the default endpoint. Google/Firebase identity verification and fresh
server-owned Firestore approval still gate both chat and cart guidance. Document
clearance filtering remains unimplemented on this shared chat endpoint.

## What each branch contributes

| Branch | Kept contribution |
| --- | --- |
| `main` (`f81b42c`) | Shared history, evaluation runner/summary, repository guidance. |
| `rag-v2-hybrid` (`87aee2f`) | API-level thinking control, retry empty completions, eight reranked passages, reference-only explanations, policy ladders, configurable model/index slots, chunk headers, corrected answer key, retrieval evaluation, model comparisons, embedder-training experiments. |
| `chore/api-grounding-ingest-guards` (`7c5b0e4`) | API validation/errors, grounding diagnostics, ingestion failure reporting/timeouts, finite non-negative purchase validation. |
| `nathan/end-to-end-grounding-evaluation` (`5e2dc52`, through main) | Evidence-preserving benchmark runner, citation diagnostics summary, regression tests. |
| `policy-correctness-guards-rule-engine` (`c4faa4c`, through safeguards) | Threshold constants reused by explanations; source/provenance checks. |
| `rules/provenance-derived-constants` (`f47fb90`) | Independent coverage check for numeric rule constants. |
| `auth` (`bb1f71b`, inherited) | Firebase/FastAPI authentication, profiles, reviewed-source index and graph infrastructure. |
| `improve-rule-engine` (`e3836f4`, inherited) | Deterministic threshold answers, fixed determinations, refusals, token/time limits. |
| `fix/docx-citation-page` (`1827ca5`, inherited) | Section-aware DOCX citation formatting. |
| `ci/run-tests` (`9191999`, inherited) | Automated backend checks, retained alongside extension tests/build. |
| `chore/remove-empty-stub-files` (`62049b9`, inherited) | Removes empty placeholder modules. |
| `agentic-reference` (`4cd431a`, through main) | Agent guidance and project conventions. |
| `frontend-develop` (`e11bb17`, both remotes, inherited) | Extension UI/settings and package-manager groundwork. |
| `develop` / `fork/main` baseline | Existing frontend, authentication, dependencies, documentation and training history. |
| `cb-integration` | Explicit cart capture, preview/confirmation, deterministic SSPR helper, authenticated requests, launcher, sanitized fixtures and tests. |

## Preserved integration behavior

- Unauthenticated and pending accounts are rejected before chat execution or cart
  source reads. Browser-provided permission overrides cannot grant access.
- Auth and health remain available without importing ML; model warm-up is opt-in.
- Cart capture uses `activeTab` and `scripting` on the supported CruzBuy SimpleCart
  page. Purchase data is previewed and sent only after confirmation. No school
  password, 2FA, order submission, or broad automatic page scraping is implemented.
- Cart guidance still reads two hash-pinned sources directly and does not call Qwen.
- Source adapters preserve extension citation compatibility. Runtime grounding
  diagnostics remain warnings rather than automatic correctness guarantees.
- Launcher reads environment-configured model/collection slots without importing
  ML, passes configuration to its child processes, and preserves process ownership.
- Python requirements and frontend lockfile were preserved. Private weights are
  optional; encrypted upstream artifacts were not decrypted or activated.
- Ingestion retains upstream headers/enrichment hooks and existing failure exit
  status and model-call limits. No local corpus was rebuilt during integration.

## Verification

- Full Python suite on develop: **333 passed, 2 skipped**. The skips are external
  FAR 2.101 quote checks requiring separate source verification.
- Extension: **23 tests passed**, TypeScript compile and Chrome MV3 build passed.
- Synthetic cart regression scenarios: **8/8 passed** against the two reviewed PDFs.
- `pip check`: no broken requirements. `./run.sh --check`: passed.
- Added merge-boundary coverage for empty-answer retries/refusals, original evidence
  with enriched retrieval text, environment-configured launcher slots, and bounded
  judge calls. Blank/failed answers cannot receive a judge pass.
- Authentication uses simulated Firebase/Firestore boundaries in automated tests;
  no new live Google sign-in or private CruzBuy session was performed.

## Live benchmark

The 60-question live run uses installed `qwen3:8b` through local Ollama, the public
MiniLM embedder and public cross-encoder, eight reranked passages, and thinking off.
It reuses the local `uc_policies` index: **3,698 chunks from 34 documents**. FAR Part
12 is absent, so scores cannot be compared directly with the teammate's corrected
33-document corpus. No private embedder was loaded and no documents were activated.

Evidence, corrected-key answers, judge results, diagnostics and reproducibility
metadata are kept under ignored `data/evaluation/develop_2026-11-06_*` paths. Full
retrieved policy excerpts and user credentials are not added to Git.

### Completed local results

- **60/60 responses completed**, **0 execution errors**, **0 empty answers**,
  **0 refusals**. All 60 responses passed the extension response-model adapter.
- Mean latency **25.37 s**, median **26.91 s**, maximum **53.20 s**; total measured
  question time **1,521.99 s** (about 25.4 minutes), excluding initial imports.
- Corrected-key judge (`qwen3:8b`, temperature 0): **56 correct, 3 partial, 1 wrong**.
  Non-passing question IDs: **15, 42, 46, 47**. The corrected-key tool changed 17
  reference answers relative to the original key; generated answers were unchanged.
- Grounding diagnostics: **0 invalid citation identifiers**, **0 empty cited
  evidence**, **25 amount-review flags**. Of those, 23 include amounts supplied by
  the question. Two additional warnings (Q4/Q7) reflect the diagnostic's shorthand
  parsing (`$10K` / `$100K`), rather than proof of incorrect policy thresholds.
- Spot-checking the four non-passing answers found substantive reference-answer
  disagreements in mixed funding (Q15) and contracting-out (Q42), even though the
  judge called them partial. Q46/Q47 also require FAR Part 12, absent locally.
  These require source/expert review; the integration is not a claim that every
  policy answer is correct. No policy rules or reference answers were changed to
  improve this run's score.
- The 8B judge is optimistic and shares the answerer's model family. Its 93.3%
  correct figure is **not expert-validated procurement accuracy** and is not
  directly comparable with upstream 32B-judge/different-corpus measurements.

Historical README tables remain upstream measurements. Raw evidence, grade labels,
corrected-key results, per-question review notes and metadata are local under
`data/evaluation/develop_2026-11-06_*` and remain ignored by Git.

### Git state and user constraints

The integration merge on `develop` is `df5d3a2`. The final follow-up commit command
was declined, so README setup edits and bounded judge generation plus regression
tests remain uncommitted. This report is also uncommitted as explicitly requested.
The pre-existing requisition workbook remains untracked. No push was performed.

