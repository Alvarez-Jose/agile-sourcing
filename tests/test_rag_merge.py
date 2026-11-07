"""Run pipeline control flow with fake retrieval/model boundaries, without loading ML."""

import ast
import logging
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock

from backend.rag.citations import citation_line
from backend.rag.grounding import evaluate_response


def pipeline_functions():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "backend/rag/pipeline.py").read_text())
    names = {"ask", "_generate_answer", "_strip_think", "_refusal", "_grounding"}
    selected = ast.Module(body=[node for node in tree.body
                               if isinstance(node, ast.FunctionDef) and node.name in names],
                          type_ignores=[])
    env = {
        "re": re, "logger": logging.getLogger(__name__),
        "citation_line": citation_line, "evaluate_response": evaluate_response,
        "get_collection": lambda: object(),
        "classifier": SimpleNamespace(classify=lambda _: {"intent": "general"}),
        "_evaluate_rules": lambda *_: None, "_rewrite_query": lambda q, _: q,
        "_retrieve_reranked": lambda *_: (["Source evidence."],
            [{"policy_name": "Test policy", "page": "1"}], [1.0]),
        "REFUSAL_MIN_RERANK": -8.0, "SYSTEM_PROMPT": "Use evidence.",
        "NOT_FOUND_ANSWER": "Not found in policy.", "VAGUE_ANSWER": re.compile("NEVER_MATCH"),
        "LLM_MODEL": "test-model", "LLM_KEEP_ALIVE": "30m", "ANSWER_MAX_TOKENS": 1024,
    }
    exec(compile(selected, "backend/rag/pipeline.py", "exec"), env)
    return env


def test_empty_completions_retry_then_return_grounded_refusal():
    env = pipeline_functions()
    chat = Mock(return_value={"message": {"content": ""}})
    env["llm"] = SimpleNamespace(chat=chat)
    result = env["ask"]("What does the policy say?")
    assert chat.call_count == 2
    assert all(call.kwargs["think"] is False for call in chat.call_args_list)
    assert result["refused"] is True
    assert result["refusal_reason"] == "empty_llm_output"
    assert result["grounding"]["review_needed"] is False
    assert result["llm_called"] is True


def test_enriched_search_text_is_not_used_as_answer_evidence():
    env = pipeline_functions()
    env["_retrieve_reranked"] = lambda *_: (["Generated retrieval-only hint"],
        [{"policy_name": "Test policy", "page": "1", "raw_text": "Original evidence."}], [1.0])
    chat = Mock(return_value={"message": {"content": "Supported explanation [1]."}})
    env["llm"] = SimpleNamespace(chat=chat)
    result = env["ask"]("Explain this policy.")
    prompt = chat.call_args.kwargs["messages"][0]["content"]
    assert "Original evidence." in prompt
    assert "Generated retrieval-only hint" not in prompt
    assert result["sources"][0]["text"] == "Original evidence."
    assert result["citations"][0]["ref"] == 1
    assert result["grounding"]["review_needed"] is False
