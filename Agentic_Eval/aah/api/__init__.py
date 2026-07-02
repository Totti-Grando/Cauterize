"""HTTP API layer that exposes the aah engine to the Possible_UI frontend.

``server.py`` is a FastAPI app serving ``/api/*`` on :8000 (matching the Vite proxy).
``scenario.py`` runs the real Layer A pipeline offline (deterministic fixtures, no keys)
so the whole UI works end-to-end; ``adapter.py`` maps the engine's AuditRecord onto the
shapes the React pages consume. Swapping the offline scenario for a live run (real
providers/LLMs) is a localized change behind these same seams.
"""
