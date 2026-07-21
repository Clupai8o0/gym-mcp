# scripts/ — offline jobs

Offline Python jobs that run **locally or in CI, never on Vercel** (they exceed the function
time limit and must not block request handlers). Managed by `uv` (their own `pyproject.toml`
lands with the first script).

Planned (Phase 4 — see [`docs/06-catalog-and-images.md`](../docs/06-catalog-and-images.md)):

- `seed_catalog.py` — idempotent import of the pinned free-exercise-db → Neon `exercises`.
- `generate_illustrations.py` — batch GPT Image 2 → Vercel Blob → `exercises.illustration_url`
  (idempotent, resumable, cost-reporting).

Both must be **idempotent** and use the **unpooled** Neon URL for DDL/bulk work.
