"""OAuth wire schemas — DCR (RFC 7591), token responses, and discovery metadata (docs/05)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClientRegistrationRequest(BaseModel):
    """Inbound DCR body. Unknown RFC 7591 metadata fields are ignored, not rejected."""

    model_config = ConfigDict(extra="ignore")

    redirect_uris: list[str] = Field(min_length=1)
    client_name: str | None = None
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    token_endpoint_auth_method: str | None = None
    scope: str | None = None


class ClientRegistrationResponse(BaseModel):
    """DCR success body (RFC 7591 §3.2.1). Public client → no ``client_secret``."""

    client_id: str
    client_id_issued_at: int
    client_name: str | None = None
    redirect_uris: list[str]
    grant_types: list[str]
    response_types: list[str]
    token_endpoint_auth_method: str
    scope: str | None = None


class TokenResponse(BaseModel):
    """Token endpoint success body (RFC 6749 §5.1)."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str


class AuthorizationServerMetadata(BaseModel):
    """RFC 8414 AS metadata (``/.well-known/oauth-authorization-server``)."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    response_types_supported: list[str]
    grant_types_supported: list[str]
    code_challenge_methods_supported: list[str]
    token_endpoint_auth_methods_supported: list[str]
    scopes_supported: list[str]


class ProtectedResourceMetadata(BaseModel):
    """RFC 9728 PRM (``/.well-known/oauth-protected-resource``)."""

    resource: str
    authorization_servers: list[str]
    scopes_supported: list[str]
    bearer_methods_supported: list[str]
