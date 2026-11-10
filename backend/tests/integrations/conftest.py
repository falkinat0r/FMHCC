"""Gemeinsame Test-Helfer fuer die Adapter-Tests (Agent 4, R1).

Prinzip: Alle Adapter-Tests sind **fixture-basiert** — es wird nie mit
echten Systemen kommuniziert. Ein ``httpx.MockTransport`` (Router-Funktion)
wird per Konstruktor-KWARG ``transport=`` in den Adapter injiziert.

Wichtige Konventionen:
- Fixtures liegen in ``tests/integrations/fixtures/*.json`` und sind klar
  als Test-/Fixture-Daten gekennzeichnet.
- Timeout-Szenarien: der Handler wirft ``httpx.ReadTimeout``.
- Nicht-erreichbar-Szenarien: der Handler wirft ``httpx.ConnectError``.
- Async-Code wird per ``asyncio.run`` laufen gelassen (kein
  pytest-asyncio im R0-Dev-Stack).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.adapters.base import AdapterConfig, SecretsProvider
from app.adapters.secrets import EnvSecretsProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Laedt eine JSON-Fixtur (Test-Daten, klar als Fixture gekennzeichnet)."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Sync-Wrapping fuer Async-Code in sync-Tests (kein pytest-asyncio)."""
    return asyncio.run(coro)


def drain(gen: Any) -> list[Any]:
    """Entleert einen Async-Generator und liefert die Items-Liste."""

    async def _drain() -> list[Any]:
        return [item async for item in gen]

    return asyncio.run(_drain())


def make_config(
    base_url: str | None = None,
    secret_ref: str | None = None,
    extra: dict[str, str] | None = None,
    timeout_seconds: float = 5.0,
) -> AdapterConfig:
    """Kurz-Factory fuer AdapterConfig (Default-Timeout fuer Tests)."""
    return AdapterConfig(
        base_url=base_url,
        secret_ref=secret_ref,
        extra=dict(extra or {}),
        timeout_seconds=timeout_seconds,
    )


def make_secrets(values: dict[str, str] | None = None) -> SecretsProvider:
    """In-memory SecretsProvider (Test-Werte, keine echten Secrets)."""
    return EnvSecretsProvider(dict(values or {}))


def mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    """MockTransport-Factory (Router-Function; waehlt Antwort anhand der URL)."""
    return httpx.MockTransport(handler)


def json_response(payload: Any, status_code: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    """JSON-Antwort aus beliebtem Python-Objekt bauen."""
    return httpx.Response(status_code, json=payload, headers=headers or {})


def route_by(
    routes: dict[str, Any],
    *,
    prefix_match: bool = True,
    default_status: int = 404,
    method_check: bool = False,
) -> Callable[[httpx.Request], httpx.Response]:
    """Erzeugt einen Handler, der nach Pfad (prefix-exact) auf Fixture-Werte dispatcht.

    ``routes``: mapping von Pfad-Präfix (bzw. exaktem Pfad, wenn
    ``prefix_match=False``) auf:
    - dict/list -> JSON-Antwort mit Status 200
    - int -> Status ohne Body
    - (int, dict) -> Status + JSON
    - Exception-Instanz -> wird geworfen (z. B. httpx.ReadTimeout)
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for prefix, value in routes.items():
            matched = path.startswith(prefix) if prefix_match else path == prefix
            if not matched:
                continue
            if method_check:
                continue
            if isinstance(value, BaseException):
                raise value
            if isinstance(value, int):
                return httpx.Response(value)
            if isinstance(value, tuple):
                return json_response(value[1], status_code=value[0])
            return json_response(value)
        return json_response({"error": f"kein Fixture-Routen-Treffer: {path}"}, status_code=default_status)

    return handler


def route_full(
    routes: dict[tuple[str, str], Any],
) -> Callable[[httpx.Request], httpx.Response]:
    """Handler mit exaktem (Method, Pfad)-Tupeln (fuer z. B. POST /api/auth)."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method.upper(), request.url.path)
        if key in routes:
            value = routes[key]
            if isinstance(value, BaseException):
                raise value
            if isinstance(value, int):
                return httpx.Response(value)
            if isinstance(value, tuple):
                return json_response(value[1], status_code=value[0])
            return json_response(value)
        return json_response({"error": "no route"}, status_code=404)

    return handler


def timeout_handler(raise_timeout: Callable[[], BaseException]) -> Callable[[httpx.Request], httpx.Response]:
    """Handler, der immer eine Exception wirft (Timeout/Connect-Fehler)."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - wirft immer
        raise raise_timeout()

    return handler


@pytest.fixture()
def no_network_guard() -> None:
    """Sicherheitsnetz: kein echter Netzwerk-Zugriff in Adapter-Tests.

    Erzeugt einen Fallback-Transport-Fehler, falls ein Adapter versehentlich
    ohne MockTransport läuft.
    """

    import app.integrations.monitoring.httputil as httputil

    original = httputil.build_async_client

    def guarded(
        config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str | None = None,
        default_headers=None,
    ) -> httpx.AsyncClient:
        if transport is None:
            raise AssertionError(
                "Adapter-Test ohne MockTransport: kein echter Netzwerk-Zugriff erlaubt"
            )
        return original(config, transport=transport, base_url=base_url, default_headers=default_headers)

    httputil.build_async_client = guarded
    yield
    httputil.build_async_client = original
