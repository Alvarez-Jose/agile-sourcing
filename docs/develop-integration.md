# Develop integration and PR review

Reviewed October 18, 2026. `develop` starts from `auth` at `bb1f71b` and contains
main at `864be07`, all fetched origin/fork branch tips, and the five open PR branches.
`auth` and `main` have not been advanced. Integration merges preserve original history.
GitHub PRs remain open for the team's review before develop is proposed for main.

## Scope agreed with the user

- Use the teammate's main RAG and merge the pending teammate PRs.
- Preserve the teammate's RAG, rules, ingestion, and evaluation code exactly. My
  intermediate RAG/evaluator fixes have been removed from the final working tree.
- Preserve Google/Firebase sign-in, FastAPI token verification, fresh Firestore
  profiles, server-owned permissions, and administrative account approval.
- Enforce sign-in and approval only for current chat. The user explicitly deferred
  document-clearance filtering to the RAG teammate. Department/role/clearance are
  still stored and returned; approved users share the team's indexed corpus.
- Keep the API/UI citation adapter outside RAG. It exposes `ref` as `citation_id`
  and `text` as supporting text without changing answer wording, rankings, refusal
  decisions, or original citation fields. It invents no source offsets or URLs.

## Pull requests

| PR | Integration outcome |
| --- | --- |
| [#1](https://github.com/Alvarez-Jose/agile-sourcing/pull/1) — frontend template | Already merged upstream; inherited through main/auth. |
| [#2](https://github.com/Alvarez-Jose/agile-sourcing/pull/2) — extension UI | Already merged upstream; inherited, with Firebase-backed sessions retained. |
| [#3](https://github.com/Alvarez-Jose/agile-sourcing/pull/3) — extension starting point | Already merged upstream; inherited. |
| [#4](https://github.com/Alvarez-Jose/agile-sourcing/pull/4) — rule engine | Already in main. Its RAG, rules, provenance, formatting, token caps, timeouts, refusals, and corrected answer key become the active implementation. |
| [#5](https://github.com/Alvarez-Jose/agile-sourcing/pull/5) — cleanup | Merged `62049b9`. The fetched tip's diff is README-only despite its broader description; substantive deletion changes arrive through #6. |
| [#6](https://github.com/Alvarez-Jose/agile-sourcing/pull/6) — CI | Merged `9191999`. Accepted empty-stub cleanup; retained graph/index/build files that auth has implemented. CI now includes auth/source-index dependencies and frontend checks and runs on develop pushes. |
| [#7](https://github.com/Alvarez-Jose/agile-sourcing/pull/7) — DOCX citations | Merged `1827ca5`. Pipeline and citation helper match this branch byte for byte. Unknown DOCX pages use section labels. Its f-string syntax requires Python 3.12+. |
| [#8](https://github.com/Alvarez-Jose/agile-sourcing/pull/8) — benchmark analysis | Merged `565644d`, script and historical CSV/Markdown reports unchanged. |
| [#9](https://github.com/Alvarez-Jose/agile-sourcing/pull/9) — citation grounding | Merged `dcf1d7e`, script and sample fixtures unchanged. |

The additional `improve-rule-engine` tip `e3836f4` is merged; its README change was
already represented in main. Earlier frontend/fork branches are ancestors of the
combined history. No branch was deleted and no PR review/comment was submitted.

## Code preservation verification

Compared raw file bytes with fetched Git refs, not just behavior:

- `backend/rag/pipeline.py` and `backend/rag/citations.py`: `origin/fix/docx-citation-page`.
- Main's hybrid retriever, intent classifier, reranker, metadata tagger, ingestion,
  benchmark runner, grader, and every `rules/` file: `origin/main`.
- `evaluation/analyze_benchmark.py`: `origin/nathan/benchmark-error-analysis`.
- `evaluation/check_citation_grounding.py`: `origin/nathan/citation-grounding-evaluation`.
- Auth's source-index Chroma library and old starter evaluation are retained unchanged;
  they are not the current main RAG entry points.

The intermediate scope adapter under `backend/rag/access.py` has been removed.
All teammate RAG/evaluation source comparisons pass. Future fixes belong to the teammate.

## Final verification

- **211 Python tests passed, 2 skipped** across `rules` and `tests`. The skips are
  external FAR source quote checks. Firebase identity/storage are mocked.
- **16 frontend tests passed**, TypeScript compilation passed, and the Chrome
  production build passed using Node 22.23.0.
- API integration tests exercise identity/approval gating, the original main
  `ask(question, think=...)` call shape, response metadata, and optional warm-up.
- Citation transport tests preserve original source numbering/text and do not
  invent section offsets or source URLs. The team's four diagnostic fixtures
  correctly flag their three deliberately invalid responses.
- All fetched remote branch tips are ancestors of develop. Secrets, raw policy
  files, generated databases/reports, and the user's untracked spreadsheet are
  excluded from this integration commit.

The local venv uses Python 3.10; final unchanged RAG requires Python 3.12+ because
of #7. Therefore earlier live checks of an intermediate modified pipeline are not
claimed as final live verification. Run the unchanged team ingestion and benchmark
in a Python 3.12/3.13 environment before merging develop into main. The full
60-question benchmark and production Google/Firebase login were not rerun against
this final version. CI uses Python 3.13 and must be checked after branch publication.

## Known limitations left for the RAG teammate

The teammate reports 49/60 top-document retrieval (previously 40/60), seven corrected
expected answers, three questions needing Procurement rulings, three requiring
absent federal evidence, and no meaningful benefit from five larger models over
local thinking-mode Qwen. These are team-reported baseline findings, not new develop
measurements. No model change was made.

The unchanged benchmark runner saves answer/scoring fields without sources or rule
provenance; the citation checker instead needs complete saved API responses. Its
input format and heuristics remain unchanged. Current observed routing, blank-output,
refusal-wording, numeric-grading, and report edge cases remain with the teammate.

The old auth source/graph index retains its review/classification controls for
inspection, but those are not active main-RAG filters. Existing auth-only starter
chat tests that assumed the replaced structured-span pipeline were removed; source
index, graph, and authentication tests remain. See [policy chat](policy-chat.md)
and [auth setup](auth-setup.md) for the current integration contract.
