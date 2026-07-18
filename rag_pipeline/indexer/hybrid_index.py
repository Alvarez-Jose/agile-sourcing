"""
ingestion/hybrid_retriever.py

Hybrid BM25 + semantic search retriever.
Replaces the pure semantic search in main.py.

BM25 catches exact keyword matches (dollar amounts, policy numbers, form names).
Semantic search catches conceptual matches (paraphrases, natural language).
RRF (Reciprocal Rank Fusion) combines both ranked lists.

Usage:
    from ingestion.hybrid_retriever import HybridRetriever
    
    retriever = HybridRetriever(collection, embedder)
    docs, metas = retriever.retrieve("What is the competitive bidding threshold?")
"""

import math
import re
from collections import defaultdict

from sentence_transformers import SentenceTransformer


class BM25:
    """
    Simple BM25 implementation over a list of documents.
    No external dependencies — pure Python.
    
    BM25 ranks documents by term frequency weighted by inverse document frequency.
    Better than TF-IDF for short queries against long documents.
    """

    def __init__(self, documents, k1=1.5, b=0.75):
        self.k1 = k1
        self.b  = b
        self.documents  = documents
        self.doc_count  = len(documents)
        self.avg_dl     = 0
        self.doc_freqs  = []   # term freq per document
        self.idf        = {}   # inverse document frequency per term
        self.doc_lens   = []

        self._build_index()

    def _tokenize(self, text):
        text = text.lower()
        text = re.sub(r'[^\w\s$]', ' ', text)
        tokens = text.split()
        return [t for t in tokens if len(t) > 1]

    def _build_index(self):
        df = defaultdict(int)  # document frequency per term

        for doc in self.documents:
            tokens    = self._tokenize(doc)
            self.doc_lens.append(len(tokens))
            freq = defaultdict(int)
            for token in tokens:
                freq[token] += 1
            self.doc_freqs.append(dict(freq))
            for term in freq:
                df[term] += 1

        self.avg_dl = sum(self.doc_lens) / max(self.doc_count, 1)

        # IDF with smoothing
        for term, count in df.items():
            self.idf[term] = math.log(
                (self.doc_count - count + 0.5) / (count + 0.5) + 1
            )

    def score(self, query, doc_idx):
        tokens = self._tokenize(query)
        score  = 0.0
        dl     = self.doc_lens[doc_idx]
        freq   = self.doc_freqs[doc_idx]

        for term in tokens:
            if term not in freq:
                continue
            tf  = freq[term]
            idf = self.idf.get(term, 0)
            numerator   = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
            score += idf * numerator / denominator

        return score

    def get_top_n(self, query, n=10):
        scores = [(i, self.score(query, i)) for i in range(self.doc_count)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in scores[:n] if s > 0]


def reciprocal_rank_fusion(ranked_lists, k=60):
    """
    Combine multiple ranked lists using Reciprocal Rank Fusion.
    
    RRF score = sum(1 / (k + rank)) for each list.
    Higher score = better combined rank.
    
    k=60 is the standard constant from the original RRF paper.
    """
    scores = defaultdict(float)

    for ranked in ranked_lists:
        for rank, (doc_id, _) in enumerate(ranked):
            scores[doc_id] += 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    """
    Hybrid retriever combining BM25 keyword search and semantic vector search.
    
    - BM25: finds documents with exact keyword matches (thresholds, form names, policy numbers)
    - Semantic: finds documents with conceptual similarity (paraphrases, natural language)
    - RRF: merges ranked results from both
    
    Significantly better than pure semantic search for:
    - Exact dollar amount queries ("$100,000 threshold")
    - Policy form names ("SSPR form", "BAA", "Data Security Appendix")
    - Regulatory references ("BFB-BUS-43", "2 CFR 200", "FAR Part 12")
    - Post-employment queries where semantic embeddings are weak
    """

    def __init__(self, collection, embedder, top_k=8, bm25_weight=0.4, semantic_weight=0.6):
        self.collection      = collection
        self.embedder        = embedder
        self.top_k           = top_k
        self.bm25_weight     = bm25_weight
        self.semantic_weight = semantic_weight

        self._build_bm25_index()

    def _build_bm25_index(self):
        print("Building BM25 index...")
        all_data = self.collection.get(include=["documents", "metadatas"])

        self.all_docs   = all_data["documents"]
        self.all_metas  = all_data["metadatas"]
        self.all_ids    = all_data["ids"]

        # filter out short/TOC chunks for BM25
        self.valid_indices = [
            i for i, doc in enumerate(self.all_docs)
            if len(doc.strip()) >= 100
        ]
        self.valid_docs  = [self.all_docs[i]  for i in self.valid_indices]
        self.valid_metas = [self.all_metas[i] for i in self.valid_indices]

        self.bm25 = BM25(self.valid_docs)
        print(f"BM25 index built: {len(self.valid_docs)} documents")

    def retrieve(self, question, top_k=None):
        if top_k is None:
            top_k = self.top_k

        fetch_n = top_k * 3  # fetch more, filter down

        # ── BM25 retrieval ────────────────────────────────────────────────────
        bm25_results = self.bm25.get_top_n(question, n=fetch_n)
        # bm25_results: [(valid_idx, score), ...]

        # ── Semantic retrieval ────────────────────────────────────────────────
        query_vec = self.embedder.encode([question])[0].tolist()
        sem_results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"]
        )

        # map semantic results to global indices
        sem_docs  = sem_results["documents"][0]
        sem_metas = sem_results["metadatas"][0]
        sem_dists = sem_results["distances"][0]

        # build a lookup from doc content to valid_index for RRF merging
        doc_to_valid = {doc: i for i, doc in enumerate(self.valid_docs)}

        sem_ranked = []
        for doc, meta, dist in zip(sem_docs, sem_metas, sem_dists):
            if doc in doc_to_valid:
                valid_idx = doc_to_valid[doc]
                sem_ranked.append((valid_idx, 1 - dist))  # convert distance to similarity

        # ── RRF fusion ────────────────────────────────────────────────────────
        fused = reciprocal_rank_fusion([bm25_results, sem_ranked])

        # ── Build final result ────────────────────────────────────────────────
        result_docs  = []
        result_metas = []
        seen = set()

        for valid_idx, rrf_score in fused:
            if valid_idx in seen:
                continue
            seen.add(valid_idx)

            doc  = self.valid_docs[valid_idx]
            meta = self.valid_metas[valid_idx]

            if len(doc.strip()) < 100:
                continue

            result_docs.append(doc)
            result_metas.append(meta)

            if len(result_docs) >= top_k:
                break

        return result_docs, result_metas

    def reload(self):
        """Rebuild BM25 index — call after re-ingesting documents."""
        self._build_bm25_index()