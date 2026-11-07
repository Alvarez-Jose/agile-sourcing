# builds the embedder fine-tune training set from the enrichment corpus: one JSONL row
# per generated question, paired with the raw chunk that answers it. The output is
# private (training/private/, gitignored; commit only its vault.sh ciphertext).
#
#   PYTHONPATH=. py -3.11 training/build_qa_pairs.py \
#       --enrichment data/enriched/corpus_v1.json \
#       --out training/private/qa_pairs_v1.jsonl

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from rag_pipeline.parser.pdf_extractor import extract_pdf
from rag_pipeline.parser.docx_extractor import extract_docx
from rag_pipeline.parser.section_parser import chunk_by_section
from rag_pipeline.parser.metadata_tagger import tag_chunk

DATA_DIR = ROOT / "data/raw_policies"


def all_chunks():
    chunks = []
    for f in sorted(DATA_DIR.iterdir()):
        try:
            if f.suffix.lower() == ".pdf":
                pages = extract_pdf(str(f))
            elif f.suffix.lower() == ".docx":
                pages = extract_docx(str(f))
            else:
                continue
            chunks.extend(tag_chunk(c) for c in chunk_by_section(pages))
        except Exception as e:
            print(f"skip {f.name}: {e}")
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrichment", default="data/enriched/corpus_v1.json")
    parser.add_argument("--out", default="training/private/qa_pairs_v1.jsonl")
    args = parser.parse_args()

    enrichment = json.loads(Path(args.enrichment).read_text(encoding="utf-8"))
    by_sha = {}
    for c in all_chunks():
        key = hashlib.sha1(c["text"].encode("utf-8")).hexdigest()
        by_sha.setdefault(key, c)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs, missing = 0, 0
    with out_path.open("w", encoding="utf-8") as f:
        for key, extra in enrichment.items():
            c = by_sha.get(key)
            if c is None:
                missing += 1
                continue
            for q in extra.get("questions", []):
                f.write(json.dumps({
                    "query": q,
                    "positive": c["text"],
                    "chunk_sha1": key,
                    "header": extra.get("header", ""),
                    "policy": c.get("policy_name", ""),
                    "section": c.get("section", ""),
                }, ensure_ascii=False) + "\n")
                pairs += 1
    print(f"{pairs} (query, chunk) pairs from {len(enrichment)} enriched chunks "
          f"({missing} enrichment keys no longer match a chunk) -> {out_path}")


if __name__ == "__main__":
    main()
