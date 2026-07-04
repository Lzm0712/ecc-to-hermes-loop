#!/usr/bin/env python3
"""
Worktree Manager — Agent Isolation
Each subagent runs in its own Git worktree to avoid file conflicts.
"""
import argparse, subprocess, sys, json, shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKTREE_ROOT = BASE_DIR.parent / "ecc-loop-worktrees"


def run(cmd: list[str], capture: bool = True) -> str:
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        print(f"ERROR: {' '.join(cmd)}", file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        sys.exit(r.returncode)
    return r.stdout.strip()


def list_worktrees() -> list[dict]:
    out = run(["git", "worktree", "list", "--json"], capture=True)
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # Fallback: parse plain text
        lines = out.splitlines()
        trees = []
        for line in lines:
            if line.startswith(" "):
                parts = line.strip().split()
                if len(parts) >= 2:
                    trees.append({"path": parts[0], "branch": parts[1].strip("[]")})
        return trees


def create_worktree(branch: str, purpose: str) -> Path:
    """Create a new worktree for an agent."""
    WORKTREE_ROOT.mkdir(exist_ok=True)
    wt_path = WORKTREE_ROOT / f"agent-{branch}"

    if wt_path.exists():
        print(f"Worktree already exists: {wt_path}")
        return wt_path

    run(["git", "worktree", "add", "-b", f"worktree/{branch}", str(wt_path), "main"])
    # Tag the worktree with purpose
    (wt_path / ".worktree-purpose").write_text(f"{purpose}\n")
    print(f"Created: {wt_path} (branch: worktree/{branch})")
    return wt_path


def remove_worktree(branch: str) -> None:
    wt_path = WORKTREE_ROOT / f"agent-{branch}"
    if not wt_path.exists():
        print(f"Worktree not found: {wt_path}")
        return
    run(["git", "worktree", "remove", str(wt_path), "--force"])
    print(f"Removed: {wt_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Worktree Manager")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List all worktrees")
    sub.add_parser("init", help="Initialize worktree root")
    create = sub.add_parser("create", help="Create a worktree")
    create.add_argument("branch", help="Branch name")
    create.add_argument("--purpose", default="", help="Purpose of this worktree")
    remove = sub.add_parser("remove", help="Remove a worktree")
    remove.add_argument("branch", help="Branch name")

    args = p.parse_args()

    if args.cmd == "list":
        trees = list_worktrees()
        print(f"Worktrees ({len(trees)}):")
        for t in trees:
            purpose = ""
            p = Path(t.get("path", ""))
            if p.exists():
                purpose_file = p / ".worktree-purpose"
                if purpose_file.exists():
                    purpose = purpose_file.read_text().strip()
            print(f"  [{t.get('branch', '?')}] {t.get('path', '?')} {purpose}")
    elif args.cmd == "init":
        WORKTREE_ROOT.mkdir(exist_ok=True)
        print(f"Initialized: {WORKTREE_ROOT}")
    elif args.cmd == "create":
        create_worktree(args.branch, args.purpose)
    elif args.cmd == "remove":
        remove_worktree(args.branch)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
