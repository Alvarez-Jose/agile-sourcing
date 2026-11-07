# cb-integration: authenticated teammate RAG and evaluation tools

Integrated October 28, 2026, only in the working tree on `cb-integration`, created
from `develop` at `6e6f87d`. No other local branch was advanced and no changes were
pushed. Imported selected source files rather than wholesale branch snapshots so
the Firebase API, frontend integration, and implemented source-index tools survive.

## Teammate changes incorporated

| Branch / commit | Incorporated behavior |
| --- | --- |
| `policy-correctness-guards-rule-engine`, `c4faa4c` | Rule explanations use threshold constants; provenance tests discover numeric constants and check source consistency. |
| `chore/api-grounding-ingest-guards`, `7c5b0e4` (including `4fea174`, `c436e3c`, `d886cc5`) | Shared grounding diagnostics in the teammate pipeline and evaluation CLI; ingestion error reporting, local CLI model-call caps/timeouts; finite/non-negative purchase validation. API timing/diagnostics integrated into our authenticated route. |
| `nathan/end-to-end-grounding-evaluation`, `5e2dc52` | Evidence-preserving benchmark runner, summary CLI, and evaluation tests. |

The RAG pipeline and rule-engine source files are byte-for-byte copies of the
safeguards branch tip. The earlier request to freeze the old RAG is superseded for
these teammate changes by the user's explicit request to integrate them here.
No threshold constants, expected benchmark answers, model choices, retrieval
ranking, or refusal decisions were independently changed.

The benchmark runner has one integration safeguard: it checks Ollama first, then
requires the actual `uc_policies` collection before running questions. Without it,
the pipeline's plain missing-database message could be misreported as an answer
with no citation issues. The guard has a regression test. The teammate's checked-in
sample summary was not imported as if it were a new local model result.

## Authentication remains the API boundary

`POST /api/ask` retains `Depends(require_approved_user)` and lazily imports the
pipeline only after authentication/approval succeeds. It retains fresh server-owned
Firestore profiles, revoked-token checking, strict approval, rejection of client
permission overrides, and source adaptation for the extension. The response adds
optional `grounding` and `elapsed_ms` fields without removing existing fields.
Health remains public and does not require the ML stack.

The teammate branch's unprotected API file was not copied. Its timing and diagnostic
response fields were added to the existing protected route instead. Tests cover
missing/invalid/expired/revoked/disabled credentials, unapproved users, approval
removal, authorized responses with grounding diagnostics, and compatibility when
diagnostics are absent. No new public evaluation endpoint was added. The offline
benchmark CLI invokes the pipeline directly and does not create an application
login or bypass an HTTP endpoint.

Document-level filtering and CruzBuy role synchronization remain unimplemented.
Approved accounts still share the indexed corpus. This integration also does not
implement cart extraction or CruzBuy page integration.

## Validation

- Full Python suite: **243 passed, 2 skipped** (`python -m pytest rules tests -q -rs`).
  The two skips are external FAR quote checks. Available local source quotes passed.
- Existing frontend authentication/session/citation tests: **16 passed**.
- Both grounding CLIs ran against the four synthetic diagnostic fixtures: three
  deliberately faulty cases flagged, one invalid citation, three unmatched-amount
  cases, zero execution errors. These are fixture checks, not model measurements.
- Local Ollama responds and lists `qwen3:8b`. Cached local model imports succeeded
  with model downloads disabled, but the five-question live runner correctly stopped
  because `uc_policies` is absent. No live question results or new accuracy figures
  are claimed. The existing versioned starter collection is a different collection.
- No policy index was rebuilt or raw document activated. Complete setup step 5
  using the intended, authorized corpus before a live benchmark, then restart the
  backend. Do not automatically index held documents merely to make a demo run.

The historical README scores remain unchanged. Grounding flags are heuristic review
signals and do not prove reasoning correctness or rewrite/block the answer. CI is
configured to run on `cb-integration` pushes; a hosted CI run is pending publication.
