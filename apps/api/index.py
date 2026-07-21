"""Vercel Python runtime entrypoint.

Vercel's Fluid Compute serves the ASGI ``app`` exported here. See docs/09-deployment-vercel.md.
"""

from __future__ import annotations

from app.main import app

__all__ = ["app"]
