"""
ingestion/chunker.py

Token-aware chunker with semantic section splitting for UC policy documents.
Replaces the original page-based chunker.

Key improvements over v1:
- Splits at 150-300 tokens per chunk (not per page)
- 50-token overlap between adjacent chunks so context isn't lost at boundaries
- Respects UC policy section structure (numbered sections, lettered subsections)
- One policy concept per chunk where possible
- Preserves section heading as metadata on each chunk
"""

import re
import tiktoken

# ── Token counter ─────────────────────────────────────────────────────────────
# Try tiktoken first (most accurate), fall back to word-count approximation
try:
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
    def truncate_to_tokens(text: str, max_tokens: int) -> str:
        tokens = _enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return _enc.decode(tokens[:max_tokens])
except Exception:
    # Fallback: ~1.3 tokens per word is a good approximation for English policy text
    def count_tokens(text: str) -> int:
        return int(len(text.split()) * 1.3)
    def truncate_to_tokens(text: str, max_tokens: int) -> str:
        words = text.split()
        target_words = int(max_tokens / 1.3)
        if len(words) <= target_words:
            return text
        return " ".join(words[:target_words])


# ── UC Policy section patterns ────────────────────────────────────────────────
# Matches UC policy structural markers like:
#   I.  II.  III.  (Roman numerals)
#   A.  B.  C.     (Capital letters)
#   1.  2.  3.     (Numbers)
#   a.  b.  c.     (Lowercase)
#   (1) (2) (a)    (Parenthetical)
#   SECTION DEFINITIONS POLICY PROCEDURES BACKGROUND
_SECTION_PATTERN = re.compile(
    r'(?m)^[ \t]*('
    r'(?:Part\s+\d+|'
    r'[IVXLCDM]{1,6}\.|'          # Roman numerals
    r'[A-Z]\.\s|'                  # Capital letter sections
    r'\d{1,2}\.\s|'                # Numbered sections
    r'[a-z]\)\s|'                  # Lowercase parenthetical
    r'\(\d+\)\s|'                  # Number parenthetical
    r'(?:SECTION|DEFINITIONS?|POLICY|PROCEDURES?|BACKGROUND|PURPOSE|'
    r'SCOPE|RESPONSIBILITIES|COMPLIANCE|REFERENCES?|APPENDIX|EXHIBIT)'
    r')'
    r')',
    re.IGNORECASE
)

# Headings that are strong section breaks
_HEADING_PATTERN = re.compile(
    r'(?m)^[ \t]*([A-Z][A-Z\s]{4,}:?)\s*$'  # ALL CAPS lines
)


# ── Core splitting logic ──────────────────────────────────────────────────────
def split_into_sections(text: str) -> list[str]:
    """
    Split text into sections based on UC policy structural markers.
    Returns a list of text sections.
    """
    # Find all section boundary positions
    boundaries = set()

    for match in _SECTION_PATTERN.finditer(text):
        boundaries.add(match.start())

    for match in _HEADING_PATTERN.finditer(text):
        boundaries.add(match.start())

    if not boundaries:
        # No structure detected — split on double newlines
        return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    # Split text at boundaries
    positions = sorted(boundaries)
    sections  = []

    for i, pos in enumerate(positions):
        end  = positions[i + 1] if i + 1 < len(positions) else len(text)
        section = text[pos:end].strip()
        if section:
            sections.append(section)

    # Include any text before the first boundary
    if positions[0] > 0:
        prefix = text[:positions[0]].strip()
        if prefix:
            sections.insert(0, prefix)

    return [s for s in sections if len(s.strip()) > 20]


def chunk_text(
    text: str,
    min_tokens: int = 80,
    max_tokens: int = 300,
    overlap_tokens: int = 50
) -> list[str]:
    """
    Split text into token-aware chunks with overlap.

    1. First splits on section boundaries
    2. If a section is too large, splits on paragraph boundaries
    3. If still too large, splits on sentence boundaries
    4. Adds overlap_tokens from previous chunk to maintain context
    """
    sections = split_into_sections(text)
    chunks   = []
    prev_tail = ""  # overlap buffer from previous chunk

    for section in sections:
        section_tokens = count_tokens(section)

        if section_tokens <= max_tokens:
            # Section fits in one chunk — add with overlap prefix
            if prev_tail:
                chunk = prev_tail + " " + section
                # If combined still fits, keep it
                if count_tokens(chunk) <= max_tokens:
                    chunks.append(chunk.strip())
                else:
                    chunks.append(section.strip())
            else:
                if section_tokens >= min_tokens:
                    chunks.append(section.strip())
                elif chunks:
                    # Too small — merge with previous chunk if possible
                    combined = chunks[-1] + " " + section
                    if count_tokens(combined) <= max_tokens:
                        chunks[-1] = combined.strip()
                    else:
                        chunks.append(section.strip())
                else:
                    chunks.append(section.strip())

            # Update overlap buffer — take last overlap_tokens of this section
            prev_tail = truncate_to_tokens(
                " ".join(section.split()[-30:]),  # last ~30 words
                overlap_tokens
            )

        else:
            # Section too large — split into paragraphs first
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', section) if p.strip()]

            if not paragraphs:
                paragraphs = [section]

            buffer = prev_tail + " " if prev_tail else ""

            for para in paragraphs:
                para_tokens = count_tokens(buffer + para)

                if para_tokens <= max_tokens:
                    buffer += para + " "
                else:
                    # Paragraph itself too long — split on sentences
                    if buffer.strip() and count_tokens(buffer.strip()) >= min_tokens:
                        chunks.append(buffer.strip())

                    # Split paragraph on sentence boundaries
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    buffer    = ""

                    for sent in sentences:
                        test = buffer + sent + " "
                        if count_tokens(test) <= max_tokens:
                            buffer = test
                        else:
                            if buffer.strip() and count_tokens(buffer.strip()) >= min_tokens:
                                chunks.append(buffer.strip())
                            # Sentence itself might be > max_tokens (rare in policy docs)
                            if count_tokens(sent) > max_tokens:
                                # Hard truncate as last resort
                                chunks.append(truncate_to_tokens(sent, max_tokens))
                                buffer = ""
                            else:
                                buffer = sent + " "

            # Flush remaining buffer
            if buffer.strip() and count_tokens(buffer.strip()) >= min_tokens:
                chunks.append(buffer.strip())
            elif buffer.strip() and chunks:
                # Too small — merge with previous
                combined = chunks[-1] + " " + buffer.strip()
                if count_tokens(combined) <= max_tokens:
                    chunks[-1] = combined.strip()

            # Update overlap
            if chunks:
                prev_tail = truncate_to_tokens(
                    " ".join(chunks[-1].split()[-30:]),
                    overlap_tokens
                )

    return [c for c in chunks if c.strip()]


# ── Public API ────────────────────────────────────────────────────────────────
def chunk_by_section(
    pages: list[dict],
    min_tokens: int = 80,
    max_tokens: int = 300,
    overlap_tokens: int = 50
) -> list[dict]:
    """
    Main entry point. Takes a list of page dicts from extract_pdf or extract_docx
    and returns a list of chunk dicts with enriched metadata.

    Input page dict shape:
        {"source": str, "page": int|str, "text": str, "section": str (optional)}

    Output chunk dict shape:
        {"source": str, "page": int|str, "text": str, "section": str,
         "chunk_index": int, "token_count": int}
    """
    all_chunks = []

    for page in pages:
        text   = page.get("text", "").strip()
        source = page.get("source", "")
        page_n = page.get("page", "")
        section = page.get("section", "")

        if not text:
            continue

        # Try to detect section heading from the start of the text
        heading_match = re.match(
            r'^([A-Z][^\n]{3,80})\n',
            text
        )
        detected_heading = heading_match.group(1).strip() if heading_match else section

        raw_chunks = chunk_text(text, min_tokens, max_tokens, overlap_tokens)

        for i, chunk_text_val in enumerate(raw_chunks):
            # Try to extract the section heading from this specific chunk
            chunk_heading = _extract_heading(chunk_text_val) or detected_heading

            all_chunks.append({
                "source":      source,
                "page":        page_n,
                "section":     chunk_heading,
                "text":        chunk_text_val,
                "chunk_index": i,
                "token_count": count_tokens(chunk_text_val),
            })

    return all_chunks


def _extract_heading(text: str) -> str:
    """Extract a section heading from the beginning of a chunk."""
    lines = text.strip().split("\n")
    for line in lines[:3]:
        line = line.strip()
        if not line:
            continue
        # Match Roman numerals, capital letters, numbers followed by text
        if re.match(r'^([IVXLCDM]+\.|[A-Z]\.|[0-9]+\.)\s+\S', line):
            return line[:80]
        # ALL CAPS heading
        if re.match(r'^[A-Z][A-Z\s]{4,}$', line) and len(line) < 80:
            return line
    return ""


# ── Diagnostics ───────────────────────────────────────────────────────────────
def print_chunk_stats(chunks: list[dict]):
    """Print a summary of chunk quality metrics."""
    if not chunks:
        print("No chunks to analyze.")
        return

    token_counts = [c["token_count"] for c in chunks]
    avg   = sum(token_counts) / len(token_counts)
    small = sum(1 for t in token_counts if t < 80)
    large = sum(1 for t in token_counts if t > 350)

    print(f"\n── Chunk Statistics ──────────────────────────────")
    print(f"  Total chunks:     {len(chunks)}")
    print(f"  Avg token count:  {avg:.0f}")
    print(f"  Min token count:  {min(token_counts)}")
    print(f"  Max token count:  {max(token_counts)}")
    print(f"  Too small (<80):  {small} ({100*small/len(chunks):.1f}%)")
    print(f"  Too large (>350): {large} ({100*large/len(chunks):.1f}%)")

    # Distribution
    buckets = {"0-80": 0, "80-150": 0, "150-300": 0, "300+": 0}
    for t in token_counts:
        if t < 80:        buckets["0-80"] += 1
        elif t < 150:     buckets["80-150"] += 1
        elif t <= 300:    buckets["150-300"] += 1
        else:             buckets["300+"] += 1

    print(f"\n  Token distribution:")
    for bucket, count in buckets.items():
        bar = "█" * int(20 * count / len(chunks))
        print(f"    {bucket:>8}  {bar:<20} {count}")
    print()


if __name__ == "__main__":
    # Quick test with a sample UC policy text
    sample = """
I. POLICY SUMMARY

The University of California requires competitive bidding for all purchases
exceeding $100,000 annually. This policy applies to all campuses, medical
centers, and national laboratories.

A. Competitive Bidding Requirements

All Purchase Agreements involving an expenditure of more than $100,000
annually must be competitively bid unless a documented exception applies.
Exceptions include sole-source justifications, emergency purchases, and
certified small business set-asides.

B. Small Business Set-Aside

Pursuant to California Public Contract Code Section 10508.5, the University
may award contracts up to $250,000 to certified small businesses or Disabled
Veteran Business Enterprises without formal competitive bidding, provided that
price quotations are obtained from at least two certified entities.

II. PROCEDURES

A. Source Selection

The buyer must document the source selection rationale using the SSPR form
for all purchases subject to federal funding requirements.

1. Complete Sections I through IV of the SSPR form.
2. Attach price quotations from at least two qualified suppliers.
3. Obtain supervisor approval for purchases exceeding $50,000.
"""

    pages = [{"source": "BUS-43_test.pdf", "page": 1, "text": sample}]
    chunks = chunk_by_section(pages)
    print_chunk_stats(chunks)
    for i, c in enumerate(chunks):
        print(f"\nChunk {i+1} ({c['token_count']} tokens) [{c['section'][:50]}]")
        print(f"  {c['text'][:150]}...")