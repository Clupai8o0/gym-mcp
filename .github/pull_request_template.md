<!--
One PR per execution phase (see docs/11-agent-workflow.md).
Branch: phase-<n>-<slug>  ·  Title: Conventional Commit style.
-->

## Phase / scope

<!-- e.g. "Phase 0 — Repo & tooling foundation". Link the section in docs/10-execution-plan.md. -->

## What shipped

<!-- Short summary of the changes. -->

## Acceptance criteria

<!-- Copy the phase's acceptance criteria from docs/10 and tick each with evidence. -->

- [ ] Criterion 1 — _evidence:_
- [ ] Criterion 2 — _evidence:_

## Definition of Done (docs/11)

- [ ] Acceptance criteria demonstrably met (evidence above)
- [ ] `lint`, `typecheck`, `test`, `build` green across affected projects
- [ ] New behavior has tests at the right layer
- [ ] Required gate(s) passed and recorded below
- [ ] `docs/STATUS.md` updated; decisions logged in `docs/01`; no blocking TODOs
- [ ] No secrets committed; `.env.example` updated if new env vars were introduced

## Gate results

<!--
- Standard review: reviewer + result
- UI phases (6–9): Antigravity rubric result + before/after captures
- Phase 3: filled-in docs/05 security checklist + HUMAN sign-off
-->
