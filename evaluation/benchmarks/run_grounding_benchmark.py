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

from evaluation.progress import Progress


def save_results(out, results):
    # Preserve completed questions on interruption; never leave a partial JSON file.
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(out)


def run_questions(questions, ask, out, progress=None):
    results = []

    for i, q in enumerate(questions, start=1):
        start = time.time()

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
        save_results(out, results)
        if progress:
            progress(i)

    return results


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

    import ollama

    try:
        ollama.list()
    except Exception as e:
        sys.exit(f"Ollama is not reachable: {e}")

    # Importing the pipeline loads local model and retrieval components. A missing
    # index otherwise returns a plain message that can look clean to the citation
    # heuristic, even though no policy answer was evaluated.
    from backend.rag.pipeline import ask, get_collection

    if get_collection() is None:
        sys.exit(
            "Policy index 'uc_policies' is not loaded. Run "
            "'python -m scripts.ingest_policies --ingest' with the intended corpus "
            "and restart the backend before benchmarking. No results were written."
        )

    questions_path = Path(
        "evaluation/results/benchmark_questions_multi.json"
    )

    with questions_path.open(encoding="utf-8") as f:
        questions = json.load(f)["questions"][:args.limit]

    with Progress("Answering", len(questions)) as progress:
        run_questions(questions, ask, args.out, progress.update)
    print(f"Saved {len(questions)} responses to {args.out}")


if __name__ == "__main__":
    main()
