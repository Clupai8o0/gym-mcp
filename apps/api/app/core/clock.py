"""Time helpers shared by the services.

One rule, applied everywhere: **instants are aware and stored in UTC**. The columns are all
``timestamptz``, so a value read back from Postgres is always aware — but a value that just
arrived from a client may not be. MCP tools take whatever their caller's JSON carried, and a
bare ``2026-06-01T12:00:00`` parses to a naive ``datetime``. Comparing that to an aware
``now()`` raises ``TypeError`` deep inside a service rather than failing as validation, so
input is normalized at the edge of the domain instead.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(moment: datetime) -> datetime:
    """Return ``moment`` as an aware UTC instant, reading a naive value as UTC.

    UTC is the only defensible reading of a bare timestamp here: the column it is going into is
    ``timestamptz``, and every instant the app produces itself is already UTC.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def now() -> datetime:
    """The current instant, aware, in UTC. A seam for tests that need to pin the clock."""
    return datetime.now(tz=UTC)
