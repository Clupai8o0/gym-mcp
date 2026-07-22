# scripts/ — offline jobs

Offline Python jobs that run **locally or in CI, never on Vercel** (they exceed the function
time limit and must not block request handlers). This is a self-contained `uv` project
(`pyproject.toml` + `uv.lock`); it imports the api's shared code (`app.services.*`, `app.models`,
`app.core`, `app.catalog`, `app.images`) via a `sys.path` shim to `../apps/api` — the same
"one Python brain" the REST/MCP surfaces use, so there is no duplicated logic here.

Both jobs are **idempotent** and safe to re-run, and both use the **unpooled** Neon URL
(`DATABASE_URL_UNPOOLED`) for bulk writes (never through PgBouncer). See
[`docs/06-catalog-and-images.md`](../docs/06-catalog-and-images.md).

Run from the repo root with the relevant env set (or a repo-root `.env`):

## `seed_catalog.py` — import the exercise catalog

Idempotent import of the pinned [free-exercise-db](https://github.com/yuhonas/free-exercise-db)
(Unlicense) → `exercises`. Upserts by `(source, source_id)`; a re-run of an unchanged dataset
changes nothing and preserves any generated art. Needs `DATABASE_URL_UNPOOLED`.

```bash
uv run --project scripts python scripts/seed_catalog.py                  # fetch the pinned SHA
uv run --project scripts python scripts/seed_catalog.py --source f.json  # a local file
uv run --project scripts python scripts/seed_catalog.py --ref <sha>      # a different ref
uv run --project scripts python scripts/seed_catalog.py --dry-run        # parse + validate only
```

## `generate_illustrations.py` — batch-generate line-art

Batch GPT Image 2 → Vercel Blob → `exercises.illustration_url`. Idempotent + resumable (only
`pending`/`failed` rows; `--retry-stale` also reclaims crashed `generating` rows); per-row commit
so Ctrl-C is safe. Emits a report (counts by status + estimated cost + failures). Needs
`DATABASE_URL_UNPOOLED`, `OPENAI_API_KEY`, `BLOB_READ_WRITE_TOKEN`. The per-image work is the
same `app.services.images.generate_and_store` the on-demand endpoint uses.

```bash
uv run --project scripts python scripts/generate_illustrations.py                 # full batch
uv run --project scripts python scripts/generate_illustrations.py --limit 20      # cap count
uv run --project scripts python scripts/generate_illustrations.py --concurrency 8
uv run --project scripts python scripts/generate_illustrations.py --retry-stale   # + generating
uv run --project scripts python scripts/generate_illustrations.py --exemplars ./out
#   ↑ generate the 5–8 style exemplars to ./out for the docs/06 design sign-off (no DB/Blob)
```

**Before the first live batch:** run `--exemplars`, get the design sign-off on the exemplars
(docs/06 reference-locking), and confirm the OpenAI Images + Vercel Blob HTTP contracts (the two
adapters in `apps/api/app/images/` note where to check).
