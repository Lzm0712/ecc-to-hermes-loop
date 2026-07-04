#!/usr/bin/env python3
"""Persist resume_point to STATE.md after gate failure."""
import sys, json, re
from pathlib import Path

base_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
resume_point = sys.argv[2] if len(sys.argv) > 2 else "verify"
state_file = base_dir / "STATE.md"

content = ""
if state_file.exists():
    content = state_file.read_text()

m = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
if m:
    state = json.loads(m.group(1))
else:
    state = {'phase_results': {}, 'current_goal': '', 'resume_point': None}

state['resume_point'] = resume_point
j = json.dumps(state, ensure_ascii=False, indent=2)

if m:
    content = re.sub(
        r'```json\s*\{.*?\}\s*```',
        '```json\n' + j + '\n```',
        content,
        flags=re.DOTALL
    )
else:
    content = content.rstrip() + '\n\n```json\n' + j + '\n```\n'

state_file.write_text(content)
print(f"STATE.md resume_point set to: {resume_point}")
