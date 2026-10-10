"""Offline extraction/index preparation; a failure never replaces a working index."""

import hashlib
from pathlib import Path
import re

from pydantic import BaseModel, Field

from rag_pipeline.documents.extractors import extract_docx_blocks, extract_pdf_blocks
from rag_pipeline.documents.manifest import DocumentManifest, observe_dates
from rag_pipeline.documents.models import ChunkRecord, DocumentRecord, SectionRecord
from rag_pipeline.documents.sections import make_sections_and_chunks
from rag_pipeline.graph.builder import build_policy_graph
from rag_pipeline.graph.schema import PolicyEdge, PolicyNode


class SourceIndexBundle(BaseModel):
    schema_version: int = 1
    documents: list[DocumentRecord]
    sections: list[SectionRecord]
    chunks: list[ChunkRecord]
    nodes: list[PolicyNode]
    edges: list[PolicyEdge]
    warnings: list[str] = Field(default_factory=list)

    def validate_integrity(self):
        versions = {item.version_id for item in self.documents}
        blocks = {block.id: block for doc in self.documents for block in doc.blocks}
        source_links = {
            doc.version_id: {
                (link.target, link.location.model_dump_json())
                for block in doc.blocks
                for link in block.links
            }
            for doc in self.documents
        }
        sections = {item.id: item for item in self.sections}
        nodes = {item.id for item in self.nodes}
        if len(versions) != len(self.documents) or len(sections) != len(self.sections):
            raise ValueError("Duplicate document version or section IDs")
        if len({chunk.id for chunk in self.chunks}) != len(self.chunks) or len(
            nodes
        ) != len(self.nodes):
            raise ValueError("Duplicate chunk or graph node IDs")
        for section in self.sections:
            if section.document_version_id not in versions:
                raise ValueError("Section has no source document")
            if section.parent_section_id and section.parent_section_id not in sections:
                raise ValueError("Section has no parent section")
            for span in section.blocks:
                source = blocks[span.block_id]
                if span.source_end is not None and (
                    not 0 <= span.start < span.end <= len(section.text)
                    or not 0 <= span.source_start < span.source_end <= len(source.text)
                    or section.text[span.start : span.end]
                    != source.text[span.source_start : span.source_end]
                ):
                    raise ValueError(
                        "Section source-block span does not preserve the original text"
                    )
        for chunk in self.chunks:
            parent = sections[chunk.parent_section_id]
            if (
                not 0 <= chunk.start < chunk.end <= len(parent.text)
                or chunk.document_version_id != parent.document_version_id
                or chunk.text != parent.text[chunk.start : chunk.end]
                or not chunk.locations
            ):
                raise ValueError(
                    "Child chunk is not an exact, located parent-section span"
                )
        for edge in self.edges:
            # Revalidate mutable records at the storage boundary, including override
            # review requirements, rather than trusting their construction history.
            PolicyEdge.model_validate(edge.model_dump())
            if edge.source_id not in nodes or edge.target_id not in nodes:
                raise ValueError("Graph edge has a missing endpoint")
            for evidence in edge.evidence:
                section = sections[evidence.section_id]
                if (
                    not 0 <= evidence.start < evidence.end <= len(section.text)
                    or evidence.document_version_id != section.document_version_id
                    or evidence.quote != section.text[evidence.start : evidence.end]
                    or not evidence.locations
                ):
                    raise ValueError(
                        "Relationship evidence does not match its actual source"
                    )
                if evidence.link_target and not all(
                    (evidence.link_target, location.model_dump_json())
                    in source_links[evidence.document_version_id]
                    for location in evidence.locations
                ):
                    raise ValueError(
                        "Relationship hyperlink target was not extracted from the source"
                    )

    def summary(self):
        return {
            "documents": len(self.documents),
            "sections": len(self.sections),
            "tables": sum(
                block.kind == "table" for doc in self.documents for block in doc.blocks
            ),
            "chunks": len(self.chunks),
            "graph_nodes": len(self.nodes),
            "graph_edges": len(self.edges),
            "overrides": sum(edge.relation == "overrides" for edge in self.edges),
            "active_documents": sum(
                doc.review_status == "active" for doc in self.documents
            ),
            "archived_documents": sum(
                doc.review_status == "archived" for doc in self.documents
            ),
            "documents_needing_review": sum(
                doc.review_status == "review" for doc in self.documents
            ),
            "warnings": self.warnings,
        }


def prepare_source_index(
    source_dir: Path, manifest_path: Path, progress=None, **chunk_options
):
    manifest = DocumentManifest.load(manifest_path)
    source_dir = source_dir.resolve()
    files = sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in (".pdf", ".docx")
    )
    if not files:
        raise ValueError(f"No PDF/DOCX sources in {source_dir}")
    documents, sections, chunks, warnings = [], [], [], []
    seen = {}
    for path in files:
        entry = manifest.resolve(path.name)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if entry.review_status == "active" and entry.reviewed_sha256 != sha:
            raise ValueError(
                f"Source changed after review; review the new bytes before activating: {path.name}"
            )
        # Source versions use full file hashes. A byte change produces a new version.
        version_id = f"document:{entry.id}:{sha}"
        relative = path.relative_to(source_dir).as_posix()
        if version_id in seen:
            seen[version_id].additional_files.append(relative)
            warnings.append(f"Duplicate source bytes retained as alias: {relative}")
            continue
        extractor = (
            extract_pdf_blocks if path.suffix.lower() == ".pdf" else extract_docx_blocks
        )
        blocks = extractor(path, version_id, relative)
        if not blocks:
            raise ValueError(
                f"No extractable content in {relative}; review OCR/source file"
            )
        notes = list(entry.review_notes)
        if any(
            link.target.startswith("unresolved-uri:")
            for block in blocks
            for link in block.links
        ):
            notes.append(
                "Malformed hyperlink target bytes retained; review original annotation"
            )
            warnings.append(
                f"Malformed hyperlink target retained for review: {relative}"
            )
        classification = entry.access_classification
        if any(
            re.search(r"internal\s+UC\s+use\s+only", block.text, re.I)
            for block in blocks
        ):
            if classification == "public":
                classification = "internal"
                warnings.append(
                    f"Promoted to internal due to source marking: {relative}"
                )
            notes.append("Source explicitly marked Internal UC use only")
        if any(
            re.search(r"^\s*DRAFT\b", block.text, re.I)
            for block in blocks
            if block.kind in ("header", "footer")
            or (block.location.part or "").startswith(("word/header", "word/footer"))
        ):
            notes.append(
                "DRAFT marking in header/footer; confirm released/template version"
            )
            warnings.append(f"DRAFT source requires version review: {relative}")
        document = DocumentRecord(
            id=entry.id,
            version_id=version_id,
            sha256=sha,
            file=relative,
            title=entry.title,
            policy_id=entry.policy_id,
            category=entry.category,
            kind=entry.kind,
            access_classification=classification,
            review_status=entry.review_status,
            source_url=entry.source_url,
            reviewed_by=entry.reviewed_by,
            reviewed_at=entry.reviewed_at,
            aliases=entry.aliases,
            dates=observe_dates(blocks),
            review_notes=notes,
            blocks=blocks,
        )
        doc_sections, doc_chunks = make_sections_and_chunks(document, **chunk_options)
        documents.append(document)
        seen[version_id] = document
        sections.extend(doc_sections)
        chunks.extend(doc_chunks)
        if progress:
            progress(document, len(doc_sections), len(doc_chunks))
    nodes, edges = build_policy_graph(documents, sections, chunks)
    bundle = SourceIndexBundle(
        documents=documents,
        sections=sections,
        chunks=chunks,
        nodes=nodes,
        edges=edges,
        warnings=warnings,
    )
    bundle.validate_integrity()
    return bundle
