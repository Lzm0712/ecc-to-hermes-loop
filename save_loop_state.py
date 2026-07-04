#!/usr/bin/env python3
"""Save loop state to STATE.md JSON block. Called by ecc-loop loop."""
import sys, json, re
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: save_loop_state.py <goal> <plan_json_file>", file=sys.stderr)
    sys.exit(1)

goal = sys.argv[1]
plan_json_path = Path(sys.argv[2])
plan_data = json.loads(plan_json_path.read_text())

BASE_DIR = Path.home() / ".hermes" / "ecc-to-hermes-loop"
state_file = BASE_DIR / "STATE.md"

content = state_file.read_text() if state_file.exists() else ""
m = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
state = json.loads(m.group(1)) if m else {
    "phase_results": {},
    "current_goal": "",
    "resume_point": None,
}

state["current_goal"] = goal
state["phase_results"]["plan"] = {"status": "success", "output": plan_data}
if "resume_point" not in state:
    state["resume_point"] = None

j = json.dumps(state, ensure_ascii=False, indent=2)
if m:
    content = re.sub(
        r'```json\s*\{.*?\}\s*```',
        f'```json\n{j}\n```',
        content,
        flags=re.DOTALL,
    )
else:
    content = content.rstrip() + f'\n\n```json\n{j}\n```\n'
state_file.write_text(content)
