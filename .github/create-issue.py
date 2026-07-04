#!/usr/bin/env python3
"""Create a GitHub issue when loop fails. Called by GitHub Actions."""
import sys, os, subprocess

title = sys.argv[1] if len(sys.argv) > 1 else "[Loop] Loop failed"
goal = os.environ.get("LOOP_GOAL", "")
trigger = os.environ.get("LOOP_TRIGGER", "")
iterations = os.environ.get("LOOP_ITERATIONS", "")
run_url = os.environ.get("RUN_URL", "")
status = os.environ.get("LOOP_STATUS", "UNKNOWN")

body = f"""## Loop Engineering Failed

**Trigger:** {trigger}
**Goal:** {goal}
**Iterations used:** {iterations}
**Final status:** {status}

**Run:** {run_url}

Please review and address remaining issues manually.
"""

result = subprocess.run(
    ["gh", "issue", "create",
     "--title", title,
     "--body", body,
     "--label", "loop-engineering, automated"],
    capture_output=True, text=True
)
print(result.stdout.strip() or result.stderr.strip())
