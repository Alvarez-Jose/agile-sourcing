# fine-tunes the retrieval embedder on the generated (question, chunk) pairs
# (training/private/qa_pairs_v1.jsonl, vaulted). MultipleNegativesRankingLoss with
# in-batch negatives; a held-out split (by chunk, so no chunk leaks between splits)
# is scored with an information-retrieval evaluator before and after training, so
# the run prints its own base-vs-tuned comparison.
#
#   python training/finetune_embedder.py --pairs qa_pairs_v1.jsonl --out uc-procurement-embedder-v1
#
# Runs anywhere with a GPU (a 5090 finishes in minutes); the real acceptance test is
# evaluation/metrics/retrieval_recall.py on the 60-question benchmark, run locally
# against a Chroma collection re-ingested with the tuned model.

import argparse
import hashlib
import json
from pathlib import Path

from datasets import Dataset
from sentence_transformers import (
    SentenceTransformer,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
    losses,
)
from sentence_transformers.evaluation import InformationRetrievalEvaluator

BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_pairs(path):
    pairs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))
    return pairs


def split_by_chunk(pairs, holdout_pct=5):
    # hash of the chunk id decides the split, so every question about a held-out
    # chunk is unseen in training
    train, held = [], []
    for p in pairs:
        bucket = int(hashlib.sha1(p["chunk_sha1"].encode()).hexdigest(), 16) % 100
        (held if bucket < holdout_pct else train).append(p)
    return train, held


def ir_evaluator(pairs, all_pairs, name):
    corpus = {p["chunk_sha1"]: p["positive"] for p in all_pairs}
    queries, relevant = {}, {}
    for i, p in enumerate(pairs):
        qid = f"q{i}"
        queries[qid] = p["query"]
        relevant[qid] = {p["chunk_sha1"]}
    return InformationRetrievalEvaluator(
        queries, corpus, relevant, name=name,
        accuracy_at_k=[1, 5], precision_recall_at_k=[1, 5], map_at_k=[5],
        show_progress_bar=False,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="training/private/qa_pairs_v1.jsonl")
    ap.add_argument("--out", default="training/private/uc-procurement-embedder-v1")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-5)
    args = ap.parse_args()

    pairs = load_pairs(args.pairs)
    train, held = split_by_chunk(pairs)
    print(f"{len(pairs)} pairs -> {len(train)} train / {len(held)} held-out "
          f"({len({p['chunk_sha1'] for p in pairs})} chunks)")

    model = SentenceTransformer(BASE_MODEL)
    evaluator = ir_evaluator(held, pairs, "held-out")

    base_scores = evaluator(model)
    print("BASE   :", {k: round(v, 4) for k, v in base_scores.items() if "accuracy" in k or "map" in k})

    train_ds = Dataset.from_dict({
        "anchor": [p["query"] for p in train],
        "positive": [p["positive"] for p in train],
    })
    trainer = SentenceTransformerTrainer(
        model=model,
        args=SentenceTransformerTrainingArguments(
            output_dir=str(Path(args.out) / "checkpoints"),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch,
            learning_rate=args.lr,
            warmup_ratio=0.1,
            bf16=True,
            logging_steps=10,
            save_strategy="no",
            report_to=[],
        ),
        train_dataset=train_ds,
        loss=losses.MultipleNegativesRankingLoss(model),
    )
    trainer.train()

    tuned_scores = evaluator(model)
    print("TUNED  :", {k: round(v, 4) for k, v in tuned_scores.items() if "accuracy" in k or "map" in k})

    model.save_pretrained(args.out)
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
