# 11 — Agent Workflow & Orchestration

How the docs get executed by agents. Read this with `10-execution-plan.md`.

## Roles

| Role | Who | Responsibility |
|---|---|---|
| **Orchestrator** | Claude Opus | Owns `10-execution-plan.md`. Assigns one phase at a time to executors, tracks state in `STATUS.md`, enforces gates, integrates PRs, decides when a phase's DoD is met, keeps the Decision Log honest. Does **not** hand-write most code. |
| **Executor** | Codex (+ Opus subagents) | Implements the tasks of the assigned phase against its reference docs. Writes code + tests. Opens the PR. Self-verifies acceptance criteria before requesting review. |
| **Frontend reviewer** | Antigravity CLI | Reviews every **UI** phase (6–9) against the `08` rubric (design + motion + a11y + performance). Blocks merge until it passes. |
| **Security reviewer** | **Human** | Mandatory sign-off on **Phase 3** (OAuth). Reviews the `05` security checklist line by line. No automated substitute. |

## The phase loop

For each phase, in order:

1. **Assign.** Orchestrator confirms dependencies' DoD are green, then briefs the executor with:
   the phase section from `10`, the named reference docs, and the current `STATUS.md`.
2. **Branch.** Executor creates `phase-<n>-<slug>` from `main`. One phase = one branch = one PR.
3. **Build.** Executor implements tasks. Keep changes within the phase's scope; if scope creep
   or a blocking ambiguity appears, **stop and escalate** to the orchestrator (don't guess on
   security, data-shape, or architecture).
4. **Self-verify.** Executor runs the full check suite (lint, typecheck, tests, and the phase's
   acceptance criteria) and writes the evidence into the PR description.
5. **Gate.** Run the phase's required gate:
   - UI phases → **Antigravity** review must pass.
   - Phase 3 → **human security** review must pass.
   - All phases → standard code review (orchestrator or a reviewer subagent).
6. **Integrate.** On green, merge to `main`. Migrations run in the deploy step (never
   destructive without an explicit reviewed plan).
7. **Record.** Update `STATUS.md` (what shipped + DoD evidence) and append any `Decision Log`
   entries in `01-architecture.md`. Then the next phase may start.

## Definition of Done (DoD) — universal

A phase is Done only when **all** hold:
- [ ] Every acceptance criterion in the phase's `10` section is demonstrably met (with evidence).
- [ ] `lint`, `typecheck`, and `test` are green across affected projects.
- [ ] New behavior has tests at the right layer (service tests for logic; router/contract tests
      for surfaces; the OAuth e2e for Phase 3).
- [ ] The required gate(s) passed and are recorded in the PR.
- [ ] `STATUS.md` updated; any decisions logged; no TODOs left that block the next phase.
- [ ] No secrets committed; `.env.example` updated if new env vars were introduced.

## STATUS.md (living state)

Create in Phase 0. One section per phase:
```
## Phase N — <title> — <NOT STARTED | IN PROGRESS | BLOCKED | DONE>
- Branch/PR: ...
- DoD evidence: <links to passing checks, test output, screenshots, connector proof>
- Notes / decisions: ...
```
The orchestrator treats `STATUS.md` as the source of truth for "where are we".

## Escalation rules (executor → orchestrator → human)

Stop and escalate — never silently decide — when you hit:
- Anything touching **security/auth** semantics (Phase 3, token handling, redirect validation).
- A change to the **data model**, a **public contract** (REST/MCP shape), or a **Decision Log** item.
- **Scope creep** beyond the phase, or a new dependency/service.
- A **destructive migration** or anything that could lose data.
- Ambiguity the docs don't resolve. (Propose options; let the orchestrator/human choose.)

## Guardrails (hard rules for every executor)

- **Keep REST and MCP in lockstep** — both call the same service; add/patch capabilities in
  both. Diverging them is a bug, caught by the contract test.
- **No business logic outside `services/`.** Routers/tools are thin adapters.
- **No blocking image generation in a request handler** beyond a single on-demand render;
  batch work is offline scripts.
- **Idempotent seeds/migrations**; safe to re-run.
- **Pooled vs unpooled** Neon URLs used correctly (app vs migrations/seed).
- **Tokens hashed at rest; PKCE mandatory; refresh rotation** — non-negotiable in Phase 3.
- **Tokens-only styling** and the motion rulebook in UI phases (`08`).
- **Don't build non-goals** (teams, billing, social, nutrition). Flag and stop.

## Parallelization

Where the dependency graph allows (see `10`), the orchestrator may run executors in parallel —
notably **Phase 4 (catalog/images)** alongside **Phase 2/3**, and starting **Phase 8** once
**Phase 6** lands. Each parallel track is still one branch/PR with its own DoD. Avoid parallel
edits to the same files across tracks; if unavoidable, isolate via worktrees.

## Review artifacts

- Every PR: description with the phase, the acceptance-criteria checklist (ticked, with
  evidence), and the gate results.
- Phase 3 PR additionally embeds the **filled-in `05` security checklist** with the human
  reviewer's sign-off.
- UI PRs embed the **Antigravity rubric** result and before/after captures of signature moments.

## First move for the orchestrator

1. Read `00`, `01`, `10`, `11`.
2. Confirm external prerequisites exist (Neon project, Google OAuth credentials, Vercel Blob,
   OpenAI key, domain) or list them as blockers for the human.
3. Start **Phase 0**.
