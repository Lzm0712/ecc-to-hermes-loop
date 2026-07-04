#!/usr/bin/env python3
"""
GitHub MCP-style Connector
Wraps GitHub REST API as a standardized tool interface.
Supports: issues, PRs, runs, status checks.
"""
import argparse, json, sys, urllib.request, urllib.parse, subprocess
from pathlib import Path

GH_TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5).stdout.strip()
GH_API = "https://api.github.com"
HEADERS = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def gh_get(path: str) -> dict:
    url = f"{GH_API}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def gh_get_issues(owner: str, repo: str, state: str = "open") -> list:
    data = gh_get(f"/repos/{owner}/{repo}/issues?state={state}&labels=bug,urgent&per_page=20")
    return [{"number": i["number"], "title": i["title"], "labels": [l["name"] for l in i["labels"]], "html_url": i["html_url"]} for i in data if not i.get("pull_request")]


def gh_get_ci_runs(owner: str, repo: str, branch: str = "main") -> list:
    data = gh_get(f"/repos/{owner}/{repo}/actions/runs?branch={branch}&per_page=10")
    return [{"id": r["id"], "status": r["status"], "conclusion": r["conclusion"], "head_branch": r["head_branch"], "created_at": r["created_at"]} for r in data["workflow_runs"]]


def gh_get_run_logs(owner: str, repo: str, run_id: int) -> str:
    data = gh_get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/logs")
    return json.dumps(data)


def gh_create_issue(owner: str, repo: str, title: str, body: str, labels: list[str] | None = None) -> dict:
    data = {"title": title, "body": body, "labels": labels or []}
    body_enc = json.dumps(data).encode()
    req = urllib.request.Request(f"{GH_API}/repos/{owner}/{repo}/issues", data=body_enc, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def gh_create_pr(owner: str, repo: str, title: str, head: str, base: str = "main", body: str = "") -> dict:
    data = {"title": title, "head": head, "base": base, "body": body}
    body_enc = json.dumps(data).encode()
    req = urllib.request.Request(f"{GH_API}/repos/{owner}/{repo}/pulls", data=body_enc, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main() -> None:
    p = argparse.ArgumentParser(description="GitHub MCP Connector")
    sub = p.add_subparsers(dest="cmd")

    p_issues = sub.add_parser("issues", help="List open issues")
    p_issues.add_argument("--owner", default="Lzm0712")
    p_issues.add_argument("--repo", default="ecc-to-hermes-loop")
    p_issues.add_argument("--state", default="open")

    p_runs = sub.add_parser("runs", help="List CI runs")
    p_runs.add_argument("--owner", default="Lzm0712")
    p_runs.add_argument("--repo", default="ecc-to-hermes-loop")
    p_runs.add_argument("--branch", default="main")

    args = p.parse_args()
    if args.cmd == "issues":
        for i in gh_get_issues(args.owner, args.repo, args.state):
            print(f"[#{i['number']}] {i['title']} — {', '.join(i['labels'])}")
    elif args.cmd == "runs":
        for r in gh_get_ci_runs(args.owner, args.repo, args.branch):
            print(f"[run #{r['id']}] {r['status']}/{r['conclusion']} on {r['head_branch']} @ {r['created_at']}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
