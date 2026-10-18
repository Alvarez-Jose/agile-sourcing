# run with: python -m pytest tests/integration/test_ask_api.py -v
#
# /api/ask response contract: the original answer/sources fields stay as they were
# (the frontend reads them), and citations/rule_sources come back alongside. the real
# pipeline loads models and needs Ollama, so it's stubbed here.

import sys
import types

import pytest
from fastapi.testclient import TestClient

SOURCE = {
    "policy": "BFB-BUS-43",
    "page": "9",
    "ref": 1,
    "section": "C. Expenditures",
    "file": "bus43.pdf",
    "text": "UC competitively bid all purchases ... $100,000 or more",
    "score": 4.2,
    "cited": True,
}
UNCITED = {**SOURCE, "ref": 2, "cited": False}
RULE_SOURCE = {
    "document_id": "bus-43",
    "page": 9,
    "quote": "$100,000 or more",
    "version": "Interim",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("RAG_WARM_UP", raising=False)
    stub = types.ModuleType("backend.rag.pipeline")
    stub.ask = lambda question, think=False, scope=None: {
        "answer": "Yes [1].",
        "sources": [SOURCE, UNCITED],
        "citations": [SOURCE],
        "rule_sources": [RULE_SOURCE],
        "determination": "=== RULE ENGINE ===",
        "intent": "threshold",
    }
    stub.warm_ups = 0

    def warm_up():
        stub.warm_ups += 1

    stub.warm_up = warm_up
    monkeypatch.setitem(sys.modules, "backend.rag.pipeline", stub)
    from backend.main import app
    from backend.auth.dependencies import require_approved_user
    from backend.auth.models import UserProfile

    app.dependency_overrides[require_approved_user] = lambda: UserProfile(
        uid="fixture", email="fixture@ucsc.edu", is_approved=True
    )
    try:
        with TestClient(app) as c:
            c.stub = stub
            yield c
    finally:
        app.dependency_overrides.pop(require_approved_user, None)


def test_auth_startup_does_not_require_local_models(client):
    client.post("/api/ask", json={"question": "a"})
    client.post("/api/ask", json={"question": "b"})
    assert client.stub.warm_ups == 0


def test_explicit_warm_up_runs_once(client, monkeypatch):
    from backend.main import app

    monkeypatch.setenv("RAG_WARM_UP", "1")
    with TestClient(app) as warmed:
        assert warmed.get("/api/health").status_code == 200
    assert client.stub.warm_ups == 1


def test_ask_keeps_original_fields(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["answer"] == "Yes [1]."
    assert [(s["policy"], s["page"]) for s in body["sources"]] == [
        ("BFB-BUS-43", "9"),
        ("BFB-BUS-43", "9"),
    ]


def test_ask_returns_citations_with_supporting_text(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["citations"] == [SOURCE]
    assert body["citations"][0]["text"] and body["citations"][0]["section"]
    assert body["rule_sources"][0]["quote"] == "$100,000 or more"
    assert body["refused"] is False and body["refusal_reason"] is None
