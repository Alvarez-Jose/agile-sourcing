'''
handles all pdfs files, given that the files hace a complex layouts such as 
policy tables, numbered sections. The idea is to use pdflumber over pypdf2
'''
import pdfplumber
import json
from pathlib import Path

def extract_pdf(filepath: str) -> list[dict]:
    '''
    Returns a list of page discts:
    {"source": filename, "page": int, "text" :str}
    '''
    results = []
    with pdfplumber.open(filepath) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and text.strip():
                results.append({
                    "source": Path(filepath).name, 
                    "page": i + 1,
                    "text": text.strip()
                })
    return results