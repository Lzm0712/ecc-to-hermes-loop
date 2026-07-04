"""
Phase 2: Verification Loop — 6-Stage Gate System

Gates: Build → Type → Lint → Test → Security → Diff

Each gate is a standalone, stateless function that returns a GateResult.
The VerificationLoop runner orchestrates sequential execution and aggregates results.

Architecture
------------
- GateFn:   Callable[[GateInput] -> GateResult]
- Gate:     NamedTuple with (name, description, gate_fn)
- GateResult: NamedTuple with (passed, messages, duration_s, metadata)
- VerificationLoop: Runs all gates in sequence, collects results
- Evaluator: Independent Ollama model assessment of gate results
  Three-state output: {ok: bool, reason: str, impossible: bool}
  - ok=true        → condition satisfied, goal achieved
  - ok=false       → not satisfied, continue iterating
  - ok=false+impossible=true → goal unreachable, stop immediately
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Result Types ────────────────────────────────────────────────────────────

class GateStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


@dataclass(frozen=True)
class GateResult:
    """Immutable result from a single gate execution."""
    gate: str
    status: GateStatus
    messages: tuple[str, ...] = ()
    duration_s: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status in (GateStatus.PASS, GateStatus.SKIP)


@dataclass
class VerificationReport:
    """Aggregated report from all gates."""
    results: list[GateResult] = field(default_factory=list)
    total_duration_s: float = 0.0

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        return f"{passed}/{total} gates passed"

    def as_dict(self) -> dict:
        return {
            "all_passed": self.all_passed,
            "summary": self.summary,
            "total_duration_s": round(self.total_duration_s, 3),
            "gates": [
                {
                    "gate": r.gate,
                    "status": r.status.value,
                    "passed": r.passed,
                    "messages": list(r.messages),
                    "duration_s": round(r.duration_s, 3),
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
        }


# ── Gate Input ──────────────────────────────────────────────────────────────

@dataclass
class GateInput:
    """
    Context passed to every gate function.
    All paths are absolute or resolved relative to project_root.
    """
    project_root: Path
    changed_files: list[Path] = field(default_factory=list)
    """Files modified in this cycle (build/type/lint/test targets these)."""

    diff_against: str = "HEAD"
    """Git ref to diff against (default: HEAD)."""

    goal: str | None = None
    """Optional goal string for independent evaluator assessment (Loop Engineering)."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Additional context (e.g. pr_number, branch_name)."""

    # Convenience accessors
    def changed_py_files(self) -> list[Path]:
        return [f for f in self.changed_files if f.suffix == ".py"]

    def changed_sh_files(self) -> list[Path]:
        return [f for f in self.changed_files if f.suffix in (".sh",)]

    def changed_js_files(self) -> list[Path]:
        return [f for f in self.changed_files if f.suffix in (".js", ".ts", ".jsx", ".tsx")]


# ── Gate Definition ─────────────────────────────────────────────────────────

GateFn = Callable[[GateInput], GateResult]


@dataclass
class Gate:
    name: str
    description: str
    fn: GateFn
    required: bool = True  # If False, failure is a WARN not a FAIL


# ── Verification Loop ────────────────────────────────────────────────────────

class VerificationLoop:
    """
    Orchestrates sequential execution of all 6 verification gates.

    Usage::

        loop = VerificationLoop(project_root=Path("/path/to/repo"))
        loop.add_gate(build_gate)
        loop.add_gate(type_gate)
        ...
        report = loop.run(changed_files=[...])
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._gates: list[Gate] = []

    def add_gate(self, gate: Gate) -> None:
        self._gates.append(gate)

    def run(self, input: GateInput) -> VerificationReport:
        """
        Execute all gates in sequence and return an aggregated report.
        Gates run even if earlier ones fail (full feedback).
        """
        report = VerificationReport()
        t0 = time.monotonic()

        for gate in self._gates:
            t_gate = time.monotonic()
            try:
                result = gate.fn(input)
            except Exception as exc:
                logger.exception("Gate '%s' raised unexpected exception", gate.name)
                result = GateResult(
                    gate=gate.name,
                    status=GateStatus.FAIL,
                    messages=(f"Gate crashed: {exc}",),
                )
            result = GateResult(
                gate=result.gate or gate.name,
                status=result.status,
                messages=result.messages,
                duration_s=time.monotonic() - t_gate,
                metadata=result.metadata,
            )
            report.results.append(result)

        report.total_duration_s = time.monotonic() - t0
        return report


# ── Independent Evaluator (Loop Engineering: Outer Loop Verify) ────────────────

EVALUATOR_MODEL = "llama3.2:3b"
EVALUATOR_TIMEOUT = 30  # seconds


@dataclass
class EvaluationResult:
    """
    Three-state result from the independent evaluator.

    ok=true              → condition satisfied, goal achieved
    ok=false             → not satisfied, continue iterating
    ok=false+impossible → goal unreachable, stop immediately
    """
    ok: bool
    reason: str
    impossible: bool = False


def evaluate_with_ollama(
    goal: str,
    gate_report: VerificationReport,
    *,
    model: str = EVALUATOR_MODEL,
    timeout: int = EVALUATOR_TIMEOUT,
) -> EvaluationResult:
    """
    Use an independent Ollama model to evaluate whether the verification goal is met.

    Uses a DIFFERENT inference call than the gate execution — pure adversarial verification.
    No tool calls, just reading the gate output and judging.
    """
    gate_summary = gate_report.summary
    gate_details = []
    for r in gate_report.results:
        icon = "✅" if r.passed else "❌"
        gate_details.append(f"  {icon} [{r.gate}] {r.status.value} ({r.duration_s:.1f}s)")
        for msg in r.messages:
            for line in msg.splitlines():
                gate_details.append(f"      {line}")
    gate_text = "\n".join(gate_details)

    prompt = f"""You are an independent evaluator. Judge whether the goal is satisfied.

Goal: {goal}

Gate results:
{gate_text}

Summary: {gate_summary}

Respond with ONLY a JSON object, no explanation:
{{"ok": true/false, "reason": "why", "impossible": true/false}}

Rules:
- ok=true if all required gates pass
- ok=false, impossible=true ONLY if the goal is logically impossible (e.g., requires files that don't exist)
- ok=false, impossible=false if gates failed but retry might help
- impossible=true is rare; prefer ok=false with a reason
"""

    try:
        result = subprocess.run(
            [
                "curl", "-s", "http://localhost:11434/api/generate",
                "-d", json.dumps({"model": model, "prompt": prompt, "stream": False}),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("Ollama curl failed: %s", result.stderr)
            return EvaluationResult(ok=False, reason=f"Ollama error: {result.stderr[:100]}", impossible=False)

        raw = json.loads(result.stdout).get("response", "")
        response_text = raw.strip()
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:]).strip()

        parsed = json.loads(response_text)
        return EvaluationResult(
            ok=bool(parsed.get("ok", False)),
            reason=str(parsed.get("reason", "evaluated")),
            impossible=bool(parsed.get("impossible", False)),
        )
    except subprocess.TimeoutExpired:
        logger.warning("Ollama evaluation timed out after %ds", timeout)
        return EvaluationResult(ok=False, reason=f"Evaluator timed out ({timeout}s)", impossible=False)
    except json.JSONDecodeError as exc:
        logger.warning("Evaluator returned invalid JSON: %s — %s", exc, response_text[:200])
        return EvaluationResult(ok=False, reason=f"Evaluator parse error: {exc}", impossible=False)
    except Exception as exc:
        logger.warning("Evaluator failed: %s", exc)
        return EvaluationResult(ok=False, reason=str(exc)[:100], impossible=False)


def evaluate_report(
    goal: str,
    report: VerificationReport,
) -> EvaluationResult:
    """
    Evaluate a VerificationReport against a goal string.

    If Ollama is available: uses independent Ollama model (true adversarial verification).
    If Ollama is unavailable: falls back to rule-based evaluation (ok = all_required_gates_passed).
    """
    return evaluate_with_ollama(goal, report)
