# Source index and policy graph

The policy source index stores complete document sections, structured tables,
revision/effective-date observations, source locations, and access/review metadata
in SQLite. Small child chunks point to their full parent sections. A separate
evidence-backed graph connects documents, sections, forms, and explicit references.

The source index and graph remain available for offline review. Current chat uses
the team's unchanged main RAG and `uc_policies` collection. Per-user document
filtering is deferred; offline index controls do not apply to the current chat
endpoint. See [policy chat](policy-chat.md).

## Build and inspect without an LLM

Run from the repository root:

```sh
./venv/bin/python -m scripts.build_policy_graph build --preview
./venv/bin/python -m scripts.build_policy_graph build
```

The preview extracts and validates every source without writing the generated
outputs. The build writes:

- `data/parsed/policy_index.sqlite`: authoritative documents, source blocks, tables,
  hierarchical full sections, child chunks, dates, graph nodes/edges, and a text-search index.
- `data/graphs/policy_index/graph.json`: local graph inspection export, including evidence quotes.

Both outputs are ignored by Git and created with owner-only file permissions.
The original PDF/DOCX files are preserved. Errors abort the build; incomplete results
do not replace a working SQLite index. Replaced source-byte versions are retained in
SQLite as archived records, excluded from default reads.

Source-only preparation uses the graph builder, separately from team RAG ingestion:

```sh
./venv/bin/python -m scripts.build_policy_graph build
```

Inspect the supplied, unreviewed internal corpus explicitly:

```sh
./venv/bin/python -m scripts.build_policy_graph documents --local-review
./venv/bin/python -m scripts.build_policy_graph search "price reasonableness" --local-review
./venv/bin/python -m scripts.build_policy_graph traverse '<version_id from documents>' --local-review --hops 2
```

Without `--local-review`, CLI reads use the same conservative default as the library:
active public documents only. Local review is an operator tool, not an authorization
mode to enable from a browser query or LLM request.

## Document manifest

`data/policies/document_manifest.json` registers source documents using stable
IDs and filename aliases. Punctuation/case differences in downloaded filenames do
not break document identity. Unknown files require registration instead of being
silently indexed under a guessed identity. Source discovery includes nested folders.

Each entry records title, policy ID, document kind, category, explicit reference
aliases, access classification, review status, source URL, and review provenance.
Unverified sources use conservative `internal` / `review` defaults. The official
January 2026 BUS-43 interim PDF and December 2025 UCSC SSPR PDF are public/active;
the old BUS-43, supplied SSPR DOCX and obsolete FAQ are archived. The checklist and
other supplied sources remain under review. See [the source review](policy-source-review.md).
`archived_sha256` excludes older/alternate bytes of an identity whose current verified
version is active. Changed unrecognized active bytes still fail validation.

After checking the exact source version and its issuing authority, a reviewer can set:

```json
{
  "review_status": "active",
  "access_classification": "public",
  "source_url": "https://issuing-authority.example/verified-source",
  "reviewed_by": "reviewer identifier",
  "reviewed_at": "2026-10-09T00:00:00Z",
  "reviewed_sha256": "the full 64-character source SHA-256 shown by documents"
}
```

These fields update the existing manifest entry; its ID, filenames, kind and aliases
remain present. Choose the real access classification, not necessarily `public`.
An active entry requires reviewer/date/byte hash, and a source changed after review
fails validation until its new bytes are reviewed. Explicit Internal UC markings
cannot be downgraded to public by a manifest flag.

Dates are observations with their original text and source locations, not guessed
from filenames. Multiple dates remain available rather than silently selecting the
largest number as a policy's effective date. DOCX pages remain unknown; locations
use OOXML parts and element paths. PDFs use physical one-based pages and table bboxes.

## Full sections and child chunks

PDF extraction retains page text, layout-derived heading hints, and structured table
cells. DOCX extraction preserves body order, hyperlink text, tables/merge information,
text boxes, checkbox/symbol markers, headers, footers and notes. Table text may appear
alongside preserved hyperlink targets (including their actual XML/annotation locations)
in the source records. Table text may also appear
in the page transcription and in a structured table view; both representations have
source provenance. Repeated PDF running headings remain in source text but do not
automatically split a continuous section at each page boundary.

Sections have hierarchical parent IDs and complete text including nested sections.
Child ownership is partitioned so full ancestors are not embedded repeatedly.
Short tails and long sentences are retained; child text must exactly equal its
stored parent character span. Every child includes `parent_section_id`, document
version, offsets and source locations.

Offline preparation uses a deterministic lexical tokenizer (240-token windows,
40-token overlap), explicitly labelled `lexical-v1`. It is not claimed to be a model
token count. Embedding builds rechunk using the actual embedding tokenizer's offset
mapping and validate its real input budget before encoding; no silent truncation.

## Graph semantics

Node types:

- `document`: a byte-versioned source with review/access metadata.
- `section`: a complete source section, including table/header/footer views.
- `form`: a registered form with a link to its source document.
- `reference`: an explicitly cited external FAR/CFR provision not supplied as a document.

Automatically built relationships are `contains`, `has_source`, and `references`.
Each edge stores its document version, source section, exact character offsets,
verbatim quote, and source locations. Validation checks every quote against the
actual section and every endpoint against an existing node.

Reference aliases use whole-word matching and longest matching names first. An
unresolved FAR/CFR reference is labelled unresolved, not fabricated into a sourced
policy. HTTP hyperlinks are source-backed unresolved reference nodes; they are not
assumed to serve the same byte version as a locally supplied document. No URLs are
fetched during graph construction. Self-references are skipped. No summaries, similarity matches, dollar
amounts or occurrences of the word "override" generate an `overrides` edge.

The schema only accepts an override with explicit conditions, source evidence and
a recorded reviewer/date. Graph traversal does not apply even a verified conditional
override without a purchase-context condition evaluator; that evaluator is later work.

`PolicyIndex(path, scope)` and `PolicyGraphIndex(path, scope)` filter documents,
chunks, parents, nodes and edge endpoints according to a trusted `AccessScope`.
Future FastAPI callers must derive that scope from server-owned authorization,
not accept it from user input. Auth/user profiles remain in Firestore.

## Chroma bridge

The Chroma view stores child text/embeddings and primitive metadata linking back to
SQLite: document ID/version, `parent_section_id`, chunk ID, offsets, source hash,
page range/section, access classification, review status and date observations.

The `rag_pipeline.indexer.source_chroma` library supports this offline publisher.
It selects reviewed public sources and writes versioned collections. Preview
collections are separate. Each generation pins an immutable SQLite snapshot, and
the runtime pointer changes only after a successful build.

This workflow is separate from the team's restored ingestion CLI. Their unchanged
RAG reads `uc_policies`, populated by `scripts.ingest_policies --ingest`, and does not
read this publisher's pointer or enforce its source-review/access metadata.

Neither preparation nor graph building downloads models or calls an LLM. Embedding
preview/publication loads the local embedding model; model downloads may occur if its
weights are not cached. None of these commands uploads source documents to a hosted LLM.

## Tests

```sh
./venv/bin/python -m pytest tests/unit/rag/test_source_index.py tests/integration/test_auth.py rules/test_engine.py -q
```

Tests cover source preservation, tables/headers/text boxes, exact child spans,
date provenance, stable IDs, byte-review invalidation, references versus overrides,
atomic rebuilds, archived versions, access filtering and Chroma publication isolation.
