# tests/test_llm_judge_experiment.py
# experiment statistics, failure handling and resume without models or network calls.
import json
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

from llm_judge_test.common import fingerprint, parse_grade
from llm_judge_test.compare_results import analyze
from llm_judge_test.run_experiment import grade_once, run


def sample_state():
    responses = [{"question_id": i, "question": f"Question {i}", "ground_truth": "Reference",
                  "system_answer": "Candidate"} for i in (1, 2, 3)]
    # Q1 unanimously correct; Q2 differs within one judge and between models;
    # Q3 has a three-way within-model tie and one failed call.
    cases = [
        [["CORRECT"] * 3, ["CORRECT"] * 3, ["CORRECT"] * 3],
        [["CORRECT", "PARTIAL", "CORRECT"], ["PARTIAL"] * 3, ["INCORRECT"] * 3],
        [["CORRECT", "PARTIAL", "INCORRECT"], ["CORRECT", None, "CORRECT"], ["CORRECT"] * 3],
    ]
    judgments = [{"question_id": number, "model": model, "run": repeat, "grade": grade,
                  "status": "ok" if grade else "error"}
                 for number, models in enumerate(cases, 1)
                 for model, grades in zip(("a", "b", "c"), models)
                 for repeat, grade in enumerate(grades, 1)]
    return {"metadata": {"config": {"models": ["a", "b", "c"]}},
            "responses": responses, "judgments": judgments}


def test_repeats_ties_failures_and_pairwise_denominators():
    rows, disagreements, summary = analyze(sample_state())
    assert summary["all_agree_question_ids"] == [1]
    assert summary["disagree_question_ids"] == [2]
    assert summary["unresolved_question_ids"] == [3]
    assert summary["per_model"]["a"]["changed_question_ids"] == [2, 3]
    assert rows[1]["panel_verdict"] == "NO_CONSENSUS"
    assert rows[2]["model1_majority"] == "NO_CONSENSUS"
    assert rows[2]["model2_majority"] == "INCOMPLETE"
    assert rows[2]["model2_consistent"] == "unavailable"
    assert summary["pairwise"][0]["comparable_questions"] == 2
    assert summary["pairwise"][0]["agreed"] == 1
    assert disagreements[0]["score_spread"] == 2
    assert summary["failed_or_skipped_judgments"] == 1


def test_missing_duplicate_and_modified_data_are_not_silently_accepted():
    state = sample_state()
    state["judgments"].pop()
    assert analyze(state)[2]["missing_judgments"] == 1
    state["judgments"].append(state["judgments"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        analyze(state)
    state = sample_state()
    state["metadata"]["responses_sha256"] = fingerprint(state["responses"])
    state["responses"][0]["system_answer"] = "Edited"
    with pytest.raises(ValueError, match="checksum"):
        analyze(state)


@pytest.mark.parametrize("content", ["", "CORRECT", '{"grade":"CORRECT"}',
                                    '{"grade":"INCORRECT","explanation":""}'])
def test_invalid_judge_responses_are_not_substring_graded(content):
    with pytest.raises(ValueError):
        parse_grade(content)


def test_judge_calls_are_independent_bounded_and_never_pass_blank_answers():
    client = Mock()
    client.chat.return_value = {"message": {"content": '{"grade":"PARTIAL","explanation":"Missing detail"}'}}
    response = {"question_id": 1, "question": "Question", "ground_truth": "Reference", "system_answer": "Candidate"}
    for repeat in (1, 2, 3):
        result = grade_once(client, "qwen3:8b", response, repeat, temperature=0, seed=42, thinking=True)
        assert result["grade"] == "PARTIAL" and result["status"] == "ok"
    assert client.chat.call_count == 3
    calls = [call.kwargs for call in client.chat.call_args_list]
    assert calls[0] == calls[1] == calls[2]
    assert len(calls[0]["messages"]) == 1
    assert calls[0]["think"] is False
    assert calls[0]["options"]["num_predict"] == 512
    blank = {**response, "system_answer": ""}
    assert grade_once(client, "qwen3:8b", blank, 1, temperature=0, seed=42, thinking=True)["grade"] is None
    assert client.chat.call_count == 3


def test_truncated_output_and_timeout_are_errors_not_incorrect_votes():
    response = sample_state()["responses"][0]
    for reply in [TimeoutError("slow"), {"message": {"content": '{"grade":"CORRECT","explanation":"ok"}'}, "done_reason": "length"}]:
        client = Mock()
        if isinstance(reply, Exception):
            client.chat.side_effect = reply
        else:
            client.chat.return_value = reply
        result = grade_once(client, "a", response, 1, temperature=0, seed=42, thinking=False)
        assert result["status"] == "error" and result["grade"] is None


def test_small_experiment_and_resume_do_not_regenerate_or_rejudge(monkeypatch, tmp_path):
    from llm_judge_test import run_experiment as runner
    client = Mock()
    client.list.return_value.models = [SimpleNamespace(model=m, digest=m + "-digest") for m in ("a", "b", "c")]
    client.show.return_value.model_dump.return_value = {"capabilities": ["completion"]}
    client.chat.return_value = {"message": {"content": '{"grade":"CORRECT","explanation":"Matches"}'}}
    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=Mock(return_value=client)))
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    pipeline = SimpleNamespace(LLM_MODEL="answer-model", EMBED_MODEL="embed-model", COLLECTION_NAME="index",
                               RERANK_TOP_K=8, get_collection=lambda: object(), ask=Mock(return_value={"answer": "Candidate"}))
    monkeypatch.setitem(sys.modules, "backend.rag", SimpleNamespace(pipeline=pipeline))

    def process(command, **kwargs):
        if command[0] == "git":
            return SimpleNamespace(stdout="test-revision")
        path = command[command.index("--out") + 1]
        with open(path, "w") as stream:
            json.dump([{"q": 1, "hit_at_5": True, "hit_in_pool": True, "first_hit_rank": 1}], stream)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", process)
    args = SimpleNamespace(models=["a", "b", "c"], timeout=120, check=False, limit=1, temperature=0,
                           seed=42, resume=None, output_dir=tmp_path / "experiment", responses=None)
    reply = client.chat.return_value
    client.chat.side_effect = [reply, KeyboardInterrupt()]
    with pytest.raises(KeyboardInterrupt):
        run(args)
    assert len(json.loads((args.output_dir / "experiment.json").read_text())["judgments"]) == 1
    client.chat.side_effect = None
    args.resume, args.output_dir = args.output_dir, None
    assert run(args) == 0
    assert client.chat.call_count == 10  # Includes one interrupted call; its vote is not recorded.
    pipeline.ask.assert_called_once()
    saved = json.loads((args.resume / "experiment.json").read_text())
    assert len(saved["judgments"]) == 9
    for name in ("judgments.csv", "results.csv", "comparison.csv", "disagreements.csv", "comparison_summary.json"):
        assert (args.resume / name).exists()
    assert run(args) == 0
    assert client.chat.call_count == 10
    pipeline.ask.assert_called_once()
    # Resuming with a changed judge setting must not mix experiments.
    args.temperature = 0.2
    with pytest.raises(ValueError, match="Resume settings"):
        run(args)
