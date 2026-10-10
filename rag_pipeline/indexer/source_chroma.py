"""Rebuildable Chroma views of authoritative source records.

Only reviewed public records are published to the active runtime collection.
Local review builds use a separate preview collection and never activate it.
"""

import json
import os
from pathlib import Path
import uuid

from rag_pipeline.documents.build import SourceIndexBundle
from rag_pipeline.documents.models import AccessScope, LOCAL_REVIEW_SCOPE
from rag_pipeline.documents.sections import make_sections_and_chunks
from rag_pipeline.documents.store import DEFAULT_INDEX, ROOT, write_source_index
from rag_pipeline.graph.builder import build_policy_graph

CHROMA_DIR = ROOT / "data/embeddings/chroma_store"
POINTER_NAME = "active_policy_collection.json"
EMBED_MODEL = "all-MiniLM-L6-v2"


def embedding_chunks(bundle: SourceIndexBundle, embedder):
    """Use actual model-token offsets; do not silently truncate source embeddings."""
    tokenizer = embedder.tokenizer
    if not getattr(tokenizer, "is_fast", False):
        raise ValueError("Embedding tokenizer must provide source character offsets")
    limit = min(
        240, embedder.max_seq_length - tokenizer.num_special_tokens_to_add(False) - 8
    )
    if limit < 2:
        raise ValueError("Embedding model has no usable input budget")

    def spans(text):
        encoded = tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_offsets_mapping=True,
        )
        return [(start, end) for start, end in encoded["offset_mapping"] if end > start]

    sections, chunks = [], []
    for doc in bundle.documents:
        doc_sections, doc_chunks = make_sections_and_chunks(
            doc,
            max_tokens=limit,
            overlap_tokens=min(40, limit - 1),
            token_spans=spans,
            tokenizer_name=getattr(tokenizer, "name_or_path", EMBED_MODEL),
        )
        for chunk in doc_chunks:
            encoded = tokenizer(chunk.text, add_special_tokens=True, truncation=False)
            if len(encoded["input_ids"]) > embedder.max_seq_length:
                raise ValueError(
                    "Child chunk exceeds actual embedding input limit; no index was published"
                )
            chunk.token_count = len(
                encoded["input_ids"]
            ) - tokenizer.num_special_tokens_to_add(False)
        sections.extend(doc_sections)
        chunks.extend(doc_chunks)
    nodes, edges = build_policy_graph(bundle.documents, sections, chunks)
    result = SourceIndexBundle(
        documents=bundle.documents,
        sections=sections,
        chunks=chunks,
        nodes=nodes,
        edges=edges,
        warnings=bundle.warnings,
    )
    result.validate_integrity()
    return result


def chroma_records(bundle: SourceIndexBundle, scope: AccessScope | None = None):
    scope = scope or AccessScope()
    docs = {
        doc.version_id: doc
        for doc in bundle.documents
        if scope.permits(doc.access_classification, doc.review_status)
    }
    sections = {section.id: section for section in bundle.sections}
    ids, texts, metadata = [], [], []
    for chunk in bundle.chunks:
        doc = docs.get(chunk.document_version_id)
        if doc is None:
            continue
        section = sections[chunk.parent_section_id]
        pages = sorted(
            {location.page for location in chunk.locations if location.page is not None}
        )
        metadata.append(
            {
                "document_id": doc.id,
                "document_version_id": doc.version_id,
                "parent_section_id": chunk.parent_section_id,
                "chunk_id": chunk.id,
                "source": doc.file,
                "policy_name": doc.title,
                "policy_id": doc.policy_id or "",
                "doc_type": doc.category,
                "document_kind": doc.kind,
                "file_format": Path(doc.file).suffix.lstrip(".").lower(),
                "page": (
                    (str(pages[0]) if len(pages) == 1 else f"{pages[0]}-{pages[-1]}")
                    if pages
                    else ""
                ),
                "section": section.title,
                "access_classification": doc.access_classification,
                "review_status": doc.review_status,
                "source_sha256": doc.sha256,
                "start": chunk.start,
                "end": chunk.end,
                "tokenizer": chunk.tokenizer,
                "effective_date": next(
                    (
                        item.value
                        for item in doc.dates
                        if item.field == "effective_date"
                    ),
                    "",
                ),
                "revision_date": next(
                    (item.value for item in doc.dates if item.field == "revision_date"),
                    "",
                ),
            }
        )
        ids.append(chunk.id)
        texts.append(chunk.text)
    return ids, texts, metadata


def publish_chroma(
    bundle: SourceIndexBundle, embedder, path: Path = CHROMA_DIR, preview=False
):
    ids, texts, metadata = chroma_records(
        bundle, LOCAL_REVIEW_SCOPE if preview else AccessScope()
    )
    if not ids:
        raise ValueError(
            "No reviewed public chunks to publish. Use a separate preview index for local review."
        )
    import chromadb

    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    name = ("uc_policies_preview_" if preview else "uc_policies_") + uuid.uuid4().hex[
        :16
    ]
    collection = client.create_collection(
        name=name, metadata={"hnsw:space": "cosine", "source_schema": 1}
    )
    # Source parents/graph are pinned to this immutable vector generation.
    snapshot_relative = Path("source_indexes") / f"{name}.sqlite"
    write_source_index(bundle, path / snapshot_relative)
    # The live pointer remains unchanged throughout embedding and all batch writes.
    for start in range(0, len(ids), 250):
        batch = texts[start : start + 250]
        vectors = embedder.encode(batch, show_progress_bar=True)
        collection.add(
            ids=ids[start : start + 250],
            documents=batch,
            embeddings=[vector.tolist() for vector in vectors],
            metadatas=metadata[start : start + 250],
        )
    if collection.count() != len(ids):
        raise ValueError("Chroma publication count does not match source records")
    if not preview:
        pointer = path / POINTER_NAME
        temporary = path / (POINTER_NAME + ".build-" + uuid.uuid4().hex)
        try:
            with os.fdopen(
                os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
            ) as stream:
                json.dump(
                    {
                        "schema_version": 1,
                        "collection": name,
                        "embedding_model": EMBED_MODEL,
                        "source_index": snapshot_relative.as_posix(),
                    },
                    stream,
                )
            os.replace(temporary, pointer)
        finally:
            if temporary.exists():
                temporary.unlink()
    return collection


def active_collection(client, path: Path = CHROMA_DIR):
    pointer = Path(path) / POINTER_NAME
    name = (
        json.loads(pointer.read_text())["collection"]
        if pointer.exists()
        else "uc_policies"
    )
    return client.get_collection(name)


def active_source_index_path(path: Path = CHROMA_DIR):
    path = Path(path).resolve()
    pointer = path / POINTER_NAME
    if not pointer.exists():
        return DEFAULT_INDEX
    relative = json.loads(pointer.read_text()).get("source_index")
    if not relative:
        return DEFAULT_INDEX
    resolved = (path / relative).resolve()
    if not resolved.is_relative_to(path):
        raise ValueError(
            "Active source index must stay inside the Chroma generation directory"
        )
    return resolved
