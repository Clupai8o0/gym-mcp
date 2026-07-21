# 00 — Product Overview

## What Tempo is

Tempo is a workout tracker with three tightly-integrated surfaces and one shared brain:

1. **Library** — a browsable catalog of ~800+ gym exercises, each with a consistent,
   minimal, AI-generated line-art illustration and structured metadata (muscles, equipment,
   mechanic, instructions).
2. **Log** — fast logging of workout sessions and sets, linked to catalog exercises, with
   automatic personal-record (PR) detection.
3. **Dashboard** — progress over time: PRs, training volume, session frequency, and the
   (secondary) calisthenics **skill-progression** tracker.

The same data and business logic are exposed through an **MCP server**, so a chat client
(Claude, ChatGPT, Claude Code) can do everything the UI can — "log today's push session,
3×5 bench at 80 kg" — over an authenticated **OAuth** connection.

> **One-line pitch:** *An illustrated exercise atlas and workout log you can drive from the
> web or from a chat, in perfect sync.*

## Who it's for

- **Primary user: the owner** (personal-first). One person's real training history.
- **Share-ready:** the architecture supports multiple real user accounts from day one
  (proper `users` table, per-user data isolation, OAuth), so inviting a few friends later is
  a config/marketing step, **not** a re-architecture.
- **Explicitly out of scope for v1:** teams/orgs, billing/subscriptions, social feed,
  coaching/marketplace features. Build seams for them; don't build them.

## Why rebuild (vs. extend the current MCP)

The current `gym-mcp` is a TypeScript-only MCP server on Supabase with free-text `user_id`
strings, API-key-in-URL auth, and a calisthenics-only, hardcoded domain. The new goals —
a real UI, a Python backend, a general-gym catalog with generated art, proper OAuth, and
Neon — touch every layer. A clean rescaffold is lower-risk than incremental surgery, and we
are deliberately taking a **greenfield database** (old Supabase archived read-only).

## Core user journeys (v1)

1. **Sign in** with Google (web) — one identity.
2. **Connect the chat client** once via OAuth ("Add Tempo as a connector"), then log/query by chat.
3. **Browse the library**, search/filter by muscle/equipment, open an exercise to see its
   illustration + how-to.
4. **Log a workout**: start a session, add exercises from the catalog, enter sets
   (weight/reps/hold/RPE); PRs are detected automatically.
5. **Review progress**: PRs per exercise, volume and frequency over a date range.
6. **(Secondary) Track a skill**: pick a calisthenics skill, set your current stage/%.

## What "done" looks like for v1

- A deployed web app at a custom domain with Google sign-in and all three surfaces working.
- A deployed MCP endpoint that connects as a **custom connector on claude.ai** via OAuth and
  can log/read workouts.
- ~800+ exercises imported, the large majority with a ready illustration; on-demand
  generation covers the rest and any user-created custom exercises.
- Everything running on Vercel (web + api) against Neon, with Blob-hosted images.

## Glossary

| Term | Meaning |
|---|---|
| **Session / workout session** | One training session on a date (e.g. "Upper — Tue"). Has many sets. |
| **Set** | One logged set of one exercise: weight_kg / reps / hold_seconds / RPE. |
| **Exercise (catalog)** | A global, shared movement definition (name, muscles, equipment, illustration). |
| **Custom exercise** | An exercise a user creates; same table, scoped to that user. |
| **PR (personal record)** | Best value for a (user, exercise, metric): heaviest weight, most reps, longest hold. |
| **Skill / skill progression** | A calisthenics goal (e.g. planche) with staged progress %. Secondary module. |
| **MCP** | Model Context Protocol — the chat-facing tool interface. |
| **AS** | OAuth 2.1 Authorization Server (we run our own, in FastAPI). |
| **PRM** | Protected Resource Metadata (RFC 9728) — how the MCP resource advertises its AS. |
| **Illustration** | The generated minimal line-art image for an exercise, stored in Vercel Blob. |
| **Seed job** | The offline Python script that imports the catalog and/or generates all illustrations. |

## Non-goals & guardrails (read before scoping any phase)

- **No new domains creep in.** If a phase wants to add nutrition, social, or coaching
  features, stop and flag it — it is out of scope.
- **No credential hand-rolling.** We hand-roll the OAuth *protocol server*, but **never**
  store passwords; end-user auth is Google OIDC. (See `05-auth-oauth.md`.)
- **No blocking image generation in request handlers.** Batch generation is offline;
  runtime only ever generates a *single* missing image, asynchronously where possible.
- **No secrets in the repo.** All secrets via Vercel env / local `.env` (gitignored).
- **Keep the MCP and REST in lockstep** — both call the same service functions so they can
  never drift. Adding a capability to one without the other is a bug.

## Open items to confirm before/around launch (non-blocking for the build)

- **Name/domain:** decided — **Tempo**, served at `tempo.clupai.com` (web) and
  `api.tempo.clupai.com` (api). As a personal project on your own domain, the "Tempo Fit"
  trademark is not a blocker; only revisit if you ever commercialize (fallbacks discussed:
  Cadence, Cadenza, Interval).
- **Units:** store canonical in **kg** and **seconds**; offer a lb display toggle in settings.
- **Illustration licensing:** images are AI-generated originals; record the model + prompt
  used for provenance (see `06-catalog-and-images.md`).
