# Embedder fine-tune v1: result — 2026-10-29

Fine-tuned `all-MiniLM-L6-v2` on the 12,345 generated (question, chunk) pairs
(`training/private/qa_pairs_v1.jsonl.enc`; builder `training/build_qa_pairs.py`;
trainer `training/finetune_embedder.py`). MultipleNegativesRankingLoss, in-batch
negatives, 2 epochs, batch 256, lr 2e-5, trained on a rented RTX 5090 in ~3 minutes.
Split is by chunk: every held-out question asks about a chunk never seen in training.

## Held-out IR eval (586 questions, 2,950-chunk corpus, dense-only)

| metric | base | tuned |
|---|---|---|
| accuracy@1 | 28.7% | **41.0%** |
| accuracy@5 | 56.7% | **74.6%** |
| mAP@5 | 0.392 | **0.540** |

## 60-question benchmark (updated key + FAR Part 12 corpus, qwen3:8b, judge qwen3:32b)

| | base | tuned |
|---|---|---|
| document recall@1 / @5 (no LLM) | 49/60, 59/60 | 48/60, 59/60 |
| judge CORRECT | 40/60 | **41/60** |
| judge PARTIAL | 13 | 13 |
| judge WRONG | 7 | **6** |

Result files: `bench_base_newkey_qwen8b.json`, `bench_tuned_newkey_qwen8b.json`
(+ `.judge.json`). These are also the first scores on the corrected key (Q13–15
aligned to the 12-2025 SSPR form) and the corpus with 48 CFR Part 12 — the earlier
39/60 (`ab_rules_qwen8b.json`) predates both and is not comparable.

## Verdict: adopted as the private embedder slot

End-to-end the tuned model is +1 correct / −1 wrong — inside the ±3 run-to-run
noise band, so the benchmark alone doesn't prove it. What tips it: the held-out
gain is large (+12.3pts accuracy@1 / +17.9pts accuracy@5) on questions about chunks
the model never saw, which is the embedder's actual job on real user phrasings
beyond the 60 benchmark questions; and document-level recall was already saturated
by BM25 + the cross-encoder (59/60 top-5), so the dense signal mostly decides
*which chunks within* the right document surface.

Deployment: weights live in the private HF repo `jalva182/uc-procurement-embedder`
(loaded via `EMBED_MODEL` + `HF_TOKEN`, Chroma collection re-ingested to match).
The public default stays `all-MiniLM-L6-v2` — the repo works for everyone without
the private slot.

## Next

- Hard-negative mining (near-miss chunks from the same document) + a reranker
  fine-tune on the same pairs: the reranker is now the main chunk-selection
  bottleneck.
- Include FAR Part 12 chunks in the next enrichment/pairs pass (postdates v1 data).
