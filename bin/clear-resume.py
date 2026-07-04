#!/usr/bin/env python3
"""Clear resume_point in STATE.md after successful loop completion."""
import sys, json, re
from pathlib import Path

base_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
state_file = base_dir / "STATE.md"

if not state_file.exists():
    sys.exit(0)

content = state_file.read_text()
m = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
if m:
    state = json.loads(m.group(1))
    state['resume_point'] = None
    j = json.dumps(state, ensure_ascii=False, indent=2)
    content = re.sub(
        r'```json\s*\{.*?\}\s*```',
        '```json\n' + j + '\n```',
        content,
        flags=re.DOTALL
    )
    state_file.write_text(content)
    print("STATE.md resume_point cleared")
