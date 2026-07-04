"""
Phase 4 tests: Professional Subagents — agent_registry
"""

import importlib.util
import sys
from pathlib import Path

# Load agent_registry the same way phase4.py does
_AGENTS_FILE = Path(__file__).resolve().parent / "agent_registry.py"
_spec = importlib.util.spec_from_file_location("agent_registry", _AGENTS_FILE)
_agent_registry_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_agent_registry_module)
AGENTS = _agent_registry_module.AGENTS


def test_agents_count():
    """Exactly 4 agents defined."""
    assert len(AGENTS) == 4


def test_planner_registered():
    """Planner agent exists with required fields."""
    assert "planner" in AGENTS
    a = AGENTS["planner"]
    assert a["skill"] == "agents/planner"
    assert a["role"] == "planner"
    assert len(a["triggers"]) > 0


def test_tdd_registered():
    """TDD agent exists with required fields."""
    assert "tdd" in AGENTS
    a = AGENTS["tdd"]
    assert a["skill"] == "agents/tdd-guide"
    assert a["role"] == "tdd-guide"
    assert len(a["triggers"]) > 0


def test_code_reviewer_registered():
    """Code reviewer agent exists."""
    assert "code-reviewer" in AGENTS
    a = AGENTS["code-reviewer"]
    assert a["skill"] == "agents/code-reviewer"
    assert a["role"] == "code-reviewer"
    assert len(a["triggers"]) > 0


def test_security_registered():
    """Security reviewer agent exists."""
    assert "security" in AGENTS
    a = AGENTS["security"]
    assert a["skill"] == "agents/security-reviewer"
    assert a["role"] == "security-reviewer"
    assert len(a["triggers"]) > 0


def test_all_have_triggers():
    """Every agent has at least one trigger."""
    for key, agent in AGENTS.items():
        assert len(agent["triggers"]) > 0, f"{key} has no triggers"


def test_all_have_required_fields():
    """Every agent has skill, description, role, triggers."""
    for key, agent in AGENTS.items():
        assert "skill" in agent, f"{key} missing skill"
        assert "description" in agent, f"{key} missing description"
        assert "role" in agent, f"{key} missing role"
        assert "triggers" in agent, f"{key} missing triggers"


def test_trigger_keywords_are_strings():
    """All trigger keywords are non-empty strings."""
    for key, agent in AGENTS.items():
        for t in agent["triggers"]:
            assert isinstance(t, str), f"{key} trigger {t!r} not a string"
            assert len(t) > 0, f"{key} has empty trigger"


def test_roles_are_unique():
    """All agent roles are unique."""
    roles = [a["role"] for a in AGENTS.values()]
    assert len(roles) == len(set(roles)), "Duplicate roles found"


def test_skills_are_unique():
    """All skill names are unique."""
    skills = [a["skill"] for a in AGENTS.values()]
    assert len(skills) == len(set(skills)), "Duplicate skills found"
