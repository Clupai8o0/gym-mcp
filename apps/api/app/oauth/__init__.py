"""The OAuth 2.1 Authorization Server + resource-server guard (docs/05 Part B).

Kept deliberately import-light (no submodule imports here) so that ``app.api.deps`` can
import :mod:`app.oauth.resource` without pulling in the routers, which themselves import
``app.api.deps`` — avoiding an import cycle.
"""
