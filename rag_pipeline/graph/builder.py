"""Build structure and explicit references; no generated summaries or rule inference."""

import hashlib
import re
from urllib.parse import urlparse

from rag_pipeline.documents.models import (
    ChunkRecord,
    DocumentRecord,
    Evidence,
    SectionRecord,
)
from rag_pipeline.documents.sections import locations_for
from rag_pipeline.graph.schema import PolicyEdge, PolicyNode


def _evidence(section, start, end):
    return Evidence(
        document_version_id=section.document_version_id,
        section_id=section.id,
        start=start,
        end=end,
        quote=section.text[start:end],
        locations=locations_for(section, start, end),
    )


def _edge(source, target, relation, evidence):
    key = f"{source}:{target}:{relation}:{evidence.section_id}:{evidence.start}:{evidence.end}"
    return PolicyEdge(
        id="edge:" + hashlib.sha256(key.encode()).hexdigest()[:24],
        source_id=source,
        target_id=target,
        relation=relation,
        evidence=[evidence],
    )


def _alias_pattern(alias):
    words = re.findall(r"[A-Za-z0-9]+", alias)
    if not words:
        raise ValueError("Empty reference alias")
    # Filenames are not reference aliases. Match complete words with flexible spaces
    # and Unicode hyphens, not BUS-43 inside BUS-430 or arbitrary substring matches.
    return re.compile(
        r"(?<!\w)" + r"[\W_]*".join(map(re.escape, words)) + r"(?!\w)", re.I
    )


def build_policy_graph(
    documents: list[DocumentRecord],
    sections: list[SectionRecord],
    chunks: list[ChunkRecord],
) -> tuple[list[PolicyNode], list[PolicyEdge]]:
    docs = {document.version_id: document for document in documents}
    nodes, edges, aliases = {}, {}, []
    for document in documents:
        nodes[document.version_id] = PolicyNode(
            id=document.version_id,
            kind="document",
            label=document.title,
            document_version_id=document.version_id,
            access_classification=document.access_classification,
            review_status=document.review_status,
            properties={
                "document_id": document.id,
                "file": document.file,
                "policy_id": document.policy_id,
                "kind": document.kind,
                "sha256": document.sha256,
            },
        )
        target = document.version_id
        if document.kind == "form":
            target = "form:" + document.version_id
            nodes[target] = PolicyNode(
                id=target,
                kind="form",
                label=document.title,
                document_version_id=document.version_id,
                access_classification=document.access_classification,
                review_status=document.review_status,
                properties={"document_id": document.id},
            )
        for alias in set(
            document.aliases + ([document.policy_id] if document.policy_id else [])
        ):
            aliases.append(
                (len(alias), _alias_pattern(alias), target, document.version_id)
            )
    aliases.sort(key=lambda item: item[0], reverse=True)
    for section in sections:
        document = docs[section.document_version_id]
        nodes[section.id] = PolicyNode(
            id=section.id,
            kind="section",
            label=section.title,
            document_version_id=document.version_id,
            access_classification=document.access_classification,
            review_status=document.review_status,
            properties={"kind": section.kind, "ordinal": section.ordinal},
        )
        end = min(len(section.text), 160)
        evidence = _evidence(section, 0, end)
        parent = section.parent_section_id or document.version_id
        relation = _edge(parent, section.id, "contains", evidence)
        edges[relation.id] = relation
        if (
            document.kind == "form"
            and section.parent_section_id is None
            and section.kind == "body"
        ):
            relation = _edge(
                "form:" + document.version_id,
                document.version_id,
                "has_source",
                evidence,
            )
            edges[relation.id] = relation

    owned_ranges = {}
    for chunk in chunks:
        owned_ranges.setdefault(chunk.parent_section_id, []).append(
            (chunk.start, chunk.end)
        )
    for section in sections:
        # Only scan this section's own child text, avoiding repeated evidence from
        # full ancestor sections and overlap windows. The source section still
        # preserves its complete children for later parent retrieval.
        ranges = []
        for start, end in sorted(owned_ranges.get(section.id, [])):
            if ranges and start <= ranges[-1][1]:
                ranges[-1] = ranges[-1][0], max(ranges[-1][1], end)
            else:
                ranges.append((start, end))
        for start, end in ranges:
            text, occupied = section.text[start:end], []
            for _, pattern, target, target_document in aliases:
                for match in pattern.finditer(text):
                    a, b = match.start(), match.end()
                    if any(
                        a < previous_end and b > previous_start
                        for previous_start, previous_end in occupied
                    ):
                        continue
                    occupied.append((a, b))
                    if target_document == section.document_version_id:
                        continue
                    relation = _edge(
                        section.id,
                        target,
                        "references",
                        _evidence(section, start + a, start + b),
                    )
                    edges[relation.id] = relation
            # Explicit external legal references are unresolved reference nodes,
            # never fabricated documents or interpretations of applicable law.
            for pattern, prefix in [
                (r"\bFAR\s+(?:subpart\s+)?\d+(?:\.\d+)+(?:-\d+)?", "FAR"),
                (r"\b\d+\s+CFR\s+(?:Part\s+)?\d+(?:\.\d+)*", "CFR"),
            ]:
                for match in re.finditer(pattern, text, re.I):
                    canonical = re.sub(r"\s+", " ", match.group().upper())
                    identifier = (
                        "reference:"
                        + hashlib.sha256(canonical.encode()).hexdigest()[:20]
                    )
                    nodes.setdefault(
                        identifier,
                        PolicyNode(
                            id=identifier,
                            kind="reference",
                            label=canonical,
                            access_classification="public",
                            review_status="review",
                            properties={"resolved": False, "authority_family": prefix},
                        ),
                    )
                    relation = _edge(
                        section.id,
                        identifier,
                        "references",
                        _evidence(section, start + match.start(), start + match.end()),
                    )
                    edges[relation.id] = relation
    # Preserve actual hyperlink targets as unresolved resources. A URL does not
    # prove that a locally supplied version is the version served by that address.
    blocks = {block.id: block for doc in documents for block in doc.blocks}
    for section in sections:
        document = docs[section.document_version_id]
        for source in section.blocks:
            block = blocks[source.block_id]
            for link in block.links:
                if (
                    urlparse(link.target).scheme not in ("http", "https")
                    or not link.text.strip()
                ):
                    continue
                parts = re.split(r"\s+", link.text.strip())
                pattern = re.compile(r"\s+".join(map(re.escape, parts)))
                matches = list(pattern.finditer(block.text))
                # Repeated labels in one block need geometry/XML-level resolution.
                # Preserve the URL in the source record rather than guess a span.
                if len(matches) != 1:
                    continue
                for match in matches:
                    source_end = (
                        source.source_end
                        if source.source_end is not None
                        else len(block.text)
                    )
                    if match.start() < source.source_start or match.end() > source_end:
                        continue
                    start = source.start + match.start() - source.source_start
                    end = source.start + match.end() - source.source_start
                    if not any(
                        a <= start and b >= end
                        for a, b in owned_ranges.get(section.id, [])
                    ):
                        continue
                    identifier = (
                        "reference:"
                        + hashlib.sha256(
                            f"{document.version_id}:{link.target}".encode()
                        ).hexdigest()[:20]
                    )
                    nodes.setdefault(
                        identifier,
                        PolicyNode(
                            id=identifier,
                            kind="reference",
                            label=link.target,
                            document_version_id=document.version_id,
                            access_classification=document.access_classification,
                            review_status=document.review_status,
                            properties={"resolved": False, "uri": link.target},
                        ),
                    )
                    evidence = _evidence(section, start, end)
                    evidence.link_target = link.target
                    evidence.locations = [link.location]
                    relation = _edge(section.id, identifier, "references", evidence)
                    edges[relation.id] = relation
    return list(nodes.values()), list(edges.values())
