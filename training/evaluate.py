"""
training/evaluate.py

Compares base Qwen3-8B vs fine-tuned UC policy model.
Uses local Qwen3 as judge instead of RAGAS — no external dependencies.

Usage:
    python training/evaluate.py --mode base
    python training/evaluate.py --mode finetuned
    python training/evaluate.py --mode both --save
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import chromadb
import ollama
import torch
from peft import PeftModel
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

CHROMA_DIR = "data/embeddings/chroma_store"
COLLECTION_NAME = "uc_policies"
EVAL_FILE = "training/dataset/eval.jsonl"
FINETUNED_DIR = "training/uc-policy-qwen3-final"
RESULTS_DIR = Path("training/results")
BASE_MODEL_ID = "Qwen/Qwen3-8B"
OLLAMA_MODEL = "qwen3:8b"
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 5
MAX_EVAL = 25
SYSTEM_PROMPT = (
    "You are a UC procurement policy assistant. Answer questions strictly "
    "based on the official UC policy excerpts provided. Cite source numbers. "
    "If the answer is not in the excerpts, say so clearly."
)


def setup_retriever():
    embedder = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    return embedder, collection


def retrieve(question, embedder, collection):
    vec = embedder.encode([question])[0].tolist()
    results = collection.query(
        query_embeddings=[vec], n_results=TOP_K,
        include=["documents", "metadatas"]
    )
    chunks = results["documents"][0]
    metas = results["metadatas"][0]
    context = []
    for chunk, meta in zip(chunks, metas):
        source = meta.get("policy_name") or meta.get("source", "UC Policy")
        context.append(f"[{source}]\n{chunk}")
    return context


def build_prompt(question, context_chunks):
    context = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(context_chunks))
    return f"""/no_think

{SYSTEM_PROMPT}

POLICY EXCERPTS:
{context}

QUESTION: {question}

ANSWER:"""


def answer_base(question, embedder, collection):
    chunks = retrieve(question, embedder, collection)
    prompt = build_prompt(question, chunks)
    resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
    raw = resp["message"]["content"]
    clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    return clean, chunks


def load_finetuned():
    if not Path(FINETUNED_DIR).exists():
        raise FileNotFoundError(f"Fine-tuned model not found at {FINETUNED_DIR}.")
    print(f"Loading fine-tuned model from {FINETUNED_DIR}...")
    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16
    )
    tok = AutoTokenizer.from_pretrained(FINETUNED_DIR, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID, quantization_config=bnb,
        device_map="auto", trust_remote_code=True, torch_dtype=torch.bfloat16
    )
    model = PeftModel.from_pretrained(base, FINETUNED_DIR)
    model.eval()
    return model, tok


def answer_finetuned(question, embedder, collection, model, tokenizer):
    chunks = retrieve(question, embedder, collection)
    prompt = build_prompt(question, chunks)
    msgs = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=512, temperature=0.1,
            do_sample=True, pad_token_id=tokenizer.eos_token_id
        )
    decoded = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    clean = re.sub(r"<think>.*?</think>", "", decoded, flags=re.DOTALL).strip()
    return clean, chunks


def score_answer(question, answer, ground_truth, context_chunks):
    """Score faithfulness and relevancy 0-10 using local Qwen3 as judge."""
    context = "\n".join(f"[{i+1}] {c[:300]}..." for i, c in enumerate(context_chunks))

    prompt = f"""/no_think
You are evaluating a UC procurement policy AI assistant.

Score the ANSWER on two dimensions (0-10 each):

1. FAITHFULNESS: Is every claim in the answer supported by the CONTEXT below?
   10 = fully grounded, no hallucinations
   0  = mostly made up, contradicts context

2. RELEVANCY: Does the answer actually address the QUESTION asked?
   10 = directly and completely answers the question
   0  = doesn't answer the question at all

QUESTION: {question}

CONTEXT:
{context}

ANSWER: {answer[:600]}

REFERENCE ANSWER: {ground_truth[:400]}

Respond in JSON only:
{{"faithfulness": <0-10>, "relevancy": <0-10>, "reason": "<one sentence>"}}"""

    try:
        resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
        raw = resp["message"]["content"]
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            scores = json.loads(match.group())
            return {
                "faithfulness": float(scores.get("faithfulness", 5)) / 10,
                "relevancy": float(scores.get("relevancy", 5)) / 10,
                "reason": scores.get("reason", "")
            }
    except Exception:
        pass
    return {"faithfulness": 0.5, "relevancy": 0.5, "reason": "scoring failed"}


def load_questions():
    if not Path(EVAL_FILE).exists():
        raise FileNotFoundError(f"Eval file not found: {EVAL_FILE}")
    questions = []
    with open(EVAL_FILE) as f:
        for line in f:
            item = json.loads(line)
            msgs = item["messages"]
            q = next(m["content"] for m in msgs if m["role"] == "user")
            a = next(m["content"] for m in msgs if m["role"] == "assistant")
            questions.append({"question": q, "ground_truth": a})
    return questions[:MAX_EVAL]


def evaluate(questions, answer_fn, label, **kwargs):
    print(f"\nEvaluating {label} on {len(questions)} questions...")
    total_faith = 0
    total_rel = 0
    results = []

    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q['question'][:60]}...")
        ans, ctx = answer_fn(q["question"], **kwargs)
        scores = score_answer(q["question"], ans, q["ground_truth"], ctx)

        total_faith += scores["faithfulness"]
        total_rel += scores["relevancy"]

        results.append({
            "question": q["question"],
            "answer": ans,
            "faithfulness": scores["faithfulness"],
            "relevancy": scores["relevancy"],
            "reason": scores["reason"]
        })
        time.sleep(0.1)

    n = len(questions)
    return {
        "faithfulness": round(total_faith / n, 3),
        "relevancy": round(total_rel / n, 3),
        "details": results
    }


def print_scores(scores, label):
    print(f"\n--- {label} ---")
    for metric in ["faithfulness", "relevancy"]:
        val = scores[metric]
        bar = "█" * int(val * 20)
        rest = "░" * (20 - int(val * 20))
        print(f"  {metric:<15} {bar}{rest}  {val:.3f}")


def print_comparison(base, ft):
    print("\n--- Comparison: Base vs Fine-Tuned ---")
    print(f"  {'Metric':<15} {'Base':>8}  {'Fine-tuned':>10}  {'Delta':>8}")
    print(f"  {'-'*15} {'-'*8}  {'-'*10}  {'-'*8}")
    for metric in ["faithfulness", "relevancy"]:
        b = base[metric]
        f = ft[metric]
        delta = f - b
        sign = "+" if delta >= 0 else ""
        print(f"  {metric:<15} {b:>8.3f}  {f:>10.3f}  {sign}{delta:>7.3f}")

    avg_delta = ((ft["faithfulness"] - base["faithfulness"]) +
                 (ft["relevancy"] - base["relevancy"])) / 2

    print(f"\n  Average improvement: {'+' if avg_delta >= 0 else ''}{avg_delta:.3f}")
    if avg_delta > 0.05:
        print("  Verdict: Fine-tuning improved the model. Isaac was wrong.")
    elif avg_delta > 0:
        print("  Verdict: Marginal improvement. More training data would help.")
    else:
        print("  Verdict: No improvement detected. Check dataset quality.")


def save_results(scores, label):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"{label.replace(' ', '_')}_{ts}.json"
    with open(path, "w") as f:
        json.dump({"label": label, "scores": scores, "timestamp": ts}, f, indent=2)
    print(f"  Saved to {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["base", "finetuned", "both"], default="both")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    print("--- Agile Sourcing Evaluation ---")
    embedder, collection = setup_retriever()
    questions = load_questions()
    print(f"Loaded {len(questions)} eval questions")

    base_scores = ft_scores = None

    if args.mode in ("base", "both"):
        base_scores = evaluate(
            questions, answer_base, "Base Qwen3-8B",
            embedder=embedder, collection=collection
        )
        print_scores(base_scores, "Base Qwen3-8B")
        if args.save:
            save_results(base_scores, "base_qwen3_8b")

    if args.mode in ("finetuned", "both"):
        model, tokenizer = load_finetuned()
        ft_scores = evaluate(
            questions, answer_finetuned, "Fine-tuned Qwen3-8B",
            embedder=embedder, collection=collection,
            model=model, tokenizer=tokenizer
        )
        print_scores(ft_scores, "Fine-tuned Qwen3-8B (UC Policy)")
        if args.save:
            save_results(ft_scores, "finetuned_qwen3_8b")

    if args.mode == "both" and base_scores and ft_scores:
        print_comparison(base_scores, ft_scores)


if __name__ == "__main__":
    main()
