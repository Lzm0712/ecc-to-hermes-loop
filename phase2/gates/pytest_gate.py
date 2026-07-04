"""
Gate 4: Test

Discovers and runs pytest on the project.
Targets changed files' corresponding test modules when possible.
"""

from __future__ import annotations

# Prevent pytest from collecting this module's functions as tests
__all__ = []

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import GateInput, GateResult, GateStatus


def _find_test_for_source(source: Path, project_root: Path) -> Path | None:
    """
    Map a source file to its likely test file.
    Conventions: src/pkg/file.py → tests/pkg/test_file.py
                pkg/file.py   → tests/pkg/test_file.py
    """
    rel = source.relative_to(project_root)
    parts = list(rel.parts)

    if parts[0] in ("src", "packages"):
        # src/pkg/file.py → tests/pkg/test_file.py
        parts[0] = "tests"
    else:
        parts.insert(0, "tests")

    # file.py → test_file.py
    name = parts[-1]
    if not name.startswith("test_"):
        name = "test_" + name
    parts[-1] = name

    candidate = project_root.joinpath(*parts)
    return candidate if candidate.exists() else None


def execute_pytest_gate(ctx: GateInput) -> GateResult:
    """
    Gate 4 — Test: Run pytest on the project.

    Anti-recursion: uses a sentinel file (.pytest_gate.running) to prevent
    subprocess pytest from re-entering this gate.
    """
    t0 = time.monotonic()
    messages: list[str] = []

    # ── Anti-recursion guard ────────────────────────────────────────────
    # If the sentinel file exists, we're already inside pytest → skip
    phase2_dir = Path(__file__).parent.parent
    sentinel = phase2_dir / ".pytest_gate.running"
    if sentinel.exists():
        return GateResult(
            gate="test",
            status=GateStatus.SKIP,
            messages=("pytest gate: skipped (recursive guard)",),
            duration_s=time.monotonic() - t0,
        )

    targets: list[Path] = []

    for src in ctx.changed_py_files():
        test_file = _find_test_for_source(src, ctx.project_root)
        if test_file and test_file.exists() and test_file not in targets:
            targets.append(test_file)

    # If no targets found via mapping, fall back to changed files themselves
    if not targets:
        targets = ctx.changed_py_files()

    # Discover tests: prefer pytest
    pytest_cmd = _discover_test_command(ctx.project_root, targets)
    if not pytest_cmd:
        return GateResult(
            gate="test",
            status=GateStatus.SKIP,
            messages=("pytest not found",),
            duration_s=time.monotonic() - t0,
        )

    try:
        # Write sentinel BEFORE running pytest; remove after
        sentinel.write_text(str(os.getpid()))
        try:
            result = subprocess.run(
                pytest_cmd,
                capture_output=True,
                text=True,
                cwd=str(phase2_dir),
                timeout=300,
            )
            stdout = result.stdout
            stderr = result.stderr
        finally:
            sentinel.unlink(missing_ok=True)

        # Parse output for summary
        summary = _parse_pytest_summary(stdout + stderr)
        if summary:
            messages.append(summary)

        # Capture failures
        if result.returncode != 0:
            failure_lines = _parse_failures(stdout + stderr)
            if failure_lines:
                messages.extend(failure_lines[:15])

    except subprocess.TimeoutExpired:
        messages.append("pytest timed out after 300s")
        return GateResult(
            gate="test",
            status=GateStatus.WARN,
            messages=tuple(messages),
            duration_s=time.monotonic() - t0,
        )
    except Exception as exc:
        messages.append(f"pytest error: {exc}")
        return GateResult(
            gate="test",
            status=GateStatus.WARN,
            messages=tuple(messages),
            duration_s=time.monotonic() - t0,
        )

    status = GateStatus.FAIL if result.returncode != 0 else GateStatus.PASS
    return GateResult(
        gate="test",
        status=status,
        messages=tuple(messages),
        duration_s=time.monotonic() - t0,
        metadata={"returncode": result.returncode},
    )


def _discover_test_command(project_root: Path, targets: list[Path]) -> list[str]:
    """Return the best pytest command for the given targets."""
    # Use sys.executable to respect the active Python interpreter
    python_pytest = [sys.executable, "-m", "pytest"]
    args = python_pytest + ["-v", "--tb=short", "--color=no"]
    if targets:
        args.extend([str(t) for t in targets[:20]])  # cap at 20 targets
    else:
        # No targets: run the phase2 gate tests only (in phase2_dir context)
        args.append("test_gate.py")
    return args


def _parse_pytest_summary(output: str) -> str:
    """Extract a one-line summary from pytest output."""
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # pytest final summary line
        if " passed" in line or " failed" in line or " error" in line:
            return line
        # pytest version banner
        if line.startswith("=====") and "=====" in line[4:]:
            return line.strip()
    return ""


def _parse_failures(output: str) -> list[str]:
    """Extract FAILED lines from pytest output."""
    failures: list[str] = []
    for line in output.splitlines():
        if line.startswith("FAILED"):
            failures.append(line.strip())
    return failures
