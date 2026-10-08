# rag_pipeline/retriever/reranker.py
# cross-encoder reranker that runs after the hybrid (BM25 + semantic) retriever.
# hybrid search finds chunks that look like the query, the cross-encoder reads the
# question and chunk together and scores if the chunk actually answers it.
# so: pull ~20 candidates with hybrid search, rerank, keep the top 5.
#
#   reranker = Reranker()
#   top = reranker.rerank(question, [{"document": d, "metadata": m} for d, m in zip(docs, metas)], top_k=5)

from sentence_transformers import CrossEncoder

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker:
    def __init__(self, model_name=DEFAULT_MODEL):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
        # chunks = list of dicts with "document" + "metadata" from the retriever
        # returns the top_k chunks sorted by cross-encoder score
        if not chunks:
            return []

        pairs = [(query, chunk["document"]) for chunk in chunks]
        scores = self.model.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)

        reranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]
