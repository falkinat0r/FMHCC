"""Applikationskonfiguration (pydantic-settings).

Alle Werte werden aus Environment-Variablen mit dem Praefix ``HCC_`` gelesen
(oder aus einer lokalen ``.env``, die nie committet wird). Secrets gehoeren
nicht in Code oder Versionierung, sondern nach ``/etc/hcc/hcc.env`` bzw.
``/etc/hcc/secrets.env`` (siehe docs/DEPLOYMENT_PLAYBOOK.md).
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HCC_", env_file=".env", extra="ignore")

    # Allgemein
    environment: Environment = Environment.DEVELOPMENT
    host: str = Field(default="127.0.0.1", description="Bind-Adresse (Loopback-Zwang in Produktion)")
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    git_commit: str = Field(default="unknown", description="Commit/Build-Referenz, 'unknown' wenn nicht bekannt")

    # Datenbank
    database_url: str = Field(
        default="postgresql+psycopg://hcc:hcc@127.0.0.1:5432/hcc",
        description="Produktion: PostgreSQL. Tests/Entwicklung: sqlite erlaubt.",
    )

    # Sessions / Cookies
    session_cookie_name: str = "hcc_session"
    csrf_cookie_name: str = "hcc_csrf"
    session_ttl_seconds: int = Field(default=12 * 3600, ge=60, le=30 * 24 * 3600)
    cookie_secure: bool = Field(default=False, description="Secure-Flag; in production zwingend true")

    # Admin-Bootstrap (einmalig, nur solange keine User existieren)
    bootstrap_token: str = Field(default="", description="Zufalls-Bootstrap-Token; leer = Bootstrap deaktiviert")

    # CORS (restriktiv: leer = nur same-origin)
    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.environment is Environment.PRODUCTION and not self.cookie_secure:
            raise ValueError("HCC_COOKIE_SECURE muss in production 'true' sein (TLS erforderlich)")
        return self


@lru_cache
def get_settings() -> Settings:
    """Prozess-weite Settings (aus Environment / .env)."""
    return Settings()
