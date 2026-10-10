"""Atomic SQLite source/graph index with scoped reads and foreign-key integrity."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from rag_pipeline.documents.build import SourceIndexBundle
from rag_pipeline.documents.models import (
    AccessScope,
    ChunkRecord,
    DocumentRecord,
    SectionRecord,
)
from rag_pipeline.graph.schema import PolicyEdge, PolicyNode

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "data/parsed/policy_index.sqlite"
DEFAULT_MANIFEST = ROOT / "data/policies/document_manifest.json"
DEFAULT_SOURCES = ROOT / "data/raw_policies"

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents(
    version_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
    access_classification TEXT NOT NULL, review_status TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE sections(
    id TEXT PRIMARY KEY, document_version_id TEXT NOT NULL REFERENCES documents(version_id),
    parent_section_id TEXT REFERENCES sections(id), payload TEXT NOT NULL
);
CREATE TABLE chunks(
    id TEXT PRIMARY KEY, document_version_id TEXT NOT NULL REFERENCES documents(version_id),
    parent_section_id TEXT NOT NULL REFERENCES sections(id), payload TEXT NOT NULL
);
CREATE VIRTUAL TABLE chunk_search USING fts5(chunk_id UNINDEXED, title, text);
CREATE TABLE nodes(
    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
    document_version_id TEXT REFERENCES documents(version_id),
    access_classification TEXT NOT NULL, review_status TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE edges(
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES nodes(id),
    target_id TEXT NOT NULL REFERENCES nodes(id), relation TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX sections_document ON sections(document_version_id);
CREATE INDEX chunks_parent ON chunks(parent_section_id);
CREATE INDEX edges_source ON edges(source_id);
CREATE INDEX edges_target ON edges(target_id);
"""


def _retain_archived_versions(bundle: SourceIndexBundle, path: Path):
    if not path.exists():
        return bundle
    current = {document.version_id for document in bundle.documents}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        if db.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone() != ("1",):
            raise ValueError(
                "Existing source index requires an explicit schema migration"
            )
        old_docs = [
            DocumentRecord.model_validate_json(row[0])
            for row in db.execute("SELECT payload FROM documents")
        ]
        archived = {doc.version_id for doc in old_docs if doc.version_id not in current}
        if not archived:
            return bundle

        def records(table, model):
            return [
                model.model_validate_json(row[0])
                for row in db.execute(f"SELECT payload FROM {table}")
            ]

        old_sections = [
            item
            for item in records("sections", SectionRecord)
            if item.document_version_id in archived
        ]
        old_chunks = [
            item
            for item in records("chunks", ChunkRecord)
            if item.document_version_id in archived
        ]
        prior_nodes = records("nodes", PolicyNode)
        node_map = {
            item.id: item
            for item in prior_nodes
            if item.document_version_id in archived
        }
        old_edges = [
            item
            for item in records("edges", PolicyEdge)
            if all(
                evidence.document_version_id in archived for evidence in item.evidence
            )
        ]
        needed = {edge.target_id for edge in old_edges}
        for node in prior_nodes:
            if node.id in needed:
                node_map.setdefault(node.id, node)
        # Current nodes win when an archived reference points to an unchanged document.
        old_nodes = [
            (
                node.model_copy(update={"review_status": "archived"})
                if node.document_version_id in archived
                else node
            )
            for node in node_map.values()
        ]
    nodes = {node.id: node for node in old_nodes + bundle.nodes}
    edges = {edge.id: edge for edge in old_edges + bundle.edges}
    return SourceIndexBundle(
        documents=bundle.documents
        + [
            doc.model_copy(update={"review_status": "archived"})
            for doc in old_docs
            if doc.version_id in archived
        ],
        sections=bundle.sections + old_sections,
        chunks=bundle.chunks + old_chunks,
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        warnings=bundle.warnings,
    )


def write_source_index(bundle: SourceIndexBundle, path: Path = DEFAULT_INDEX):
    bundle.validate_integrity()
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = _retain_archived_versions(bundle, path)
    bundle.validate_integrity()
    temporary = path.with_name(path.name + f".build-{uuid.uuid4().hex}")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with sqlite3.connect(temporary) as db:
            db.executescript(_SCHEMA)
            db.execute("INSERT INTO metadata VALUES (?, ?)", ("schema_version", "1"))
            db.execute(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    "built_at",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO metadata VALUES (?, ?)",
                ("summary", json.dumps(bundle.summary())),
            )
            for doc in bundle.documents:
                db.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
                    (
                        doc.version_id,
                        doc.id,
                        doc.access_classification,
                        doc.review_status,
                        doc.model_dump_json(),
                    ),
                )
            # Sections are generated parents-first. Foreign keys validate all links.
            sections = {section.id: section for section in bundle.sections}
            remaining = dict(sections)
            inserted = set()
            while remaining:
                ready = [
                    item
                    for item in remaining.values()
                    if not item.parent_section_id or item.parent_section_id in inserted
                ]
                if not ready:
                    raise ValueError("Section parents contain a cycle")
                for section in ready:
                    db.execute(
                        "INSERT INTO sections VALUES (?, ?, ?, ?)",
                        (
                            section.id,
                            section.document_version_id,
                            section.parent_section_id,
                            section.model_dump_json(),
                        ),
                    )
                    inserted.add(section.id)
                    del remaining[section.id]
            for chunk in bundle.chunks:
                db.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?)",
                    (
                        chunk.id,
                        chunk.document_version_id,
                        chunk.parent_section_id,
                        chunk.model_dump_json(),
                    ),
                )
                db.execute(
                    "INSERT INTO chunk_search VALUES (?, ?, ?)",
                    (
                        chunk.id,
                        sections[chunk.parent_section_id].title,
                        chunk.text,
                    ),
                )
            for node in bundle.nodes:
                db.execute(
                    "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        node.id,
                        node.kind,
                        node.document_version_id,
                        node.access_classification,
                        node.review_status,
                        node.model_dump_json(),
                    ),
                )
            for edge in bundle.edges:
                db.execute(
                    "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
                    (
                        edge.id,
                        edge.source_id,
                        edge.target_id,
                        edge.relation,
                        edge.model_dump_json(),
                    ),
                )
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Index has invalid foreign keys")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        return bundle
    finally:
        if temporary.exists():
            temporary.unlink()


class PolicyIndex:
    def __init__(self, path: Path = DEFAULT_INDEX, scope: AccessScope | None = None):
        self.path = Path(path).resolve()
        self.scope = scope or AccessScope()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def _allowed(self, row):
        return row is not None and self.scope.permits(
            row["access_classification"], row["review_status"]
        )

    def summary(self):
        # Scoped counts never reveal the existence of inaccessible source records.
        return {
            "documents": len(self.documents()),
            "nodes": len(self.nodes()),
            "edges": len(self.edges()),
        }

    def documents(self):
        with self.connection() as db:
            return [
                DocumentRecord.model_validate_json(row["payload"])
                for row in db.execute("SELECT * FROM documents ORDER BY document_id")
                if self._allowed(row)
            ]

    def document(self, version_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE version_id = ?", (version_id,)
            ).fetchone()
            return (
                DocumentRecord.model_validate_json(row["payload"])
                if self._allowed(row)
                else None
            )

    def _source_record(self, table, identifier, model):
        if table not in ("sections", "chunks"):
            raise ValueError("Unsupported record table")
        with self.connection() as db:
            row = db.execute(
                f"""SELECT r.payload, d.access_classification, d.review_status
                FROM {table} r JOIN documents d ON d.version_id = r.document_version_id
                WHERE r.id = ?""",
                (identifier,),
            ).fetchone()
            return (
                model.model_validate_json(row["payload"])
                if self._allowed(row)
                else None
            )

    def section(self, identifier):
        return self._source_record("sections", identifier, SectionRecord)

    def chunk(self, identifier):
        return self._source_record("chunks", identifier, ChunkRecord)

    def parent_section(self, chunk_id):
        chunk = self.chunk(chunk_id)
        return self.section(chunk.parent_section_id) if chunk else None

    def search(self, query: str, limit: int = 10):
        words = re.findall(r"\w+", query)[:20]
        if not words or limit < 1:
            return []
        match = " AND ".join('"' + word + '"' for word in words)
        statuses = (
            ["active"]
            + (["review"] if self.scope.include_review else [])
            + (["archived"] if self.scope.include_archived else [])
        )
        if not self.scope.classifications:
            return []

        def placeholders(items):
            return ",".join("?" for _ in items)

        with self.connection() as db:
            rows = db.execute(
                f"""SELECT c.payload FROM chunk_search f
                JOIN chunks c ON c.id = f.chunk_id JOIN documents d ON d.version_id = c.document_version_id
                WHERE chunk_search MATCH ? AND d.access_classification IN ({placeholders(self.scope.classifications)})
                AND d.review_status IN ({placeholders(statuses)})
                ORDER BY bm25(chunk_search) LIMIT ?""",
                (
                    match,
                    *self.scope.classifications,
                    *statuses,
                    max(1, min(limit, 100)),
                ),
            )
            return [ChunkRecord.model_validate_json(row["payload"]) for row in rows]

    def nodes(self):
        with self.connection() as db:
            return [
                PolicyNode.model_validate_json(row["payload"])
                for row in db.execute("SELECT * FROM nodes ORDER BY id")
                if self._allowed(row)
            ]

    def edges(self):
        allowed = {node.id for node in self.nodes()}
        with self.connection() as db:
            return [
                PolicyEdge.model_validate_json(row["payload"])
                for row in db.execute("SELECT * FROM edges ORDER BY id")
                if row["source_id"] in allowed and row["target_id"] in allowed
            ]
