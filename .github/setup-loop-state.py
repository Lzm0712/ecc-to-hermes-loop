#!/usr/bin/env python3
"""Write initial loop state to STATE.md. Called by GitHub Actions."""
import json, re, sys, os
from pathlib import Path

goal = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LOOP_GOAL", "")
trigger = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("LOOP_TRIGGER", "manual")
run_url = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("RUN_URL", "")
github_run_id = os.environ.get("GITHUB_RUN_ID", "")
github_event = os.environ.get("GITHUB_EVENT_NAME", "")

state_file = Path.home() / ".hermes/ecc-to-hermes-loop/STATE.md"
state_file.parent.mkdir(parents=True, exist_ok=True)

state = {
    "current_goal": goal,
    "trigger": trigger,
    "resume_point": None,
    "loop_state": {
        "run_url": run_url,
        "github_run_id": github_run_id,
        "github_event": github_event,
        "discovered_issues": []
    },
    "phase_results": {}
}

j = json.dumps(state, ensure_ascii=False, indent=2)
content = f"# ECC-to-Hermes Loop — GitHub Actions Run\n\n```json\n{j}\n```\n"
state_file.write_text(content)
print(f"STATE.md written: goal={goal}, trigger={trigger}")
