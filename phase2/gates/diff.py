"""
Gate 6: Diff

Runs `git diff` against a configurable ref (default: HEAD) and returns
a structured summary of changed files, LOC delta, and file-type breakdown.
This is the final gate — human-readable diff summary before merge/approval.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import GateInput, GateResult, GateStatus


def diff_gate(input: GateInput) -> GateResult:
    """
    Gate 6 — Diff: Summarise changes vs ref.
    """
    t0 = time.monotonic()
    messages: list[str] = []
    project_root = input.project_root
    ref = input.diff_against

    # git diff --stat
    try:
        stat_result = subprocess.run(
            ["git", "diff", "--stat", ref],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return GateResult(
            gate="diff",
            status=GateStatus.WARN,
            messages=("git diff timed out",),
            duration_s=time.monotonic() - t0,
        )
    except Exception as exc:
        return GateResult(
            gate="diff",
            status=GateStatus.SKIP,
            messages=(f"git not available: {exc}",),
            duration_s=time.monotonic() - t0,
        )

    stat_output = stat_result.stdout.strip()

    if not stat_output:
        return GateResult(
            gate="diff",
            status=GateStatus.PASS,
            messages=("No changes detected",),
            duration_s=time.monotonic() - t0,
        )

    # Parse --stat summary
    files_changed, insertions, deletions = _parse_stat(stat_output)
    messages.append(f"vs {ref}: {files_changed} file(s), +{insertions} / -{deletions} LOC")

    # Breakdown by file type
    type_summary = _git_diff_by_type(project_root, ref)
    if type_summary:
        messages.append(type_summary)

    # List changed files (truncated)
    try:
        name_result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=15,
        )
        names = [n for n in name_result.stdout.strip().splitlines() if n]
        if names:
            messages.append("Changed:")
            messages.extend(names[:20])
            if len(names) > 20:
                messages.append(f"... and {len(names) - 20} more")
    except Exception:
        pass

    # New files (untracked, staged, or --diff-filter=A)
    try:
        new_result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=A", ref],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=15,
        )
        new_files = [n for n in new_result.stdout.strip().splitlines() if n]
        if new_files:
            messages.append(f"{len(new_files)} new file(s):")
            messages.extend(new_files[:10])
    except Exception:
        pass

    status = GateStatus.PASS  # Diff is informational, always passes
    return GateResult(
        gate="diff",
        status=status,
        messages=tuple(messages),
        duration_s=time.monotonic() - t0,
        metadata={
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
        },
    )


def _parse_stat(stat_output: str) -> tuple[int, int, int]:
    """Parse `git diff --stat` output. Returns (files, insertions, deletions)."""
    files = 0
    insertions = 0
    deletions = 0

    for line in stat_output.splitlines():
        # e.g. "  file.py | 10 +  3 -"
        # or  "  file.py | 100"
        parts = line.split("|")
        if len(parts) != 2:
            continue
        files += 1
        nums = parts[1].strip()
        # Extract numbers before + and -
        import re
        plus_nums = re.findall(r"(\d+)\s+\+", nums)
        minus_nums = re.findall(r"(\d+)\s+-", nums)
        if plus_nums:
            insertions += int(plus_nums[-1])
        if minus_nums:
            deletions += int(minus_nums[-1])

    return files, insertions, deletions


def _git_diff_by_type(project_root: Path, ref: str) -> str:
    """Return a per-extension LOC summary."""
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", ref],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=30,
        )
    except Exception:
        return ""

    from collections import defaultdict
    by_ext: dict[str, dict[str, int]] = defaultdict(lambda: {"add": 0, "del": 0})

    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            add = int(parts[0]) if parts[0] != "-" else 0
            dele = int(parts[1]) if parts[1] != "-" else 0
            path = parts[2]
            ext = Path(path).suffix or "(no ext)"
            by_ext[ext]["add"] += add
            by_ext[ext]["del"] += dele
        except (ValueError, IndexError):
            continue

    if not by_ext:
        return ""

    lines = ["Breakdown by type:"]
    for ext, counts in sorted(by_ext.items()):
        if counts["add"] or counts["del"]:
            lines.append(f"  {ext}: +{counts['add']} / -{counts['del']}")

    return "\n".join(lines)
