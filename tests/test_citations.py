# run with: python -m pytest tests/test_citations.py -v
#
# docx policy chunks have a section but no page number; the citation line
# must not end in a dangling "p."

from backend.rag.citations import citation_line


def test_pdf_chunk_cites_page():
    assert citation_line("BFB-BUS-43", "9", "C. Expenditures") == "BFB-BUS-43, p.9"


def test_docx_chunk_falls_back_to_section():
    assert citation_line("SSPR", "", "Instructions") == "SSPR (Instructions)"


def test_no_page_no_section_is_bare_policy():
    assert citation_line("BFB-BUS-43") == "BFB-BUS-43"
