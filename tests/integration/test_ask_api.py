# run with: python -m pytest tests/integration/test_ask_api.py -v
#
# /api/ask response contract: the original answer/sources fields stay as they were
# (the frontend reads them), and citations/rule_sources come back alongside. the real
# pipeline loads models and needs Ollama, so it's stubbed here.

import sys
import types

import pytest
from fastapi.testclient import TestClient

SOURCE = {"policy": "BFB-BUS-43", "page": "9", "ref": 1, "section": "C. Expenditures", "file": "bus43.pdf",
          "text": "UC competitively bid all purchases ... $100,000 or more", "score": 4.2, "cited": True}
UNCITED = {**SOURCE, "ref": 2, "cited": False}
RULE_SOURCE = {"document_id": "bus-43", "page": 9, "quote": "$100,000 or more", "version": "Interim"}
GROUNDING = {"review_needed": False, "invalid_references": "", "unmatched_dollar_amounts": ""}


@pytest.fixture
def client(monkeypatch):
    stub = types.ModuleType("backend.rag.pipeline")
    stub.ask = lambda question, think=False: {
        "answer": "Yes [1].", "sources": [SOURCE, UNCITED], "citations": [SOURCE],
        "rule_sources": [RULE_SOURCE], "determination": "=== RULE ENGINE ===", "intent": "threshold",
        "grounding": GROUNDING, "llm_called": True,
    }
    stub.warm_ups = 0

    def warm_up():
        stub.warm_ups += 1
    stub.warm_up = warm_up
    monkeypatch.setitem(sys.modules, "backend.rag.pipeline", stub)
    monkeypatch.delitem(sys.modules, "backend.api.routes", raising=False)
    monkeypatch.delitem(sys.modules, "backend.main", raising=False)
    from backend.main import app
    with TestClient(app) as c:          # context manager runs the startup lifespan
        c.stub = stub
        yield c


def test_models_warm_up_once_at_startup(client):
    client.post("/api/ask", json={"question": "a"})
    client.post("/api/ask", json={"question": "b"})
    assert client.stub.warm_ups == 1


def test_ask_keeps_original_fields(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["answer"] == "Yes [1]."
    assert [(s["policy"], s["page"]) for s in body["sources"]] == [("BFB-BUS-43", "9"), ("BFB-BUS-43", "9")]


def test_ask_returns_citations_with_supporting_text(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["citations"] == [SOURCE]
    assert body["citations"][0]["text"] and body["citations"][0]["section"]
    assert body["rule_sources"][0]["quote"] == "$100,000 or more"
    assert body["refused"] is False and body["refusal_reason"] is None


@pytest.mark.parametrize("question", ["", "   \n\t", "x" * 2001])
def test_invalid_question_is_rejected_before_the_pipeline(client, question):
    assert client.post("/api/ask", json={"question": question}).status_code == 422


def test_pipeline_failure_returns_503(client, monkeypatch):
    # routes.py imports ask directly, so patching the stub module is not enough
    from backend.api import routes

    def boom(question, think=False):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(routes, "ask", boom)

    assert client.post("/api/ask", json={"question": "bid threshold?"}).status_code == 503


def test_response_reports_llm_called_and_elapsed(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["llm_called"] is True
    assert isinstance(body["elapsed_ms"], int) and body["elapsed_ms"] >= 0


def test_grounding_is_passed_through(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["grounding"] == GROUNDING
