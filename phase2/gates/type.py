"""
Gate 2: Type

Runs mypy on changed .py files to catch type errors.
Skips if mypy is not installed or no .py files changed.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import GateInput, GateResult, GateStatus


def type_gate(input: GateInput) -> GateResult:
    """
    Gate 2 — Type: Run mypy on changed Python files.
    """
    t0 = time.monotonic()
    messages: list[str] = []

    if not shutil.which("mypy"):
        return GateResult(
            gate="type",
            status=GateStatus.SKIP,
            messages=("mypy not installed",),
            duration_s=time.monotonic() - t0,
        )

    py_files = input.changed_py_files()
    if not py_files:
        return GateResult(
            gate="type",
            status=GateStatus.SKIP,
            messages=("no .py files changed",),
            duration_s=time.monotonic() - t0,
        )

    # Run mypy on changed files
    args = ["mypy", "--no-error-summary", "--output-format", "text"]
    # Use incremental cache if available
    if (input.project_root / ".mypy_cache").exists():
        args.append("--incremental")
    args.extend([str(f) for f in py_files[:30]])  # cap at 30 files

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=str(input.project_root),
            timeout=120,
        )
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        combined = "\n".join(filter(None, [stderr, stdout]))

        # mypy returns 0 on success, 1 on type errors, 2 on usage errors
        if result.returncode == 2:
            messages.append(f"mypy usage error:\n{combined[:500]}")
        elif result.returncode == 1:
            # Count error lines
            error_lines = [l for l in combined.splitlines() if ": error:" in l or ": note:" in l]
            messages.append(f"mypy found {len(error_lines)} issue(s):")
            messages.extend(error_lines[:10])
            if len(error_lines) > 10:
                messages.append(f"... and {len(error_lines) - 10} more")

        status = GateStatus.FAIL if result.returncode == 1 else GateStatus.PASS
    except subprocess.TimeoutExpired:
        messages.append("mypy timed out after 120s")
        status = GateStatus.WARN
    except Exception as exc:
        messages.append(f"mypy error: {exc}")
        status = GateStatus.WARN

    return GateResult(
        gate="type",
        status=status,
        messages=tuple(messages),
        duration_s=time.monotonic() - t0,
        metadata={"files_checked": len(py_files)},
    )
