"""Grouped test reporting must preserve failures, evidence, and honest metrics."""

import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from evaluation.benchmarks.run_grounding_benchmark import run_questions
from evaluation.progress import Progress
from scripts import test_project as runner


def test_answers_are_checkpointed_before_interruption(tmp_path):
    ask = Mock(side_effect=[{"answer": "Answer [1]", "sources": []}, KeyboardInterrupt])
    questions = [{"question": "One", "answer": "Reference"}, {"question": "Two", "answer": "Reference"}]
    target = tmp_path / "responses.json"
    with pytest.raises(KeyboardInterrupt):
        run_questions(questions, ask, target)
    rows = json.loads(target.read_text())
    assert len(rows) == 1 and rows[0]["question"] == "One"
    assert not target.with_suffix(".json.tmp").exists()


def test_benchmark_failure_is_saved_and_remaining_questions_run(tmp_path):
    ask = Mock(side_effect=[RuntimeError("Unavailable"), {"answer": "Answer", "sources": []}])
    questions = [{"question": "One", "answer": "Reference"}, {"question": "Two", "answer": "Reference"}]
    progress = Mock()
    rows = run_questions(questions, ask, tmp_path / "responses.json", progress)
    assert rows[0]["error"] == "Unavailable"
    assert rows[1]["error"] is None
    assert progress.call_args_list[-1].args == (2,)


def test_judge_failure_stays_ungraded_and_does_not_inflate_accuracy():
    rows = [{"answer": "Answer", "system_answer": "Answer", "latency_seconds": 1,
             "sources": [], "rule_sources": [], "error": error}
            for error in (None, "Execution failed", None, None)]
    judge = Mock(side_effect=["correct", RuntimeError("Judge failed"), "partial"])
    runner.grade_responses(rows, judge)
    summary = runner.quality_summary(rows)
    assert summary["judge_accuracy"] == .25
    assert summary["wrong"] == summary["partial"] == summary["ungraded"] == 1
    assert summary["grounding"]["execution_errors"] == 1
    assert rows[2]["judge_error"] == "Judge failed"
    assert judge.call_count == 3


def test_terminal_progress_shows_count_percentage_and_elapsed_time():
    stream = io.StringIO()
    with Progress("Answering", 2, stream) as progress:
        progress.update(1)
        progress.update(2)
    output = stream.getvalue()
    assert "0/2 (0%)" in output
    assert "1/2 (50%)" in output
    assert "2/2 (100%)" in output
    assert "elapsed" in output and "ETA" in output


@pytest.mark.parametrize("body,status,expected", [
    ('{"status":"ok"}', 200, 0), ('{"status":"bad"}', 200, 1),
    ('{"status":"ok"}', 503, 1), ('[]', 200, 1), ('not-json', 200, 1),
])
def test_health_requires_successful_status_and_expected_json(monkeypatch, body, status, expected):
    response = io.StringIO(body)
    response.status = status
    monkeypatch.setattr(runner, "urlopen", lambda *a, **k: response)
    assert runner.health("http://localhost:8000") == expected


def test_health_unavailable_is_a_failure(monkeypatch):
    monkeypatch.setattr(runner, "urlopen", Mock(side_effect=URLError("No server")))
    assert runner.health("http://localhost:8000") == 1


def test_frontend_stops_after_failed_type_check(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: "available")
    run = Mock(side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=2)])
    monkeypatch.setattr(runner.subprocess, "run", run)
    assert runner.frontend() == 2
    assert run.call_count == 2


def test_all_runs_both_groups_and_propagates_failure(monkeypatch):
    monkeypatch.setattr(runner, "run_pytest", Mock(return_value=1))
    frontend = Mock(return_value=0)
    monkeypatch.setattr(runner, "frontend", frontend)
    assert runner.main(["all"]) == 1
    frontend.assert_called_once()


def test_auth_reports_frontend_failure_even_when_backend_passes(monkeypatch, capsys):
    monkeypatch.setattr(runner, "run_pytest", Mock(return_value=0))
    frontend = Mock(return_value=2)
    monkeypatch.setattr(runner, "frontend", frontend)
    assert runner.main(["auth"]) == 1
    frontend.assert_called_once_with(auth_only=True)
    assert "Auth report: backend PASS, frontend FAIL" in capsys.readouterr().out


def test_pytest_report_counts_teardown_and_collection_errors(monkeypatch, capsys):
    def fake_main(args, plugins):
        plugin = plugins[0]
        plugin.pytest_runtest_logreport(SimpleNamespace(nodeid="a", when="call", failed=False, skipped=False, outcome="passed"))
        plugin.pytest_runtest_logreport(SimpleNamespace(nodeid="a", when="teardown", failed=True))
        plugin.pytest_collectreport(SimpleNamespace(failed=True))
        return 2

    monkeypatch.setattr(pytest, "main", fake_main)
    assert runner.run_pytest(["tests"]) == 2
    assert "0 passed, 0 failed, 2 errors" in capsys.readouterr().out


def test_recall_at_five_does_not_count_sixth_result(monkeypatch, tmp_path):
    from evaluation.metrics import retrieval_recall
    import backend.rag

    candidates = [{"document": f"Passage {i}", "metadata": {"policy_name": "BUS-43" if i == 5 else "Other"}}
                  for i in range(8)]
    retriever = SimpleNamespace(retrieve=lambda *a, **k: ([c["document"] for c in candidates],
                                                       [c["metadata"] for c in candidates]))
    def rerank(question, values, top_k):
        return [{**c, "rerank_score": 1.0} for c in values[:top_k]]

    pipeline = SimpleNamespace(RERANK_POOL=20, RERANK_TOP_K=8, get_collection=lambda: object(),
        _get_retriever=lambda _: retriever, _get_reranker=lambda: SimpleNamespace(rerank=rerank),
        classifier=SimpleNamespace(classify=lambda _: {"intent": "general", "search_terms": ""}))
    monkeypatch.setattr(backend.rag, "pipeline", pipeline, raising=False)
    target = tmp_path / "recall.json"
    monkeypatch.setattr(sys, "argv", ["recall", "--limit", "1", "--out", str(target)])
    retrieval_recall.main()
    rows = json.loads(target.read_text())
    assert rows[0]["hit_in_pool"] is True
    assert rows[0]["hit_at_5"] is False
    assert rows[0]["first_hit_rank"] is None


def test_rag_defaults_to_full_benchmark_and_honors_short_trial(monkeypatch, tmp_path):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_: False)
    seen = []
    def fake_rag(args, output):
        seen.append(args.limit)
        return 0
    monkeypatch.setattr(runner, "rag", fake_rag)
    assert runner.main(["rag", "--output-dir", str(tmp_path / "full")]) == 0
    assert runner.main(["rag", "--limit", "5", "--output-dir", str(tmp_path / "short")]) == 0
    assert seen == [60, 5]
