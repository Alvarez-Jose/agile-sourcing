# run with: python -m pytest tests/test_grounding.py -v
#
# the same diagnostic runs at request time in pipeline.ask() and as the
# check_citation_grounding.py CLI. these cases are the CLI's fixture file:
# a clean answer, an invented threshold, an invented citation number, and an
# amount that came from the question rather than the policy text.

import json
from pathlib import Path

import pytest

from backend.rag.grounding import evaluate_response

FIXTURES = Path(__file__).resolve().parents[1] / "evaluation" / "results" / "citation_grounding_test.json"


@pytest.fixture(scope="module")
def cases():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_clean_answer_is_not_flagged(cases):
    result = evaluate_response(cases[0])
    assert result["review_needed"] is False
    assert result["invalid_references"] == ""
    assert result["unmatched_dollar_amounts"] == ""


def test_invented_threshold_is_flagged(cases):
    result = evaluate_response(cases[1])
    assert result["review_needed"] is True
    assert result["unmatched_dollar_amounts"] == "$250,000.00"


def test_invented_citation_is_flagged(cases):
    result = evaluate_response(cases[2])
    assert result["review_needed"] is True
    assert result["invalid_references"] == "5"


def test_question_amount_is_still_flagged_but_categorized(cases):
    result = evaluate_response(cases[3])
    assert result["review_needed"] is True
    assert result["unmatched_dollar_amounts"] == "$150,000.00"
    assert result["question_amounts_not_in_evidence"] == "$150,000.00"
