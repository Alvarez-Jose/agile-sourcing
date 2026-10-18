"""Adapt main's Chroma retriever to an authoritative, permission-filtered snapshot.

Chroma is a disposable vector cache. Only exact chunks from the current reviewed
SQLite snapshot may enter BM25, reranking, prompts, or returned citations.
"""

import re
import unicodedata

from rag_pipeline.documents.sections import locations_for
from rag_pipeline.retriever.section_retriever import Passage


def _compact(text):
    typography = str.maketrans({"‐": "-", "‑": "-", "–": "-", "—": "-",
                               "’": "'", "‘": "'", "“": '"', "”": '"'})
    return "".join(unicodedata.normalize("NFKC", text).translate(typography).split())


class ScopedCorpus:
    def __init__(self, index):
        self.snapshot = index.retrieval_snapshot()
        self.documents = {d.version_id: d for d in self.snapshot["documents"]}
        self.sections = {s.id: s for s in self.snapshot["sections"]}
        self.records = {}
        for chunk in self.snapshot["chunks"]:
            section = self.sections[chunk.parent_section_id]
            ancestor = section
            historical = False
            while ancestor:
                historical |= "REVISION HISTORY" in ancestor.title.upper()
                ancestor = self.sections.get(ancestor.parent_section_id)
            if historical or section.kind not in ("body", "table"):
                continue
            doc = self.documents[chunk.document_version_id]
            passage = Passage(doc, section, chunk.start, chunk.end)
            citation = passage.citation(0)
            self.records[chunk.id] = (chunk.text, {
                "policy_name": doc.title, "source": doc.file,
                "document_id": doc.id, "document_version_id": doc.version_id,
                "chunk_id": chunk.id, "section": section.title,
                "page": citation["page"], "parent_section_id": section.id,
                "start": chunk.start, "end": chunk.end,
            })

    def citation(self, metadata, number):
        text, meta = self.records[metadata["chunk_id"]]
        section = self.sections[meta["parent_section_id"]]
        doc = self.documents[meta["document_version_id"]]
        result = Passage(doc, section, meta["start"], meta["end"]).citation(number)
        return {**result, "ref": number, "file": doc.file, "text": text,
                "score": None, "cited": False,
                "evidence": [{"quote": text, "start": meta["start"], "end": meta["end"],
                              "locations": result["locations"]}]}

    def rule_citations(self, result):
        """Reject a whole determination if any supporting source is unavailable.

        Rule provenance must match original text in an active, authorized version.
        External/unreviewed rule sources cannot bypass document permissions.
        """
        citations = []
        for source in result.sources:
            matches = []
            for section in self.sections.values():
                doc = self.documents[section.document_version_id]
                if doc.id != source.document_id:
                    continue
                # Build an original-character offset map while normalizing typography.
                compact, offsets = [], []
                for position, char in enumerate(section.text):
                    value = _compact(char)
                    compact.extend(value)
                    offsets.extend([position] * len(value))
                needle = _compact(source.quote)
                at = "".join(compact).find(needle) if needle else -1
                if at < 0:
                    continue
                start, end = offsets[at], offsets[at + len(needle) - 1] + 1
                locations = locations_for(section, start, end)
                if source.page and source.page not in {loc.page for loc in locations}:
                    continue
                matches.append(Passage(doc, section, start, end))
            if not matches:
                return None
            passage = min(matches, key=lambda p: len(p.section.text))
            number = len(citations) + 1
            citation = passage.citation(number)
            citations.append({**citation, "ref": number, "file": passage.document.file,
                              "text": passage.text, "score": None, "cited": True,
                              "evidence": [{"quote": passage.text, "start": passage.start,
                                            "end": passage.end, "locations": citation["locations"]}]})
        return citations or None


class ScopedCollection:
    """Chroma's get/query subset used by main's unchanged HybridRetriever.

    Each request owns this view, including the named-source subset. Never reuse a
    corpus or BM25 cache across users, clearances, source versions, or requests.
    """
    def __init__(self, collection, corpus, document_ids=None):
        self.collection = collection
        self.records = {key: value for key, value in corpus.records.items()
                        if document_ids is None or value[1]["document_id"] in document_ids}
        self.ids = []
        keys = list(self.records)
        for start in range(0, len(keys), 250):
            stored = collection.get(ids=keys[start:start + 250], include=["documents", "metadatas"])
            for identifier, text, meta in zip(stored["ids"], stored["documents"], stored["metadatas"]):
                original, expected = self.records[identifier]
                if (text != original or not meta
                        or meta.get("document_version_id") != expected["document_version_id"]
                        or meta.get("chunk_id") != identifier):
                    raise ValueError("Policy vector cache differs from reviewed sources; rerun ingestion")
                self.ids.append(identifier)
        if set(self.ids) != set(keys):
            raise ValueError("Policy vector cache is incomplete or stale; run python -m scripts.ingest_policies --ingest")

    def count(self):
        return len(self.ids)

    def get(self, include=None):
        return {"ids": self.ids,
                "documents": [self.records[key][0] for key in self.ids],
                "metadatas": [self.records[key][1] for key in self.ids]}

    def query(self, query_embeddings, n_results, include=None):
        if not self.ids:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        # Filtering happens inside vector search, before the candidate pool is cut.
        result = self.collection.query(
            query_embeddings=query_embeddings, n_results=min(n_results, len(self.ids)),
            where={"chunk_id": {"$in": self.ids}}, include=["distances"],
        )
        pairs = [(key, distance) for key, distance in zip(result["ids"][0], result["distances"][0])
                 if key in self.records]
        return {"documents": [[self.records[key][0] for key, _ in pairs]],
                "metadatas": [[self.records[key][1] for key, _ in pairs]],
                "distances": [[distance for _, distance in pairs]]}
