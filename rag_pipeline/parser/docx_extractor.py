'''
This handles .docx files like the GDPR addndumsn and Federal funds checklist, 
TC-operating lease, etc
'''

from docx import Document
from pathlib import Path

def extract_docx(filepath: str) -> list[dict]:
    doc = Document(filepath)
    pages = []
    current_section = ""
    buffer = []

    for para in doc.paragraphs:
        # this treats the heading styles as section breaks
        if para.style.name.startswith("Heading"):
            if buffer:
                pages.append({
                    "source": Path(filepath).name,
                    "section": current_section,
                    "text": "\n".join(buffer).strip()
                })
                buffer = []
            current_section = para.text
        else:
            if para.text.strip():
                buffer.append(para.text.strip())

    # flushes any remaning 
    if buffer:
        pages.append({
            "source": Path(filepath).name,
            "section": current_section,
            "text": "\n".join(buffer).strip()
        })
    
    return pages