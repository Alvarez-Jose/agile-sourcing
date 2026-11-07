
"""Summarize citation grounding diagnostics across saved responses."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from evaluation.check_citation_grounding import evaluate_response


def summarize_responses(responses):
    """Count grounding issues, refusals, and execution errors."""

    counts = Counter({
        "total": 0,
        "evaluated": 0,
        "flagged": 0,
        "execution_errors": 0,
        "refusals": 0,
        "invalid_citations": 0,
        "empty_evidence": 0,
        "unmatched_dollar_amounts": 0,
        "question_amounts_not_in_evidence": 0,
    })

    for response in responses:
        counts["total"] += 1

        if response.get("error"):
            counts["execution_errors"] += 1
            continue

        if response.get("refused"):
            counts["refusals"] += 1
            continue

        # The benchmark runner saves both "answer" and "system_answer".
        # Support either field for compatibility with saved records.
        if "answer" not in response and "system_answer" in response:
            response = {
                **response,
                "answer": response["system_answer"],
            }

        result = evaluate_response(response)
        counts["evaluated"] += 1

        if result["review_needed"]:
            counts["flagged"] += 1

        if result["invalid_references"]:
            counts["invalid_citations"] += 1

        if result["empty_evidence_references"]:
            counts["empty_evidence"] += 1

        if result["unmatched_dollar_amounts"]:
            counts["unmatched_dollar_amounts"] += 1

        if result["question_amounts_not_in_evidence"]:
            counts["question_amounts_not_in_evidence"] += 1

    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/grounding_summary.csv"),
    )
    args = parser.parse_args()

    with args.input_json.open(encoding="utf-8") as f:
        data = json.load(f)

    responses = data if isinstance(data, list) else [data]

    if not responses:
        parser.error("Input file contains no responses")

    counts = summarize_responses(responses)

    print("\nGrounding Evaluation Summary")
    print("----------------------------")

    for name, value in counts.items():
        print(f"{name}: {value}")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "count"])

        for name, value in counts.items():
            writer.writerow([name, value])

    print(f"\nSaved summary to {args.output}")


if __name__ == "__main__":
    main()
