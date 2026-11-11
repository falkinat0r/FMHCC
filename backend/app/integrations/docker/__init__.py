"""Docker-Integration (Agent 4, R1).

Read-only-Adapter für die Docker Engine-API; Zugriffsmodelle und
Sicherheitspolitik in security.py.
"""

from app.integrations.docker.adapter import DockerAdapter
from app.integrations.docker.security import (
    DockerAccess,
    build_docker_transport,
    resolve_docker_access,
)

__all__ = ["DockerAccess", "DockerAdapter", "build_docker_transport", "resolve_docker_access"]
