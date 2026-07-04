"""
Phase 2: VerificationLoop — Main Entry Point

Wires together the 6-stage gate system and exposes a simple CLI/API.

Usage (Python)::

    from phase2.verification_loop import create_loop
    from phase2.gates import GateInput
    from pathlib import Path

    loop = create_loop(Path("/path/to/repo"))
    input = GateInput(project_root=Path("/path/to/repo"), changed_files=[...])
    report = loop.run(input)
    print(report.summary)
    print(report.as_dict())

Usage (CLI)::

    python -m phase2.verification_loop --root /path/to/repo --changed-file src/foo.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow `python verification_loop.py` (direct) to find gates/ as well as
# `python -m phase2.verification_loop` (module). The two execution modes set
# __spec__ differently; when it is None we are running directly.
if __name__ == "__main__" or (__spec__ is not None and __spec__.parent == ""):
    # Direct execution — add phase2/ to sys.path so `from gates import` works
    sys.path.insert(0, str(Path(__file__).parent))
    from gates import Gate, GateInput, GateStatus, VerificationLoop
    from gates.build import build_gate
    from gates.type import type_gate
    from gates.lint import lint_gate
    from gates.pytest_gate import execute_pytest_gate as _test_gate
    from gates.security import security_gate
    from gates.diff import diff_gate
else:
    # Module execution (pytest / -m) — use relative imports
    from .gates import Gate, GateInput, GateStatus, VerificationLoop
    from .gates.build import build_gate
    from .gates.type import type_gate
    from .gates.lint import lint_gate
    from .gates.pytest_gate import execute_pytest_gate as _test_gate
    from .gates.security import security_gate
    from .gates.diff import diff_gate

logger = logging.getLogger(__name__)


def create_loop(project_root: Path) -> VerificationLoop:
    """Build a VerificationLoop with all 6 gates registered."""
    loop = VerificationLoop(project_root)
    loop.add_gate(Gate(
        name="build",
        description="Compile Python files and run build system",
        fn=build_gate,
        required=True,
    ))
    loop.add_gate(Gate(
        name="type",
        description="Run mypy type checker",
        fn=type_gate,
        required=False,
    ))
    loop.add_gate(Gate(
        name="lint",
        description="Run ruff + shellcheck linters",
        fn=lint_gate,
        required=True,
    ))
    loop.add_gate(Gate(
        name="test",
        description="Run pytest test suite",
        fn=_test_gate,
        required=True,
    ))
    loop.add_gate(Gate(
        name="security",
        description="Run pip-audit + semgrep security scans",
        fn=security_gate,
        required=False,
    ))
    loop.add_gate(Gate(
        name="diff",
        description="Summarise changes vs HEAD",
        fn=diff_gate,
        required=False,
    ))
    return loop


def run(
    project_root: Path,
    changed_files: list[Path] | None = None,
    diff_against: str = "HEAD",
    goal: str | None = None,
    verbose: bool = False,
    json_output: bool = False,
) -> int:
    """
    Run the full verification loop and return exit code.
    Exit 0 = all required gates passed; Exit 1 = at least one required gate failed.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    input_ = GateInput(
        project_root=project_root,
        changed_files=changed_files or [],
        diff_against=diff_against,
        goal=goal,
    )

    loop = create_loop(project_root)
    report = loop.run(input_)

    # Independent evaluator assessment (Loop Engineering: outer loop verify)
    evaluator_result = None
    if json_output and input_.goal:
        from gates import evaluate_report
        evaluator_result = evaluate_report(input_.goal, report)

    if json_output:
        output = report.as_dict()
        if evaluator_result:
            output["evaluator"] = {
                "ok": evaluator_result.ok,
                "reason": evaluator_result.reason,
                "impossible": evaluator_result.impossible,
            }
        print(json.dumps(output, indent=2, default=str))
    else:
        _print_report(report)
        if evaluator_result:
            _print_evaluator(evaluator_result)

    # Determine exit code: fail if any required gate (required=True) failed
    required_failures = [
        r for r in report.results
        if not r.passed and any(g.required for g in loop._gates if g.name == r.gate)
    ]

    return 0 if not required_failures else 1


def _print_evaluator(result) -> None:
    """Print evaluator result in human-readable format."""
    if result.ok:
        icon = "✅"
    elif result.impossible:
        icon = "❌"
    else:
        icon = "🔄"
    print(f"\n{icon} [EVALUATOR] {result.reason}")


def _print_report(report) -> None:
    """Human-readable report output."""
    print("=" * 60)
    print("  Verification Loop — Phase 2")
    print("=" * 60)
    for result in report.results:
        icon = {
            GateStatus.PASS: "✅",
            GateStatus.FAIL: "❌",
            GateStatus.SKIP: "⏭",
            GateStatus.WARN: "⚠",
        }.get(result.status, "?")
        req_marker = ""
        print(f"\n{icon} [{result.gate.upper()}] {result.status.value.upper()} ({result.duration_s:.2f}s)")
        for msg in result.messages:
            for line in msg.splitlines():
                print(f"   {line}")
    print()
    print(f"  Total: {report.summary} in {report.total_duration_s:.2f}s")
    print("=" * 60)


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="ECC-to-Hermes Phase 2: Verification Loop")
    parser.add_argument("--root", type=Path, required=True, help="Project root directory")
    parser.add_argument("--changed-file", type=Path, action="append", dest="changed_files",
                        default=[], help="Changed file (repeatable)")
    parser.add_argument("--diff-against", default="HEAD", help="Git ref to diff against")
    parser.add_argument("--goal", default=None, help="Goal string for independent evaluator (Loop Engineering)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    return run(
        project_root=args.root,
        changed_files=args.changed_files,
        diff_against=args.diff_against,
        goal=args.goal,
        verbose=args.verbose,
        json_output=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
