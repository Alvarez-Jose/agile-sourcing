"""Exercise the real auth routes/dependencies without contacting Firebase or loading ML."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth
from google.api_core.exceptions import AlreadyExists, ServiceUnavailable

from backend.auth import dependencies
from backend.main import app

IDENTITY = {
    "uid": "verified-user",
    "email": "buyer@ucsc.edu",
    "name": "Test Buyer",
    "picture": "https://example.com/avatar.png",
    # These claims must not become application permissions or department assignments.
    "is_approved": True,
    "clearance": "admin",
    "department": "untrusted-department",
}
HEADERS = {"Authorization": "Bearer test-firebase-token"}


@pytest.fixture
def server(monkeypatch):
    records = {}
    document = Mock()

    def read(**kwargs):
        data = records.get(IDENTITY["uid"])
        return SimpleNamespace(
            exists=data is not None, to_dict=lambda: dict(data) if data else None
        )

    def create(data, **kwargs):
        if IDENTITY["uid"] in records:
            raise AlreadyExists("Document already exists")
        records[IDENTITY["uid"]] = dict(data)

    document.get.side_effect = read
    document.create.side_effect = create
    db = Mock()
    db.collection.return_value.document.return_value = document
    firebase_app = object()
    verifier = Mock(return_value=dict(IDENTITY))
    monkeypatch.setattr(dependencies, "get_firebase_app", lambda: firebase_app)
    monkeypatch.setattr(dependencies, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dependencies.auth, "verify_id_token", verifier)
    pipeline = Mock(return_value={"answer": "Policy answer", "sources": []})
    monkeypatch.setitem(
        sys.modules, "backend.rag.pipeline", SimpleNamespace(ask=pipeline)
    )
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            records=records,
            document=document,
            db=db,
            verifier=verifier,
            firebase_app=firebase_app,
            pipeline=pipeline,
        )


@pytest.mark.parametrize(
    "path,method",
    [
        ("/auth/session", "post"),
        ("/auth/me", "get"),
        ("/api/ask", "post"),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic invalid"}])
def test_missing_bearer_is_rejected_before_firebase(server, path, method, headers):
    response = server.client.request(
        method, path, headers=headers, json={"question": "Hello"}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    server.verifier.assert_not_called()
    server.document.get.assert_not_called()
    server.pipeline.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        auth.InvalidIdTokenError("Invalid signature or wrong Firebase project"),
        auth.ExpiredIdTokenError("Expired", cause=None),
        auth.RevokedIdTokenError("Revoked"),
        auth.UserDisabledError("Disabled"),
    ],
)
def test_invalid_tokens_cannot_load_profiles(server, error):
    server.verifier.side_effect = error
    response = server.client.post("/auth/session", headers=HEADERS)
    assert response.status_code == 401
    server.document.get.assert_not_called()


def test_first_login_creates_pending_profile_from_verified_identity(server):
    response = server.client.post(
        "/auth/session",
        headers=HEADERS,
        json={
            "uid": "somebody-else",
            "is_approved": True,
            "clearance": "admin",
            "department": "IT",
        },
    )
    assert response.status_code == 200
    profile = response.json()
    assert profile["uid"] == IDENTITY["uid"]
    assert profile["email"] == IDENTITY["email"]
    assert profile["name"] == IDENTITY["name"]
    assert profile["photoURL"] == IDENTITY["picture"]
    assert profile["department"] is None
    assert profile["clearance"] == "none"
    assert profile["is_approved"] is False
    assert profile["role"] == "buyer"
    assert profile["created_at"]
    assert response.headers["cache-control"] == "no-store"
    server.verifier.assert_called_once_with(
        "test-firebase-token", app=server.firebase_app, check_revoked=True
    )
    server.db.collection.assert_called_with("users")
    server.db.collection.return_value.document.assert_called_with(IDENTITY["uid"])
    server.document.create.assert_called_once()


def test_existing_profile_keeps_server_owned_department_and_clearance(server):
    server.records[IDENTITY["uid"]] = {
        "name": "Directory Name",
        "department": "Chemistry",
        "clearance": "department_buyer",
        "role": "buyer",
        "is_approved": True,
        "created_at": "2026-01-01T00:00:00Z",
    }
    response = server.client.get("/auth/me", headers=HEADERS)
    assert response.status_code == 200
    profile = response.json()
    assert profile["name"] == "Directory Name"
    assert profile["department"] == "Chemistry"
    assert profile["clearance"] == "department_buyer"
    assert profile["is_approved"] is True
    assert profile["uid"] == IDENTITY["uid"]
    server.document.create.assert_not_called()


def test_repeated_login_does_not_reset_administrative_approval(server):
    server.client.post("/auth/session", headers=HEADERS)
    server.records[IDENTITY["uid"]].update(
        is_approved=True, clearance="department_buyer"
    )
    response = server.client.post("/auth/session", headers=HEADERS)
    assert response.json()["is_approved"] is True
    assert response.json()["clearance"] == "department_buyer"
    server.document.create.assert_called_once()


def test_concurrent_first_login_does_not_overwrite_an_existing_profile(server):
    def concurrent_creation(data, **kwargs):
        server.records[IDENTITY["uid"]] = {
            **data,
            "is_approved": True,
            "clearance": "buyer",
        }
        raise AlreadyExists("Concurrent request already created the document")

    server.document.create.side_effect = concurrent_creation
    response = server.client.post("/auth/session", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["is_approved"] is True
    assert response.json()["clearance"] == "buyer"


def test_pending_user_cannot_invoke_pipeline(server):
    response = server.client.post(
        "/api/ask", headers=HEADERS, json={"question": "Hello"}
    )
    assert response.status_code == 403
    server.pipeline.assert_not_called()


def test_approval_is_reloaded_on_each_protected_request(server):
    server.records[IDENTITY["uid"]] = {"is_approved": True, "department": "Chemistry"}
    response = server.client.post(
        "/api/ask", headers=HEADERS, json={"question": "Hello"}
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "Policy answer", "sources": []}
    server.records[IDENTITY["uid"]]["is_approved"] = False
    response = server.client.post(
        "/api/ask", headers=HEADERS, json={"question": "Hello"}
    )
    assert response.status_code == 403
    server.pipeline.assert_called_once_with("Hello", think=False)


def test_invalid_permission_data_fails_closed(server):
    server.records[IDENTITY["uid"]] = {"is_approved": "true"}
    response = server.client.post(
        "/api/ask", headers=HEADERS, json={"question": "Hello"}
    )
    assert response.status_code == 503
    server.pipeline.assert_not_called()


def test_firestore_outage_does_not_create_a_mock_session(server):
    server.document.get.side_effect = ServiceUnavailable("Firestore unavailable")
    response = server.client.post("/auth/session", headers=HEADERS)
    assert response.status_code == 503
    server.document.create.assert_not_called()


def test_verification_service_outage_returns_retryable_error(server):
    server.verifier.side_effect = auth.CertificateFetchError(
        "Certificate fetch failed", cause=None
    )
    response = server.client.post("/auth/session", headers=HEADERS)
    assert response.status_code == 503
    server.document.get.assert_not_called()


def test_health_remains_public_and_does_not_initialize_firebase(server):
    response = server.client.get("/api/health")
    assert response.status_code == 200
    server.verifier.assert_not_called()
    server.pipeline.assert_not_called()


@pytest.mark.parametrize(
    "error,expected_detail",
    [
        (
            ModuleNotFoundError("No module named 'ollama'", name="ollama"),
            "The assistant server is not ready yet. Please try again later.",
        ),
        (
            ConnectionError("Ollama is not running"),
            "The assistant is temporarily unavailable. Please try again later.",
        ),
    ],
)
def test_pipeline_failures_return_an_actionable_response(
    server, error, expected_detail
):
    server.records[IDENTITY["uid"]] = {"is_approved": True}
    server.pipeline.side_effect = error
    response = server.client.post(
        "/api/ask", headers=HEADERS, json={"question": "Hello"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": expected_detail}
    assert "ollama" not in response.text.lower()
