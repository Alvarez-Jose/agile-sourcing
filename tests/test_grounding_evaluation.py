
"""Tests for citation grounding diagnostics and summary reporting."""

import unittest

from evaluation.check_citation_grounding import evaluate_response
from evaluation.summarize_grounding import summarize_responses


class TestGroundingEvaluation(unittest.TestCase):

    def test_supported_answer(self):
        response = {
            "question": "What is the bidding threshold?",
            "answer": "The threshold is $100,000 [1].",
            "sources": [{
                "ref": 1,
                "text": "Competitive bidding is required at $100,000."
            }],
            "rule_sources": []
        }

        result = evaluate_response(response)

        self.assertFalse(result["review_needed"])

    def test_invalid_citation(self):
        response = {
            "question": "What is the bidding threshold?",
            "answer": "The threshold is $100,000 [5].",
            "sources": [{
                "ref": 1,
                "text": "Competitive bidding is required at $100,000."
            }],
            "rule_sources": []
        }

        result = evaluate_response(response)

        self.assertTrue(result["review_needed"])
        self.assertEqual(result["invalid_references"], "5")

    def test_unsupported_amount(self):
        response = {
            "question": "What is the bidding threshold?",
            "answer": "The threshold is $250,000 [1].",
            "sources": [{
                "ref": 1,
                "text": "Competitive bidding is required at $100,000."
            }],
            "rule_sources": []
        }

        result = evaluate_response(response)

        self.assertTrue(result["review_needed"])
        self.assertIn(
            "$250,000.00",
            result["unmatched_dollar_amounts"]
        )

    def test_empty_evidence(self):
        response = {
            "question": "What is required?",
            "answer": "Form X is required [1].",
            "sources": [{
                "ref": 1,
                "text": ""
            }],
            "rule_sources": []
        }

        result = evaluate_response(response)

        self.assertTrue(result["review_needed"])
        self.assertEqual(
            result["empty_evidence_references"],
            "1"
        )

    def test_refusal_is_counted_separately(self):
        responses = [
            {
                "question": "What is the weather?",
                "answer": "Not found in policy.",
                "sources": [],
                "refused": True,
                "error": None
            }
        ]

        counts = summarize_responses(responses)

        self.assertEqual(counts["total"], 1)
        self.assertEqual(counts["refusals"], 1)
        self.assertEqual(counts["execution_errors"], 0)
        self.assertEqual(counts["evaluated"], 0)
        self.assertEqual(counts["flagged"], 0)

    def test_execution_error_is_counted_separately(self):
        responses = [
            {
                "question": "What is the bidding threshold?",
                "answer": "ERROR: Model unavailable",
                "sources": [],
                "error": "Model unavailable"
            }
        ]

        counts = summarize_responses(responses)

        self.assertEqual(counts["total"], 1)
        self.assertEqual(counts["execution_errors"], 1)
        self.assertEqual(counts["refusals"], 0)
        self.assertEqual(counts["evaluated"], 0)
        self.assertEqual(counts["flagged"], 0)


if __name__ == "__main__":
    unittest.main()
