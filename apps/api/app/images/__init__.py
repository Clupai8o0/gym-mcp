"""Illustration I/O adapters (docs/06).

Framework-free, DB-free boundaries for the illustration pipeline: the locked prompt
(``prompt``), cost estimation (``cost``), the OpenAI GPT Image 2 call (``openai_images``), and
the Vercel Blob upload (``blob``). Orchestration + persistence is a service
(``app/services/images.py``). Held to the "no DB in adapters" guard
(tests/test_architecture.py); the network boundaries are stubbed in tests.
"""
