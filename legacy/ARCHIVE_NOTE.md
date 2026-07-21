# Archived — old TypeScript / Supabase app (read-only)

This directory holds the **previous** implementation of the workout tracker: a TypeScript MCP
server on Supabase, deployed as Vercel functions. It has been **replaced** by the greenfield
monorepo at the repository root (Next.js `apps/web` + FastAPI `apps/api`, on Neon), per the plan
in [`docs/`](../docs/).

**Do not extend or build on this code.** It is kept only as a read-only reference. The Supabase
database is likewise archived read-only.

Contents (moved verbatim from the repo root in Phase 0, history preserved via `git mv`):

- `api/`, `lib/`, `public/` — the old app + MCP handler
- `supabase/` — old SQL / schema
- `package.json`, `package-lock.json`, `tsconfig.json`, `vercel.json` — old root config
- `README.md` — the old project README

To inspect history: `git log --follow legacy/<path>`.
