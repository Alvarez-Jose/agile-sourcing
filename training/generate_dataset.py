"""
training/generate_dataset.py

Generates UC policy Q&A training pairs from existing ChromaDB chunks
using local Qwen3. Outputs train.jsonl and eval.jsonl for fine-tuning.

Usage:
    python training/generate_dataset.py
    python training/generate_dataset.py --max 200
    python training/generate_dataset.py --review
"""

import argparse
import json
import random
import re
import time
from pathlib import Path

import chromadb
import ollama

CHROMA_DIR = "data/embeddings/chroma_store"
COLLECTION_NAME = "uc_policies"
OUTPUT_DIR = Path("training/dataset")
TRAIN_FILE = OUTPUT_DIR / "train.jsonl"
EVAL_FILE = OUTPUT_DIR / "eval.jsonl"
LLM_MODEL = "qwen3:8b"
EVAL_SPLIT = 0.15
MAX_PAIRS = 500
SYSTEM_PROMPT = (
    "You are a UC procurement policy expert. Answer questions strictly based "
    "on UC and UCSC policy documents. Always cite the policy source. "
    "If the answer is not in the policy, say so clearly."
)

# question templates to get diversity in the generated pairs
QUESTION_TEMPLATES = [
    "What is the requirement for {topic}?",
    "When is {topic} required?",
    "What are the dollar thresholds for {topic}?",
    "What forms are needed for {topic}?",
    "What happens if {topic} is not followed?",
    "How does federal funding affect {topic}?",
    "What exceptions exist for {topic}?",
    "What is the process for {topic}?",
    "Who is responsible for {topic}?",
    "What documentation is required for {topic}?",
]

# edge cases and high-stakes scenarios that have to be in the dataset
# these are the ones that determine whether the model actually understands policy
MUST_INCLUDE_SCENARIOS = [
    {
        "question": "I need to purchase a $75,000 microscope using an NIH federal grant. What procurement process do I follow?",
        "doc_type": "Procurement"
    },
    {
        "question": "Can I split a $120,000 purchase into two $60,000 orders to avoid competitive bidding?",
        "doc_type": "Procurement"
    },
    {
        "question": "What is the competitive bidding threshold for UC purchases?",
        "doc_type": "Procurement"
    },
    {
        "question": "When do I need to complete an SSPR form?",
        "doc_type": "Procurement"
    },
    {
        "question": "I want to hire an independent contractor for $15,000. What do I need to do?",
        "doc_type": "Contracting"
    },
    {
        "question": "What insurance requirements apply when contracting for services?",
        "doc_type": "Risk & Insurance"
    },
    {
        "question": "When does a Business Associate Agreement need to be signed?",
        "doc_type": "GDPR & Privacy"
    },
    {
        "question": "What are the small business set-aside thresholds for UC procurement?",
        "doc_type": "Procurement"
    },
    {
        "question": "I have a conflict of interest with a vendor. What must I disclose?",
        "doc_type": "Conflict of Interest"
    },
    {
        "question": "What happens to university equipment when a grant ends?",
        "doc_type": "Property & Equipment"
    },
    {
        "question": "Can I use federal grant funds to buy alcohol for a faculty event?",
        "doc_type": "Finance"
    },
    {
        "question": "What is the simplified acquisition threshold for federal purchases?",
        "doc_type": "Procurement"
    },
    {
        "question": "When is a Data Security Appendix required in a vendor contract?",
        "doc_type": "GDPR & Privacy"
    },
    {
        "question": "What are the post-employment conflict of interest restrictions for UC employees?",
        "doc_type": "Conflict of Interest"
    },
    {
        "question": "What is the threshold that requires a formal source selection process?",
        "doc_type": "Procurement"
    },
]


def load_chunks():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    results = collection.get(include=["documents", "metadatas"])
    chunks = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        if doc and len(doc.strip()) > 100:
            chunks.append({"text": doc, "meta": meta})
    print(f"Loaded {len(chunks)} chunks from ChromaDB")
    return chunks


def generate_qa(chunk: dict, retries: int = 2) -> dict | None:
    source = chunk["meta"].get("policy_name") or chunk["meta"].get("source", "UC Policy")
    text = chunk["text"]

    prompt = f"""/no_think

You are creating training data for a UC procurement AI assistant.

Given the policy excerpt below, generate ONE realistic question that a UC faculty
or staff member might ask about procurement, and a precise answer grounded
strictly in the excerpt.

RULES:
- The question must be something a real person would actually ask
- The answer must come ONLY from the excerpt — no outside knowledge
- The answer must cite the policy name
- If the excerpt does not contain enough information for a good Q&A pair, respond with: SKIP

POLICY SOURCE: {source}

POLICY EXCERPT:
{text}

Respond in valid JSON only, no markdown, no extra text:
{{"question": "...", "answer": "..."}}"""

    for attempt in range(retries + 1):
        try:
            response = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response["message"]["content"].strip()
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            if "SKIP" in raw:
                return None

            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not json_match:
                return None

            pair = json.loads(json_match.group())

            if not pair.get("question") or not pair.get("answer"):
                return None

            if len(pair["answer"]) < 40:
                return None

            return {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": pair["question"]},
                    {"role": "assistant", "content": pair["answer"]}
                ],
                "metadata": {
                    "source": source,
                    "doc_type": chunk["meta"].get("doc_type", ""),
                    "page": chunk["meta"].get("page", "")
                }
            }

        except (json.JSONDecodeError, KeyError):
            if attempt < retries:
                time.sleep(1)
            continue

    return None


def generate_scenario(scenario: dict, collection) -> dict | None:
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    query_vec = embedder.encode([scenario["question"]])[0].tolist()

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=4,
        include=["documents", "metadatas"]
    )
    chunks = results["documents"][0]
    metas = results["metadatas"][0]

    context = ""
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        source = meta.get("policy_name") or meta.get("source", "UC Policy")
        context += f"\n[{i+1}] {source}\n{chunk}\n"

    prompt = f"""/think

You are creating a high-quality training example for a UC procurement AI assistant.

Answer the question below using ONLY the policy excerpts provided.
This is a complex scenario requiring careful multi-policy reasoning.
Be thorough, specific, and cite sources [1], [2], etc.

POLICY EXCERPTS:
{context}

QUESTION: {scenario["question"]}

Respond in valid JSON only:
{{"question": "{scenario["question"]}", "answer": "..."}}"""

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response["message"]["content"].strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return None

        pair = json.loads(json_match.group())

        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": pair["question"]},
                {"role": "assistant", "content": pair["answer"]}
            ],
            "metadata": {
                "source": "multi-policy scenario",
                "doc_type": scenario["doc_type"],
                "page": ""
            }
        }
    except Exception:
        return None


def write_jsonl(pairs: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"Wrote {len(pairs)} pairs to {path}")


def main():
    parser = argparse.ArgumentParser(description="Generate UC policy training dataset")
    parser.add_argument("--max", type=int, default=MAX_PAIRS, help="Max Q&A pairs to generate")
    parser.add_argument("--review", action="store_true", help="Print sample pairs for review")
    args = parser.parse_args()

    chunks = load_chunks()

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION_NAME)

    all_pairs = []

    # step 1: must-include scenarios first so they always make it in
    print(f"\nGenerating {len(MUST_INCLUDE_SCENARIOS)} must-include scenarios...")
    for i, scenario in enumerate(MUST_INCLUDE_SCENARIOS):
        print(f"  Scenario {i+1}/{len(MUST_INCLUDE_SCENARIOS)}: {scenario['question'][:60]}...")
        pair = generate_scenario(scenario, collection)
        if pair:
            all_pairs.append(pair)
            print(f"    generated")
        else:
            print(f"    skipped")

    # step 2: fill rest from chunk-based generation
    remaining = args.max - len(all_pairs)
    print(f"\nGenerating {remaining} Q&A pairs from policy chunks...")

    priority_types = ["Procurement", "Contracting", "Risk & Insurance", "Conflict of Interest"]
    priority_chunks = [c for c in chunks if c["meta"].get("doc_type") in priority_types]
    other_chunks = [c for c in chunks if c["meta"].get("doc_type") not in priority_types]

    # 70/30 split toward priority doc types
    priority_n = int(len(chunks) * 0.7)
    other_n = len(chunks) - priority_n

    sampled = (
        random.sample(priority_chunks, min(priority_n, len(priority_chunks))) +
        random.sample(other_chunks, min(other_n, len(other_chunks)))
    )
    random.shuffle(sampled)

    generated = 0
    skipped = 0

    for chunk in sampled:
        if generated >= remaining:
            break

        doc_type = chunk["meta"].get("doc_type", "General")
        print(f"  [{generated+1}/{remaining}] {doc_type} — {chunk['meta'].get('source','')[:40]}...")

        pair = generate_qa(chunk)
        if pair:
            all_pairs.append(pair)
            generated += 1
        else:
            skipped += 1

        time.sleep(0.2)

    print(f"\nGenerated: {len(all_pairs)} pairs  |  Skipped: {skipped} chunks")

    # step 3: split train/eval
    random.shuffle(all_pairs)
    eval_n = max(1, int(len(all_pairs) * EVAL_SPLIT))
    eval_pairs = all_pairs[:eval_n]
    train_pairs = all_pairs[eval_n:]

    write_jsonl(train_pairs, TRAIN_FILE)
    write_jsonl(eval_pairs, EVAL_FILE)

    if args.review:
        print("\n--- Sample training pairs ---")
        for pair in random.sample(all_pairs, min(3, len(all_pairs))):
            print(f"\nQ: {pair['messages'][1]['content']}")
            print(f"A: {pair['messages'][2]['content'][:300]}...")
            print(f"   Source: {pair['metadata']['source']}")

    print(f"\nDataset ready:")
    print(f"  Train: {len(train_pairs)} pairs  ->  {TRAIN_FILE}")
    print(f"  Eval:  {len(eval_pairs)} pairs   ->  {EVAL_FILE}")
    print(f"\nNext step: python training/finetune.py")


if __name__ == "__main__":
    main()
