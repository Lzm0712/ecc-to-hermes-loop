"""
Gate 3: Lint

Runs ruff on changed .py files (and optionally shellcheck on .sh files).
Replicates the Phase 1 post_lint hook but as a standalone gate.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import GateInput, GateResult, GateStatus


def lint_gate(input: GateInput) -> GateResult:
    """
    Gate 3 — Lint: Run ruff on .py files and shellcheck on .sh files.
    """
    t0 = time.monotonic()
    all_messages: list[str] = []

    py_files = input.changed_py_files()
    sh_files = input.changed_sh_files()

    if not py_files and not sh_files:
        return GateResult(
            gate="lint",
            status=GateStatus.SKIP,
            messages=("no .py or .sh files changed",),
            duration_s=time.monotonic() - t0,
        )

    total_issues = 0

    # ruff on .py files
    if py_files and shutil.which("ruff"):
        args = ["ruff", "check", "--output-format", "text"]
        args.extend([str(f) for f in py_files[:30]])
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=str(input.project_root),
                timeout=60,
            )
            output = result.stdout.strip() + result.stderr.strip()
            if output:
                lines = output.splitlines()
                total_issues += len(lines)
                all_messages.append(f"ruff ({len(lines)} issue(s)):")
                all_messages.extend(lines[:10])
                if len(lines) > 10:
                    all_messages.append(f"... and {len(lines) - 10} more")
        except subprocess.TimeoutExpired:
            all_messages.append("ruff timed out after 60s")
        except Exception as exc:
            all_messages.append(f"ruff error: {exc}")
    elif py_files:
        all_messages.append("ruff not installed — skipping Python lint")

    # shellcheck on .sh files
    if sh_files and shutil.which("shellcheck"):
        args = ["shellcheck", "-S", "warning", "-f", "text"]
        args.extend([str(f) for f in sh_files])
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip()
            if output:
                lines = output.splitlines()
                total_issues += len(lines)
                all_messages.append(f"shellcheck ({len(lines)} issue(s)):")
                all_messages.extend(lines[:10])
        except subprocess.TimeoutExpired:
            all_messages.append("shellcheck timed out after 30s")
        except Exception as exc:
            all_messages.append(f"shellcheck error: {exc}")
    elif sh_files:
        all_messages.append("shellcheck not installed — skipping shell lint")

    status = GateStatus.FAIL if total_issues > 0 else GateStatus.PASS
    return GateResult(
        gate="lint",
        status=status,
        messages=tuple(all_messages),
        duration_s=time.monotonic() - t0,
        metadata={"files_checked": len(py_files) + len(sh_files), "total_issues": total_issues},
    )
