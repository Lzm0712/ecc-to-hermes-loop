#!/usr/bin/env python3
"""
Phase 4: Professional Subagents

Routes user tasks to specialized subagents based on task type.
Each subagent is invoked via delegate_task with the appropriate skill loaded.

Usage:
    python phase4.py --task "review code in phase2/gates/"
    python phase4.py --list
    ecc-loop p4                    # Show registry
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

# Resolve agent_registry.py from the same directory as this script
_AGENTS_FILE = Path(__file__).resolve().parent / "agent_registry.py"
_spec = importlib.util.spec_from_file_location("agent_registry", _AGENTS_FILE)
_agent_registry_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_agent_registry_module)
AGENTS = _agent_registry_module.AGENTS


def list_agents() -> None:
    """Print available agents."""
    print("ECC-to-Hermes Loop — Phase 4 Agent Registry")
    print("=" * 50)
    for key, agent in AGENTS.items():
        print(f"\n  [{key}]")
        print(f"    Skill:    {agent['skill']}")
        print(f"    Desc:     {agent['description']}")
        print(f"    Triggers: {', '.join(agent['triggers'])}")


def list_agent_roles() -> list[str]:
    """Return list of agent role names (for phase5 stats)."""
    return list(AGENTS.keys())


def route_task(task: str) -> dict:
    """Route a task string to the best matching agent."""
    task_lower = task.lower()
    scores: dict[str, int] = {}

    for key, agent in AGENTS.items():
        score = sum(1 for trigger in agent["triggers"] if trigger.lower() in task_lower)
        if score > 0:
            scores[key] = score

    if not scores:
        return {"agent": None, "reason": "no matching triggers found"}

    best_key = max(scores, key=lambda k: scores.get(k, 0))
    return {
        "agent": best_key,
        "skill": AGENTS[best_key]["skill"],
        "reason": f"matched triggers: {[t for t in AGENTS[best_key]['triggers'] if t.lower() in task_lower]}",
    }


def run_agent(agent_key: str, task: str, dry_run: bool = True) -> None:
    """Execute a subagent task via hermes chat subprocess.

    When dry_run=True: print the plan without executing.
    When dry_run=False: spawn `hermes chat --cli --skills <skill> --toolsets terminal,file,web`
    with a prompt instructing the agent to act as the named subagent and exit after
    completing the task (outputting RESULT: <summary>).

    This replaces the previous delegate_task approach, which required running inside
    the Hermes Agent tool-calling context and was unavailable in standalone CLI mode.
    """
    agent = AGENTS.get(agent_key)
    if not agent:
        print(f"Unknown agent: {agent_key}", file=sys.stderr)
        sys.exit(1)

    print(f"Routing to {agent['skill']}...")
    print(f"Task: {task}")

    if dry_run:
        print("\n[DRY RUN] delegate_task call skipped.")
        print(f"  Skill:  {agent['skill']}")
        print(f"  Role:   {agent['role']}")
        print(f"  Task:   {task}")
        print("\nTo execute, invoke via the main agent with delegate_task.")
        return

    print(f"Routing to {agent['skill']}...")
    print(f"Task: {task}")

    # Build the subagent prompt — tell the agent to act as the named subagent,
    # load the skill, execute the task, then output RESULT: <summary> and exit.
    task_block = f"""You are the {agent['role']} subagent.

Load and follow the skill: {agent['skill']}

Execute this task:
{task}

When done, output your conclusion on a single line starting with RESULT: and then exit immediately.
Example: RESULT: Created fibonacci.py with iterative implementation"""

    # Build hermes chat invocation — use -q for single-query (non-interactive) mode
    # --ignore-rules suppresses AGENTS.md/memory injection for clean subagent isolation
    hermes_bin = Path(sys.executable).parent / "hermes"
    cmd = [
        str(hermes_bin), "chat",
        "-q", task_block,
        "--skills", agent["skill"],
        "--toolsets", "terminal,file,web",
        "--ignore-rules",
    ]

    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if result.stdout:
            print("\n--- Subagent Output ---")
            print(result.stdout)
        if result.stderr:
            print("\n--- Subagent Stderr ---")
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"\nSubagent exited with code {result.returncode}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Subagent timed out (120s)", file=sys.stderr)
    except FileNotFoundError:
        print(
            f"hermes not found at {hermes_bin} — is Hermes installed?",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4: Professional Subagents")
    parser.add_argument("--list", action="store_true", help="List available agents")
    parser.add_argument("--task", type=str, help="Task to route to an agent")
    parser.add_argument("--agent", type=str, choices=list(AGENTS.keys()), help="Force specific agent")
    parser.add_argument("--execute", action="store_true", help="Execute delegation (default is dry-run)")
    args = parser.parse_args()

    if args.list or (not args.task):
        list_agents()
        return

    if args.agent:
        route = {"agent": args.agent, "skill": AGENTS[args.agent]["skill"], "reason": "explicit"}
    else:
        route = route_task(args.task)
        print(f"Route: {route['agent']} ({route['reason']})")

    if route["agent"] is None:
        print("Could not determine which agent to use.", file=sys.stderr)
        print("Use --agent to specify explicitly.", file=sys.stderr)
        sys.exit(1)

    run_agent(route["agent"], args.task, dry_run=not args.execute)


if __name__ == "__main__":
    main()
