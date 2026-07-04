"""
Phase 4 E2E tests: Subagent routing + delegation

These tests run the real phase4.py script and verify routing + delegation work.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Load agent_registry the same way phase4.py does
_AGENTS_FILE = Path(__file__).resolve().parent / "agent_registry.py"
_spec = importlib.util.spec_from_file_location("agent_registry", _AGENTS_FILE)
_agent_registry_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_agent_registry_module)
AGENTS = _agent_registry_module.AGENTS

PHASE4_SCRIPT = Path(__file__).resolve().parent / "phase4.py"


def run_phase4(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Run phase4.py with given args, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(PHASE4_SCRIPT)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestPhase4Routing:
    """Test routing logic via CLI."""

    def test_list_agents(self):
        """--list prints all agents."""
        r = run_phase4(["--list"])
        assert r.returncode == 0, r.stderr
        for key in AGENTS:
            assert key in r.stdout, f"{key} missing from --list output"

    def test_explicit_planner_agent(self):
        """--agent planner routes to planner even without matching trigger."""
        r = run_phase4(["--agent", "planner", "--task", "random gibberish xyz"])
        assert r.returncode == 0, r.stderr
        assert "planner" in r.stdout.lower()

    def test_explicit_tdd_agent(self):
        """--agent tdd routes to tdd."""
        r = run_phase4(["--agent", "tdd", "--task", "random xyz"])
        assert r.returncode == 0, r.stderr
        assert "tdd" in r.stdout.lower()

    def test_planner_trigger_routes_to_planner(self):
        """Task containing 'plan' routes to planner."""
        r = run_phase4(["--agent", "planner", "--task", "plan the authentication system"])
        assert r.returncode == 0, r.stderr
        # Should print "planner-agent" (the skill)
        assert "planner-agent" in r.stdout or "planner" in r.stdout.lower()

    def test_review_trigger_routes_to_code_reviewer(self):
        """Task containing 'review' routes to code-reviewer."""
        r = run_phase4(["--agent", "code-reviewer", "--task", "review all the code in phase2/"])
        assert r.returncode == 0, r.stderr

    def test_security_trigger_routes_to_security(self):
        """Task containing 'security' routes to security reviewer."""
        r = run_phase4(["--agent", "security", "--task", "check for security vulnerabilities"])
        assert r.returncode == 0, r.stderr

    def test_unknown_agent_fails(self):
        """Unknown --agent name exits with error."""
        r = run_phase4(["--agent", "nonexistent", "--task", "do something"])
        assert r.returncode != 0

    def test_task_only_no_agent_shows_route(self):
        """--task without --agent prints routing decision."""
        r = run_phase4(["--task", "plan a trip to Tokyo"])
        # Should route to planner (contains "plan") and print something
        assert r.returncode == 0, r.stderr
        assert "planner" in r.stdout.lower() or "Route" in r.stdout


class TestRouteTask:
    """Unit test route_task directly (no subprocess)."""

    def _load_route_task(self):
        # Import phase4.py as a module using its file path
        spec = importlib.util.spec_from_file_location("phase4", PHASE4_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.route_task

    def test_plan_routes_to_planner(self):
        rt = self._load_route_task()
        r = rt("plan a trip to Tokyo")
        assert r["agent"] == "planner"

    def test_review_routes_to_code_reviewer(self):
        rt = self._load_route_task()
        r = rt("review the authentication code")
        assert r["agent"] == "code-reviewer"

    def test_security_routes_to_security(self):
        rt = self._load_route_task()
        r = rt("check for security vulnerabilities")
        assert r["agent"] == "security"

    def test_tdd_routes_to_tdd(self):
        rt = self._load_route_task()
        r = rt("write tests first with tdd")
        assert r["agent"] == "tdd"

    def test_no_trigger_returns_none(self):
        rt = self._load_route_task()
        r = rt("do something random xyz123")
        assert r["agent"] is None

    def test_approach_routes_to_planner(self):
        rt = self._load_route_task()
        r = rt("what is the best approach?")
        assert r["agent"] == "planner"

    def test_chinese_trigger_步骤_routes_to_planner(self):
        rt = self._load_route_task()
        r = rt("请给我步骤")
        assert r["agent"] == "planner"

    def test_role_is_correct_for_planner(self):
        rt = self._load_route_task()
        r = rt("plan something")
        assert r["skill"] == "agents/planner"

    def test_reason_contains_match(self):
        rt = self._load_route_task()
        r = rt("plan something")
        assert "matched triggers" in r["reason"]
        assert "plan" in r["reason"]
