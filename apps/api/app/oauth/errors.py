"""Translate a domain :class:`OAuthError` into the correct spec response (docs/05).

Token/registration errors are JSON bodies (RFC 6749 §5.2 / RFC 7591 §3.2.2); authorize
errors are returned to a **validated** ``redirect_uri`` as query parameters (RFC 6749
§4.1.2.1). Non-redirectable errors are handled by the routers with an HTML error page.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi.responses import JSONResponse, RedirectResponse

from app.services.oauth import OAuthError


def oauth_error_json(exc: OAuthError) -> JSONResponse:
    """OAuth error as a JSON body with the mapped status (400/401/429)."""
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.error, "error_description": exc.description},
        headers={"Cache-Control": "no-store"},
    )


def redirect_with_error(redirect_uri: str, exc: OAuthError, state: str | None) -> RedirectResponse:
    """Redirect a recoverable authorize error back to the (already-validated) ``redirect_uri``."""
    params = {"error": exc.error, "error_description": exc.description}
    if state:
        params["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(params)}", status_code=302)
