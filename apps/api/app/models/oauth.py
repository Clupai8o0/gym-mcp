"""OAuth 2.1 Authorization-Server tables (docs/02 §OAuth, docs/05).

Deferred out of the Phase 1 baseline so the data-model phase could complete independently;
they land in Phase 3's migration (``0003_oauth``). Every credential is stored **only as a
hash** (``core.security.hash_token``) — a DB leak never exposes a live token or code.

Three columns extend the docs/02 reference DDL to satisfy mandatory docs/05 requirements
(recorded in the Decision Log, docs/01):

* ``oauth_access_tokens.resource`` / ``oauth_refresh_tokens.resource`` — the RFC 8707
  audience each token was minted for, so the resource server's audience-binding check
  (docs/05 B5) is a real per-token comparison rather than a global assumption.
* ``oauth_refresh_tokens.chain_id`` — a stable id shared by every token in one rotation
  lineage, so reuse detection revokes the **whole chain** in a single indexed write
  (docs/05 B4). ``rotated_from`` is kept alongside it as the exact-predecessor audit link.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class OAuthClient(Base):
    """A registered MCP client. claude.ai self-registers via DCR (RFC 7591) as *public*."""

    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Null for public clients (claude.ai has no secret); set only for confidential clients.
    client_secret_hash: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str | None] = mapped_column(Text)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    grant_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{authorization_code,refresh_token}'::text[]"),
    )
    token_endpoint_auth_method: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="none"
    )
    scope: Mapped[str | None] = mapped_column(Text)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = created_at_col()


class OAuthAuthorizationCode(Base):
    """Short-lived (≤60s), single-use, PKCE-bound authorization code — stored hashed."""

    __tablename__ = "oauth_authorization_codes"
    __table_args__ = (
        CheckConstraint("code_challenge_method = 'S256'", name="code_challenge_method"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)
    code_challenge: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(Text, nullable=False, server_default="S256")
    resource: Mapped[str | None] = mapped_column(Text)  # RFC 8707 resource indicator
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class OAuthAccessToken(Base):
    """Opaque bearer token (~1h), stored hashed, audience-bound to ``resource``."""

    __tablename__ = "oauth_access_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str | None] = mapped_column(Text)
    resource: Mapped[str | None] = mapped_column(Text)  # audience binding (docs/05 B5)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class OAuthRefreshToken(Base):
    """Opaque refresh token (~60d), rotated on every use; reuse revokes the whole chain."""

    __tablename__ = "oauth_refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str | None] = mapped_column(Text)
    resource: Mapped[str | None] = mapped_column(Text)  # carried across rotation
    # Stable per-lineage id → reuse detection revokes the whole chain in one write.
    chain_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, server_default=text("gen_random_uuid()"), index=True
    )
    # Exact predecessor (audit link, docs/02). Null on the first token of a chain.
    rotated_from: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("oauth_refresh_tokens.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
