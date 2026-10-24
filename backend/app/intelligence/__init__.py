"""Shared intelligence facade.

Single calculation path for both the public dashboard routes
(app/api/routers/coins.py) and the agent API (app/agentapi/routers.py).
Logic was extracted verbatim from the original coins router; response shapes
are unchanged.
"""

from app.intelligence import assets  # noqa: F401
