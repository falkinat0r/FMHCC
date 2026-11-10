"""Config-/Token-Parsing-Tests (Agent 3, R1).

Deckung: Secret-Format, Fehlermauerung auf AdapterConfigError,
Option-Defaults, api_root-Varianten, TLS-Optionen.
"""

from __future__ import annotations

import pytest

from app.adapters.base import AdapterConfig
from app.adapters.errors import AdapterConfigError, AdapterState
from app.integrations.proxmox.config import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_PER_SECOND,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    MINIMUM_PVE_MAJOR,
    build_options,
    parse_token,
)


def test_parse_token_valid() -> None:
    token = parse_token("hcc@pve!hcc-inventory=0123456789abcdef01234789abcdef012345")
    assert token.token_id == "hcc@pve!hcc-inventory"
    assert token.secret == "0123456789abcdef01234789abcdef012345"


def test_parse_token_colon_separator_fallback() -> None:
    token = parse_token("hcc@pve!hcc-inventory:0123456789abcdef01234789abcdef012345")
    assert token.token_id == "hcc@pve!hcc-inventory"
    assert token.secret == "0123456789abcdef01234789abcdef012345"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "kein-separator-hier",
        "nur@realm!ohne-separator",
        "hcc@pve!=0123456789abcdef",  # Token-ID leer
        "=0123456789abcdef",  # komplett leer davor
        "hcc@pve!hcc=zu_kurz",
    ],
)
def test_parse_token_invalid_values_raise_not_configured(raw: str | None) -> None:
    with pytest.raises(AdapterConfigError) as exc_info:
        parse_token(raw)
    assert exc_info.value.state is AdapterState.NOT_CONFIGURED
    # Meldungen duerfen keinen Secret-Teil zurueckgeben
    if isinstance(raw, str) and len(raw) > 20:
        assert raw.split("=", 1)[-1] not in exc_info.value.message


def test_parse_token_bad_token_id() -> None:
    # Secret vorhanden, aber Token-ID ohne '@'/'!'
    with pytest.raises(AdapterConfigError):
        parse_token("hcc-inventory=0123456789abcdef01234789abcdef012345")


def test_build_options_defaults() -> None:
    options = build_options(AdapterConfig(base_url="https://pve.example.lan:8006"))
    assert options.timeout_seconds == 10.0
    assert options.rate_limit_per_second == DEFAULT_RATE_LIMIT_PER_SECOND
    assert options.max_retries == DEFAULT_MAX_RETRIES
    assert options.retry_backoff_seconds == DEFAULT_RETRY_BACKOFF_SECONDS
    assert options.tls_ca_bundle is None
    assert options.tls_verify_disabled is False
    assert options.fetch_resource_details is True
    assert options.api_root == "https://pve.example.lan:8006/api2/json"


def test_build_options_missing_base_url_raises() -> None:
    with pytest.raises(AdapterConfigError) as exc_info:
        build_options(AdapterConfig())
    assert exc_info.value.state is AdapterState.NOT_CONFIGURED


def test_build_options_invalid_fallback_to_defaults() -> None:
    options = build_options(
        AdapterConfig(
            base_url="https://pve.example.lan:8006",
            extra={
                "rate_limit_per_second": "0",
                "max_retries": "-3",
                "retry_backoff_seconds": "abc",
                "fetch_resource_details": "false",
            },
        )
    )
    assert options.rate_limit_per_second == DEFAULT_RATE_LIMIT_PER_SECOND
    assert options.max_retries == DEFAULT_MAX_RETRIES
    assert options.retry_backoff_seconds == DEFAULT_RETRY_BACKOFF_SECONDS
    assert options.fetch_resource_details is False


def test_build_options_tls_opt_in() -> None:
    options = build_options(
        AdapterConfig(
            base_url="https://pve.example.lan:8006",
            extra={"tls_ca_bundle": "/etc/hcc/certs/proxmox-ca.pem", "tls_verify_disabled": "true"},
        )
    )
    assert options.tls_ca_bundle == "/etc/hcc/certs/proxmox-ca.pem"
    assert options.tls_verify_disabled is True


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://pve.example.lan:8006", "https://pve.example.lan:8006/api2/json"),
        ("https://pve.example.lan:8006/", "https://pve.example.lan:8006/api2/json"),
        ("https://pve.example.lan:8006/api2/json/", "https://pve.example.lan:8006/api2/json"),
        ("https://pve.example.lan:8006/api2", "https://pve.example.lan:8006/api2/json"),
    ],
)
def test_api_root_normalization(base_url: str, expected: str) -> None:
    assert build_options(AdapterConfig(base_url=base_url)).api_root == expected


def test_minimum_pve_major_constant() -> None:
    assert MINIMUM_PVE_MAJOR == 8
