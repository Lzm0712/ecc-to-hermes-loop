"""
Phase 5: HUD Status Contract

Implements cross-harness portable state payload for `hermes status --json`.

The HUD (Heads-Up Display) Status Contract standardizes what a Hermes agent
exposes about its current state — enabling external harness tools (ECC,
cron jobs, dashboards, other agents) to query and act on agent state
without knowing implementation details.

Design goals:
- Self-contained JSON payload with versioned schema
- Zero coupling to internal data structures
- Works across different harness implementations (local dev, CI, production)
- Extensible via optional fields (hints forward-compatibility)
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path

# Ensure the project root is on sys.path before the `from shared.paths import` line below.
# __file__ at module level = /path/to/phaseN/script.py → parent.parent = project root.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from phase2.gates import VerificationReport

from shared.paths import HERMES_HOME, STATE_DB, SKILLS_DIR, ECC_LOOP_DIR
from shared.session_db import get_db

# ---------------------------------------------------------------------------
# Schema version — bump only on breaking changes
# ---------------------------------------------------------------------------

HUD_VERSION = "1.0.0"

# Confidence and health thresholds
MIN_CONFIDENCE = 0.70      # Minimum confidence to promote a skill pattern
HEALTHY_THRESHOLD = 0.60   # Fraction of phases passing for HEALTHY status

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

class LoopPhase(Enum):
    """ECC loop phases this agent has implemented."""
    PHASE1_HOOK = "phase1_hook"
    PHASE2_VERIFICATION = "phase2_verification"
    PHASE3_INSTINCT = "phase3_instinct"
    PHASE4_SUBAGENTS = "phase4_subagents"
    PHASE5_HUD = "phase5_hud"
    PHASE6_EVALUATOR_RAG = "phase6_evaluator_rag"

class VigilanceMode(Enum):
    """How aggressively the agent monitors itself."""
    PASSIVE = "passive"      # React only
    GUARDED = "guarded"      # Active on request
    VIGILANT = "vigilant"    # Continuous monitoring

# ---------------------------------------------------------------------------
# Dataclasses — all fields are JSON-serializable primitives
# ---------------------------------------------------------------------------

@dataclass
class TestStats:
    """Test execution statistics for a phase."""
    passed: int = 0
    failed: int = 0
    cached: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PhaseProgress:
    """Progress within a single ECC loop phase."""
    id: str              # phase identifier e.g. "phase5_hud"
    name: str            # human-readable name
    status: str          # "complete" | "in_progress" | "pending"
    completed_at: float | None = None   # unix timestamp
    artifacts: list[str] = field(default_factory=list)   # file paths produced
    test_stats: TestStats | None = None   # structured test results
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class RecentAction:
    """A recent agent action for HUD display."""
    timestamp: float     # unix timestamp
    action_type: str     # "tool_call" | "decision" | "verification" | "learning"
    description: str     # human-readable summary
    tool: str | None = None       # which tool was used
    outcome: str | None = None   # "success" | "failure" | "pending"
    duration_ms: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PendingTask:
    """A task awaiting action."""
    id: str
    description: str
    priority: str = "normal"   # "low" | "normal" | "high" | "critical"
    blocked_by: list[str] = field(default_factory=list)  # task IDs
    created_at: float = field(default_factory=lambda: time.time())
    phase: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InstinctStats:
    """Instinct Learning subsystem statistics."""
    skills_installed: int = 0
    high_confidence_count: int = 0
    last_extraction: float | None = None
    recent_promotions: int = 0   # since last status

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SubagentStats:
    """Subagent subsystem statistics."""
    roles_registered: int = 0
    roles_available: list[str] = field(default_factory=list)
    dispatches_total: int = 0
    dispatches_success: int = 0

    @property
    def success_rate(self) -> float:
        if self.dispatches_total == 0:
            return 0.0
        return self.dispatches_success / self.dispatches_total

    def to_dict(self) -> dict:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        return d


@dataclass
class VerificationCheck:
    """Single verification gate result — mirrors Phase2 GateResult structure."""
    gate_name: str      # "build" | "type" | "lint" | "test" | "security" | "diff"
    status: str         # "pass" | "fail" | "skip" | "warn"
    duration_s: float   # seconds (matches Phase2 GateResult.duration_s)
    messages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_gate_result(cls, r) -> "VerificationCheck":
        """Convert from Phase2 gates.GateResult."""
        return cls(
            gate_name=r.gate,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            duration_s=r.duration_s,
            messages=list(r.messages),
            metadata=r.metadata,
        )


@dataclass
class VerificationGate:
    """Status of a single verification gate."""
    name: str
    status: str          # "pass" | "fail" | "skip" | "not_run"
    duration_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationStats:
    """Verification Loop subsystem statistics."""
    last_run: float | None = None
    gates_passed: int = 0
    gates_failed: int = 0
    gates_skipped: int = 0
    last_error: str | None = None
    recent_gates: list[VerificationGate] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recent_gates"] = [g.to_dict() for g in self.recent_gates]
        return d


@dataclass
class HUDEvent:
    """A significant HUD event for event-sourced state tracking."""
    event_id: str
    timestamp: float
    phase: str
    event_type: str      # "phase_complete" | "verification_fail" | "skill_promoted" | "error"
    description: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# HUDStatus — the root state payload
# ---------------------------------------------------------------------------

@dataclass
class HUDStatus:
    """
    Root of the HUD Status Contract JSON payload.

    This is what `hermes status --json` returns — a portable,
    versioned, self-describing state snapshot.
    """
    # Schema identity
    version: str = HUD_VERSION
    generated_at: str = ""     # ISO 8601 string for JSON serializability
    agent_id: str = "hermes-default"

    # Identity
    health: str = HealthStatus.UNKNOWN.value
    vigilance_mode: str = VigilanceMode.GUARDED.value
    loop_phase: str = "phase5_hud"

    # Phases
    phases: list[PhaseProgress] = field(default_factory=list)
    current_phase: str = "phase5_hud"

    # Live data
    recent_actions: list[RecentAction] = field(default_factory=list)
    pending_tasks: list[PendingTask] = field(default_factory=list)
    recent_events: list[HUDEvent] = field(default_factory=list)

    # Subsystem stats
    instinct_stats: InstinctStats = field(default_factory=InstinctStats)
    subagent_stats: SubagentStats = field(default_factory=SubagentStats)
    verification_stats: VerificationStats = field(default_factory=VerificationStats)

    # Live verification gate results (Phase2 VerificationLoop output)
    checks: list[VerificationCheck] = field(default_factory=list)

    # Optional: hints for external consumers
    hints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "version": self.version,
            "generated_at": self.generated_at,
            "agent_id": self.agent_id,
            "health": self.health,
            "vigilance_mode": self.vigilance_mode,
            "loop_phase": self.loop_phase,
            "phases": [p.to_dict() for p in self.phases],
            "current_phase": self.current_phase,
            "recent_actions": [a.to_dict() for a in self.recent_actions],
            "pending_tasks": [t.to_dict() for t in self.pending_tasks],
            "recent_events": [e.to_dict() for e in self.recent_events],
            "instinct_stats": self.instinct_stats.to_dict(),
            "subagent_stats": self.subagent_stats.to_dict(),
            "verification_stats": self.verification_stats.to_dict(),
            "checks": [c.to_dict() for c in self.checks],
            "hints": self.hints,
        }
        return d

    def to_json(self, indent: bool = True) -> str:
        return json.dumps(self.to_dict(), indent=2 if indent else None, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> HUDStatus:
        """Reconstruct from a dict (e.g. when loading cached state)."""
        kwargs = dict(d)
        kwargs.pop("version", None)
        # Re-nest dataclasses
        if "instinct_stats" in kwargs:
            kwargs["instinct_stats"] = InstinctStats(**kwargs["instinct_stats"])
        if "subagent_stats" in kwargs:
            ss_data = kwargs.pop("subagent_stats")
            ss_data.pop("success_rate", None)  # computed field, not init arg
            kwargs["subagent_stats"] = SubagentStats(**ss_data)
        if "verification_stats" in kwargs:
            vs_data = kwargs.pop("verification_stats")
            vs_data["recent_gates"] = [VerificationGate(**g) for g in vs_data.get("recent_gates", [])]
            kwargs["verification_stats"] = VerificationStats(**vs_data)
        if "checks" in kwargs:
            kwargs["checks"] = [VerificationCheck(**c) for c in kwargs["checks"]]
        if "phases" in kwargs:
            kwargs["phases"] = [PhaseProgress(**p) for p in kwargs["phases"]]
        if "recent_actions" in kwargs:
            kwargs["recent_actions"] = [RecentAction(**a) for a in kwargs["recent_actions"]]
        if "pending_tasks" in kwargs:
            kwargs["pending_tasks"] = [PendingTask(**t) for t in kwargs["pending_tasks"]]
        if "recent_events" in kwargs:
            kwargs["recent_events"] = [HUDEvent(**e) for e in kwargs["recent_events"]]
        # Filter fields not accepted by HUDStatus.__init__
        import inspect
        init_params = set(inspect.signature(HUDStatus.__init__).parameters.keys()) - {"self"}
        kwargs = {k: v for k, v in kwargs.items() if k in init_params}
        return cls(**kwargs)

    @classmethod
    def from_json(cls, s: str) -> HUDStatus:
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# Data collection helpers
# -----------------------------------------------------------------------------

def get_recent_sessions(limit: int = 10) -> list[sqlite3.Row]:
    """Fetch most recent sessions for HUD recent_actions."""
    db = get_db()
    try:
        rows = db.execute("""
            SELECT id, title, source, started_at, tool_call_count
            FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return rows
    finally:
        db.close()


def get_session_action_summary(session_row: sqlite3.Row) -> RecentAction:
    """Build a RecentAction from a session row."""
    return RecentAction(
        timestamp=float(session_row[3]),
        action_type="session",
        description=f"Session: {session_row[1] or 'untitled'}",
        outcome="success",
    )


def count_skills_installed() -> tuple[int, int]:
    """Count total skills and high-confidence ones."""
    skill_dir = SKILLS_DIR
    if not skill_dir.exists():
        return 0, 0
    total = 0
    high_conf = 0
    for skill_path in skill_dir.rglob("SKILL.md"):
        total += 1
        content = skill_path.read_text(encoding="utf-8")
        if "confidence:" in content:
            try:
                for line in content.splitlines():
                    if line.strip().startswith("confidence:"):
                        val = float(line.split(":")[1].strip().rstrip("%"))
                        if val >= MIN_CONFIDENCE:
                            high_conf += 1
                        break
            except Exception:
                pass  # best-effort confidence scan
    return total, high_conf


def load_phase_progress() -> list[PhaseProgress]:
    """Load phase completion status from the ECC-to-Hermes loop workspace."""
    loop_dir = ECC_LOOP_DIR
    phases = []

    phase_map = {
        "phase1": ("phase1_hook", "PostToolUse Hook", ["hook_executor.py", "post_format.py", "post_lint.py"]),
        "phase2": ("phase2_verification", "Verification Loop", ["verification_loop.py", "gates/"]),
        "phase3": ("phase3_instinct", "Instinct Learning", ["instinct_learning.py"]),
        "phase4": ("phase4_subagents", "Professional Subagents", ["phase4.py", "agents/"]),
        "phase5": ("phase5_hud", "HUD Status Contract", ["phase5.py"]),
        "phase6": ("phase6_evaluator_rag", "Evaluator RAG", []),
    }

    for dir_name, (phase_id, name, expected_artifacts) in phase_map.items():
        phase_path = loop_dir / dir_name
        exists = phase_path.exists()

        status = "complete" if exists else "pending"

        # Check if test results exist
        test_stats: TestStats | None = None
        if exists:
            test_cache = phase_path / ".pytest_cache" / "v" / "cache" / "nodeids"
            if test_cache.exists():
                try:
                    content = test_cache.read_text(encoding="utf-8")
                    if content.strip():
                        count = len([l for l in content.strip().splitlines() if l.strip()])
                        test_stats = TestStats(passed=count, cached=True)
                except Exception as exc:
                    logging.warning(f"Failed to read test cache for {phase_id}: {exc}")

        phases.append(PhaseProgress(
            id=phase_id,
            name=name,
            status=status,
            completed_at=time.time() if status == "complete" else None,
            artifacts=[str(phase_path)] if exists else [],
            test_stats=test_stats,
        ))

    return phases


_VERIFICATION_CACHE: tuple["VerificationReport", float] | None = None
_VERIFICATION_CACHE_TTL = 3600  # 1 hour


def _get_verification_report() -> Optional["VerificationReport"]:
    """Run phase2 verification loop once, cache result for TTL seconds."""
    global _VERIFICATION_CACHE
    now = time.time()
    if _VERIFICATION_CACHE is not None:
        report, cached_at = _VERIFICATION_CACHE
        if now - cached_at < _VERIFICATION_CACHE_TTL:
            return report

    phase2_path = ECC_LOOP_DIR / "phase2"
    if not phase2_path.exists():
        return None
    try:
        sys.path.insert(0, str(phase2_path))
        from verification_loop import create_loop
        from gates import GateInput
        loop = create_loop(phase2_path)
        report = loop.run(GateInput(project_root=phase2_path, changed_files=[]))
        _VERIFICATION_CACHE = (report, now)
        return report
    except Exception:
        return None
    finally:
        if str(phase2_path) in sys.path:
            sys.path.remove(str(phase2_path))


def load_verification_stats() -> VerificationStats:
    """Load verification loop stats from phase2 (cached, TTL=1h)."""
    stats = VerificationStats()
    report = _get_verification_report()
    if report is None:
        return stats
    stats.gates_passed = sum(1 for r in report.results if r.passed)
    stats.gates_failed = sum(1 for r in report.results if not r.passed and r.status.value != "skip")
    stats.gates_skipped = sum(1 for r in report.results if r.status.value == "skip")
    stats.last_run = time.time()
    return stats


def load_verification_checks() -> list["VerificationCheck"]:
    """Load live verification gate results from Phase2 VerificationLoop (cached, TTL=1h)."""
    report = _get_verification_report()
    if report is None:
        return []
    return [VerificationCheck.from_gate_result(r) for r in report.results]


def load_subagent_stats() -> SubagentStats:
    """Load subagent stats from phase4."""
    stats = SubagentStats()
    phase4_path = ECC_LOOP_DIR / "phase4"

    if not phase4_path.exists():
        return stats

    # Import from phase4 if available
    try:
        sys.path.insert(0, str(phase4_path))
        import phase4 as p4
        roles = p4.list_agent_roles()
        stats.roles_registered = len(roles)
        stats.roles_available = roles  # list[str], not enum
    except Exception as exc:
        logging.debug(f"Could not load subagent stats: {exc}")
    finally:
        if str(phase4_path) in sys.path:
            sys.path.remove(str(phase4_path))

    return stats


def load_instinct_stats() -> InstinctStats:
    """Load instinct learning stats."""
    stats = InstinctStats()
    try:
        total, high_conf = count_skills_installed()
        stats.skills_installed = total
        stats.high_confidence_count = high_conf
    except Exception as exc:
        logging.debug(f"Could not load instinct stats: {exc}")

    # Find most recent instinct skill
    instinct_dir = SKILLS_DIR
    if instinct_dir.exists():
        mtimes = []
        for skill_path in (instinct_dir).rglob("SKILL.md"):
            if "instinct" in skill_path.parent.name.lower() or "instinct" in skill_path.read_text(encoding="utf-8").lower():
                mtimes.append(skill_path.stat().st_mtime)
        if mtimes:
            stats.last_extraction = max(mtimes)

    return stats


# ---------------------------------------------------------------------------
# HUD Status Builder
# ---------------------------------------------------------------------------

def build_hud_status(
    agent_id: str = "hermes-default",
    include_recent_actions: bool = True,
    include_events: bool = True,
    max_recent_actions: int = 10,
) -> HUDStatus:
    """
    Build a complete HUD status payload by querying all available data sources.

    This is the main entry point — call this to get a fresh HUD status snapshot.
    """
    # Load all subsystems
    phases = load_phase_progress()
    instinct_stats = load_instinct_stats()
    subagent_stats = load_subagent_stats()
    verification_stats = load_verification_stats()
    checks = load_verification_checks()

    # Recent actions from session history
    recent_actions: list[RecentAction] = []
    if include_recent_actions:
        try:
            sessions = get_recent_sessions(limit=max_recent_actions)
            for row in sessions:
                recent_actions.append(get_session_action_summary(row))
        except Exception as exc:
            logging.debug(f"Could not load recent sessions: {exc}")

    # Phase completion assessment
    completed_phases = sum(1 for p in phases if p.status == "complete")
    total_phases = len(phases)

    # Health: healthy if > 60% phases complete, degraded otherwise
    if completed_phases >= (total_phases * HEALTHY_THRESHOLD):
        health = HealthStatus.HEALTHY.value
    elif completed_phases > 0:
        health = HealthStatus.DEGRADED.value
    else:
        health = HealthStatus.UNKNOWN.value

    # Current phase: first non-complete phase
    current_phase = "phase6_evaluator_rag"
    for p in phases:
        if p.status != "complete":
            current_phase = p.id
            break

    # Build hints
    hints: dict[str, Any] = {
        "next_phase": current_phase,
        "completion": f"{completed_phases}/{total_phases} phases",
        "generated_by": "phase5_hud",
    }

    return HUDStatus(
        version=HUD_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        agent_id=agent_id,
        health=health,
        vigilance_mode=VigilanceMode.GUARDED.value,
        loop_phase=current_phase,
        phases=phases,
        current_phase=current_phase,
        recent_actions=recent_actions,
        pending_tasks=[],  # Would be populated by agent loop
        recent_events=[],  # Would be populated by event sourcing
        instinct_stats=instinct_stats,
        subagent_stats=subagent_stats,
        verification_stats=verification_stats,
        checks=checks,
        hints=hints,
    )


def export_hud_to_file(path: Path | str, status: HUDStatus | None = None) -> Path:
    """Export HUD status to a JSON file (for external consumers)."""
    if status is None:
        status = build_hud_status()
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(status.to_json(), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HUD Status Contract — Phase 5")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--export", metavar="PATH", help="Export status to file")
    parser.add_argument("--agent-id", default="hermes-default")
    args = parser.parse_args()

    status = build_hud_status(agent_id=args.agent_id)

    if args.export:
        path = export_hud_to_file(args.export, status)
        print(f"HUD status exported to {path}")
    elif args.json:
        print(status.to_json())
    else:
        # Human-readable summary
        print(f"HUD Status Contract v{status.version}")
        print(f"=" * 50)
        print(f"Agent: {status.agent_id}")
        print(f"Health: {status.health}")
        print(f"Current phase: {status.current_phase}")
        print(f"Loop completion: {status.hints.get('completion', 'unknown')}")
        print()
        print(f"Phases:")
        for p in status.phases:
            icon = "✅" if p.status == "complete" else "🔄" if p.status == "in_progress" else "⬜"
            print(f"  {icon} [{p.id}] {p.name} — {p.status}")
        print()
        print(f"Instinct: {status.instinct_stats.skills_installed} skills installed "
              f"({status.instinct_stats.high_confidence_count} high-confidence)")
        print(f"Subagents: {status.subagent_stats.roles_registered} roles registered")
        print(f"Verification: {status.verification_stats.gates_passed} gates passed, "
              f"{status.verification_stats.gates_failed} failed")
        print()
        print(f"Generated at: {status.generated_at}")
