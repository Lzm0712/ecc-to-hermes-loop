"""
conftest.py — pytest configuration and shared fixtures for Phase 2 tests.

NOTE: Gate imports are kept OUTSIDE this file to prevent pytest from
collecting gate functions as test items during module scan.
Gate functions are imported directly in test_gates.py instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root (parent of phase2/) is on sys.path so that
# `from gates import ...` resolves to the `phase2/gates/` subpackage.
# Using parent.parent to go from conftest.py → phase2/ → project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture
def project_root():
    return Path(__file__).parent


@pytest.fixture
def gate_input(project_root):
    from gates import GateInput
    return GateInput(
        project_root=project_root,
        changed_files=[],
        diff_against="HEAD",
    )


@pytest.fixture
def loop(project_root):
    # Import here so pytest never loads gates.pytest_gate during collection
    from verification_loop import create_loop
    return create_loop(project_root)
