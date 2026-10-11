# Grounded policy chat

`POST /api/ask` now uses the reviewed SQLite source index, full parent sections and
one hop of explicit policy references. It never uses legacy Chroma chunks to bypass
review or permissions. The Chroma publishing bridge remains available for vector
exports; chat ranks an authorized source snapshot directly, so source/access changes
apply without rebuilding a separate vector collection.

## Request flow

1. Verify the Firebase token and load the fresh Firestore profile.
2. Reject pending accounts. Derive an exact clearance grant on the server.
3. Open one read-only SQLite snapshot; filter documents, sections, chunks and graph
   endpoints before decoding their payloads or passing their text to model hooks.
4. Combine BM25 and local semantic ranking, then cross-encoder rerank the candidates.
   Retain short policy instructions; suppress heading-only/header/footer records and
   revision-history sections as answer candidates.
   Explicitly named sources must be available in the user's reviewed corpus;
   otherwise abstain before model calls. Named sources supply the primary results.
5. Expand useful matches into full sections. Large sections use explicitly marked,
   source-aligned partial excerpts. Context is bounded to six passages / 24,000
   source characters, with at most two reference additions. Traverse only explicit
   `references` to available documents/sections/forms. No URL fetches or overrides.
6. Ask local `qwen3:8b` for structured claims and numbered supporting source spans
   using Ollama JSON mode. The server partitions full context at original block and
   paragraph boundaries, preserving all non-whitespace content, footnotes and page
   transitions. It supplies the original quote and offsets for each selected span.
   Validate the schema, source/span IDs and numerical facts. One repair is allowed;
   invalid/insufficient evidence produces an abstention. Literal supporting quotes
   also require exact source matches, with equivalent typography permitted.
7. Return cited document/section/version, evidence offsets and PDF physical pages.
   The UI links official sources and displays the supporting quotes. DOCX pages
   remain unknown. Chat history and late responses clear on session/clearance changes.

The old deterministic threshold engine is excluded from chat until its rules have
current source/version provenance. Its existing standalone tests still run. Local
models are loaded lazily; Firebase/login/health do not require loading ML models.
Ollama calls are pinned to `http://127.0.0.1:11434`, not cloud model names.

## Clearance grants

All values come from `users/{uid}` in Firestore. Request-body permissions are rejected.

| Approved user's `clearance` | Accessible classifications |
| --- | --- |
| `none`, `public`, missing, or an unknown value | public |
| `internal` | public, internal |
| `restricted` | public, internal, restricted |

Only **active** documents are available, even for restricted users. Role `admin`,
email domain, department name, and legacy strings such as `department_buyer` do not
implicitly grant internal access. This controls document visibility, not purchasing
or signing authority. No private profiles were edited during implementation.

## Run and test

From the repository root, restore/build the starter sources as described in
[the source review](policy-source-review.md). Then:

```sh
# Terminal 1; if Ollama is already running, this is unnecessary.
ollama serve
# Terminal 2
./venv/bin/python -m uvicorn backend.main:app --reload --port 8000
# Terminal 3
cd frontend
pnpm dev
```

An approved user with clearance `none` can test the two public starter sources.
Try: “How should I document price reasonableness on the SSPR form?” Then expand
Supporting text and check the page/link. Questions requiring the unverified checklist
or private supplier/order records should receive an insufficient-evidence response.

```sh
./venv/bin/python -m pytest tests/unit/rag/test_source_index.py tests/unit/rag/test_grounded_chat.py tests/integration/test_auth.py rules/test_engine.py -q
./venv/bin/python -m scripts.evaluate_policy_chat
# Additionally exercise actual local models; do not expect instant responses.
./venv/bin/python -m scripts.evaluate_policy_chat --live --output /private/tmp/policy-chat-evaluation.json
cd frontend
pnpm test
pnpm compile
```

The evaluation checks expected evidence and answer/abstention behavior for price
reasonableness, funding thresholds with campus qualification, informal quote counts,
sole-source brand justification, annual bidding, unavailable checklist and unknown
supplier data. Unit/integration tests separately exercise unauthorized, pending,
internal/restricted access, clearance reduction, graph filtering and malformed
citations. Test policies are synthetic, not actual procurement guidance.

Source-span validation proves provenance, not complete semantic entailment. Inspect live
answers against their supporting text for funding type, exceptions, annual versus
aggregate amounts and campus qualifications. These checks are a starter evaluation,
not an accuracy guarantee for arbitrary questions. The detailed live report is local
and should not be committed if additional internal sources are later activated.

## Verified implementation checkpoint

On October 10, 2026:

- 148 Python tests passed across the source index, grounded chat, authentication and
  standalone rules suites. Firebase calls are mocked in integration tests.
- 16 frontend tests passed, including source links and late-response isolation across
  logout, account changes and clearance reduction; TypeScript and the extension
  production build passed.
- All seven real local-Qwen cases passed retrieval, expected answer-content and
  abstention checks using numbered source spans. No grounding repair was needed in
  this final run. Answers were inspected against the cited excerpts. The annual
  bidding case retains separate supporting source spans on physical PDF pages 9–10.
- The runtime source snapshot contains two active public documents, three archived
  supplied byte versions, and 29 documents still under review. No override edges
  were introduced.

This small checkpoint is not a percentage accuracy estimate for the complete policy
corpus. In particular, the annual-bidding case checks the annual trigger and examples
of exceptions; it does not establish which exception applies to a particular purchase.
The unverified checklist and private supplier/order data remain unavailable.
