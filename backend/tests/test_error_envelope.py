"""Error-Envelope-Tests (frozen Contract, R0)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient


def _assert_envelope_shape(body: dict) -> None:
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert set(error.keys()) == {"code", "message", "details", "request_id"}
    assert isinstance(error["request_id"], str) and len(error["request_id"]) >= 8


def test_not_found_uses_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/definitiv-nicht-da")
    assert response.status_code == 404
    body = response.json()
    _assert_envelope_shape(body)
    assert body["error"]["code"] == "not_found"


def test_validation_error_uses_envelope_with_details(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "", "password": ""})
    assert response.status_code == 422
    body = response.json()
    _assert_envelope_shape(body)
    assert body["error"]["code"] == "validation_error"
    details = body["error"]["details"]
    assert details["errors"]
    assert all({"loc", "msg", "type"} <= set(e.keys()) for e in details["errors"])


def test_unhandled_exception_returns_internal_error_without_traceback(client: TestClient) -> None:
    def boom() -> None:
        raise RuntimeError("interner fehler mit details")

    router = APIRouter()

    @router.get("/api/v1/__boom__")
    def _boom() -> None:
        boom()

    client.app.include_router(router)
    response = client.get("/api/v1/__boom__")
    assert response.status_code == 500
    body = response.json()
    _assert_envelope_shape(body)
    assert body["error"]["code"] == "internal_error"
    assert "interner fehler" not in response.text


def test_request_id_header_is_set(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")


def test_error_envelope_model_is_serializable() -> None:
    from app.errors import ErrorBody, ErrorCode, ErrorEnvelope

    envelope = ErrorEnvelope(
        error=ErrorBody(code=ErrorCode.NOT_FOUND, message="nichts", details=None, request_id="abc123")
    )
    data = envelope.model_dump()
    assert data["error"]["code"] == "not_found"
