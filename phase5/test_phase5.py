"""
Phase 5: HUD Status Contract — Tests

Tests the HUD status payload schema, serialization, and builder logic.
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure phase5 is importable
sys.path.insert(0, str(Path(__file__).parent))

import phase5 as p5


class TestHUDVersion:
    """Schema version is consistent."""

    def test_version_is_semver_string(self):
        assert p5.HUD_VERSION == "1.0.0"
        assert isinstance(p5.HUD_VERSION, str)

    def test_version_in_status(self):
        status = p5.build_hud_status()
        assert status.version == p5.HUD_VERSION


class TestHUDStatusDataclass:
    """HUDStatus dataclass roundtrips correctly."""

    def test_to_dict_contains_all_required_keys(self):
        status = p5.HUDStatus()
        d = status.to_dict()
        required = [
            "version", "generated_at", "agent_id",
            "health", "vigilance_mode", "loop_phase",
            "phases", "current_phase",
            "recent_actions", "pending_tasks", "recent_events",
            "instinct_stats", "subagent_stats", "verification_stats",
            "hints",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_to_json_produces_valid_json(self):
        status = p5.HUDStatus()
        s = status.to_json()
        parsed = json.loads(s)
        assert parsed["version"] == p5.HUD_VERSION

    def test_from_json_roundtrip(self):
        original = p5.build_hud_status()
        json_str = original.to_json()
        restored = p5.HUDStatus.from_json(json_str)
        assert restored.version == original.version
        assert restored.agent_id == original.agent_id
        assert restored.health == original.health

    def test_from_dict_roundtrip(self):
        original = p5.build_hud_status()
        d = original.to_dict()
        restored = p5.HUDStatus.from_dict(d)
        assert restored.version == original.version
        assert restored.loop_phase == original.loop_phase


class TestStats:
    """TestStats dataclass (R7 structured test results)."""

    def test_test_stats_defaults(self):
        ts = p5.TestStats()
        assert ts.passed == 0
        assert ts.failed == 0
        assert ts.cached is False

    def test_test_stats_to_dict(self):
        ts = p5.TestStats(passed=32, failed=1, cached=True)
        d = ts.to_dict()
        assert d["passed"] == 32
        assert d["failed"] == 1
        assert d["cached"] is True

    def test_test_stats_cached_flag(self):
        ts = p5.TestStats(passed=10, cached=True)
        assert ts.cached is True
        ts2 = p5.TestStats(passed=10, cached=False)
        assert ts2.cached is False

    def test_test_stats_failed_count(self):
        ts = p5.TestStats(passed=25, failed=3, cached=False)
        assert ts.failed == 3
        assert ts.passed == 25


class TestPhaseProgress:
    """PhaseProgress dataclass."""

    def test_phase_progress_to_dict(self):
        pp = p5.PhaseProgress(
            id="phase5_hud",
            name="HUD Status Contract",
            status="complete",
            completed_at=1234567890.0,
            artifacts=["phase5.py"],
            test_stats=p5.TestStats(passed=10, cached=True),
            notes=["v1 implemented"],
        )
        d = pp.to_dict()
        assert d["id"] == "phase5_hud"
        assert d["status"] == "complete"
        assert d["completed_at"] == 1234567890.0
        assert "phase5.py" in d["artifacts"]

    def test_phase_progress_defaults(self):
        pp = p5.PhaseProgress(id="phase1_hook", name="Hook", status="pending")
        assert pp.completed_at is None
        assert pp.artifacts == []
        assert pp.test_stats is None


class TestRecentAction:
    """RecentAction dataclass."""

    def test_recent_action_required_fields(self):
        ra = p5.RecentAction(
            timestamp=1234567890.0,
            action_type="tool_call",
            description="patch applied",
            tool="patch",
            outcome="success",
            duration_ms=150,
        )
        d = ra.to_dict()
        assert d["timestamp"] == 1234567890.0
        assert d["action_type"] == "tool_call"
        assert d["tool"] == "patch"
        assert d["outcome"] == "success"
        assert d["duration_ms"] == 150


class TestPendingTask:
    """PendingTask dataclass."""

    def test_pending_task_defaults(self):
        pt = p5.PendingTask(id="task1", description="Fix bug")
        assert pt.priority == "normal"
        assert pt.blocked_by == []
        assert pt.phase == "unknown"

    def test_pending_task_blocked_by(self):
        pt = p5.PendingTask(
            id="task2",
            description="Deploy",
            blocked_by=["task1", "task3"],
        )
        assert len(pt.blocked_by) == 2


class TestInstinctStats:
    """InstinctStats dataclass."""

    def test_instinct_stats_defaults(self):
        stats = p5.InstinctStats()
        assert stats.skills_installed == 0
        assert stats.high_confidence_count == 0
        assert stats.last_extraction is None
        assert stats.recent_promotions == 0

    def test_instinct_stats_to_dict(self):
        stats = p5.InstinctStats(skills_installed=21, high_confidence_count=18)
        d = stats.to_dict()
        assert d["skills_installed"] == 21
        assert d["high_confidence_count"] == 18


class TestSubagentStats:
    """SubagentStats dataclass."""

    def test_subagent_stats_defaults(self):
        stats = p5.SubagentStats()
        assert stats.roles_registered == 0
        assert stats.roles_available == []
        assert stats.dispatches_total == 0

    def test_success_rate_zero_when_no_dispatches(self):
        stats = p5.SubagentStats()
        assert stats.success_rate == 0.0

    def test_success_rate_calculation(self):
        stats = p5.SubagentStats(dispatches_total=10, dispatches_success=7)
        assert abs(stats.success_rate - 0.7) < 0.001

    def test_subagent_stats_to_dict(self):
        stats = p5.SubagentStats(roles_registered=4, dispatches_total=5, dispatches_success=5)
        d = stats.to_dict()
        assert d["roles_registered"] == 4
        assert d["success_rate"] == 1.0


class TestVerificationStats:
    """VerificationStats dataclass."""

    def test_verification_stats_defaults(self):
        stats = p5.VerificationStats()
        assert stats.gates_passed == 0
        assert stats.gates_failed == 0
        assert stats.gates_skipped == 0
        assert stats.last_error is None

    def test_recent_gates_to_dict(self):
        gate = p5.VerificationGate(name="lint", status="pass", duration_ms=200)
        stats = p5.VerificationStats(recent_gates=[gate])
        d = stats.to_dict()
        assert len(d["recent_gates"]) == 1
        assert d["recent_gates"][0]["name"] == "lint"


class TestHUDEvent:
    """HUDEvent dataclass."""

    def test_hud_event_to_dict(self):
        event = p5.HUDEvent(
            event_id="evt1",
            timestamp=1234567890.0,
            phase="phase5_hud",
            event_type="phase_complete",
            description="Phase 5 complete",
            data={"tests_passed": 10},
        )
        d = event.to_dict()
        assert d["event_id"] == "evt1"
        assert d["phase"] == "phase5_hud"
        assert d["data"]["tests_passed"] == 10


class TestHealthStatus:
    """HealthStatus enum."""

    def test_health_status_values(self):
        assert p5.HealthStatus.HEALTHY.value == "healthy"
        assert p5.HealthStatus.DEGRADED.value == "degraded"
        assert p5.HealthStatus.UNKNOWN.value == "unknown"


class TestLoopPhase:
    """LoopPhase enum."""

    def test_all_phases_present(self):
        expected = [
            "phase1_hook", "phase2_verification", "phase3_instinct",
            "phase4_subagents", "phase5_hud", "phase6_evaluator_rag",
        ]
        actual = [p.value for p in p5.LoopPhase]
        for e in expected:
            assert e in actual, f"Missing phase: {e}"


class TestVigilanceMode:
    """VigilanceMode enum."""

    def test_vigilance_modes(self):
        assert p5.VigilanceMode.PASSIVE.value == "passive"
        assert p5.VigilanceMode.GUARDED.value == "guarded"
        assert p5.VigilanceMode.VIGILANT.value == "vigilant"


class TestBuildHUDStatus:
    """build_hud_status() integration."""

    def test_build_returns_hud_status(self):
        status = p5.build_hud_status()
        assert isinstance(status, p5.HUDStatus)

    def test_phases_are_loaded(self):
        status = p5.build_hud_status()
        assert len(status.phases) == 6
        phase_ids = [p.id for p in status.phases]
        assert "phase1_hook" in phase_ids
        assert "phase5_hud" in phase_ids

    def test_current_phase_is_first_incomplete(self):
        status = p5.build_hud_status()
        # All phases except phase6 should be complete (they exist as dirs)
        assert status.current_phase == "phase6_evaluator_rag"

    def test_health_assessed(self):
        status = p5.build_hud_status()
        assert status.health in ["healthy", "degraded", "unknown"]

    def test_instinct_stats_populated(self):
        status = p5.build_hud_status()
        assert isinstance(status.instinct_stats, p5.InstinctStats)
        assert isinstance(status.instinct_stats.skills_installed, int)

    def test_subagent_stats_populated(self):
        status = p5.build_hud_status()
        assert isinstance(status.subagent_stats, p5.SubagentStats)
        assert status.subagent_stats.roles_registered >= 0

    def test_verification_stats_populated(self):
        status = p5.build_hud_status()
        assert isinstance(status.verification_stats, p5.VerificationStats)

    def test_hints_contain_next_phase(self):
        status = p5.build_hud_status()
        assert "next_phase" in status.hints
        assert "completion" in status.hints

    def test_agent_id_customizable(self):
        status = p5.build_hud_status(agent_id="test-agent")
        assert status.agent_id == "test-agent"

    def test_generated_at_is_iso8601_string(self):
        from datetime import datetime
        status = p5.build_hud_status()
        # generated_at must be an ISO 8601 string, not a Unix timestamp float
        assert isinstance(status.generated_at, str), f"expected str, got {type(status.generated_at).__name__}"
        # Must parse without error
        parsed = datetime.fromisoformat(status.generated_at)
        assert parsed.year >= 2024, "ISO timestamp year too low"
        assert abs((parsed.timestamp() - datetime.now().timestamp())) < 60, "timestamp too far from now"


class TestExport:
    """Export helpers."""

    def test_export_hud_to_file(self, tmp_path):
        status = p5.build_hud_status()
        out = tmp_path / "hud.json"
        path = p5.export_hud_to_file(out, status)
        assert path == out
        assert out.exists()
        content = json.loads(out.read_text(encoding="utf-8"))
        assert content["version"] == p5.HUD_VERSION


class TestSchemaExtensibility:
    """Schema is extensible via optional fields and hints."""

    def test_hints_accepts_arbitrary_data(self):
        status = p5.build_hud_status()
        status.hints["custom_field"] = {"nested": "value"}
        d = status.to_dict()
        assert d["hints"]["custom_field"]["nested"] == "value"

    def test_extra_fields_in_from_dict_ignored(self):
        d = p5.HUDStatus().to_dict()
        d["extra_field"] = "should be ignored"
        # Should not raise — extra fields in dict are dropped by dataclass
        restored = p5.HUDStatus.from_dict(d)
        assert not hasattr(restored, "extra_field")


class TestRecentActionsFromSessions:
    """Recent actions are populated from session history."""

    def test_recent_actions_is_list(self):
        status = p5.build_hud_status()
        assert isinstance(status.recent_actions, list)

    def test_recent_action_has_required_fields(self):
        status = p5.build_hud_status()
        for action in status.recent_actions:
            d = action.to_dict()
            assert "timestamp" in d
            assert "action_type" in d
            assert "description" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
