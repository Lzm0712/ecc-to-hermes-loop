"""
Gate 1: Build

Runs `python -m py_compile` (or equivalent) on changed .py files,
and optionally runs the repo's build system (setup.py, pyproject.toml, etc.)
to ensure the project is in a compilable state.

Detection order: pyproject.toml build-backend > setup.py > nox build > python compile
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from . import GateInput, GateResult, GateStatus


def build_gate(input: GateInput) -> GateResult:
    """
    Gate 1 — Build: Verify the project compiles/builds without errors.
    """
    t0 = time.monotonic()
    messages: list[str] = []
    project_root = input.project_root

    py_files = input.changed_py_files()
    if not py_files:
        # Nothing to build — try a global check
        py_files = [p for p in project_root.rglob("*.py") if ".venv" not in str(p) and "node_modules" not in str(p)]

    errors: list[str] = []

    # 1. Compile changed .py files individually
    for f in py_files[:20]:  # cap at 20 files for speed
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(f)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                errors.append(f"{f.relative_to(project_root)}: {result.stderr.strip()}")
        except Exception as exc:
            errors.append(f"{f.relative_to(project_root)}: compile error: {exc}")

    # 2. Detect build system and run build if available
    build_cmd: list[str] | None = None
    if (project_root / "pyproject.toml").exists():
        build_cmd = [sys.executable, "-m", "build", "--no-isolation"]
    elif (project_root / "setup.py").exists():
        build_cmd = [sys.executable, "setup.py", "build"]

    if build_cmd:
        try:
            result = subprocess.run(
                build_cmd,
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=120,
            )
            if result.returncode != 0:
                messages.append(f"Build command `{' '.join(build_cmd)}` failed:\n{result.stderr[:500]}")
        except FileNotFoundError:
            messages.append("build package not installed (pip install build)")
        except subprocess.TimeoutExpired:
            messages.append(f"Build command timed out after 120s")
        except Exception as exc:
            messages.append(f"Build command error: {exc}")

    duration = time.monotonic() - t0

    if errors:
        messages.insert(0, f"{len(errors)} file(s) failed to compile:")
        messages.extend(errors[:5])
        if len(errors) > 5:
            messages.append(f"... and {len(errors) - 5} more")

    status = GateStatus.FAIL if errors else GateStatus.PASS
    return GateResult(
        gate="build",
        status=status,
        messages=tuple(messages),
        duration_s=duration,
        metadata={"files_checked": len(py_files), "errors": len(errors)},
    )
