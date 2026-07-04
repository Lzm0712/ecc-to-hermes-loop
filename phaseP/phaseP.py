#!/usr/bin/env python3
"""
Phase P: Plan — Goal Decomposition

Input:  raw goal (string)
Output: sub-tasks written to STATE.md phase_results.plan

Minimal implementation per Loop Engineering:
  DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE
  Plan = "break down goals into specific steps, clarifying constraints and dependencies"

Uses MiniMax LLM for decomposition.
"""
import sys
import json
import argparse
from pathlib import Path

# Ensure project root on sys.path (3-line hack)
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared.paths import ECC_LOOP_DIR, HERMES_HOME

STATE_FILE = HERMES_HOME / "ecc-to-hermes-loop" / "STATE.md"


def load_state() -> dict:
    """Load current STATE.md as dict."""
    import re
    if not STATE_FILE.exists():
        return {}
    content = STATE_FILE.read_text()
    # Extract JSON block from STATE.md
    m = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    """Save state dict back to STATE.md JSON block.
    
    Creates a JSON block if none exists.
    """
    import re
    if not STATE_FILE.exists():
        STATE_FILE.write_text("# ECC-to-Hermes Loop State\n\n```json\n{}\n```\n")
    
    content = STATE_FILE.read_text()
    json_block_pattern = r"(`{3}json\s*)(\{.*?\})(\s*`{3})"
    m = re.search(json_block_pattern, content, re.DOTALL)
    
    if m:
        new_json = json.dumps(state, ensure_ascii=False, indent=2)
        content = content[:m.start()] + m.group(1) + new_json + m.group(3) + content[m.end():]
    else:
        # No JSON block — append one at the end
        new_json = json.dumps(state, ensure_ascii=False, indent=2)
        content = content.rstrip() + "\n\n```json\n" + new_json + "\n```\n"
    
    STATE_FILE.write_text(content)


def call_minimax_planner(goal: str) -> tuple[list[str], list[str]]:
    """
    Two-pass planning:
    1. Decompose goal into sub-tasks
    2. Identify constraints and dependencies for each step

    Returns (sub_tasks, constraints).
    """
    from agent.credential_pool import load_pool
    token = load_pool("minimax-cn").entries()[0].access_token
    import urllib.request

    # Pass 1: decomposition
    decomp_payload = json.dumps({
        "model": "MiniMax-Text-01",
        "messages": [
            {"role": "system", "content": "You are a task decomposition assistant. Given a goal, break it down into numbered sub-tasks. Each sub-task should be a single actionable step.\n\nOutput ONLY a JSON array of strings:\n[\"1. First step\", \"2. Second step\", ...]\n\nMaximum 7 sub-tasks. No explanation, just the JSON array."},
            {"role": "user", "content": f"Goal: {goal}"}
        ],
        "temperature": 0.3,
        "max_tokens": 512,
    }).encode()

    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        data=decomp_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        decomp_result = json.loads(resp.read())

    decomp_text = decomp_result["choices"][0]["message"]["content"]
    sub_tasks = json.loads(decomp_text)

    # Pass 2: constraint identification
    constraints_payload = json.dumps({
        "model": "MiniMax-Text-01",
        "messages": [
            {"role": "system", "content": "You are a constraint identification assistant. Given a goal and its sub-tasks, identify the key constraints, dependencies, and requirements.\n\nOutput ONLY a JSON array of strings (max 5 items). Example:\n[\"Must maintain backward compatibility\", \"Requires database migration\", \"API must remain stable\"]\n\nIf no special constraints, return [\"No special constraints\"]. No explanation, just the JSON array."},
            {"role": "user", "content": f"Goal: {goal}\n\nSub-tasks:\n" + "\n".join(sub_tasks)}
        ],
        "temperature": 0.3,
        "max_tokens": 256,
    }).encode()

    req2 = urllib.request.Request(
        "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        data=constraints_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req2, timeout=30) as resp:
        constr_result = json.loads(resp.read())

    constr_text = constr_result["choices"][0]["message"]["content"]
    constraints = json.loads(constr_text)

    return sub_tasks, constraints


def run_plan(goal: str) -> dict:
    """Run Plan phase: decompose goal into sub-tasks."""
    import time
    start = time.time()

    try:
        sub_tasks, constraints = call_minimax_planner(goal)
        duration_s = time.time() - start
        return {
            "status": "success",
            "goal": goal,
            "sub_tasks": sub_tasks,
            "constraints": constraints,
            "duration_s": round(duration_s, 2),
        }
    except Exception as e:
        duration_s = time.time() - start
        return {
            "status": "error",
            "goal": goal,
            "error": str(e),
            "duration_s": round(duration_s, 2),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase P: Plan — Goal Decomposition")
    parser.add_argument("--goal", "-g", required=True, help="Goal to decompose")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show prompt without calling LLM")
    args = parser.parse_args()

    result = run_plan(args.goal)

    if args.json:
        # JSON only to stdout — no header
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Human-readable to stderr (so stdout is clean for piping)
        import sys as _sys
        if result["status"] == "success":
            _sys.stderr.write(f"✅ Plan generated ({result['duration_s']}s)\n")
            for t in result["sub_tasks"]:
                _sys.stderr.write(f"  {t}\n")
            if result.get("constraints"):
                _sys.stderr.write(f"\n  Constraints:\n")
                for c in result["constraints"]:
                    _sys.stderr.write(f"  • {c}\n")
        else:
            _sys.stderr.write(f"❌ Plan failed: {result['error']}\n")
        _sys.stderr.flush()

    # Persist to STATE.md
    state = load_state()
    if "phase_results" not in state:
        state["phase_results"] = {}
    state["phase_results"]["plan"] = result
    state["current_phase"] = "plan"
    save_state(state)

    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
