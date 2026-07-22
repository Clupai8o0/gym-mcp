"""Service layer — the *only* place business logic and DB access live (docs/03).

Every service function takes ``db`` and ``user_id`` explicitly and imports no web
framework, so REST routers, MCP tools, and scripts can all reuse it unchanged. Domain
failures are raised as :class:`app.core.errors.ServiceError`.
"""
