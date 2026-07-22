"""Application settings (pydantic-settings), read from the environment.

Phase 1 needed only the two Neon connection strings (pooled for the app runtime,
unpooled/direct for migrations & seeds). Phase 2 adds the CORS origin and log level
(both defaulted for local/test). Later phases extend this with the OAuth, Google OIDC,
Blob, and OpenAI settings listed in ``.env.example`` / docs/09 — required then, not now,
so the auth-stubbed backend boots without them.

``get_settings()`` is cached and instantiated lazily, so importing this module never
requires the environment to be populated — only the first call does (fail-fast on the
required Neon URLs).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration. Required fields fail fast when missing."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Neon Postgres. The app connects via the POOLED URL; Alembic and offline seed
    # jobs use the UNPOOLED (direct) URL — DDL through PgBouncer is unreliable.
    database_url: str
    database_url_unpooled: str

    # CORS: the browser app origin (same-site subdomain). Additional stable preview
    # origins may be supplied comma-separated. Never combined with a wildcard when
    # credentials are allowed (docs/03). Defaulted for local dev; set in each Vercel env.
    web_origin: str = "http://localhost:3000"
    cors_extra_origins: str = ""

    log_level: str = "INFO"

    @property
    def cors_allow_origins(self) -> list[str]:
        """The exact CORS allowlist: ``web_origin`` plus any configured preview origins."""
        extra = [o.strip() for o in self.cors_extra_origins.split(",") if o.strip()]
        return [self.web_origin, *extra]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (instantiated on first use)."""
    return Settings()  # values are sourced from the environment / .env
