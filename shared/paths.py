"""
Shared path constants for ECC-to-Hermes Loop.

All phase modules should import from here instead of redefining
HERMES_HOME / STATE_DB / SKILLS_DIR locally.

Version: 1.0.0
"""
from __future__ import annotations

import os
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
STATE_DB = HERMES_HOME / "state.db"
SKILLS_DIR = HERMES_HOME / "skills"

# Derive ECC_LOOP_DIR from this file's location: shared/paths.py → shared/ → project root
ECC_LOOP_DIR = Path(__file__).resolve().parent.parent


def ensure_sys_path() -> None:
    """
    Ensure ecc-to-hermes-loop is on sys.path for all phase modules.

    Idempotent — safe to call multiple times.

    Handles all calling conventions:
      python3 phase3/instinct_learning.py   → script dir = phase3/, parent has shared/ → use project root
      python3 -m phase3.instinct_learning   → project root already on sys.path via -m
      ecc-loop p3                            → same as above
    """
    import sys as _sys

    # Fast path: project root already on sys.path
    if str(ECC_LOOP_DIR) in _sys.path:
        return

    # Look for the first sys.path entry that has shared/ as a subdirectory.
    #
    # Two patterns to handle:
    # 1. `python3 script.py` from project root:
    #      sys.path[0] = '' (CWD = project root), check candidate/shared ✓
    # 2. `python3 phase3/script.py` from project root:
    #      sys.path[0] = 'phase3/' (script's dir), check candidate/shared ✗
    #      but candidate.parent ('phase3/..' = project root)/shared ✓
    for _entry in _sys.path:
        _candidate = Path(_entry) if _entry else Path.cwd()
        # Walk up from this entry: check this dir and its parents for shared/
        # When running `python3 phase3/script.py`, sys.path[0] = 'phase3/',
        # so we need to walk up to find the project root that has shared/.
        _scan: Path | None = _candidate
        while _scan != _scan.parent:
            if (_scan / "shared").is_dir():
                if str(_scan) not in _sys.path:
                    _sys.path.insert(0, str(_scan))
                return
            _scan = _scan.parent

