"""Guardrail: no business logic / direct DB access in routers (docs/03, docs/11).

Routers must be thin adapters — resolve deps, call one service, shape output. This greps
every router module for SQLAlchemy query building or ORM writes; the only DB touch allowed
is the ``AsyncSession`` type import and passing ``db`` through to a service.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROUTERS_DIR = Path(__file__).resolve().parent.parent / "app" / "api" / "routers"

# Patterns that signal a router is doing the DB's / a service's job.
_FORBIDDEN = {
    "sqlalchemy core import": re.compile(r"^from sqlalchemy import ", re.MULTILINE),
    "bare sqlalchemy import": re.compile(r"^import sqlalchemy\b", re.MULTILINE),
    "query execution": re.compile(r"\.execute\("),
    "select() query building": re.compile(r"\bselect\("),
    "ORM add": re.compile(r"\.add\("),
    "manual flush": re.compile(r"\.flush\("),
    "manual commit": re.compile(r"\.commit\("),
}


def _router_files() -> list[Path]:
    return [p for p in _ROUTERS_DIR.glob("*.py") if p.name != "__init__.py"]


def test_routers_exist() -> None:
    assert _router_files(), "expected router modules under app/api/routers"


def test_no_db_access_in_routers() -> None:
    offenders: list[str] = []
    for path in _router_files():
        source = path.read_text()
        for label, pattern in _FORBIDDEN.items():
            if pattern.search(source):
                offenders.append(f"{path.name}: {label}")
    assert not offenders, "business logic / DB access leaked into routers:\n" + "\n".join(offenders)
