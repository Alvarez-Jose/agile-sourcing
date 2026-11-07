# evaluation/metrics/retrieval_recall.py
# measures retrieval on its own, no LLM: for each benchmark question, did the chunks the
# pipeline would hand to the LLM come from the policy document the answer lives in?
#
#   recall@5   - the reranked top 5 (what the LLM actually sees)
#   recall@20  - the hybrid candidate pool before reranking (what the reranker could pick from)
#   top score  - best cross-encoder score, the pipeline's refusal signal
#
# the expected document per question comes from EXPECTED_DOCS below (substrings of the
# policy_name metadata, any match counts). the rule engine is bypassed on purpose: this
# is about the retrieval path, so a question the engine would answer still counts.
#
#   python evaluation/metrics/retrieval_recall.py
#   python evaluation/metrics/retrieval_recall.py --pool 40 --out evaluation/results/recall_pool40.json
#   python evaluation/metrics/retrieval_recall.py --no-rerank

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# question number ranges -> acceptable policy_name substrings. the benchmark is built in
# triples (simple / scenario / edge_case) on one source fact, so the labels go by triple
_TRIPLES = {
    (1, 2, 3): ["BUS-43"],
    (4, 5, 6): ["BUS-43", "Source Selection & Price Reasonableness Justification Form"],
    (7, 8, 9): ["Source Selection & Price Reasonableness", "Federal Funds Checklist"],
    (10, 11, 12): ["BUS-43", "Source Selection & Price Reasonableness FAQ"],
    (13, 14, 15): ["Source Selection & Price Reasonableness", "Federal Funds Checklist"],
    (16, 17, 18): ["Independent Contractor"],
    (19, 20, 21): ["Business Associate Agreement"],
    (22, 23, 24): ["Data Security", "IS-3"],
    (25, 26, 27): ["Post-Employment"],
    (28, 29, 30): ["BUS-43", "Source Selection & Price Reasonableness"],
    (31, 32, 33): ["BUS-29"],
    (34, 35, 36): ["Tax-Free Alcohol"],
    # the $1M-per-occurrence figure is in the T&Cs' insurance article, not BUS-63 itself
    (37, 38, 39): ["BUS-63", "UC Terms and Conditions", "Operating Lease"],
    (40, 41, 42): ["Regents Policy 5402", "Article 5", "Contracting for Services"],
    (43, 44, 45): ["Conflict of Interest"],
    (46, 47, 48): ["Federal Funds Checklist", "UC Terms and Conditions"],
    (49, 50, 51): ["Source Selection & Price Reasonableness", "BUS-43"],
    (52, 53, 54): ["UC Terms and Conditions"],
    (55, 56, 57): ["G-13"],
    (58, 59, 60): ["BUS-79"],
}
EXPECTED_DOCS = {q: names for qs, names in _TRIPLES.items() for q in qs}


def hits(metas, expected):
    return [any(e in (m.get("policy_name") or "") for e in expected) for m in metas]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pool', type=int, default=None, help='override RERANK_POOL')
    parser.add_argument('--top-k', type=int, default=None, help='override RERANK_TOP_K')
    parser.add_argument('--no-rerank', action='store_true')
    parser.add_argument('--collection', default=None, help='chroma collection to search instead of the default')
    parser.add_argument('--reranker', default=None, help='cross-encoder model name to rerank with')
    parser.add_argument('--questions', default='evaluation/results/benchmark_questions_corrected.json')
    parser.add_argument('--out', default=None, help='write per-question results as json')
    parser.add_argument('--label', default='', help='name for this run in the summary line')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    from backend.rag import pipeline
    if args.pool:
        pipeline.RERANK_POOL = args.pool
    if args.top_k:
        pipeline.RERANK_TOP_K = args.top_k
    if args.collection:
        pipeline.COLLECTION_NAME = args.collection
    if args.reranker:
        from rag_pipeline.retriever.reranker import Reranker
        pipeline._reranker = Reranker(args.reranker)

    questions = json.load(open(args.questions, encoding='utf-8'))['questions']
    collection = pipeline.get_collection()
    if collection is None:
        sys.exit('no collection; run ingestion first')
    retriever = pipeline._get_retriever(collection)

    rows = []
    start = time.time()
    for i, q in enumerate(questions, 1):
        expected = EXPECTED_DOCS[i]
        intent = pipeline.classifier.classify(q['question'])
        search_query = intent['search_terms'] or q['question']

        # the candidate pool, same as pipeline._retrieve_reranked builds it
        pool_metas, seen, candidates = [], set(), []
        for query in dict.fromkeys([search_query, q['question']]):
            docs, metas = retriever.retrieve(query, top_k=pipeline.RERANK_POOL)
            for doc, meta in zip(docs, metas):
                if doc not in seen:
                    seen.add(doc)
                    candidates.append({"document": doc, "metadata": meta})
                    pool_metas.append(meta)

        if args.no_rerank:
            top = candidates[:pipeline.RERANK_TOP_K]
            top_score = None
        else:
            top = pipeline._get_reranker().rerank(q['question'], candidates, top_k=pipeline.RERANK_TOP_K)
            top_score = top[0]["rerank_score"] if top else None

        top_hits = hits([c["metadata"] for c in top], expected)
        pool_hits = hits(pool_metas, expected)
        rows.append({
            'q': i, 'difficulty': q['difficulty'], 'intent': intent['intent'],
            'expected': expected,
            'top_docs': [c["metadata"].get("policy_name") for c in top],
            'hit_at_5': any(top_hits), 'hits_in_top5': sum(top_hits),
            'first_hit_rank': (top_hits.index(True) + 1) if any(top_hits) else None,
            'hit_in_pool': any(pool_hits), 'pool_size': len(pool_metas),
            'top_score': round(top_score, 3) if top_score is not None else None,
        })

    n = len(rows)
    r5 = sum(r['hit_at_5'] for r in rows)
    rpool = sum(r['hit_in_pool'] for r in rows)
    r1 = sum(1 for r in rows if r['first_hit_rank'] == 1)
    avg_pool = sum(r['pool_size'] for r in rows) / n
    label = args.label or ('no-rerank' if args.no_rerank else f'pool={pipeline.RERANK_POOL}')
    print(f"{label:14s} recall@1 {r1}/{n}  recall@5 {r5}/{n} ({100*r5/n:.0f}%)  "
          f"recall@pool {rpool}/{n}  avg pool {avg_pool:.0f}  {time.time()-start:.0f}s")
    misses = [r['q'] for r in rows if not r['hit_at_5']]
    pool_misses = [r['q'] for r in rows if not r['hit_in_pool']]
    print(f"  missed@5: {misses}")
    print(f"  missed in pool: {pool_misses}")
    if args.out:
        json.dump(rows, open(args.out, 'w', encoding='utf-8'), indent=1)
        print(f"  wrote {args.out}")


if __name__ == '__main__':
    main()
