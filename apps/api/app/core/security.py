"""Cryptographic primitives for auth & OAuth (docs/05 — SECURITY-CRITICAL).

Everything the security reviewer needs to audit the *crypto* lives here, small and
explicit (docs/05: "keep the AS endpoints explicit and readable"). No framework imports.

What this module guarantees:

* **Opaque secrets** — access/refresh tokens and authorization codes are
  ``secrets.token_urlsafe(32)`` → 256 bits of CSPRNG entropy (checklist: "opaque, random
  ≥256-bit").
* **At-rest hashing** — secrets are persisted only as ``hash_token()`` digests, never in
  plaintext. The digest is **HMAC-SHA256 keyed by ``TOKEN_HASH_PEPPER``**: a DB leak alone
  (without the server-side pepper) cannot be used to confirm a guessed/stolen token.
* **Constant-time comparison** — every secret/PKCE/MAC comparison uses
  :func:`hmac.compare_digest`, never ``==``.
* **PKCE S256 only** — :func:`verify_pkce_s256`; ``plain`` is never accepted anywhere.
* **Signed, tamper-evident payloads** — the stateless web-session cookie and the two
  short-lived transaction tokens (OIDC login, authorize consent) are HMAC-SHA256 signed
  with domain separation (``typ``) so a token minted for one purpose can't be replayed as
  another, and carry ``iat`` for server-side max-age enforcement.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

# Opaque tokens: 32 bytes of entropy → 256-bit (token_urlsafe yields ~43 url-safe chars).
_TOKEN_BYTES = 32
# Reject signed payloads whose ``iat`` is more than this far in the *future* (clock skew).
_MAX_FUTURE_SKEW_SECONDS = 60


# ── base64url (no padding), used for PKCE digests and payload bodies ─────────────────
def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ── Opaque tokens + at-rest hashing ──────────────────────────────────────────────────
def generate_opaque_token() -> str:
    """A fresh 256-bit URL-safe opaque secret (access/refresh token, auth code)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str, *, pepper: str | None = None) -> str:
    """Return the at-rest digest for ``token`` (HMAC-SHA256 keyed by the pepper).

    Deterministic, so a presented token is looked up by recomputing its digest. ``pepper``
    defaults to the configured ``TOKEN_HASH_PEPPER`` (read lazily to keep this importable
    without an environment).
    """
    if pepper is None:
        from app.core.config import get_settings

        pepper = get_settings().token_hash_pepper
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_equal(a: str, b: str) -> bool:
    """Constant-time comparison of two hex digests."""
    return hmac.compare_digest(a, b)


# ── PKCE (RFC 7636) — S256 only ──────────────────────────────────────────────────────
def compute_s256_challenge(code_verifier: str) -> str:
    """The S256 code challenge for a verifier: ``base64url(sha256(verifier))`` (no pad)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return b64url_encode(digest)


def verify_pkce_s256(code_verifier: str, code_challenge: str) -> bool:
    """True iff ``code_verifier`` matches ``code_challenge`` under S256 (constant-time)."""
    if not code_verifier or not code_challenge:
        return False
    return hmac.compare_digest(compute_s256_challenge(code_verifier), code_challenge)


# ── Signed, tamper-evident payloads (session cookie + transaction tokens) ─────────────
def sign_payload(payload: dict[str, Any], *, key: str, typ: str) -> str:
    """Serialize ``payload`` and return ``<body>.<mac>`` (HMAC-SHA256, base64url).

    A ``typ`` (domain-separation tag) and ``iat`` (issued-at) are stamped in automatically;
    the caller's keys must not collide with them.
    """
    stamped = {**payload, "typ": typ, "iat": int(time.time())}
    body = b64url_encode(json.dumps(stamped, separators=(",", ":"), sort_keys=True).encode())
    mac = _mac(body, key)
    return f"{body}.{mac}"


def verify_payload(
    token: str, *, key: str, typ: str, max_age_seconds: int | None
) -> dict[str, Any] | None:
    """Verify signature, ``typ``, and age; return the payload dict, or ``None`` if invalid.

    Returns ``None`` (never raises) on any tampering, wrong purpose, malformed body, or
    expiry — callers treat that as "no valid credential".
    """
    try:
        body, mac = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(mac, _mac(body, key)):
        return None
    try:
        payload = json.loads(b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("typ") != typ:
        return None

    iat = payload.get("iat")
    if not isinstance(iat, (int, float)):
        return None
    now = time.time()
    if iat - now > _MAX_FUTURE_SKEW_SECONDS:  # minted in the future → reject
        return None
    if max_age_seconds is not None and now - iat > max_age_seconds:
        return None
    return payload


def _mac(body: str, key: str) -> str:
    return b64url_encode(
        hmac.new(key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
