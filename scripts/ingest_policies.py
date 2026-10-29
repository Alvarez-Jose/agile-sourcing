"""
scripts/ingest_policies.py - Agile Sourcing RAG
Ingest UC policy docs into ChromaDB, then query with local Qwen3.

Usage:
    python scripts/ingest_policies.py --ingest
    python scripts/ingest_policies.py --query "what is the competitive bidding threshold?"
    python scripts/ingest_policies.py --query "..." --think
    python scripts/ingest_policies.py --ingest --query "..."
"""

import argparse
import hashlib
import json
import os
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

DATA_DIR        = Path("data/raw_policies")
CHROMA_DIR      = "data/embeddings/chroma_store"
COLLECTION_NAME = "uc_policies"
# fine-tuned weights / enriched corpus drop in via env; unset = public base model
# and plain chunks, so ingestion works for everyone out of the box
EMBED_MODEL     = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
ENRICHED_CORPUS_PATH = os.environ.get("ENRICHED_CORPUS_PATH")
LLM_MODEL       = os.environ.get("LLM_MODEL", "qwen3:8b")
TOP_K           = 8

SYSTEM_PROMPT = (
    "You are a UC procurement policy assistant for UC Santa Cruz. "
    "Answer questions strictly based on the official UC policy excerpts provided. "
    "Never output placeholder text like [Cite policy] or [Policy Text]. "
    "Always provide the actual answer. "
    "Cite source numbers like [1], [2] for every claim you make."
)

print("Loading embedding model...")
embedder     = SentenceTransformer(EMBED_MODEL)
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
hybrid_retriever = None


def load_enrichment() -> dict:
    # optional per-chunk enrichment keyed by sha1 of the raw chunk text:
    #   {"<sha1>": {"header": "...", "questions": ["...", ...]}, ...}
    # generated offline (contextual header + likely questions); absent file = no-op
    if not ENRICHED_CORPUS_PATH or not Path(ENRICHED_CORPUS_PATH).exists():
        return {}
    with open(ENRICHED_CORPUS_PATH, encoding="utf-8") as f:
        enrichment = json.load(f)
    print(f"Loaded enrichment for {len(enrichment)} chunks from {ENRICHED_CORPUS_PATH}")
    return enrichment


def enrich_chunk(chunk: dict, enrichment: dict) -> dict:
    key = hashlib.sha1(chunk["text"].encode("utf-8")).hexdigest()
    extra = enrichment.get(key)
    if extra:
        parts = ([extra["header"]] if extra.get("header") else []) + extra.get("questions", [])
        chunk["text"] = "\n".join(parts) + "\n" + chunk["text"]
    return chunk


def chunk_header(chunk: dict) -> str:
    # policy name + section in front of the text so the embedder, BM25 and the reranker
    # all see which document a chunk is from (the metadata alone never reaches them)
    section = (chunk.get("section") or "").strip()
    return f"[{chunk.get('policy_name', '')}" + (f" | {section}" if section else "") + "]\n"


def ingest(collection_name=COLLECTION_NAME, prefix_headers=False):
    if not DATA_DIR.exists():
        print(f"ERROR: {DATA_DIR} not found.")
        return None

    files = list(DATA_DIR.iterdir())
    if not files:
        print(f"ERROR: No files in {DATA_DIR}.")
        return None

    enrichment = load_enrichment()
    all_chunks = []

    for f in sorted(files):
        print(f"  Processing: {f.name}")
        try:
            if f.suffix.lower() == ".pdf":
                pages = extract_pdf(str(f))
            elif f.suffix.lower() == ".docx":
                pages = extract_docx(str(f))
            else:
                print(f"    Skipping {f.suffix} file")
                continue

            chunks = chunk_by_section(pages)
            chunks = [tag_chunk(c) for c in chunks]
            if enrichment:
                chunks = [enrich_chunk(c, enrichment) for c in chunks]
            if prefix_headers:
                for c in chunks:
                    c["text"] = chunk_header(c) + c["text"]
            all_chunks.extend(chunks)
            print(f"    -> {len(chunks)} chunks")

        except Exception as e:
            print(f"    ERROR processing {f.name}: {e}")
            continue

    if not all_chunks:
        print("No chunks produced.")
        return None

    print(f"\nTotal chunks: {len(all_chunks)}")
    print("Embedding chunks (this takes a few minutes on first run)...")

    texts   = [c["text"] for c in all_chunks]
    vectors = embedder.encode(texts, show_progress_bar=True)

    try:
        chroma_client.delete_collection(collection_name)
    except Exception:
        pass

    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    BATCH_SIZE = 500
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch      = all_chunks[i:i + BATCH_SIZE]
        batch_vecs = vectors[i:i + BATCH_SIZE]

        collection.add(
            documents=[c["text"] for c in batch],
            embeddings=[v.tolist() for v in batch_vecs],
            metadatas=[
                {
                    "source":      c.get("source", ""),
                    "policy_name": c.get("policy_name", ""),
                    "doc_type":    c.get("doc_type", ""),
                    "page":        str(c.get("page", "")),
                    "section":     c.get("section", ""),
                }
                for c in batch
            ],
            ids=[f"chunk_{i + j}" for j in range(len(batch))],
        )

    print(f"Stored {len(all_chunks)} chunks in ChromaDB collection '{collection_name}' at '{CHROMA_DIR}'")
    return collection


def get_collection():
    try:
        return chroma_client.get_collection(COLLECTION_NAME)
    except Exception:
        print("No collection found — run with --ingest first.")
        return None


def get_retriever(collection):
    global hybrid_retriever
    if hybrid_retriever is None:
        hybrid_retriever = HybridRetriever(collection, embedder)
    return hybrid_retriever


def retrieve(question, collection, top_k=TOP_K):
    retriever = get_retriever(collection)
    return retriever.retrieve(question, top_k=top_k)


def rewrite_query(question):
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


def ask(question, collection, think=False):
    retrieval_query = rewrite_query(question)
    chunks, metas   = retrieve(retrieval_query, collection)

    context = ""
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        source = meta.get("policy_name") or meta.get("source", "Unknown")
        page   = meta.get("page", "")
        ref    = f"{source}, p.{page}" if page else source
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
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def main():
    parser = argparse.ArgumentParser(description="Agile Sourcing RAG")
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--query",  type=str)
    parser.add_argument("--think",  action="store_true")
    parser.add_argument("--collection", default=COLLECTION_NAME,
                        help="chroma collection to (re)build; use a different name to compare indexes")
    # on by default: lifted recall@1 on the 60-question benchmark from 40 to 46 with the same
    # reranker (evaluation/metrics/retrieval_recall.py)
    parser.add_argument("--prefix-headers", action=argparse.BooleanOptionalAction, default=True,
                        help="put '[policy name | section]' in front of every chunk's text")
    args = parser.parse_args()

    if not args.ingest and not args.query:
        parser.print_help()
        return

    collection = None

    if args.ingest:
        print("\n--- Ingestion ---")
        collection = ingest(args.collection, args.prefix_headers)

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