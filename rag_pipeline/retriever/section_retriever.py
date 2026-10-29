"""Permission-filtered hybrid ranking, full parents, and bounded explicit references.

SQLite is the live authorization/source authority. Model vectors are a disposable,
bounded in-memory view of an already scoped corpus; legacy Chroma records cannot
bypass source review or leak into prompts. Models are supplied by the caller.
"""

from collections import Counter
from dataclasses import dataclass
import math
import re

from rag_pipeline.documents.models import DocumentRecord, SectionRecord
from rag_pipeline.documents.manifest import DocumentManifest
from rag_pipeline.documents.sections import locations_for
from rag_pipeline.documents.store import DEFAULT_MANIFEST, PolicyIndex


def requested_source_ids(question, manifest_path=DEFAULT_MANIFEST):
    """An explicit named source cannot be answered using a different document.

    Match longest registered names first (SSPR FAQ before SSPR), without exposing
    unavailable identities in the response. This never changes an access scope.
    """
    aliases = []
    for entry in DocumentManifest.load(manifest_path).entries:
        for alias in set(
            [
                entry.title,
                *entry.aliases,
                *([entry.policy_id] if entry.policy_id else []),
            ]
        ):
            words = re.findall(r"[A-Za-z0-9]+", alias)
            if not words or len("".join(words)) < 4:
                continue
            pattern = re.compile(
                r"(?<!\w)" + r"[\W_]*".join(map(re.escape, words)) + r"(?!\w)", re.I
            )
            aliases.append((len(alias), pattern, entry.id))
    occupied, requested = [], set()
    for _, pattern, identifier in sorted(aliases, key=lambda item: -item[0]):
        for match in pattern.finditer(question):
            if any(
                match.start() < end and match.end() > start for start, end in occupied
            ):
                continue
            occupied.append((match.start(), match.end()))
            requested.add(identifier)
    return requested


def requested_sources_available(question, documents, manifest_path=DEFAULT_MANIFEST):
    return requested_source_ids(question, manifest_path).issubset(
        {document.id for document in documents}
    )


STOPWORDS = set(
    "a an and are as at be by can do does for from how i if in is it me my of on or should that the their this to use what when where which who with would must need required please".split()
)


def terms(text):
    return [
        word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOPWORDS
    ]


def search_terms(question):
    words = terms(question)
    expansions = {
        "sspr": "source selection price reasonableness form",
        "bid": "competitive bidding",
        "bidding": "competitive bid",
        "quotes": "quotations proposals",
        "quote": "quotations proposals",
        "federally": "federal",
    }
    return " ".join(words + [expansions[word] for word in words if word in expansions])


def lexical_scores(query, texts):
    """BM25 over the authorized corpus only. Zero-match records do not rank."""
    tokens = [Counter(terms(text)) for text in texts]
    lengths = [sum(token.values()) for token in tokens]
    average = sum(lengths) / max(len(texts), 1)
    frequencies = Counter(word for token in tokens for word in token)
    scores = []
    for token, length in zip(tokens, lengths):
        score = 0.0
        for word in set(terms(query)):
            frequency = token[word]
            if frequency:
                idf = math.log(
                    1
                    + (len(texts) - frequencies[word] + 0.5) / (frequencies[word] + 0.5)
                )
                score += (
                    idf
                    * frequency
                    * 2.5
                    / (frequency + 1.5 * (0.25 + 0.75 * length / max(average, 1)))
                )
        scores.append(score)
    return scores


def substantive(section):
    if section.kind not in ("body", "table"):
        return False
    # Heading-only records and document footers remain stored, but are not answers.
    lines = [line.strip() for line in section.text.splitlines() if line.strip()]
    content = " ".join(line for line in lines if line != section.title.strip())
    return (
        len(terms(content)) >= 6 or (len(content) >= 25 and "." in content)
    ) and not (len(lines) < 5 and all(line.isupper() for line in lines))


@dataclass
class Passage:
    document: DocumentRecord
    section: SectionRecord
    start: int
    end: int
    via_reference: dict | None = None

    @property
    def text(self):
        return self.section.text[self.start : self.end]

    def citation(self, number):
        locations = locations_for(self.section, self.start, self.end)
        pages = sorted({location.page for location in locations if location.page})
        page = (
            ""
            if not pages
            else str(pages[0]) if len(pages) == 1 else f"{pages[0]}-{pages[-1]}"
        )
        return {
            "citation_id": number,
            "policy": self.document.title,
            "section": self.section.title,
            "page": page,
            "document_id": self.document.id,
            "document_version_id": self.document.version_id,
            "parent_section_id": self.section.id,
            "source_url": self.document.source_url,
            "start": self.start,
            "end": self.end,
            "is_full_section": self.start == 0 and self.end == len(self.section.text),
            "locations": [location.model_dump() for location in locations],
            "via_reference": self.via_reference,
        }


class SectionRetriever:
    def __init__(self, index: PolicyIndex, semantic_rank=None, rerank=None):
        self.corpus = index.retrieval_snapshot()
        self.docs = {doc.version_id: doc for doc in self.corpus["documents"]}
        self.sections = {section.id: section for section in self.corpus["sections"]}
        self.nodes = {node.id: node for node in self.corpus["nodes"]}
        self.semantic_rank = semantic_rank
        self.rerank = rerank
        self.candidates = []
        seen = set()
        for chunk in self.corpus["chunks"]:
            section = self.sections[chunk.parent_section_id]
            ancestor = section
            historical = False
            while ancestor:
                if "REVISION HISTORY" in ancestor.title.upper():
                    historical = True
                    break
                ancestor = self.sections.get(ancestor.parent_section_id)
            if historical:
                continue
            # A matched heading may promote to its nearest substantive parent.
            while not substantive(section) and section.parent_section_id:
                section = self.sections[section.parent_section_id]
            if not substantive(section):
                continue
            if section.id != chunk.parent_section_id:
                if len(section.text) > 12000:
                    continue
                key, text, start, end = section.id, section.text, 0, len(section.text)
            else:
                key, text, start, end = chunk.id, chunk.text, chunk.start, chunk.end
                if len(terms(text)) < 4:
                    continue
            if key in seen:
                continue
            seen.add(key)
            self.candidates.append(
                dict(id=key, section=section, text=text, start=start, end=end)
            )

    def rank(self, question, candidates=None):
        candidates = self.candidates if candidates is None else candidates
        if not candidates:
            return []
        query = search_terms(question)
        texts = [item["text"] for item in candidates]
        lexical = lexical_scores(query, texts)
        lexical_order = sorted(
            (i for i in range(len(texts)) if lexical[i] > 0), key=lambda i: -lexical[i]
        )[:40]
        ranks = [lexical_order]
        if self.semantic_rank:
            # This hook sees only source records admitted by the server scope.
            semantic = self.semantic_rank(
                question, [(item["id"], item["text"]) for item in candidates]
            )
            ranks.append(
                [
                    i
                    for i in sorted(range(len(texts)), key=lambda i: -semantic[i])
                    if semantic[i] >= 0.25
                ][:40]
            )
        scores = Counter()
        for ranked in ranks:
            for position, i in enumerate(ranked):
                scores[i] += 1 / (60 + position)
        ordered = sorted(scores, key=lambda i: (-scores[i], candidates[i]["id"]))[:30]
        if self.rerank and ordered:
            values = self.rerank(question, [texts[i] for i in ordered])
            ordered = [
                i for _, i in sorted(zip(values, ordered), key=lambda pair: -pair[0])
            ]
        return [candidates[i] for i in ordered]

    def _passage(self, candidate, reference=None, max_characters=12000):
        section = candidate["section"]
        start, end = 0, len(section.text)
        if end > max_characters:
            # Keep an explicitly identified, exact source span around the match.
            # No representation of a partial excerpt as a complete section.
            center = (candidate["start"] + candidate["end"]) // 2
            start = max(0, center - max_characters // 2)
            end = min(len(section.text), start + max_characters)
            # Move inward to paragraph boundaries without dropping the match.
            boundary = section.text.find("\n\n", start, candidate["start"])
            if boundary >= 0:
                start = boundary + 2
            boundary = section.text.rfind("\n\n", candidate["end"], end)
            if boundary >= candidate["end"]:
                end = boundary
        return Passage(
            self.docs[section.document_version_id], section, start, end, reference
        )

    def retrieve(self, question, max_sources=6, max_characters=24000):
        requested = requested_source_ids(question)
        primary = (
            [
                candidate
                for candidate in self.candidates
                if self.docs[candidate["section"].document_version_id].id in requested
            ]
            if requested
            else self.candidates
        )
        ranked = self.rank(question, primary)
        passages, chosen, used = [], set(), 0

        def add(candidate, reference=None):
            nonlocal used
            section = candidate["section"]
            if section.id in chosen or len(passages) >= max_sources:
                return False
            # Avoid duplicate full ancestor/descendant text.
            if any(
                p.section.document_version_id == section.document_version_id
                and (section.text in p.text or p.text in section.text)
                for p in passages
            ):
                return False
            remaining = max_characters - used
            if remaining < 500:
                return False
            passage = self._passage(candidate, reference, min(12000, remaining))
            if candidate["end"] - candidate["start"] > len(passage.text):
                return False
            passages.append(passage)
            chosen.add(section.id)
            used += len(passage.text)
            return True

        for candidate in ranked:
            add(candidate)
            if len(passages) >= min(4, max_sources):
                break
        # One explicit reference hop. Do not traverse a document's contains edges
        # indiscriminately, follow external URLs, or interpret overrides as rules.
        reference_count = 0
        for passage in list(passages):
            for edge in self.corpus["edges"]:
                if edge.relation != "references":
                    continue
                evidence = next(
                    (
                        e
                        for e in edge.evidence
                        if e.document_version_id == passage.document.version_id
                        and e.quote in passage.text
                        and (
                            e.section_id == passage.section.id
                            or self.sections[e.section_id].text in passage.text
                        )
                    ),
                    None,
                )
                if evidence is None:
                    continue
                target = self.nodes[edge.target_id]
                if (
                    target.kind == "reference"
                    or target.document_version_id == passage.document.version_id
                ):
                    continue
                candidates = [
                    item
                    for item in self.candidates
                    if item["section"].document_version_id == target.document_version_id
                ]
                if target.kind == "section":
                    candidates = [
                        item for item in candidates if item["section"].id == target.id
                    ]
                for candidate in self.rank(question + " " + target.label, candidates):
                    if add(
                        candidate,
                        {
                            "edge_id": edge.id,
                            "relation": edge.relation,
                            "from_section_id": evidence.section_id,
                            "quote": evidence.quote,
                            "locations": [
                                location.model_dump() for location in evidence.locations
                            ],
                        },
                    ):
                        reference_count += 1
                        break
                if len(passages) >= max_sources or reference_count >= 2:
                    return passages
        return passages
