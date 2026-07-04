#!/usr/bin/env python3
"""Update a specific field in STATE.md JSON block. Called by ecc-loop."""
import sys, json, re
from pathlib import Path

if len(sys.argv) != 4:
    print("Usage: update_state_field.py <field_path> <value_json> <state_md_path>", file=sys.stderr)
    sys.exit(1)

field_path = sys.argv[1]  # e.g. "loop_state.discovered_issues"
value_json = sys.argv[2]   # JSON string
state_path = Path(sys.argv[3])

value = json.loads(value_json)

if state_path.exists():
    content = state_path.read_text()
    m = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
    if m:
        state = json.loads(m.group(1))
    else:
        state = {}
else:
    content = ""
    state = {}

# Navigate nested field path
parts = field_path.split(".")
current = state
for p in parts[:-1]:
    current = current.setdefault(p, {})

current[parts[-1]] = value

j = json.dumps(state, ensure_ascii=False, indent=2)
new_content = re.sub(
    r'```json\s*\{.*?\}\s*```',
    '```json\n' + j + '\n```',
    content,
    flags=re.DOTALL
)
state_path.write_text(new_content)
print("OK", file=sys.stderr)
