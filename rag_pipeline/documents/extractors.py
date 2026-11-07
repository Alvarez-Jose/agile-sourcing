"""Extract original content and structured tables without model/API calls."""

from pathlib import Path
from collections import Counter
import base64
import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET

import pdfplumber
from pdfminer.pdftypes import resolve1
from pdfminer.utils import decode_text

from rag_pipeline.documents.models import (
    SourceBlock,
    SourceLink,
    SourceLocation,
    TableCell,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _block_id(version_id: str, ordinal: int) -> str:
    return f"{version_id}:block:{ordinal:05d}"


def pdf_source_links(page, location):
    """Read only link targets, avoiding malformed annotation title/contents codecs."""
    links = []
    for ordinal, reference in enumerate(resolve1(page.page_obj.annots) or [], start=1):
        annotation = resolve1(reference)
        if not isinstance(annotation, dict):
            continue
        action = resolve1(annotation.get("A", {}))
        raw = resolve1(action.get("URI")) if isinstance(action, dict) else None
        if raw is None:
            continue
        raw_base64, encoding = None, None
        if isinstance(raw, bytes):
            raw_base64 = base64.b64encode(raw).decode("ascii")
            try:
                if raw.startswith((b"\xfe\xff", b"\xff\xfe")):
                    target, encoding = raw.decode("utf-16"), "utf-16"
                else:
                    try:
                        target, encoding = raw.decode("utf-8"), "utf-8"
                    except UnicodeDecodeError:
                        target, encoding = decode_text(raw), "pdfdocencoding"
            except (UnicodeError, IndexError):
                target = "unresolved-uri:" + hashlib.sha256(raw).hexdigest()
                encoding = "unresolved; original bytes preserved"
        else:
            target = str(raw)
        rectangle = resolve1(annotation.get("Rect"))
        bbox, label = None, ""
        if rectangle and len(rectangle) == 4:
            x0, y0, x1, y1 = map(float, rectangle)
            bbox = [
                min(x0, x1),
                page.height - max(y0, y1),
                max(x0, x1),
                page.height - min(y0, y1),
            ]
            try:
                label = page.crop(tuple(bbox), strict=False).extract_text() or ""
            except ValueError:
                pass
        links.append(
            SourceLink(
                text=label,
                target=target,
                raw_target_base64=raw_base64,
                encoding=encoding,
                location=location.model_copy(
                    update={"bbox": bbox, "element": f"annotation[{ordinal}]"}
                ),
            )
        )
    return links


def extract_pdf_blocks(path: Path, version_id: str, source: str) -> list[SourceBlock]:
    blocks = []
    with pdfplumber.open(path) as pdf:
        sizes = Counter(
            round(char.get("size", 0), 1)
            for page in pdf.pages
            for char in page.chars
            if str(char.get("text", "")).strip()
        )
        body_size = sizes.most_common(1)[0][0] if sizes else 0
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(layout=False) or ""
            location = SourceLocation(file=source, format="pdf", page=number)
            tables = page.find_tables()
            hints, cursor = [], 0
            for line in page.extract_text_lines(layout=False):
                label = line["text"].strip()
                start = text.find(line["text"], cursor)
                if start < 0:
                    continue
                cursor = start + len(line["text"])
                chars = [
                    char
                    for char in line.get("chars", [])
                    if str(char.get("text", "")).strip()
                ]
                if not chars or not 4 <= len(label) <= 150 or label.endswith("."):
                    continue
                if any(
                    line["x0"] >= table.bbox[0]
                    and line["x1"] <= table.bbox[2]
                    and line["top"] >= table.bbox[1]
                    and line["bottom"] <= table.bbox[3]
                    for table in tables
                ):
                    continue
                size = max(char.get("size", 0) for char in chars)
                bold = sum(
                    "bold" in char.get("fontname", "").lower() for char in chars
                ) / len(chars)
                if size >= body_size + 2 or bold >= 0.85:
                    hints.append(
                        {
                            "start": start,
                            "title": label,
                            "level": 1 if size >= body_size + 4 else 2,
                            "bbox": [
                                line["x0"],
                                line["top"],
                                line["x1"],
                                line["bottom"],
                            ],
                        }
                    )
            if text.strip():
                links = pdf_source_links(page, location)
                blocks.append(
                    SourceBlock(
                        id=_block_id(version_id, len(blocks)),
                        kind="text",
                        text=text,
                        location=location,
                        heading_hints=hints,
                        links=links,
                    )
                )
            # The page transcription remains intact. Tables are a second, structured
            # representation with exact page/bbox provenance; they are not substituted
            # for, or silently removed from, the original page text.
            for ordinal, table in enumerate(tables):
                rows = [
                    [TableCell(text=value or "") for value in row]
                    for row in table.extract()
                ]
                if not any(cell.text.strip() for row in rows for cell in row):
                    continue
                table_text = "\n".join(
                    " | ".join(cell.text for cell in row) for row in rows
                )
                blocks.append(
                    SourceBlock(
                        id=_block_id(version_id, len(blocks)),
                        kind="table",
                        text=table_text,
                        rows=rows,
                        location=location.model_copy(
                            update={
                                "bbox": list(table.bbox),
                                "element": f"table[{ordinal + 1}]",
                            }
                        ),
                    )
                )
    return blocks


def _text(element: ET.Element, skip_textboxes=True) -> str:
    parts = []

    def walk(node):
        if skip_textboxes and node.tag == W + "txbxContent":
            return
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
        elif node.tag == W + "sym":
            parts.append(
                f"[symbol:{node.get(W + 'font', '')}:{node.get(W + 'char', '')}]"
            )
        elif node.tag == W + "checkBox":
            checked = node.find(W + "checked")
            value = (
                checked.get(W + "val", "1") if checked is not None else "unspecified"
            )
            parts.append(f"[checkbox:{value}]")
        for child in node:
            walk(child)

    walk(element)
    return "".join(parts)


def extract_docx_blocks(path: Path, version_id: str, source: str) -> list[SourceBlock]:
    blocks = []
    with zipfile.ZipFile(path) as package:
        styles = {}
        if "word/styles.xml" in package.namelist():
            for style in ET.fromstring(package.read("word/styles.xml")).iter(
                W + "style"
            ):
                name = style.find(W + "name")
                label = name.get(W + "val", "") if name is not None else ""
                match = re.search(r"heading\s*(\d+)", label, re.I)
                if match:
                    styles[style.get(W + "styleId")] = int(match.group(1))

        relationships = {}
        for filename in package.namelist():
            if filename.startswith("word/_rels/") and filename.endswith(".rels"):
                source_part = "word/" + Path(filename).name[:-5]
                relationships[source_part] = {
                    node.get("Id"): node.get("Target", "")
                    for node in ET.fromstring(package.read(filename))
                }

        def source_links(node, part, location):
            result = []
            for ordinal, link in enumerate(node.iter(W + "hyperlink"), start=1):
                relation = link.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                target = relationships.get(part, {}).get(relation)
                target = target or (
                    "#" + link.get(W + "anchor") if link.get(W + "anchor") else ""
                )
                if target:
                    result.append(
                        SourceLink(
                            text=_text(link),
                            target=target,
                            location=location.model_copy(
                                update={
                                    "element": f"({location.element}//w:hyperlink)[{ordinal}]"
                                }
                            ),
                        )
                    )
            return result

        def emit(kind, text, part, element, level=None, rows=None, node=None):
            if text.strip():
                location = SourceLocation(
                    file=source, format="docx", part=part, element=element
                )
                blocks.append(
                    SourceBlock(
                        id=_block_id(version_id, len(blocks)),
                        kind=kind,
                        text=text,
                        heading_level=level,
                        rows=rows or [],
                        location=location,
                        links=(
                            source_links(node, part, location)
                            if node is not None
                            else []
                        ),
                    )
                )

        def visit(container, part, prefix, part_kind="text"):
            for index, node in enumerate(container, start=1):
                locator = f"{prefix}/*[{index}]"
                if node.tag == W + "p":
                    pstyle = node.find(f"{W}pPr/{W}pStyle")
                    level = (
                        styles.get(pstyle.get(W + "val"))
                        if pstyle is not None
                        else None
                    )
                    emit(
                        "heading" if level and part_kind == "text" else part_kind,
                        _text(node),
                        part,
                        locator,
                        level,
                        node=node,
                    )
                    for box_index, box in enumerate(
                        node.iter(W + "txbxContent"), start=1
                    ):
                        visit(
                            box,
                            part,
                            f"({locator}//w:txbxContent)[{box_index}]",
                            "textbox",
                        )
                elif node.tag == W + "tbl":
                    rows = []
                    for row in node.findall(W + "tr"):
                        cells = []
                        for cell in row.findall(W + "tc"):
                            props = cell.find(W + "tcPr")
                            span = (
                                props.find(W + "gridSpan")
                                if props is not None
                                else None
                            )
                            merge = (
                                props.find(W + "vMerge") if props is not None else None
                            )
                            texts = [_text(p) for p in cell.findall(W + "p")]
                            # Preserve nested tables inside the physical cell as text.
                            texts.extend(_text(t) for t in cell.findall(W + "tbl"))
                            cells.append(
                                TableCell(
                                    text="\n".join(texts),
                                    column_span=(
                                        int(span.get(W + "val", "1"))
                                        if span is not None
                                        else 1
                                    ),
                                    vertical_merge=(
                                        merge.get(W + "val", "continue")
                                        if merge is not None
                                        else None
                                    ),
                                )
                            )
                        rows.append(cells)
                    emit(
                        "table",
                        "\n".join(" | ".join(c.text for c in row) for row in rows),
                        part,
                        locator,
                        rows=rows,
                        node=node,
                    )
                    for box_index, box in enumerate(
                        node.iter(W + "txbxContent"), start=1
                    ):
                        visit(
                            box,
                            part,
                            f"({locator}//w:txbxContent)[{box_index}]",
                            "textbox",
                        )
                elif node.tag not in (W + "sectPr", W + "pPr", W + "tcPr"):
                    # Content controls (sdt), custom XML and wrapper elements retain order.
                    visit(node, part, locator, part_kind)

        body = ET.fromstring(package.read("word/document.xml")).find(W + "body")
        if body is None:
            raise ValueError("DOCX has no document body")
        visit(body, "word/document.xml", "/w:document/w:body")
        # These parts contain revision dates, contextual titles, and footnotes. They
        # are indexed as separate source blocks, not appended to fake body pages.
        for part in sorted(package.namelist()):
            match = re.fullmatch(r"word/(header|footer)\d+\.xml", part)
            if match:
                visit(
                    ET.fromstring(package.read(part)),
                    part,
                    "/w:hdr" if match.group(1) == "header" else "/w:ftr",
                    match.group(1),
                )
            elif part in ("word/footnotes.xml", "word/endnotes.xml"):
                visit(
                    ET.fromstring(package.read(part)),
                    part,
                    "/w:footnotes" if part.endswith("footnotes.xml") else "/w:endnotes",
                    "footnote",
                )
    return blocks
