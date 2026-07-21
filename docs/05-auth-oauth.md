# 05 — Auth & OAuth 2.1 (SECURITY-CRITICAL)

> ⚠️ **This is the highest-risk doc in the build.** A mistake here is a security
> vulnerability, not a bug. The phase that implements it has a **mandatory human security
> review gate** (see `11-agent-workflow.md`). Do not deploy this to production without it.

## The two things we are building

1. **End-user authentication → delegated to Google (OIDC).** We do **not** store passwords.
   Google tells us who the user is; we create/lookup a `users` row by `google_sub`.
2. **An OAuth 2.1 Authorization Server (AS) → hand-rolled in FastAPI.** This is what an MCP
   client (claude.ai) talks to so it can act on the user's behalf against our MCP resource.

Keeping (1) delegated shrinks the hand-rolled surface to the OAuth *protocol* only. This is
the safe interpretation of "hand-rolled OAuth 2.1" and is the design of record (Decision D5).

```
        ┌─────────── end user (browser) ───────────┐
        │                                           │
   web login                                  MCP authorize
        │                                           │
        ▼                                           ▼
  auth/ (Google OIDC) ──creates/loads──► users ◄── oauth/ (our AS)
        │                                           │  issues Tempo tokens
   sets web session cookie                          ▼
                                          claude.ai (MCP client)
                                                    │ Bearer <tempo access token>
                                                    ▼
                                          /mcp  (protected resource)
```

## Part A — Web login (Google OIDC)

Used by the browser to establish a session, **and** reused as the login step inside the AS's
authorize flow (so a user logging into the connector uses the same Google button).

Endpoints (in `app/auth/`):
- `GET /oauth/login/google` → build Google OIDC auth URL (scope `openid email profile`,
  `state`, `nonce`, PKCE), redirect.
- `GET /oauth/callback/google` → validate `state`/`nonce`, exchange code, verify the ID token
  (issuer, audience, signature via Google JWKS, expiry), upsert `users` by `google_sub`, set a
  **signed, httpOnly, Secure, SameSite=Lax** session cookie with `Domain=tempo.clupai.com`
  (set by `api.tempo.clupai.com` for its parent domain → delivered to both subdomains), redirect
  to `WEB_ORIGIN` (or back into the AS authorize flow).

Session cookie:
- Signed (HMAC via `SESSION_SIGNING_KEY`) or a random opaque token stored server-side. Short
  TTL with sliding renewal. `httpOnly`, `Secure`, `SameSite=Lax`, `Domain=tempo.clupai.com`.
- `tempo.clupai.com` (web) and `api.tempo.clupai.com` (api) are **same-site** (shared
  registrable domain), so the parent-domain cookie reaches both and `SameSite=Lax` holds.
- **CORS:** the API allows only `https://tempo.clupai.com` (+ any stable preview origin) with
  `allow_credentials=True` — never `*` with credentials.
- **CSRF:** since the SPA authenticates via the cookie, require a **custom header**
  (e.g. `X-Tempo-Client: web`) on all state-changing API requests. The custom header forces a
  CORS preflight that only our web origin passes, so a cross-site page cannot forge an
  authenticated mutation. (Double-submit CSRF token is an acceptable alternative.)

> **Preview environments:** random `*.vercel.app` preview pairs are **cross-site**, so the
> parent-domain cookie won't span them. For auth-capable previews use **stable preview
> subdomains** under the real domain (e.g. `staging.tempo.clupai.com` +
> `api.staging.tempo.clupai.com`) with their own Google redirect entry + Neon branch. See `09`.

## Part B — The Authorization Server (MCP-facing)

Implements the **MCP Authorization spec (2025-06-18)** = OAuth 2.1 + these RFCs. Every MUST
below is from the spec; treat them as acceptance criteria.

### B1. Discovery metadata (two well-known documents)

**Protected Resource Metadata — RFC 9728** (the MCP resource advertises its AS):
`GET /.well-known/oauth-protected-resource`
```json
{
  "resource": "https://api.tempo.clupai.com/mcp",
  "authorization_servers": ["https://api.tempo.clupai.com"],
  "scopes_supported": ["workouts.read", "workouts.write"],
  "bearer_methods_supported": ["header"]
}
```
The MCP endpoint's **401** responses MUST include:
`WWW-Authenticate: Bearer resource_metadata="https://api.tempo.clupai.com/.well-known/oauth-protected-resource"`

**Authorization Server Metadata — RFC 8414**:
`GET /.well-known/oauth-authorization-server`
```json
{
  "issuer": "https://api.tempo.clupai.com",
  "authorization_endpoint": "https://api.tempo.clupai.com/oauth/authorize",
  "token_endpoint": "https://api.tempo.clupai.com/oauth/token",
  "registration_endpoint": "https://api.tempo.clupai.com/oauth/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["none"],
  "scopes_supported": ["workouts.read", "workouts.write"]
}
```
- `code_challenge_methods_supported` **MUST** advertise `["S256"]` (claude.ai checks this).
- `issuer` MUST exactly match and be the base for the endpoints.

### B2. Dynamic Client Registration — RFC 7591

`POST /oauth/register` — claude.ai auto-registers itself as a **public** client.
- Accept the client metadata (`client_name`, `redirect_uris`, `grant_types`,
  `token_endpoint_auth_method: "none"`, `response_types`).
- **Validate `redirect_uris`** — must be `https` (allow the known Claude callback
  `https://claude.ai/api/mcp/auth_callback`; be ready for `https://claude.com/...` too).
- Generate a `client_id` (public, no secret for public clients), persist to `oauth_clients`,
  return the registration response with `client_id`.
- Rate-limit this endpoint; it is unauthenticated by spec. Consider capping registrations and
  logging them. (Manual client_id/secret is the fallback if DCR is ever disabled.)

### B3. Authorization endpoint (PKCE, code flow)

`GET /oauth/authorize` with `response_type=code`, `client_id`, `redirect_uri`, `scope`,
`state`, `code_challenge`, `code_challenge_method=S256`, and (per RFC 8707) `resource`.
1. Validate `client_id` exists and `redirect_uri` **exactly** matches a registered URI.
2. Require an authenticated user: if no valid web session, redirect into `GET /oauth/login/google`
   and return here afterward (preserve all params).
3. Show a **consent screen** ("Claude wants to read & update your Tempo workouts") — at least
   once per client; record consent.
4. Mint a single-use **authorization code** (store only its SHA-256 hash), bound to
   `client_id`, `user_id`, `redirect_uri`, `scope`, `code_challenge`, `resource`, **TTL ≤ 60s**.
5. Redirect to `redirect_uri?code=...&state=...`.

### B4. Token endpoint

`POST /oauth/token` (form-encoded). Two grants:

**`grant_type=authorization_code`:**
- Look up the code by hash; reject if missing, **consumed**, or expired. Mark consumed atomically.
- Verify `client_id` and `redirect_uri` match the code.
- **PKCE:** `SHA256(code_verifier) == code_challenge` (base64url, no padding). Reject on mismatch.
- Verify `resource` matches. Issue:
  - `access_token`: opaque random (store SHA-256 hash), TTL ~1h, scope, `user_id`, `client_id`.
  - `refresh_token`: opaque random (store hash), longer TTL.
  - Response: `{access_token, token_type: "Bearer", expires_in, refresh_token, scope}`.

**`grant_type=refresh_token`:**
- Look up by hash; reject if missing/expired/revoked.
- **Rotate:** issue a new refresh token, **revoke the old one** (record `rotated_from`). This
  is REQUIRED for public clients. Detect reuse of a revoked refresh token → **revoke the whole
  chain** (token theft response).
- Issue a new access token.

### B5. Resource server enforcement (the `/mcp` guard)

- Every `/mcp` request: extract `Bearer` token, hash, look up `oauth_access_tokens`; reject if
  missing/expired/revoked → **401 + WWW-Authenticate** (PRM pointer, B1).
- **Audience binding:** the token was issued for `resource = https://api.tempo.clupai.com/mcp`;
  reject tokens not bound to this resource (prevents token pass-the-hash across resources).
- Map token → `user_id`, run tools scoped to that user. Enforce `scope` (`workouts.write` for
  mutations).

## Security checklist (the review gate blocks on all of these)

- [ ] **PKCE S256 mandatory**; `plain` rejected; advertised in metadata.
- [ ] Authorization codes: single-use, hashed at rest, ≤60s TTL, bound to client+redirect+PKCE+resource.
- [ ] `redirect_uri` **exact-match** validation (no substring/prefix matching, no open redirect).
- [ ] Access & refresh tokens: **opaque, random ≥256-bit, stored only as SHA-256 hashes**.
- [ ] Refresh token **rotation** with reuse detection → chain revocation.
- [ ] Tokens **audience/resource-bound**; resource server checks it.
- [ ] `state` and `nonce` validated on both the Google flow and the AS flow (CSRF).
- [ ] All endpoints **HTTPS only**; cookies `Secure`+`httpOnly`+`SameSite=Lax`+`Domain=tempo.clupai.com`.
- [ ] Cookie-authed API mutations are CSRF-protected (custom-header-forces-preflight or
      double-submit token); CORS `allow_credentials` with an **explicit** origin allowlist (never `*`).
- [ ] `/oauth/register` rate-limited; redirect_uris https-validated; registrations logged.
- [ ] Consent screen shown and recorded per client.
- [ ] No secrets/tokens in logs; log token **ids/hashes prefixes** only.
- [ ] ID token from Google fully verified (iss, aud, exp, signature via JWKS, nonce).
- [ ] Clock-skew tolerance small and explicit; expiries enforced server-side.
- [ ] A revoked/expired token path is tested (returns 401, triggers client refresh).

## Reference implementation notes

- **Don't reinvent crypto.** Use `authlib` for JWT/JWS verification of Google's ID token and
  for OAuth primitives where it helps, but keep the AS endpoints explicit and readable so the
  reviewer can audit them. `secrets.token_urlsafe(32)` for opaque tokens; `hashlib.sha256` for
  at-rest hashing; `hmac.compare_digest` for comparisons.
- **Scopes (v1):** `workouts.read`, `workouts.write`. Keep it minimal; expand later.
- **Token TTLs:** access ~1h, refresh ~30–90d (rotated). Tune after review.
- **Testing:** a full end-to-end test that simulates a client: discovery → register → authorize
  (with a logged-in test user) → token (PKCE) → call `/mcp` → refresh → reuse-old-refresh
  (expect chain revocation). This test is part of the DoD.

## Definition of Done (auth phase)
- Both well-known documents serve valid, spec-conformant JSON; `/mcp` 401s carry the PRM pointer.
- The end-to-end OAuth test above passes.
- **claude.ai successfully adds the connector** via the live handshake (discovery → DCR →
  Google login → consent → token) and can call a tool.
- The security checklist is fully checked **and signed off in a human review** recorded in the
  phase's PR.
