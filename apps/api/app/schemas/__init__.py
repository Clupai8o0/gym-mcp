"""Pydantic v2 request/response schemas — the REST I/O boundary (docs/03).

Schemas validate inbound bodies and shape outbound JSON; they carry no DB access.
Response models read straight off ORM objects / service dataclasses via
``from_attributes`` (plus a few ``from_*`` classmethods for grouped shapes) so routers
stay one-liners.
"""
