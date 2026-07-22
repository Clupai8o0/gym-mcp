"""Unit tests for the crypto primitives (docs/05 checklist — no DB)."""

from __future__ import annotations

import time

import pytest
from app.core import security

_KEY = "unit-test-signing-key"


# ── opaque tokens + at-rest hashing ──────────────────────────────────────────────────
def test_opaque_tokens_are_unique_and_high_entropy() -> None:
    tokens = {security.generate_opaque_token() for _ in range(200)}
    assert len(tokens) == 200  # no collisions
    # token_urlsafe(32) → 32 bytes base64url, ~43 chars.
    assert all(len(t) >= 43 for t in tokens)


def test_hash_token_is_deterministic_and_pepper_dependent() -> None:
    token = "s3cret-token"
    assert security.hash_token(token, pepper="p1") == security.hash_token(token, pepper="p1")
    assert security.hash_token(token, pepper="p1") != security.hash_token(token, pepper="p2")
    # The digest never contains the plaintext, and is a 64-char sha256 hex string.
    digest = security.hash_token(token, pepper="p1")
    assert token not in digest
    assert len(digest) == 64


# ── PKCE S256 ─────────────────────────────────────────────────────────────────────────
def test_pkce_s256_roundtrip_and_rejects_mismatch() -> None:
    verifier = security.generate_opaque_token()
    challenge = security.compute_s256_challenge(verifier)
    assert security.verify_pkce_s256(verifier, challenge) is True
    assert security.verify_pkce_s256("wrong-verifier", challenge) is False
    assert security.verify_pkce_s256("", challenge) is False
    assert security.verify_pkce_s256(verifier, "") is False


def test_pkce_challenge_is_unpadded_base64url() -> None:
    challenge = security.compute_s256_challenge("abc123")
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge


# ── signed payloads (session + tx tokens) ─────────────────────────────────────────────
def test_sign_verify_roundtrip_stamps_typ_and_iat() -> None:
    token = security.sign_payload({"sub": "u1"}, key=_KEY, typ="session")
    payload = security.verify_payload(token, key=_KEY, typ="session", max_age_seconds=60)
    assert payload is not None
    assert payload["sub"] == "u1"
    assert payload["typ"] == "session"
    assert isinstance(payload["iat"], int)


def test_verify_rejects_tampered_body_and_mac() -> None:
    token = security.sign_payload({"sub": "u1"}, key=_KEY, typ="session")
    body, mac = token.split(".", 1)
    tampered_body = ("A" if body[0] != "A" else "B") + body[1:]
    tampered_mac = ("A" if mac[0] != "A" else "B") + mac[1:]
    assert (
        security.verify_payload(
            f"{tampered_body}.{mac}", key=_KEY, typ="session", max_age_seconds=60
        )
        is None
    )
    assert (
        security.verify_payload(
            f"{body}.{tampered_mac}", key=_KEY, typ="session", max_age_seconds=60
        )
        is None
    )
    assert (
        security.verify_payload("not-a-token", key=_KEY, typ="session", max_age_seconds=60) is None
    )


def test_verify_rejects_wrong_key_and_wrong_typ() -> None:
    token = security.sign_payload({"sub": "u1"}, key=_KEY, typ="session")
    assert (
        security.verify_payload(token, key="other-key", typ="session", max_age_seconds=60) is None
    )
    # Domain separation: a session token must not validate as an oidc_tx token.
    assert security.verify_payload(token, key=_KEY, typ="oidc_tx", max_age_seconds=60) is None


def test_verify_enforces_expiry_and_future_skew(monkeypatch: pytest.MonkeyPatch) -> None:
    now = int(time.time())
    # Minted 2h ago → expired under a 1h max_age.
    monkeypatch.setattr(time, "time", lambda: now - 7200)
    old = security.sign_payload({"sub": "u1"}, key=_KEY, typ="session")
    monkeypatch.setattr(time, "time", lambda: now)
    assert security.verify_payload(old, key=_KEY, typ="session", max_age_seconds=3600) is None

    # Minted 10min in the future → rejected as clock-skew implausible.
    monkeypatch.setattr(time, "time", lambda: now + 600)
    future = security.sign_payload({"sub": "u1"}, key=_KEY, typ="session")
    monkeypatch.setattr(time, "time", lambda: now)
    assert security.verify_payload(future, key=_KEY, typ="session", max_age_seconds=3600) is None


def test_verify_with_no_max_age_ignores_age(monkeypatch: pytest.MonkeyPatch) -> None:
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now - 10_000)
    token = security.sign_payload({"sub": "u1"}, key=_KEY, typ="session")
    monkeypatch.setattr(time, "time", lambda: now)
    assert security.verify_payload(token, key=_KEY, typ="session", max_age_seconds=None) is not None
