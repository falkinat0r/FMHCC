"""Docker-Transport-Modell und Sicherheitspolitik (Agent 4, R1).

Vergleich der technisch geeigneten Zugriffsmodelle fuer die Docker Engine
API (read-only):

1. **Unix-Socket (lokal) — empfohlen.** HCC laeuft auf dem Docker-Host
   (oder einem dedizierten Host) und nutzt ``/var/run/docker.sock``.
   Sicherheitsanforderung: Socket-Zugriff ist host-seitig ca.
   root-aequivalent (Container-Escape). Deshalb strikt read-only, und der
   HCC-User darf nur Mitglied der Socket-Gruppe sein. Kein Mount eines
   fremden Docker-Sockets aus einem anderen Container (AGENTS.md).
2. **TCP + mTLS (remote) — erlaubt.** ``https://<host>:2376`` mit
   Client-Zertifikat (mutual TLS); optionales Server-CA-Datei/Pfad.
   Zertifikatspfade sind administrativ verwaltete Dateien (keine Secrets).
3. **Plain TCP (``http://``) — abgelehnt.** Ein ungeschuetzter,
   unauthentifizierter TCP-Socket bedeutet Host-Kontrolle. Ausnahme:
   Loopback (127.0.0.1/::1/localhost), das als weiterhin hohes Risiko
   dokumentiert wird.

Konsequenz: HCC setzt **keinen** direkten, ungeschuetzten
Remote-Docker-Socket voraus (AGENTS.md Regel: 'niemals ungeschuetzten
TCP-Socket').

Die eigentliche httpx-Transport-Konstruktion findet erst beim
Client-Setup statt (``build_docker_transport``) — Zertifikatsdateien
werden dadurch nicht bei jeder Config-Pruefung gelesen.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.adapters.base import AdapterConfig
from app.adapters.errors import AdapterConfigError

__all__ = ["DockerAccess", "build_docker_transport", "resolve_docker_access"]

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class DockerAccess:
    """Aufloesung: welches Zugriffsmodell, welche Parameter.

    Die httpx-Transport-Konstruktion (``build_docker_transport``) ist
    bewusst getrennt: so werden Zertifikatspfade erst beim tatsaechlichen
    Client-Setup geladen, nicht bei reinen Config-/Policy-Pruefungen.
    """

    base_url: str
    mode: str  # unix_socket | tcp_tls | tcp_loopback
    uds_path: str | None = None
    ca: str | None = None
    cert: str | None = None
    key: str | None = None
    security_notes: list[str] = field(default_factory=list)


def build_docker_transport(access: DockerAccess) -> httpx.AsyncBaseTransport | None:
    """Erzeugt den httpx-Transport fuer das Zugriffsmodell (lazig)."""
    if access.uds_path:
        return httpx.AsyncHTTPTransport(uds=access.uds_path)
    if access.ca or access.cert:
        context = ssl.create_default_context(cafile=access.ca) if access.ca else ssl.create_default_context()
        return httpx.AsyncHTTPTransport(verify=context, cert=(access.cert, access.key) if access.cert else None)
    return None


def resolve_docker_access(config: AdapterConfig) -> DockerAccess:
    """Waehlt das Zugriffsmodell aus und erzwingt die Sicherheitspolitik."""
    socket_path = config.extra.get("docker_socket")
    if socket_path:
        if not socket_path.startswith("/"):
            raise AdapterConfigError(
                "Docker: extra.docker_socket muss ein absoluter Pfad sein (z. B. /var/run/docker.sock)"
            )
        return DockerAccess(
            base_url="http://docker",  # Hostname ist Platzhalter, UDS-Transport uebernimmt
            mode="unix_socket",
            uds_path=socket_path,
            security_notes=[
                "Socket-Zugriff ist host-seitig ca. root-aequivalent: read-only-Profile, "
                "HCC-User nur in der Socket-Gruppe, kein fremder Socket aus anderen Containern"
            ],
        )

    base = str(config.base_url) if config.base_url else ""
    if not base:
        raise AdapterConfigError(
            "Docker: kein Zugriff konfiguriert (base_url oder extra.docker_socket erforderlich)"
        )
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https"):
        raise AdapterConfigError(f"Docker: ungueltiges Protokoll '{parsed.scheme}'")
    if not parsed.hostname:
        raise AdapterConfigError("Docker: base_url ohne Host")

    if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
        raise AdapterConfigError(
            "Docker: plain TCP (http://) zu Nicht-Loopback ist nicht erlaubt "
            "(ungeschuetzter Engine-Socket = Host-Kontrolle); TLS (https://) oder lokales Socket verwenden"
        )

    if parsed.scheme == "http":
        return DockerAccess(
            base_url=base,
            mode="tcp_loopback",
            security_notes=["Plain TCP nur auf Loopback — hohes Risiko (ungeschuetzt), nur fuer isolierte Umgebungen"],
        )

    # TLS remote: optionales Client-Zertifikat / Server-CA (admin-verwaltete Pfade)
    ca = config.extra.get("docker_ca")
    cert = config.extra.get("docker_cert")
    key = config.extra.get("docker_key")
    if cert and not key:
        raise AdapterConfigError("Docker: extra.docker_cert erfordert extra.docker_key")
    notes = [
        "Remote-Docker-API nur ueber TLS (https://) mit mTLS-Client-Zertifikat empfohlen; "
        "Port 2376 statt 2375"
    ]
    if not cert:
        notes.append("Kein Client-Zertifikat konfiguriert — nur wenn die API zusaetzlich Auth erzwingt")
    return DockerAccess(base_url=base, mode="tcp_tls", ca=ca, cert=cert, key=key, security_notes=notes)
