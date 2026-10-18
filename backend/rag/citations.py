"""
backend/rag/citations.py
Citation label for a retrieved chunk. Kept separate from pipeline.py so it can
be unit-tested without importing the heavy model stack.
"""


def citation_line(policy: str, page: str = "", section: str = "") -> str:
    # docx chunks carry a section, not a page number; avoid a dangling "p."
    if page:
        return f"{policy}, p.{page}"
    if section:
        return f"{policy} ({section})"
    return policy
