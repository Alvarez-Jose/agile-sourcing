# generates the enriched-corpus file for ENRICHED_CORPUS_PATH (plan item 1):
# for every chunk the ingest pipeline produces, a contextual header (policy, section,
# conditions, exceptions) and 3-5 casual-wording questions the chunk answers, written
# by an LLM. Keyed by sha1 of the raw chunk text, matching enrich_chunk() in
# scripts/ingest_policies.py. Resumable: reruns skip keys already in the output file.
#
#   OLLAMA_HOST=http://127.0.0.1:11435 ENRICH_MODEL=qwen3:32b \
#     python evaluation/benchmarks/generate_enrichment.py --out data/enriched/corpus_v1.json

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import ollama

from rag_pipeline.parser.pdf_extractor import extract_pdf
from rag_pipeline.parser.docx_extractor import extract_docx
from rag_pipeline.parser.section_parser import chunk_by_section
from rag_pipeline.parser.metadata_tagger import tag_chunk

ENRICH_MODEL = os.environ.get("ENRICH_MODEL", "qwen3:32b")
DATA_DIR = ROOT / "data/raw_policies"

PROMPT = """/no_think
You are indexing UC procurement policy text for search. Given one chunk of a policy
document, return JSON with exactly these keys:
  "header": one sentence naming the policy, the section, what the rule applies to, and
            any dollar thresholds, conditions or exceptions stated IN THIS CHUNK.
  "questions": 3 to 5 short questions, in casual employee wording, that this chunk
            answers. Only ask what the chunk actually answers.
Use only facts present in the chunk. No markdown, JSON only.

POLICY: {policy}
SECTION: {section}
CHUNK:
{text}"""


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
    parser.add_argument("--out", default="data/enriched/corpus_v1.json")
    parser.add_argument("--limit", type=int, default=0, help="stop after N new chunks (0 = all)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    chunks = all_chunks()
    todo = {}
    for c in chunks:
        key = hashlib.sha1(c["text"].encode("utf-8")).hexdigest()
        if key not in done and key not in todo:
            todo[key] = c
    print(f"{len(chunks)} chunks, {len(done)} already enriched, {len(todo)} to do "
          f"(model={ENRICH_MODEL}, host={os.environ.get('OLLAMA_HOST', 'local')})")

    client = ollama.Client(timeout=120)
    start, new = time.time(), 0
    for key, c in todo.items():
        prompt = PROMPT.format(policy=c.get("policy_name", ""), section=c.get("section", ""),
                               text=c["text"][:6000])
        try:
            resp = client.chat(model=ENRICH_MODEL, format="json", think=False,
                               messages=[{"role": "user", "content": prompt}],
                               keep_alive="60m", options={"temperature": 0, "num_predict": 500})
            raw = re.sub(r"<think>.*?(</think>|$)", "", resp["message"]["content"], flags=re.S).strip()
            data = json.loads(raw)
            header = str(data.get("header", "")).strip()
            questions = [str(q).strip() for q in data.get("questions", []) if str(q).strip()][:5]
            if not header and not questions:
                raise ValueError("empty enrichment")
            done[key] = {"header": header, "questions": questions,
                         "policy": c.get("policy_name", ""), "section": c.get("section", "")}
        except Exception as e:
            print(f"\n  {key[:8]} failed: {e}")
            continue
        new += 1
        if new % 25 == 0:
            out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
            rate = new / (time.time() - start)
            print(f"\r{new}/{len(todo)}  {rate:.2f} chunks/s  eta {(len(todo) - new) / rate / 60:.0f}m",
                  end="", flush=True)
        if args.limit and new >= args.limit:
            break
    out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
    print(f"\ndone: {len(done)} enriched chunks -> {out_path}")


if __name__ == "__main__":
    main()
