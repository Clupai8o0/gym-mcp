"""Guardrail: no business logic / direct DB access in routers (docs/03, docs/11).

Routers must be thin adapters — resolve deps, call one service, shape output. This greps
every router module for SQLAlchemy query building or ORM writes; the only DB touch allowed
is the ``AsyncSession`` type import and passing ``db`` through to a service.
"""

from __future__ import annotations

import re
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_ROUTERS_DIR = _APP_DIR / "api" / "routers"
# The adapter packages are held to the same rule as routers: thin adapters that call services
# — never build queries or touch the DB directly. Phase 3 added auth/OAuth/MCP; Phase 4 added
# the catalog (dataset I/O) and images (OpenAI/Blob/prompt) adapters.
_ADAPTER_DIRS = (
    _APP_DIR / "auth",
    _APP_DIR / "oauth",
    _APP_DIR / "mcp",
    _APP_DIR / "catalog",
    _APP_DIR / "images",
)

# Patterns that signal an adapter is doing the DB's / a service's job.
_FORBIDDEN = {
    "sqlalchemy core import": re.compile(r"^from sqlalchemy import ", re.MULTILINE),
    "bare sqlalchemy import": re.compile(r"^import sqlalchemy\b", re.MULTILINE),
    "query execution": re.compile(r"\.execute\("),
    "select() query building": re.compile(r"\bselect\("),
    "ORM add": re.compile(r"\.add\("),
    "manual flush": re.compile(r"\.flush\("),
    "manual commit": re.compile(r"\.commit\("),
}


def _py_files(directory: Path) -> list[Path]:
    return [p for p in directory.glob("*.py") if p.name != "__init__.py"]


def _scan(directory: Path) -> list[str]:
    offenders: list[str] = []
    for path in _py_files(directory):
        source = path.read_text()
        for label, pattern in _FORBIDDEN.items():
            if pattern.search(source):
                offenders.append(f"{path.relative_to(_APP_DIR)}: {label}")
    return offenders


def test_routers_exist() -> None:
    assert _py_files(_ROUTERS_DIR), "expected router modules under app/api/routers"


def test_no_db_access_in_routers() -> None:
    offenders = _scan(_ROUTERS_DIR)
    assert not offenders, "business logic / DB access leaked into routers:\n" + "\n".join(offenders)


def test_no_db_access_in_adapters() -> None:
    offenders: list[str] = []
    for directory in _ADAPTER_DIRS:
        offenders.extend(_scan(directory))
    assert not offenders, "DB access leaked into an adapter package:\n" + "\n".join(offenders)
