# Phase 4: Professional Subagents

**Status: COMPLETE** ✅

**Date:** 2026-06-20

---

## What Was Done

### 4 Professional Subagent Roles

Implemented a task-routing delegation system. Tasks are routed to specialized subagents via keyword matching + confidence scoring.

| Agent | Skill | Role | Description |
|-------|-------|------|-------------|
| `planner` | `planner-agent` | `planner` | Writes actionable markdown plans |
| `tdd-guide` | `tdd-guide-agent` | `tdd_guide` | Enforces RED-GREEN-REFACTOR TDD cycle |
| `code-reviewer` | `code-reviewer-agent` | `code_reviewer` | Independent code quality + logic review |
| `security` | `security-reviewer-agent` | `security_reviewer` | Security vulnerability review |

---

## Core Architecture

**`agent_registry.py`** — static registry:

```python
AGENTS = {
    "planner": {
        "skill": "planner-agent",
        "role": "planner",
        "description": "...",
        "triggers": ["plan", "approach", "步骤"],
    },
    ...
}
```

**`phase4.py`** — routing engine:

```python
def route_task(task: str) -> dict:
    """Route a task string to the best matching agent."""

def run_agent(agent_key: str, task: str, dry_run: bool = True) -> None:
    """Execute via delegate_task (or dry-run in CLI mode)."""
```

---

## Delegation Protocol

CLI mode (`ecc-loop p4 --agent X --task Y`) runs in **dry-run** mode — routing is verified but `delegate_task` is not called from the script (tool injection only available via main agent).

真实 delegation 由主 agent 通过 `phase4/skills/delegation/SKILL.md` 执行：

```python
delegate_task(
    goal=f"You are the {role} agent. Task: {task}",
    context=f"Skill: {skill}\nRole: {role}",
    toolsets=["terminal", "file", "web"],
)
```

---

## Usage

```bash
# List agents
ecc-loop p4 --list

# Route a task (dry-run)
ecc-loop p4 --agent planner --task "plan auth system"

# Route by keyword
ecc-loop p4 --task "review the code in phase2/"
```

---

## Test Results

- `test_phase4.py`: 10 unit tests — registry structure, routing logic
- `test_phase4_e2e.py`: 17 e2e tests — CLI routing, unit route_task coverage

**27 tests total** ✅

---

## Files

```
phase4/
├── phase4.py          # route_task(), run_agent(), main()
├── agent_registry.py  # AGENTS dict, list_agents()
├── skills/delegation/SKILL.md  # Main-agent delegation guide
├── test_phase4.py     # 10 unit tests
├── test_phase4_e2e.py # 17 e2e tests
└── README.md          # This file

~/.hermes/skills/agents/
├── planner/SKILL.md
├── tdd-guide/SKILL.md
├── code-reviewer/SKILL.md
└── security-reviewer/SKILL.md
```

---

## Phase Completion Criteria ✅

✅ Routing engine with keyword triggers
✅ 4 agents registered (planner, tdd-guide, code-reviewer, security)
✅ CLI with `--list`, `--agent`, `--task`, `--execute`
✅ Dry-run delegation (safe for CI)
✅ Real delegation via skill + main agent
✅ 27 tests passing
