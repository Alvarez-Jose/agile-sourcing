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


@pytest.fixture
def client(monkeypatch):
    stub = types.ModuleType("backend.rag.pipeline")
    stub.ask = lambda question, think=False: {
        "answer": "Yes [1].", "sources": [SOURCE, UNCITED], "citations": [SOURCE],
        "rule_sources": [RULE_SOURCE], "determination": "=== RULE ENGINE ===", "intent": "threshold",
    }
    monkeypatch.setitem(sys.modules, "backend.rag.pipeline", stub)
    monkeypatch.delitem(sys.modules, "backend.api.routes", raising=False)
    monkeypatch.delitem(sys.modules, "backend.main", raising=False)
    from backend.main import app
    return TestClient(app)


def test_ask_keeps_original_fields(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["answer"] == "Yes [1]."
    assert [(s["policy"], s["page"]) for s in body["sources"]] == [("BFB-BUS-43", "9"), ("BFB-BUS-43", "9")]


def test_ask_returns_citations_with_supporting_text(client):
    body = client.post("/api/ask", json={"question": "bid threshold?"}).json()
    assert body["citations"] == [SOURCE]
    assert body["citations"][0]["text"] and body["citations"][0]["section"]
    assert body["rule_sources"][0]["quote"] == "$100,000 or more"
