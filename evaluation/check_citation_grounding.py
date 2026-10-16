"""Diagnostic checks for citations and dollar amounts in policy answers.

Input: JSON containing one backend response or a list of responses.
This is a heuristic check, not proof of policy correctness.
"""
import argparse
import csv
import json
import re
from pathlib import Path

CITATION_RE = re.compile(r"\[(\d+)\]")
DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")


def dollar_amounts(text):
    return {
        float(value.replace(",", ""))
        for value in DOLLAR_RE.findall(str(text))
    }


def evaluate_response(response):
    answer = response.get("answer", "")
    question = response.get("question", "")
    sources = response.get("sources", [])
    rule_sources = response.get("rule_sources", [])

    references = set(CITATION_RE.findall(answer))
    source_map = {
        str(source["ref"]): source
        for source in sources
        if source.get("ref") is not None
    }

    invalid_refs = sorted(ref for ref in references if ref not in source_map)
    cited_sources = [
        source_map[ref] for ref in references if ref in source_map
    ]

    empty_evidence = [
        str(s.get("ref")) for s in cited_sources
        if not str(s.get("text", "")).strip()
    ]

    evidence = "\n".join(str(s.get("text", "")) for s in cited_sources)
    evidence += "\n" + "\n".join(
        str(s.get("quote", "")) for s in rule_sources
    )

    answer_amounts = dollar_amounts(answer)
    question_amounts = dollar_amounts(question)
    evidence_amounts = dollar_amounts(evidence)

    # Flag all amounts absent from the cited evidence, even if an amount
    # originally appeared in the user's question.
    unmatched = sorted(answer_amounts - evidence_amounts)

    # Separate amounts supplied in the question for easier manual review.
    # Such amounts may be purchase details rather than policy thresholds.
    question_only = sorted(
        (answer_amounts & question_amounts) - evidence_amounts
    )

    return {
        "question": question,
        "citation_count": len(references),
        "invalid_references": ";".join(invalid_refs),
        "empty_evidence_references": ";".join(empty_evidence),
        "unmatched_dollar_amounts": ";".join(
            f"${amount:,.2f}" for amount in unmatched
        ),
        "question_amounts_not_in_evidence": ";".join(
            f"${amount:,.2f}" for amount in question_only
        ),
        "review_needed": bool(invalid_refs or empty_evidence or unmatched),
    }


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
