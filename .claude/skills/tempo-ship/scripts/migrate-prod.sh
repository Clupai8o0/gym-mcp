#!/bin/zsh
# Apply pending Alembic migrations to production Neon, taking the connection
# string from the macOS clipboard so it never appears in an argument, in the
# shell history, or in this session's transcript.
#
# Every line of output is passed through a redactor that rewrites anything
# looking like a postgres URL, because SQLAlchemy and asyncpg both put the DSN
# into their error messages.

set -o pipefail
# Resolve the repo from this script's own location: .claude/skills/tempo-ship/scripts/
REPO="${0:A:h}/../../../.."
cd "$REPO/apps/api" || { print "FAIL: cannot find apps/api from $REPO"; exit 1; }

redact() { sed -E 's#postgres(ql)?(\+[a-z]+)?://[^[:space:]"]*#postgresql://<redacted>#g'; }

URL="$(pbpaste 2>/dev/null | tr -d '[:space:]')"

# ---- validate shape before touching anything -------------------------------
if [[ -z "$URL" ]]; then
  print "FAIL: clipboard is empty."
  exit 1
fi
if [[ "$URL" != postgres://* && "$URL" != postgresql://* ]]; then
  print "FAIL: clipboard does not start with postgres:// or postgresql:// (length ${#URL})."
  print "      Copy the connection string itself, not the psql command around it."
  exit 1
fi
if [[ "$URL" != *"@"* ]]; then
  print "FAIL: no credentials/host separator in the URL."
  exit 1
fi
if [[ "$URL" == *-pooler* ]]; then
  print "FAIL: that is the POOLED host. Migrations need the direct/unpooled one"
  print "      (turn off 'Pooled connection' in Neon; the host has no -pooler)."
  exit 1
fi

print "Shape OK: length ${#URL}, direct host, credentials present."
print ""

export DATABASE_URL_UNPOOLED="$URL"
export DATABASE_URL="$URL"

print "=== alembic current (before) ==="
uv run alembic current 2>&1 | redact || exit 1

print ""
print "=== alembic upgrade head ==="
uv run alembic upgrade head 2>&1 | redact || exit 1

print ""
print "=== alembic current (after) ==="
uv run alembic current 2>&1 | redact

print ""
print "=== alembic check (drift) ==="
uv run alembic check 2>&1 | redact

unset URL DATABASE_URL DATABASE_URL_UNPOOLED
