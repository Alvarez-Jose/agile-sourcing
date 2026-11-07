# A/B: rules pipeline vs grounded (auth) pipeline — 2026-10-29

Both pipelines, same 60-question benchmark (`benchmark_questions_multi.json`, graded
against the corrected key), same LLM (qwen3:8b Q4_K_M, Ollama on an A100, 100% GPU),
same judge (qwen3:32b, temperature 0). Result files: `ab_rules_qwen8b.json`,
`ab_grounded_shipped_qwen8b.json`, `ab_grounded_full_qwen8b.json`.

| | rules (ours) | grounded as-shipped | grounded full-corpus |
|---|---|---|---|
| judge CORRECT | **39/60 (65%)** | 4/60 (6.7%) | 14/60 (23.3%) |
| judge CORRECT+PARTIAL | **56/60** | 28/60 | 32/60 |
| judge WRONG | **4** | 32 | 28 |
| refusals | 0 | 34 | 25 |
| median latency | **2.6s** | 5.7s | 9.5s |
| max latency | 5.3s | 27.2s | 42.6s |
| errors | 0 | 0 | 0 |

## Configurations

- **rules**: `--pipeline rules`. Rule engine + intent classifier + hybrid
  (BM25+MiniLM) retrieval + ms-marco cross-encoder, 8 chunks to the LLM.
- **grounded as-shipped**: `--pipeline grounded`. The auth branch pipeline exactly as
  merged: SQLite source index + policy graph + section retriever + JSON claims with
  span-verified quotes. Its manifest marks 29 of 32 documents internal/review and
  `ask()` refuses review scopes, so chat retrieves from only BUS-43 and the SSPR form.
- **grounded full-corpus**: `--pipeline grounded-full`. Same pipeline over an
  equalized index (`build_grounded_index.py`: all 33 local documents marked active),
  scope widened to public+internal+restricted.

## Why the grounded pipeline loses

1. **The review gate starves it.** As shipped, 31 of 33 local documents are
   unreachable through its own chat API (review scopes are rejected outright), which
   caps it at whatever BUS-43 and the SSPR form can answer: 34 of 60 questions came
   back "I couldn't find enough verified policy evidence."
2. **Span-verified claims abstain under pressure.** Even with the full corpus it
   refused 25/60. Every numeric claim must appear verbatim in a selected quote span;
   qwen3:8b often fails to pick valid spans twice in a row, and the pipeline then
   returns the refusal. Bigger models would repair more often, but the architecture
   trades coverage for provenance.
3. **No rule engine.** It dropped the deterministic threshold layer, so questions our
   pipeline answers from provenance-backed rules (exact thresholds, forms,
   prohibitions) depend entirely on retrieval + the 8B model.
4. **Latency.** Building per-question candidate rankings over 1,724 sections plus the
   JSON grounding loop costs 9.5s median vs our 2.6s.

## What the grounded pipeline does better (worth keeping)

- **Citation integrity.** When it does answer, each claim carries an exact source
  span with document version, byte offsets, and page locations — stronger provenance
  than our `[n]` chunk citations. On the full corpus, only 3 of its 35 actual answers
  were judged flat wrong.
- **Section-level retrieval.** Heading matches promote to the full parent section, so
  the LLM sees whole rules instead of chunk fragments.
- **Cross-policy reference hops.** "References" edges in the policy graph pull in the
  target document of an explicit mention (e.g. a form named by a policy).
- **Source review model.** Documents are hash-pinned; a changed file cannot silently
  serve answers. Operationally the right idea, but it needs a review workflow before
  it is usable — today it reduces the corpus to 2 documents.

## Verdict

The rules pipeline stays the default `/api/ask` path. Next steps: enrich the chunk
corpus (contextual headers + likely questions), fine-tune the embedder and reranker
on near-miss pairs, and consider adopting the grounded pipeline's section promotion
and reference hops inside our retriever — its provenance machinery is the part worth
keeping, its abstention-heavy answer path is not.
