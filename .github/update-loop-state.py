#!/usr/bin/env python3
"""Update loop state on completion. Called by GitHub Actions."""
import json, re, os
from pathlib import Path

state_file = Path.home() / ".hermes/ecc-to-hermes-loop/STATE.md"
if not state_file.exists():
    print("STATE.md not found, skipping")
    exit(0)

content = state_file.read_text()
m = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
if not m:
    print("No JSON block in STATE.md")
    exit(0)

state = json.loads(m.group(1))
status = os.environ.get("LOOP_STATUS", "UNKNOWN")
state["loop_state"]["last_run_status"] = status
state["loop_state"]["last_run_url"] = os.environ.get("RUN_URL", "")
state["loop_state"]["github_run_id"] = os.environ.get("GITHUB_RUN_ID", "")
state["loop_state"]["last_run"] = os.environ.get("GITHUB_EVENT_NAME", "")

j = json.dumps(state, ensure_ascii=False, indent=2)
content = re.sub(
    r'```json\s*\{.*?\}\s*```',
    '```json\n' + j + '\n```',
    content,
    flags=re.DOTALL
)
state_file.write_text(content)
print(f"STATE.md updated: status={status}")
