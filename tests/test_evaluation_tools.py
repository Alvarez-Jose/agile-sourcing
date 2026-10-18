"""Exercise the team's diagnostic fixtures without changing its evaluation code."""

import json
from pathlib import Path

from evaluation.analyze_benchmark import analyze
from evaluation.check_citation_grounding import evaluate_response


def test_teammate_citation_fixtures_flag_the_three_bad_examples():
    cases = json.loads(
        Path("evaluation/results/citation_grounding_test.json").read_text()
    )
    assert [evaluate_response(case)["review_needed"] for case in cases] == [
        False,
        True,
        True,
        True,
    ]


def test_teammate_diagnostics_accept_saved_benchmark_results():
    cases = json.loads(Path("evaluation/results/benchmark_results_v2.json").read_text())
    rows = analyze(cases)
    assert len(rows) == len(cases) == 60
    assert all("flags" in row and "manual_grade" in row for row in rows)
