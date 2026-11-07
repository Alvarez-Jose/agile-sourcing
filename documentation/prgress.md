# Project progress

Measurements describe their recorded
models, corpus, answer key, judge, and hardware; they are not interchangeable or
proof that every policy answer is correct.

## Progress records

- [Develop integration and PR review — October 18](develop-integration.md)
- [Dependency audit — October 18](dependency-audit.md)
- [Authenticated RAG integration — October 28](cb-integration.md)
- [Rules versus grounded pipeline — October 29](ab_rules_vs_grounded_2026-10-29.md)
- [Chunk enrichment experiment — October 29](enrichment_v1_2026-10-29.md)
- [Embedder fine-tuning experiment — October 29](embedder_finetune_v1_2026-10-29.md)

The November 6 validation report is retained locally as
`documentation/branch-integration-2026-11-06.md` and remains uncommitted as requested.
Generated diagnostic summaries and raw results remain with the evaluation artifacts.

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

- **Embedder fine-tune (adopted).** MiniLM fine-tuned on 12,345 generated (question, chunk) pairs; on a chunk-level held-out split, retrieval accuracy@1 rose from 28.7% to 41.0% and accuracy@5 from 56.7% to 74.6%. The end-to-end gain (+1 correct / −1 wrong) is within run-to-run noise; the held-out gain is the evidence it generalizes to phrasings beyond the benchmark. Details: [embedder fine-tuning results](embedder_finetune_v1_2026-10-29.md).
- **Private model slots.** Fine-tuned weights live in a private Hugging Face repo and load via `EMBED_MODEL` + `HF_TOKEN`; unset, everything falls back to the public base models, so the repo works for everyone out of the box. Private training data ships in the repo as AES-256 ciphertext (`*.enc`, `scripts/vault.sh`); plaintext stays untracked.
- **Chunk enrichment (tried, not adopted).** Contextual headers + likely questions per chunk scored no better than the baseline in either serving mode (36/60 and 39/60 vs 40/60); the generated questions were instead reused as the fine-tune training set. Details: [chunk enrichment results](enrichment_v1_2026-10-29.md).

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
same judge (qwen3:32b). Full analysis: [pipeline comparison](ab_rules_vs_grounded_2026-10-29.md).

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

## Integration status (November 6, 2026)

`develop` combines the authenticated extension and cart helper with the
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

The Git merge history records the integrated branches. See the
[cart demo guide](../docs/cart-demo.md) for supported workflow and source limits.
