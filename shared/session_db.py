"""
Shared session database utilities.

Provides the canonical get_db() function used across all phases.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from shared.paths import STATE_DB


def get_db() -> sqlite3.Connection:
    """Return a connection to the Hermes session state DB."""
    return sqlite3.connect(str(STATE_DB), timeout=10)
