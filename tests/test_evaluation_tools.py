"""Exercise the team's diagnostic fixtures without changing its evaluation code."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from evaluation.analyze_benchmark import analyze
from evaluation.check_citation_grounding import evaluate_response
from evaluation.metrics.score import score_judge


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


@pytest.mark.parametrize("answer", ["", "   ", "ERROR: unavailable"])
def test_judge_never_passes_empty_or_failed_answers(monkeypatch, answer):
    client = Mock()
    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=client))
    assert score_judge({"system_answer": answer}) == "wrong"
    client.assert_not_called()


def test_live_judge_has_bounded_generation_and_timeout(monkeypatch):
    chat = Mock(return_value={"message": {"content": "INCORRECT"}})
    client = Mock(return_value=SimpleNamespace(chat=chat))
    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=client))
    assert score_judge({"question": "Question", "ground_truth": "Reference",
                        "system_answer": "Wrong answer"}, model="local-judge") == "wrong"
    client.assert_called_once_with(timeout=90)
    assert chat.call_args.kwargs["model"] == "local-judge"
    assert chat.call_args.kwargs["think"] is False
    assert chat.call_args.kwargs["options"]["num_predict"] == 256
