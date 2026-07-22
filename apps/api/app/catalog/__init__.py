"""Exercise-catalog source adapters (docs/06).

Framework-free, DB-free I/O + validation for the free-exercise-db dataset. The *import*
(DB upsert) is a service (``app/services/catalog.py``); this package only fetches, validates,
and normalizes records into the DTO that service consumes. Held to the "no DB in adapters"
guard (tests/test_architecture.py).
"""
