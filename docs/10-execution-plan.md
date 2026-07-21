# 10 — Execution Plan (the master roadmap)

This is the checklist the executing agents work through. **Hybrid sequencing:** foundation
phases (0–5) build the spine top-down; feature slices (6–8) ship the app vertically; then
polish (9) and launch (10).

**Rules for agents (see `11-agent-workflow.md` for the full protocol):**
- Do **one phase at a time**, on its own branch, in order. A phase starts only when its
  dependencies' Definition of Done (DoD) are met.
- Every phase ends with its **acceptance criteria** demonstrably passing (tests + checks) and
  a PR. UI phases also pass the **Antigravity** review; Phase 3 also passes a **human security
  review**.
- Update `docs/STATUS.md` (create it in Phase 0) at the end of each phase: what shipped, DoD
  evidence, and any Decision-Log entries.

Legend: **Depends** = prerequisite phases · **Gate** = required review beyond tests.

---

## Phase 0 — Repo & tooling foundation
**Goal:** an empty but correct monorepo everyone can build.
**Depends:** none · **Gate:** standard review
- Scaffold pnpm workspaces + Turborepo; `apps/web`, `apps/api`, `packages/*`, `scripts/`.
- `apps/web`: Next.js App Router app boots ("hello"). `apps/api`: FastAPI app boots with
  `GET /api/health`. Python via **uv** (`pyproject.toml`, `uv.lock`).
- Root tooling: ruff+black+mypy (Python), eslint+prettier+tsconfig strict (TS), pytest,
  conventional-commit + PR templates, `.env.example`, `.gitignore`, CI running lint+type+test.
- Create `docs/STATUS.md`.
**Acceptance:** `turbo run build lint typecheck test` passes clean; both apps boot locally;
CI green on a trivial PR.

## Phase 1 — Neon + data model
**Goal:** the greenfield schema exists and round-trips.
**Depends:** 0 · **Gate:** standard review · **Ref:** `02-data-model.md`
- Provision Neon (primary + a preview branch); wire pooled + unpooled URLs.
- SQLAlchemy models for all **core + skills** tables; Alembic `0001_init` (extensions + tables +
  indexes). Seed the 13 `skills` definitions.
- (OAuth tables are deferred to Phase 3's migration.)
**Acceptance:** `alembic upgrade head` builds every core+skills table on an empty Neon branch;
`downgrade base` reverses cleanly; model round-trip tests pass; skills seeded.

## Phase 2 — Backend skeleton + core services + REST
**Goal:** the "brain" and its REST surface exist (auth stubbed).
**Depends:** 1 · **Gate:** standard review · **Ref:** `03-backend-fastapi.md`
- `services/` for exercises, sessions, sets (incl. **PR detection**), prs, skills, analytics —
  framework-free, typed, unit-tested against a Neon test branch.
- REST routers mirroring the surface table in `03`; DI for db; **stubbed `current_user`** (a
  fixed dev user) so features work before real auth lands.
- `core/errors.py` mapping; Pydantic schemas; structured logging.
**Acceptance:** router tests pass for exercises/sessions/sets/prs/analytics with the stub user;
PR-detection unit tests pass; **no logic outside `services/`** (enforced by review + a lint/grep
check).

## Phase 3 — Identity + OAuth 2.1 AS  🔒
**Goal:** real Google login + a spec-compliant OAuth server; `/mcp` protectable.
**Depends:** 2 · **Gate:** **HUMAN SECURITY REVIEW** (mandatory) · **Ref:** `05-auth-oauth.md`
- Google OIDC login (`auth/`) + signed httpOnly session cookie; real `current_user` (session
  **or** bearer) replaces the stub.
- Alembic migration for the OAuth tables.
- AS (`oauth/`): PRM + AS metadata well-knowns, DCR, authorize (consent + PKCE), token
  (code + refresh with **rotation & reuse detection**), token hashing at rest, resource/audience
  binding.
**Acceptance:** the full end-to-end OAuth test passes (discovery→register→authorize→token→
refresh→reuse-revocation); well-knowns valid; **the entire security checklist in `05` is
checked and signed off by a human** and recorded in the PR.

## Phase 4 — Catalog import + illustration pipeline
**Goal:** ~800+ exercises in Neon with consistent line-art.
**Depends:** 1 (2 helpful) · **Gate:** design sign-off on style exemplars · **Ref:** `06-catalog-and-images.md`
- `scripts/seed_catalog.py`: idempotent import of pinned free-exercise-db → `exercises`.
- **Lock the illustration style** on 5–8 exemplars (human/Antigravity sign-off) → commit prompt
  template (+ reference).
- `scripts/generate_illustrations.py`: batch GPT Image 2 → Vercel Blob → `illustration_url`,
  idempotent, resumable, cost-reporting.
- On-demand `services/images.ensure` + `POST /api/exercises/{id}/illustration`.
**Acceptance:** catalog count ≈ dataset; re-running seed changes nothing; majority of rows
`illustration_status='ready'` with Blob URLs + provenance; on-demand generates one image for a
custom exercise; cost report within range.

## Phase 5 — MCP server (Python) + connector verification
**Goal:** chat parity with REST, OAuth-protected, live on claude.ai.
**Depends:** 2, 3 (4 for catalog tools) · **Gate:** standard review + live connector test · **Ref:** `04-mcp-server.md`
- Mount the Python MCP app at `/mcp`; register all tools (each ≤~15 lines → a service).
- Protect `/mcp` with bearer resolution + scope enforcement; 401 carries the PRM pointer.
- `tempo://guide` resource; exercise name→id resolution rule.
**Acceptance:** MCP↔REST **contract tests** pass (no drift); claude.ai adds the connector via
the live OAuth handshake; the five verification prompts in `04` succeed end-to-end; token
refresh works without re-auth.

## Phase 6 — Slice: Design system + app shell + **Library**
**Goal:** the first beautiful, working vertical surface.
**Depends:** 2 (5 optional) · **Gate:** **Antigravity frontend review** · **Ref:** `07`, `08`
- Install `getdesign x.ai`; define tokens; build `components/ui/` + `components/motion/`
  primitives (reduced-motion aware).
- App shell: authed `(app)` layout, nav, view-transition wrapper, signed-out landing.
- **Library** surface: catalog grid + filters (URL-synced), exercise detail with illustration +
  instructions + the user's PRs; placeholder state for missing art; shared-element list→detail.
**Acceptance:** Library renders real catalog data for an authed user; filters work; motion obeys
`08`; a11y + CWV budgets met; passes the Antigravity rubric.

## Phase 7 — Slice: **Log a workout** (UI + MCP parity)
**Goal:** the core loop — log a session/sets from the web, mirrored in chat.
**Depends:** 5, 6 · **Gate:** Antigravity frontend review · **Ref:** `07`, `04`
- Start/continue session; `ExercisePicker`; `SetEntryPad` (fast, one-handed, prev-set prefill);
  optimistic saves; **PR celebration** signature moment.
- PWA offline write-queue for set logging (IndexedDB → sync on reconnect).
- Verify the same actions via MCP tools produce identical data.
**Acceptance:** a full workout can be logged from the UI (optimistic, with PR feedback) **and**
from chat, landing identically in Neon; offline logging syncs on reconnect; passes Antigravity.

## Phase 8 — Slice: **Dashboard** + Skills module
**Goal:** progress visualization + the secondary skill tree.
**Depends:** 6 (7 for fresh data) · **Gate:** Antigravity frontend review · **Ref:** `07`, `08`
- Dashboard: PRs (with illustrations), volume (range-selectable), frequency heatmap.
- `/dashboard/skills`: skill rings/stages; edit current stage/% (writes via the skills service).
- Settings: units toggle, **Connected apps** (MCP URL + revoke OAuth clients).
**Acceptance:** dashboard reflects real analytics from the API; skills read/write works; connected-
apps revoke actually revokes tokens; passes Antigravity.

## Phase 9 — Flagship polish pass
**Goal:** raise everything to the design bar.
**Depends:** 6–8 · **Gate:** Antigravity frontend review (final) · **Ref:** `08`, `07`
- Sweep all surfaces for the motion rulebook, signature moments, empty/error/loading states,
  reduced-motion, keyboard/focus, contrast.
- Performance: CWV budgets, image sizing, code-splitting, bundle audit.
- PWA install polish; icons; offline UX copy.
**Acceptance:** every surface passes the full `08` rubric; CWV budgets green on preview;
reduced-motion verified; no unstyled/placeholder states remain.

## Phase 10 — Deploy & launch
**Goal:** production on Vercel, end-to-end.
**Depends:** all · **Gate:** launch checklist sign-off · **Ref:** `09`
- Two Vercel projects on subdomains (`tempo.clupai.com` + `api.tempo.clupai.com`); CORS +
  parent-domain cookie; env matrix (Preview + Prod); Neon prod at `head`; Blob; monitoring/logging.
- Run the seed + image jobs against prod Neon/Blob (offline) if not already.
**Acceptance:** the **Launch checklist** in `09` is fully checked, including a live claude.ai
connector logging a real workout into production and the web app reflecting it.

---

## Dependency graph

```
0 ─▶ 1 ─▶ 2 ─▶ 3(🔒) ─┐
          │            ├─▶ 5 ─▶ 7 ─┐
          │   4 ───────┘           ├─▶ 9 ─▶ 10
          └─▶ 6 ─────────▶ 7       │
                 └────────▶ 8 ─────┘
   (4 depends on 1; can run in parallel with 2/3. 6 depends on 2; 8 can start after 6.)
```

## What "shippable" means at each milestone
- **After 5:** headless product works — log & query workouts via chat, OAuth-secured, on Neon.
- **After 7:** the core web loop works and is beautiful — browse + log, UI/chat in sync.
- **After 10:** public-ready personal app, deployed, with the full illustrated catalog.
