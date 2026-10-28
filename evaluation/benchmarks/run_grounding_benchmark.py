"""Run procurement benchmark questions and save their retrieved evidence."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evaluation/results/grounding_responses.json")
    )
    args = parser.parse_args()

    if args.limit < 1 or args.limit > 60:
        parser.error("--limit must be between 1 and 60")

    # Importing the pipeline loads the model and retrieval components.
    import ollama
    from backend.rag.pipeline import ask

    try:
        ollama.list()
    except Exception as e:
        sys.exit(f"Ollama is not reachable: {e}")

    questions_path = Path(
        "evaluation/results/benchmark_questions_multi.json"
    )

    with questions_path.open(encoding="utf-8") as f:
        questions = json.load(f)["questions"][:args.limit]

    results = []

    for i, q in enumerate(questions, start=1):
        start = time.time()
        print(f"Running question {i}/{len(questions)}...", flush=True)

        try:
            response = ask(q["question"])

            record = {
                "question": q["question"],
                "ground_truth": q["answer"],
                "system_answer": response["answer"],
                "answer": response["answer"],
                "difficulty": q.get("difficulty", ""),
                "generator": q.get("generator", ""),
                "sources": response.get("sources", []),
                "citations": response.get("citations", []),
                "rule_sources": response.get("rule_sources", []),
                "determination": response.get("determination"),
                "intent": response.get("intent"),
                "refused": response.get("refused", False),
                "error": None,
                "latency_seconds": round(time.time() - start, 2),
            }

        except Exception as e:
            record = {
                "question": q["question"],
                "ground_truth": q["answer"],
                "system_answer": f"ERROR: {e}",
                "answer": f"ERROR: {e}",
                "sources": [],
                "citations": [],
                "rule_sources": [],
                "error": str(e),
                "latency_seconds": round(time.time() - start, 2),
            }

        results.append(record)

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(results)} responses to {args.out}")


if __name__ == "__main__":
    main()