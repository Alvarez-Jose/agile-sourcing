"""
scripts/ingest_policies.py - Agile Sourcing RAG
Ingest UC policy docs into ChromaDB, then query with local Qwen3.

Usage:
    python -m scripts.ingest_policies --ingest
    python -m scripts.ingest_policies --query "what is the competitive bidding threshold?"
    python -m scripts.ingest_policies --query "..." --think
    python -m scripts.ingest_policies --ingest --query "..."
"""

import argparse
import re
from pathlib import Path

from rag_pipeline.documents.build import prepare_source_index
from rag_pipeline.documents.models import AccessScope
from rag_pipeline.documents.store import (
    DEFAULT_INDEX,
    DEFAULT_MANIFEST,
    DEFAULT_SOURCES,
    write_source_index,
)
from rag_pipeline.indexer.source_chroma import (
    CHROMA_DIR,
    active_collection,
    chroma_records,
    embedding_chunks,
    publish_chroma,
)
from scripts.build_policy_graph import export_graph, progress


DATA_DIR = DEFAULT_SOURCES
COLLECTION_NAME = "uc_policies"
EMBED_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = "qwen3:8b"
TOP_K = 8

SYSTEM_PROMPT = (
    "You are a UC procurement policy assistant for UC Santa Cruz. "
    "Answer questions strictly based on the official UC policy excerpts provided. "
    "Never output placeholder text like [Cite policy] or [Policy Text]. "
    "Always provide the actual answer. "
    "Cite source numbers like [1], [2] for every claim you make."
)

embedder = None
chroma_client = None
hybrid_retriever = None


def get_embedder():
    global embedder
    if embedder is None:
        from sentence_transformers import SentenceTransformer

        print("Loading embedding model...")
        embedder = SentenceTransformer(EMBED_MODEL)
    return embedder


def get_client():
    global chroma_client
    if chroma_client is None:
        import chromadb

        chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return chroma_client


def ingest(prepare_only=False, preview_index=False, manifest_path=DEFAULT_MANIFEST):
    bundle = prepare_source_index(DATA_DIR, manifest_path, progress=progress)
    if prepare_only:
        bundle = write_source_index(bundle, DEFAULT_INDEX)
        export_graph(bundle)
        print("Source index and graph prepared; no embedding/LLM calls.")
        print(bundle.summary())
        return None
    if not preview_index and not chroma_records(bundle, AccessScope())[0]:
        raise ValueError(
            "No sources are reviewed/public yet. Run --prepare-only for the source graph, "
            "or --preview-index for a separate local review collection. "
            "Activate verified byte versions in data/policies/document_manifest.json before publication."
        )
    model = get_embedder()
    bundle = embedding_chunks(bundle, model)
    bundle = write_source_index(bundle, DEFAULT_INDEX)
    export_graph(bundle)
    collection = publish_chroma(bundle, model, preview=preview_index)
    print(f"Stored {collection.count()} source-aligned chunks in {collection.name}")
    if preview_index:
        print("Local preview only; the active assistant collection was not changed.")
    return collection


def get_collection():
    try:
        return active_collection(get_client())
    except Exception:
        print("No collection found — run with --ingest first.")
        return None


def get_retriever(collection):
    global hybrid_retriever
    if hybrid_retriever is None:
        from rag_pipeline.indexer.hybrid_index import HybridRetriever

        hybrid_retriever = HybridRetriever(collection, get_embedder())
    return hybrid_retriever


def retrieve(question, collection, top_k=TOP_K):
    retriever = get_retriever(collection)
    return retriever.retrieve(question, top_k=top_k)


def rewrite_query(question):
    import ollama

    prompt = (
        "/no_think\n"
        "Convert this question into UC procurement policy search keywords only.\n"
        "Output keywords only, no question format, no punctuation, under 10 words.\n\n"
        "Question: " + question + "\n\nKeywords:"
    )
    response = ollama.chat(
        model=LLM_MODEL, messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def ask(question, collection, think=False):
    import ollama

    retrieval_query = rewrite_query(question)
    chunks, metas = retrieve(retrieval_query, collection)

    context = ""
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        source = meta.get("policy_name") or meta.get("source", "Unknown")
        page = meta.get("page", "")
        ref = f"{source}, p.{page}" if page else source
        context += f"\n[{i+1}] {ref}\n{chunk}\n"

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
        model=LLM_MODEL, messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def main():
    parser = argparse.ArgumentParser(description="Agile Sourcing RAG")
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Build source/graph index without models",
    )
    parser.add_argument(
        "--preview-index",
        action="store_true",
        help="Embed unreviewed local sources in a separate preview collection",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--query", type=str)
    parser.add_argument("--think", action="store_true")
    args = parser.parse_args()

    if not (args.ingest or args.prepare_only or args.preview_index or args.query):
        parser.print_help()
        return

    collection = None

    if args.ingest or args.prepare_only or args.preview_index:
        if args.prepare_only and (args.preview_index or args.query):
            parser.error(
                "--prepare-only cannot be combined with --preview-index or --query"
            )
        print("\n--- Source index / ingestion ---")
        try:
            collection = ingest(args.prepare_only, args.preview_index, args.manifest)
        except Exception as error:
            parser.exit(1, f"Ingestion failed: {error}\n")

    if args.query:
        print("\n--- Query ---")
        if collection is None:
            collection = get_collection()
        if collection is None:
            return

        mode_label = "thinking" if args.think else "direct"
        print(f"Q: {args.query}  [{mode_label} mode]\n")
        answer = ask(args.query, collection, think=args.think)
        print(f"A: {answer}")


if __name__ == "__main__":
    main()
