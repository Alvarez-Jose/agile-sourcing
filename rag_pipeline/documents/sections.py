"""Hierarchical full sections and lossless, source-aligned child windows."""

import hashlib
import re
from collections import Counter
from collections.abc import Callable

from rag_pipeline.documents.models import (
    ChunkRecord,
    DocumentRecord,
    SectionBlock,
    SectionRecord,
    SourceLocation,
)


def lexical_spans(text: str) -> list[tuple[int, int]]:
    """Offline preview tokenizer. Embedding builds may supply model token offsets."""
    return [(match.start(), match.end()) for match in re.finditer(r"\w+|[^\w\s]", text)]


def _heading(line: str):
    text = line.strip()
    if len(text) > 180 or re.search(r"\.{3,}\s*\d+\s*$", text):
        return None
    if re.match(r"^(ARTICLE|PART|SECTION)\s+(\d+|[IVX]+)\b", text, re.I):
        return 1, text
    if re.match(r"^[IVXLCDM]{1,6}\.\s+[A-Z]", text):
        return 1, text
    if re.match(r"^[A-Z]\.\s+[A-Z]", text):
        return 2, text
    if len(text) >= 6 and re.fullmatch(r"[A-Z][A-Z &/()\-:]{4,}", text):
        return 2, text
    return None


def locations_for(section: SectionRecord, start: int, end: int) -> list[SourceLocation]:
    unique = {}
    for block in section.blocks:
        if block.end > start and block.start < end:
            unique[block.location.model_dump_json()] = block.location
    return list(unique.values())


def make_sections_and_chunks(
    document: DocumentRecord,
    max_tokens: int = 240,
    overlap_tokens: int = 40,
    token_spans: Callable[[str], list[tuple[int, int]]] = lexical_spans,
    tokenizer_name: str = "lexical-v1",
) -> tuple[list[SectionRecord], list[ChunkRecord]]:
    if max_tokens < 2 or not 0 <= overlap_tokens < max_tokens:
        raise ValueError("Require max_tokens >= 2 and 0 <= overlap_tokens < max_tokens")
    body, ancillary = [], []
    for block in document.blocks:
        part = block.location.part or ""
        (
            ancillary
            if block.kind in ("header", "footer", "footnote")
            or part.startswith(
                ("word/header", "word/footer", "word/footnotes", "word/endnotes")
            )
            else body
        ).append(block)
    text, positions = "", []
    for block in body:
        if text:
            text += "\n\n"
        start = len(text)
        text += block.text
        positions.append((start, len(text), block))

    ranges = [(0, len(text), document.title, 0, "body")]
    headings, tables = [], []
    running_labels = Counter()
    for _, _, block in positions:
        if block.location.format == "pdf" and block.kind == "text":
            lines = block.text.splitlines()
            running_labels.update(set(line.strip() for line in lines[:3] + lines[-3:]))
    repeated = {label for label, count in running_labels.items() if count > 1}
    seen_running = set()
    for start, end, block in positions:
        if block.kind == "table":
            tables.append(
                (
                    start,
                    end,
                    f"Table: {block.location.element or block.id}",
                    99,
                    "table",
                )
            )
            continue
        offset = start
        lines = block.text.splitlines(keepends=True)
        hints = {
            hint["start"]: (hint["level"], hint["title"])
            for hint in block.heading_hints
        }
        for line_index, line in enumerate(lines):
            found = _heading(line)
            found = found or hints.get(offset - start)
            if block.kind == "heading" and offset == start:
                found = block.heading_level or 1, block.text.strip()
            is_running = (
                block.location.format == "pdf"
                and line.strip() in repeated
                and (line_index < 3 or line_index >= len(lines) - 3)
                and not re.match(
                    r"^(ARTICLE|PART|SECTION)\b|^[IVXLCDM]{1,6}\.|^[A-Z]\.",
                    line.strip(),
                    re.I,
                )
            )
            if found and is_running and line.strip() in seen_running:
                found = None
            if found:
                headings.append((offset, found[0], found[1]))
                if is_running:
                    seen_running.add(line.strip())
            offset += len(line)
    for index, (start, level, title) in enumerate(headings):
        end = next(
            (
                other_start
                for other_start, other_level, _ in headings[index + 1 :]
                if other_level <= level
            ),
            len(text),
        )
        ranges.append((start, end, title, level, "body"))
    ranges.extend(tables)
    # Every non-body source part gets its own genuine location, not a fabricated page.
    for block in ancillary:
        kind = next(
            (
                name
                for name in ("header", "footer")
                if (block.location.part or "").startswith("word/" + name)
            ),
            "footnote",
        )
        ranges.append(
            (
                0,
                len(block.text),
                f"{block.kind.title()}: {block.location.part}",
                100,
                kind,
            )
        )

    sections, range_sections = [], []
    body_count = 1 + len(headings) + len(tables)
    for ordinal, (start, end, title, level, kind) in enumerate(ranges):
        ancillary_block = (
            ancillary[ordinal - body_count] if ordinal >= body_count else None
        )
        value = ancillary_block.text if ancillary_block else text[start:end]
        if not value.strip():
            continue
        identifier = hashlib.sha256(
            f"{document.version_id}:{ordinal}:{start}:{end}:{title}:{value}".encode()
        ).hexdigest()[:20]
        section = SectionRecord(
            id=f"section:{identifier}",
            document_version_id=document.version_id,
            ordinal=ordinal,
            title=title,
            kind=kind,
            text=value,
        )
        if ancillary_block:
            section.blocks.append(
                SectionBlock(
                    block_id=ancillary_block.id,
                    start=0,
                    end=len(value),
                    source_end=len(value),
                    location=ancillary_block.location,
                    kind=ancillary_block.kind,
                )
            )
        else:
            for bs, be, block in positions:
                if be > start and bs < end:
                    section.blocks.append(
                        SectionBlock(
                            block_id=block.id,
                            start=max(bs, start) - start,
                            end=min(be, end) - start,
                            source_start=max(bs, start) - bs,
                            source_end=min(be, end) - bs,
                            location=block.location,
                            kind=block.kind,
                        )
                    )
            candidates = [
                (s, e, previous_level, previous)
                for s, e, previous_level, previous in range_sections
                if s <= start and e >= end and previous_level < level
            ]
            if candidates:
                section.parent_section_id = max(candidates, key=lambda item: item[2])[
                    3
                ].id
            range_sections.append((start, end, level, section))
        sections.append(section)

    chunks = []

    def windows(section, value, base_offset):
        spans = token_spans(value)
        cursor = 0
        while cursor < len(spans):
            last = min(cursor + max_tokens, len(spans))
            start = 0 if cursor == 0 else spans[cursor][0]
            end = len(value) if last == len(spans) else spans[last][0]
            start, end = start + base_offset, end + base_offset
            snippet = section.text[start:end]
            identifier = hashlib.sha256(
                f"{section.id}:{start}:{end}".encode()
            ).hexdigest()[:24]
            chunks.append(
                ChunkRecord(
                    id=f"chunk:{identifier}",
                    document_version_id=document.version_id,
                    parent_section_id=section.id,
                    start=start,
                    end=end,
                    text=snippet,
                    token_count=last - cursor,
                    tokenizer=tokenizer_name,
                    locations=locations_for(section, start, end),
                )
            )
            if last == len(spans):
                break
            cursor = last - overlap_tokens

    # Partition ownership so nested full sections do not cause duplicate embeddings.
    boundaries = sorted(
        {
            0,
            len(text),
            *(start for start, *_ in range_sections),
            *(end for _, end, *_ in range_sections),
        }
    )
    for start, end in zip(boundaries, boundaries[1:]):
        owners = [
            item for item in range_sections if item[0] <= start and item[1] >= end
        ]
        if owners:
            section_start, _, _, section = max(owners, key=lambda item: item[2])
            windows(section, text[start:end], start - section_start)
    for section in sections:
        if section.kind in ("header", "footer", "footnote"):
            windows(section, section.text, 0)
    return sections, chunks
