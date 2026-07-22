"""OAuth discovery well-knowns (docs/05 B1): AS metadata (RFC 8414) + PRM (RFC 9728).

``public_base_url`` is the single canonical origin: the ``issuer`` and the base of every
advertised endpoint, so ``issuer`` is exactly the endpoints' prefix as the spec demands
(``OAUTH_ISSUER`` must equal ``PUBLIC_BASE_URL`` — see config).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.oauth import AuthorizationServerMetadata, ProtectedResourceMetadata
from app.services.oauth import SUPPORTED_SCOPES

router = APIRouter(tags=["oauth-metadata"])


@router.get(
    "/.well-known/oauth-authorization-server",
    response_model=AuthorizationServerMetadata,
)
async def authorization_server_metadata() -> AuthorizationServerMetadata:
    settings = get_settings()
    base = settings.public_base_url
    return AuthorizationServerMetadata(
        issuer=base,
        authorization_endpoint=f"{base}/oauth/authorize",
        token_endpoint=f"{base}/oauth/token",
        registration_endpoint=f"{base}/oauth/register",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        code_challenge_methods_supported=["S256"],
        token_endpoint_auth_methods_supported=["none"],
        scopes_supported=sorted(SUPPORTED_SCOPES),
    )


@router.get(
    "/.well-known/oauth-protected-resource",
    response_model=ProtectedResourceMetadata,
)
async def protected_resource_metadata() -> ProtectedResourceMetadata:
    settings = get_settings()
    return ProtectedResourceMetadata(
        resource=settings.mcp_resource,
        authorization_servers=[settings.public_base_url],
        scopes_supported=sorted(SUPPORTED_SCOPES),
        bearer_methods_supported=["header"],
    )
