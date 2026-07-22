"""Application settings (pydantic-settings), read from the environment.

Phase 1 needed only the two Neon connection strings (pooled for the app runtime,
unpooled/direct for migrations & seeds). Phase 2 added the CORS origin and log level.
Phase 3 adds the auth/OAuth surface: canonical origins + issuer, the session-cookie and
token-hashing secrets, the Google OIDC client, and the redirect-URI allowlist
(docs/05-auth-oauth.md, docs/09).

Every Phase 3 field carries a **local/dev default** so the app and test suite boot without
a populated environment — but the two secrets (``session_signing_key``, ``token_hash_pepper``)
and the Google client default to clearly-marked *insecure* dev sentinels. Production MUST
override them; :meth:`Settings.insecure_defaults_in_use` surfaces any that were not, and the
deploy checklist (docs/09) + the human security review (docs/05) gate on it.

``get_settings()`` is cached and instantiated lazily, so importing this module never
requires the environment to be populated — only the first call does (fail-fast on the
required Neon URLs).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev sentinels: safe to boot locally, never acceptable in production. Kept as module
# constants so the "are we still running on an insecure default?" check is exact.
_DEV_SIGNING_KEY = "dev-insecure-session-signing-key-change-me"
_DEV_HASH_PEPPER = "dev-insecure-token-hash-pepper-change-me"


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

    # ── Canonical origins / OAuth issuer ────────────────────────────────────────────
    # The API's own public origin — the base for every absolute OAuth/callback URL and
    # the RFC 8707 ``resource`` the MCP audience is bound to. In production this is
    # ``https://api.tempo.clupai.com`` and MUST equal ``oauth_issuer``.
    public_base_url: str = "http://localhost:8000"
    oauth_issuer: str = "http://localhost:8000"

    # ── Web session cookie (Google login) ───────────────────────────────────────────
    # Empty domain → host-only cookie (correct for localhost). In production set to the
    # parent domain ``tempo.clupai.com`` so the cookie reaches both subdomains (docs/05).
    session_cookie_domain: str = ""
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days, sliding (renewed past half-life)

    # ── Secrets (generate with `openssl rand -hex 32`) ──────────────────────────────
    session_signing_key: str = _DEV_SIGNING_KEY
    token_hash_pepper: str = _DEV_HASH_PEPPER

    # ── Google OIDC (end-user identity is delegated to Google) ───────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    # Empty → derived as ``{public_base_url}/oauth/callback/google`` (see the property).
    google_redirect_uri: str = ""

    # ── OAuth AS: client redirect-URI host allowlist (DCR) ───────────────────────────
    # Comma-separated hosts a registered client's redirect_uris must belong to. claude.ai
    # is the MCP client today; claude.com is included for the impending rename (docs/05).
    allowed_redirect_hosts: str = "claude.ai,claude.com"

    # ── OAuth AS: token/code lifetimes ───────────────────────────────────────────────
    auth_code_ttl_seconds: int = 60  # spec: ≤ 60s
    access_token_ttl_seconds: int = 60 * 60  # ~1h
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 60  # ~60d (rotated on every use)

    # ── OAuth AS: DCR abuse backstop ─────────────────────────────────────────────────
    # ``/oauth/register`` is unauthenticated by spec; cap new registrations per minute
    # (a coarse, stateless backstop — see services/oauth.register_client).
    oauth_registration_rate_limit_per_minute: int = 20

    @property
    def cors_allow_origins(self) -> list[str]:
        """The exact CORS allowlist: ``web_origin`` plus any configured preview origins."""
        extra = [o.strip() for o in self.cors_extra_origins.split(",") if o.strip()]
        return [self.web_origin, *extra]

    @property
    def google_redirect_uri_resolved(self) -> str:
        """The Google OIDC callback URL (explicit override, else derived from the base)."""
        return self.google_redirect_uri or f"{self.public_base_url}/oauth/callback/google"

    @property
    def allowed_redirect_hosts_list(self) -> list[str]:
        """Parsed, lower-cased redirect-URI host allowlist for DCR clients."""
        return [h.strip().lower() for h in self.allowed_redirect_hosts.split(",") if h.strip()]

    @property
    def mcp_resource(self) -> str:
        """The canonical MCP resource URL that access tokens are audience-bound to."""
        return f"{self.public_base_url}/mcp"

    @property
    def cookie_secure(self) -> bool:
        """Cookies are ``Secure`` whenever the public origin is HTTPS (i.e. not localhost)."""
        return self.public_base_url.lower().startswith("https://")

    def insecure_defaults_in_use(self) -> list[str]:
        """Names of security-critical settings still on their insecure dev default.

        Empty on a correctly-configured production environment. Used by the deploy
        checklist / startup warning — never fatal in dev so local boot stays frictionless.
        """
        offenders: list[str] = []
        if self.session_signing_key == _DEV_SIGNING_KEY:
            offenders.append("SESSION_SIGNING_KEY")
        if self.token_hash_pepper == _DEV_HASH_PEPPER:
            offenders.append("TOKEN_HASH_PEPPER")
        if self.cookie_secure and not (self.google_client_id and self.google_client_secret):
            offenders.append("GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET")
        return offenders


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (instantiated on first use)."""
    return Settings()  # values are sourced from the environment / .env
