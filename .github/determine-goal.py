#!/usr/bin/env python3
"""Determine loop goal and trigger from event context. Called by GitHub Actions."""
import argparse, os, re

def write(name, value):
    path = f"/tmp/loop_{name}.txt"
    with open(path, "w") as f:
        f.write(value)
    print(f"{name}={value}", file=__import__('sys').stderr)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--event-name", required=True)
    p.add_argument("--event-action", default="")
    p.add_argument("--workflow-goal", default="")
    p.add_argument("--workflow-trigger", default="manual")
    p.add_argument("--workflow-max-iterations", default="3")
    p.add_argument("--branch", default="")
    p.add_argument("--ci-goal", default="")
    p.add_argument("--issue-number", default="")
    p.add_argument("--issue-title", default="")
    p.add_argument("--run-url", required=True)
    p.add_argument("--github-run-id", required=True)
    args = p.parse_args()

    trigger = "manual"
    goal = ""

    event = args.event_name
    action = args.event_action or ""

    if event == "schedule":
        trigger = "daily"
        goal = "Daily triage: scan for issues and fix quick wins"
    elif event == "workflow_dispatch":
        trigger = args.workflow_trigger or "manual"
        goal = args.workflow_goal or ""
    elif event == "repository_dispatch":
        if action == "ci-failed":
            trigger = "ci"
            goal = args.ci_goal or derive_goal_from_branch(args.branch)
        elif action == "issue-created":
            trigger = "issue"
            if args.issue_title:
                goal = f"Resolve GitHub Issue #{args.issue_number}: {args.issue_title}"
            else:
                goal = f"Address issue #{args.issue_number}"
        elif action == "daily-trigger":
            trigger = "daily"
            goal = "Daily triage: scan for issues and fix quick wins"

    if not goal:
        goal = "ECC-to-Hermes: improve code quality and fix issues"

    max_iter = args.workflow_max_iterations if event == "workflow_dispatch" else "3"

    write("goal", goal)
    write("trigger", trigger)
    write("max_iter", max_iter)
    write("run_url", args.run_url)

def derive_goal_from_branch(branch):
    m = re.match(r'(feature|fix|hotfix|bugfix)/(.*)', branch)
    if not m:
        return f"Investigate and fix CI failure on branch {branch}"
    prefix, name = m.groups()
    name = name.replace("-", " ")
    if prefix == "feature":
        return f"Implement {name}"
    elif prefix == "fix":
        return f"Fix {name}"
    elif prefix == "hotfix":
        return f"Hotfix {name}"
    return f"Work on {branch}"

if __name__ == "__main__":
    main()
