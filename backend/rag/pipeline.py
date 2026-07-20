"""
backend/rag/pipeline.py
RAG pipeline entry point for the FastAPI backend.
Call ask() from your API routes to get answers from the UC policy corpus.
"""

import re
from pathlib import Path

import chromadb
import ollama
from sentence_transformers import SentenceTransformer

from rag_pipeline.parser.pdf_extractor import extract_pdf
from rag_pipeline.parser.docx_extractor import extract_docx
from rag_pipeline.parser.section_parser import chunk_by_section
from rag_pipeline.parser.metadata_tagger import tag_chunk
from rag_pipeline.indexer.hybrid_index import HybridRetriever
from rag_pipeline.retriever.intent_classifier import get_search_keywords

CHROMA_DIR      = "data/embeddings/chroma_store"
COLLECTION_NAME = "uc_policies"
EMBED_MODEL     = "all-MiniLM-L6-v2"
LLM_MODEL       = "qwen3:8b"
TOP_K           = 8

SYSTEM_PROMPT = (
    "You are a UC procurement policy assistant for UC Santa Cruz. "
    "Answer questions strictly based on the official UC policy excerpts provided. "
    "Never output placeholder text like [Cite policy] or [Policy Text]. "
    "Always provide the actual answer. "
    "Cite source numbers like [1], [2] for every claim you make."
)

embedder = SentenceTransformer(EMBED_MODEL)
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
_retriever = None


def get_collection():
    try:
        return chroma_client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


def _get_retriever(collection):
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(collection, embedder)
    return _retriever


def _rewrite_query(question: str) -> str:
    # Try intent classifier first
    keywords = get_search_keywords(question)
    if keywords:
        return keywords

    # Fall back to LLM keyword rewrite
    prompt = (
        "/no_think\n"
        "Convert this question into UC procurement policy search keywords only.\n"
        "Output keywords only, no question format, no punctuation, under 10 words.\n\n"
        "Question: " + question + "\n\nKeywords:"
    )
    response = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def ask(question: str, think: bool = False) -> dict:
    """
    Main entry point for the API.

    Returns:
        {
            "answer": str,
            "sources": [{"policy": str, "page": str}, ...]
        }
    """
    collection = get_collection()
    if collection is None:
        return {"answer": "Policy database not loaded. Run ingestion first.", "sources": []}

    retrieval_query = _rewrite_query(question)
    retriever = _get_retriever(collection)
    chunks, metas = retriever.retrieve(retrieval_query, top_k=TOP_K)

    context = ""
    sources = []
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        policy = meta.get("policy_name") or meta.get("source", "Unknown")
        page = meta.get("page", "")
        context += f"\n[{i+1}] {policy}, p.{page}\n{chunk}\n"
        sources.append({"policy": policy, "page": page})

    mode_tag = "/think" if think else "/no_think"
    prompt = (
        f"{mode_tag}\n\n"
        f"{SYSTEM_PROMPT}\n\n"
        "RULES:\n"
        "- Read every excerpt carefully before answering.\n"
        "- If ANY excerpt contains the answer, use it.\n"
        "- Cite source numbers [1], [2] etc. for every claim.\n"
        "- Be direct and specific.\n\n"
        f"POLICY EXCERPTS:\n{context}\n"
        f"QUESTION: {question}\n\n"
        "ANSWER:"
    )

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    answer = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    return {"answer": answer, "sources": sources}
