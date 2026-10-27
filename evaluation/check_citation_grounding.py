"""Diagnostic checks for citations and dollar amounts in policy answers.

Input: JSON containing one backend response or a list of responses.
This is a heuristic check, not proof of policy correctness.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rag.grounding import evaluate_response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path("evaluation/results/citation_grounding.csv"))
    args = parser.parse_args()

    with args.input_json.open(encoding="utf-8") as f:
        data = json.load(f)

    responses = data if isinstance(data, list) else [data]
    rows = [evaluate_response(response) for response in responses]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Analyzed {len(rows)} responses")
    print(f"Flagged {sum(r['review_needed'] for r in rows)} for review")
    print(f"Saved report: {args.output}")


if __name__ == "__main__":
    main()
