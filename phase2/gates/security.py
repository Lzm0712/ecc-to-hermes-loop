"""
Gate 5: Security

Runs pip-audit on requirements.txt / pyproject.toml dependencies,
and optionally semgrep on code patterns.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from . import GateInput, GateResult, GateStatus


def security_gate(input: GateInput) -> GateResult:
    """
    Gate 5 — Security: Dependency vulnerability and code-pattern scanning.
    """
    t0 = time.monotonic()
    all_messages: list[str] = []
    total_issues = 0

    # 1. pip-audit for dependency vulnerabilities
    pip_issues, pip_err = _run_pip_audit(input.project_root)
    if pip_err:
        all_messages.append(pip_err)
    else:
        total_issues += pip_issues
        if pip_issues > 0:
            all_messages.append(f"pip-audit: {pip_issues} vulnerability/vulnerabilities found")

    # 2. semgrep for dangerous patterns (optional)
    if shutil.which("semgrep"):
        semgrep_issues, semgrep_err = _run_semgrep(input.project_root, input.changed_files)
        if semgrep_err:
            all_messages.append(semgrep_err)
        else:
            total_issues += semgrep_issues
            if semgrep_issues > 0:
                all_messages.append(f"semgrep: {semgrep_issues} pattern(s) found")
    else:
        all_messages.append("semgrep not installed — skipping SAST scan")

    if total_issues == 0 and not all_messages:
        all_messages.append("No security scan tools available (pip-audit / semgrep)")

    status = GateStatus.FAIL if total_issues > 0 else GateStatus.PASS
    return GateResult(
        gate="security",
        status=status,
        messages=tuple(all_messages),
        duration_s=time.monotonic() - t0,
        metadata={"total_issues": total_issues},
    )


def _run_pip_audit(project_root: Path) -> tuple[int, str | None]:
    """
    Run pip-audit. Returns (issue_count, error_message).
    error_message is None on success, or a descriptive string on failure.
    """
    if not shutil.which("pip-audit"):
        return 0, None  # skip — tool not available

    # Determine dependency file
    dep_file: Path | None = None
    for name in ("requirements.txt", "pyproject.toml", "setup.py"):
        candidate = project_root / name
        if candidate.exists():
            dep_file = candidate
            break

    if not dep_file:
        return 0, None  # skip — no dep file

    try:
        result = subprocess.run(
            ["pip-audit", "-r", str(dep_file), "--format=grug", "--no-deprecated"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # pip-audit returns 0 (clean), 1 (vulns found), 2 (error)
        if result.returncode == 2:
            return 0, f"pip-audit usage error: {result.stderr[:200]}"
        output = result.stdout + result.stderr
        lines = [l for l in output.splitlines() if " Vuln " in l or "漏洞" in l]
        return len(lines), None
    except subprocess.TimeoutExpired:
        return 0, "pip-audit timed out after 120s"
    except Exception as e:
        return 0, f"pip-audit error: {e}"


def _run_semgrep(project_root: Path, changed_files: list[Path]) -> tuple[int, str | None]:
    """
    Run semgrep on changed files.
    Returns (issue_count, error_message). error_message is None on success.
    """
    if not changed_files:
        return 0, None

    py_files = [f for f in changed_files if f.suffix == ".py"]
    if not py_files:
        return 0, None

    try:
        result = subprocess.run(
            [
                "semgrep",
                "--config", "p/security-audit",
                "--no-git-ignore",
                "--json",
                "-f", ",".join(str(f) for f in py_files[:20]),
            ],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=120,
        )
        # Parse JSON output
        try:
            data = json.loads(result.stdout)
            findings = data.get("results", []) if isinstance(data, dict) else []
            return len(findings), None
        except (json.JSONDecodeError, ValueError):
            fallback = len([l for l in result.stderr.splitlines() if l.strip()]) if result.stderr else 0
            return fallback, f"semgrep returned non-JSON output ({fallback} issues in stderr)"
    except subprocess.TimeoutExpired:
        return 0, "semgrep timed out after 120s"
    except Exception as e:
        return 0, f"semgrep error: {e}"
