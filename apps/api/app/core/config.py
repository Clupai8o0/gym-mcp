"""Application settings (pydantic-settings), read from the environment.

Phase 1 only needs the two Neon connection strings (pooled for the app runtime,
unpooled/direct for migrations & seeds). Later phases extend this with the OAuth,
Google OIDC, Blob, and OpenAI settings listed in ``.env.example`` / docs/09.

``get_settings()`` is cached and instantiated lazily, so importing this module never
requires the environment to be populated — only the first call does (fail-fast).
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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (instantiated on first use)."""
    return Settings()  # values are sourced from the environment / .env
