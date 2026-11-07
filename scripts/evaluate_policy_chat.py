"""Reproducible starter-corpus checks; --live additionally calls local Qwen.

Automated evidence checks verify retrieval and quote provenance, not every semantic
claim. Read the live report and assess applicability/conditions before deployment.
"""

import argparse
import json
import re
from pathlib import Path

from backend.rag import pipeline
from rag_pipeline.documents.store import PolicyIndex
from rag_pipeline.retriever.section_retriever import (
    SectionRetriever,
    requested_sources_available,
)

CASES = [
    dict(
        id="price-reasonableness",
        question="How should I document price reasonableness on the SSPR form?",
        document="sspr-form",
        evidence=["comparable/similar quotes", "historical prices"],
        answer_patterns=[r"comparable|historical|comparison"],
    ),
    dict(
        id="sspr-thresholds",
        question="What purchase thresholds does the current SSPR form list for federal contracts, grants or cooperative agreements, and non-federal purchases? Include the campus micro-purchase qualification.",
        document="sspr-form",
        evidence=["15,000", "50,000", "100,000", "Campus locations may establish"],
        answer_patterns=[
            r"15,000",
            r"50,000",
            r"100,000",
            r"campus|location",
            r"up to|may establish",
        ],
    ),
    dict(
        id="competitive-quotes",
        question="How many qualified supplier quotations does Section II of the SSPR form require, including the selected supplier?",
        document="sspr-form",
        evidence=["three (3)", "including your selected supplier"],
        answer_patterns=[r"three|\b3\b", r"selected|including"],
    ),
    dict(
        id="sole-source-brand",
        question="Can price or brand names be used as sole-source justifications on the SSPR form?",
        document="sspr-form",
        evidence=["Price and brand names are not allowable"],
        answer_patterns=[r"not|\bno\b", r"brand", r"price"],
    ),
    dict(
        id="annual-bidding",
        question="What does BUS-43 say about competitive bidding for proposed annual expenditures of $100,000 or more, and exceptions?",
        document="bus-43",
        evidence=["$100,000 or more", "unless an exception applies"],
        answer_patterns=[r"100,000", r"annual", r"exception"],
    ),
    dict(
        id="missing-checklist",
        question="What does Section 3 of the Federal Funds Checklist require for this purchase?",
        abstain=True,
    ),
    dict(
        id="unknown-supplier",
        question="Is supplier NebulaWidget approved in our vendor database?",
        abstain=True,
    ),
]


def check_answer(case, answer):
    return bool(answer["sources"]) != case.get("abstain", False) and all(
        re.search(pattern, answer["answer"], flags=re.I)
        for pattern in case.get("answer_patterns", [])
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Call local Ollama for every case"
    )
    parser.add_argument(
        "--output", type=Path, help="Write a detailed local JSON report"
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=[case["id"] for case in CASES],
        help="Run only these cases; repeat for more than one",
    )
    args = parser.parse_args()
    retriever = SectionRetriever(
        PolicyIndex(),
        pipeline.semantic_rank if args.live else None,
        pipeline.rerank if args.live else None,
    )
    results = []
    for case in CASES:
        if args.case and case["id"] not in args.case:
            continue
        passages = retriever.retrieve(case["question"])
        text = " ".join(
            p.text for p in passages if p.document.id == case.get("document")
        )
        retrieval_ok = all(fragment in text for fragment in case.get("evidence", []))
        result = dict(
            id=case["id"],
            question=case["question"],
            retrieval_check=retrieval_ok,
            context=[
                dict(
                    document=p.document.id,
                    section=p.section.title,
                    text=p.text,
                    via_reference=p.via_reference,
                )
                for p in passages
            ],
        )
        if args.live:
            correction = None
            for attempt in range(2):
                generated = None
                try:
                    if not requested_sources_available(
                        case["question"], retriever.corpus["documents"]
                    ):
                        answer = dict(answer=pipeline.INSUFFICIENT, sources=[])
                        break
                    generated = pipeline.generate_answer(
                        case["question"], passages, correction=correction
                    )
                    answer = pipeline.grounded_response(generated, passages)
                    break
                except ValueError as error:
                    result.setdefault("validation_failures", []).append(str(error))
                    if generated is not None:
                        result["unvalidated_model_claims"] = generated.model_dump()
                    correction = {
                        "error": str(error),
                        "claims": (
                            generated.model_dump() if generated is not None else None
                        ),
                    }
                    answer = dict(answer=pipeline.INSUFFICIENT, sources=[])
            result["response"] = answer
            result["expected_answer_or_abstention"] = check_answer(case, answer)
        results.append(result)
        print(
            case["id"],
            "retrieval PASS" if retrieval_ok else "retrieval FAIL",
            (
                (
                    "answer/abstention PASS"
                    if result.get("expected_answer_or_abstention")
                    else "answer/abstention FAIL"
                )
                if args.live
                else ""
            ),
            flush=True,
        )
        if args.output:
            args.output.write_text(json.dumps(results, indent=2) + "\n")
    if not all(
        r["retrieval_check"] and (not args.live or r["expected_answer_or_abstention"])
        for r in results
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
