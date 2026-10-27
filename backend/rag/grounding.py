"""
backend/rag/grounding.py
Heuristic checks that the answer only cites sources it was given and that dollar
amounts in the answer also appear in the cited evidence.

This is a diagnostic, not proof of policy correctness: a clean result means the
answer did not invent a citation number or a threshold, not that the reasoning is
right. It runs on the finished answer in pipeline.ask() and is reused by
evaluation/check_citation_grounding.py so the CLI and the API agree.
"""

import re

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
