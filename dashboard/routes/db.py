"""Database access for dashboard routes.

Re-exports from dashboard.db so both app.py and route modules
can import from their natural locations without duplication.
"""
from dashboard.db import is_configured, query  # noqa: F401
