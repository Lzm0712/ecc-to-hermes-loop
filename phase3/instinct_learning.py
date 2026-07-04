"""
Instinct Learning — Phase 3: ECC-to-Hermes Loop

从 session 历史提取模式，高置信度晋升为 skill。

核心思想：观察同一类任务反复出现时的共同解法，当置信度足够高时，
自动固化为一个可复用的 skill，下次遇到同类任务时直接调用。

数据来源：
- ~/.hermes/state.db — SQLite session store (sessions + messages tables)
- FTS5 full-text search index on messages.content
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path

# Ensure the project root is on sys.path before the `from shared.paths import` line below.
# __file__ at module level = /path/to/phase3/script.py → parent.parent = project root.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)

import json
import argparse
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.paths import HERMES_HOME, SKILLS_DIR
from shared.session_db import get_db
from shared.tool_sequence import extract_tool_names_from_messages

# ---------------------------------------------------------------------------
# observations.jsonl — hook-based tool call observation (from pre_tool_call hook)
# ---------------------------------------------------------------------------

OBSERVATIONS_FILE = HERMES_HOME / "observations.jsonl"


def load_observations(
    session_ids: set[str] | None = None,
    max_age_hours: float = 48.0,
) -> dict[str, list[str]]:
    """
    Load tool call sequences from observations.jsonl (written by pre_tool_call hook).

    This is the PREFERRED data source — 100% reliable vs session transcript parsing.

    Returns:
        dict[session_id, list of tool names in call order]
        Only sessions with >= 3 tool calls are included.

    Falls back to empty dict if file missing (caller falls back to session parsing).
    """
    if not OBSERVATIONS_FILE.exists():
        return {}

    cutoff = time.time() - (max_age_hours * 3600)
    session_seqs: dict[str, list[str]] = defaultdict(list)

    try:
        with open(OBSERVATIONS_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = entry.get("ts", 0)
                if ts < cutoff:
                    continue

                sid = entry.get("session_id", "")
                tool = entry.get("tool", "")
                if not sid or not tool:
                    continue

                # Filter by session_ids if provided
                if session_ids and sid not in session_ids:
                    continue

                session_seqs[sid].append(tool)
    except Exception:
        return {}

    # Only keep sessions with meaningful activity
    return {sid: seq for sid, seq in session_seqs.items() if len(seq) >= 3}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SessionRecord:
    id: str
    title: str
    source: str
    started_at: float
    message_count: int
    tool_call_count: int

@dataclass
class ToolSequence:
    """A recurring tool-call pattern extracted from sessions."""
    tools: list[str]           # e.g. ["read_file", "patch", "terminal"]
    count: int                 # how many times this exact sequence appeared
    sessions: list[str]        # session IDs where this appeared
    examples: list[str]        # first 2 session IDs as examples
    confidence: float           # 0.0–1.0

@dataclass
class SkillPattern:
    """A candidate skill distilled from observed patterns."""
    name: str
    trigger_keywords: list[str]   # FTS5 keywords that should fire this
    description: str
    workflow_steps: list[str]     # what to do
    tool_sequence: list[str]       # canonical tool order
    confidence: float
    source_sessions: list[str]
    skill_file_path: Path

@dataclass
class ExtractionReport:
    total_sessions: int
    sessions_with_tools: int
    tool_sequences_found: int
    high_confidence_patterns: int
    skills_promoted: int
    skills_updated: int
    errors: list[str]

# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------

def get_recent_sessions(limit: int = 200, min_tool_calls: int = 5) -> list[SessionRecord]:
    """Fetch recent sessions with meaningful tool-call activity."""
    db = get_db()
    try:
        rows = db.execute("""
            SELECT id, title, source, started_at, message_count, tool_call_count
            FROM sessions
            WHERE tool_call_count >= ?
            ORDER BY started_at DESC
            LIMIT ?
        """, (min_tool_calls, limit)).fetchall()
        return [
            SessionRecord(
                id=str(r[0]),
                title=str(r[1] or ""),
                source=str(r[2] or ""),
                started_at=float(r[3]),
                message_count=int(r[4]),
                tool_call_count=int(r[5]),
            )
            for r in rows
        ]
    finally:
        db.close()

def get_session_messages(session_id: str) -> list[dict]:
    """Get all messages for a session, ordered chronologically."""
    db = get_db()
    try:
        rows = db.execute("""
            SELECT role, content, tool_calls, tool_name, tool_call_id
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,)).fetchall()
        result = []
        for r in rows:
            result.append({
                "role": str(r[0]),
                "content": str(r[1] or ""),
                "tool_calls": r[2],
                "tool_name": str(r[3] or ""),
                "tool_call_id": str(r[4] or ""),
            })
        return result
    finally:
        db.close()

def get_tool_call_sequence(messages: list[dict]) -> list[str]:
    """Extract ordered list of tool names from a message list."""
    return extract_tool_names_from_messages(messages)

# ---------------------------------------------------------------------------
# Pattern extraction
# ---------------------------------------------------------------------------

def ngram(seq: list[str], n: int) -> list[tuple]:
    """Return all n-length sliding windows from seq."""
    return [tuple(seq[i:i+n]) for i in range(len(seq) - n + 1)]

def extract_tool_sequences(sessions: list[SessionRecord], min_count: int = 2) -> list[ToolSequence]:
    """Find recurring tool-call sequences across sessions."""
    pattern_map: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "sessions": set()})

    for session in sessions:
        if session.tool_call_count < 3:
            continue
        messages = get_session_messages(session.id)
        seq = get_tool_call_sequence(messages)
        if not seq:
            continue
        # Extract 2-grams through 5-grams
        for n in range(2, 6):
            for gram in ngram(seq, n):
                pattern_map[gram]["count"] += 1
                pattern_map[gram]["sessions"].add(session.id)

    results = []
    for gram, data in pattern_map.items():
        if data["count"] < min_count:
            continue
        sid_list = list(data["sessions"])
        confidence = min(1.0, (data["count"] - 1) / 10 + 0.3)
        results.append(ToolSequence(
            tools=list(gram),
            count=data["count"],
            sessions=sid_list,
            examples=sid_list[:2],
            confidence=confidence,
        ))

    results.sort(key=lambda x: (-x.confidence, -x.count))
    return results


def extract_tool_sequences_from_observations(
    obs_dict: dict[str, list[str]], min_count: int = 2
) -> list[ToolSequence]:
    """
    Same pattern-extraction logic as extract_tool_sequences, but reads from
    observations.jsonl data (dict[session_id, list[tool_name]]) instead of DB.

    100% reliable data source vs session transcript parsing.
    """
    pattern_map: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "sessions": set()})

    for session_id, seq in obs_dict.items():
        if len(seq) < 3:
            continue
        for n in range(2, 6):
            for gram in ngram(seq, n):
                pattern_map[gram]["count"] += 1
                pattern_map[gram]["sessions"].add(session_id)

    results = []
    for gram, data in pattern_map.items():
        if data["count"] < min_count:
            continue
        sid_list = list(data["sessions"])
        confidence = min(1.0, (data["count"] - 1) / 10 + 0.3)
        results.append(ToolSequence(
            tools=list(gram),
            count=data["count"],
            sessions=sid_list,
            examples=sid_list[:2],
            confidence=confidence,
        ))

    results.sort(key=lambda x: (-x.confidence, -x.count))
    return results

# ---------------------------------------------------------------------------
# Keyword extraction from session content
# ---------------------------------------------------------------------------

def extract_keywords_from_sessions(session_ids: list[str]) -> list[str]:
    """Pull meaningful action keywords from session user messages."""
    db = get_db()
    try:
        placeholders = ",".join("?" * len(session_ids))
        rows = db.execute(f"""
            SELECT substr(content, 1, 200) FROM messages
            WHERE session_id IN ({placeholders}) AND role = 'user'
            ORDER BY id ASC
        """, session_ids).fetchall()
        text = " ".join(str(r[0]) for r in rows if r[0])
        # Extract meaningful words (3+ chars, alphanumeric + Chinese)
        words = re.findall(r"[\w\u4e00-\u9fff]{3,30}", text.lower())
        # Filter stopwords
        stop = {"the", "and", "for", "that", "this", "with", "from", "your", "you", "are", "was", "have", "has", "been", "not", "but", "what", "when", "where", "which", "their", "there", "will", "would", "could", "should", "about", "into", "only", "also", "very", "just"}
        words = [w for w in words if w not in stop and len(w) >= 3]
        # Count frequency
        return [w for w, _ in Counter(words).most_common(20)]
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Skill promotion logic
# ---------------------------------------------------------------------------

# Tool sequence → canonical skill templates
SEQUENCE_TEMPLATES: dict[tuple, dict] = {
    ("read_file", "patch"): {
        "name": "read-patch-loop",
        "description": "读取文件后直接修补，适用于'先看代码再改'的快速修改场景。",
        "steps": ["read_file 读取目标文件", "分析代码问题", "patch 进行针对性修改"],
        "trigger": ["read", "patch", "fix", "edit", "修改", "修复", "改"],
    },
    ("read_file", "terminal"): {
        "name": "read-run-loop",
        "description": "读取文件或项目后运行命令验证，适用于'先看再跑'的验证场景。",
        "steps": ["read_file 读取目标文件或配置", "terminal 执行验证命令", "分析输出"],
        "trigger": ["run", "test", "execute", "验证", "运行", "执行"],
    },
    ("search_files", "read_file", "patch"): {
        "name": "search-read-patch",
        "description": "搜索代码库定位问题文件后读取并修复，适用于定位 + 修复类任务。",
        "steps": ["search_files 全局搜索关键词", "read_file 读取匹配文件", "patch 修复问题"],
        "trigger": ["search", "find", "grep", "搜索", "查找", "定位"],
    },
    ("terminal", "terminal"): {
        "name": "terminal-iterate",
        "description": "反复运行终端命令直到达到目标，适用于需要逐步调式的任务。",
        "steps": ["terminal 执行命令", "分析输出", "根据结果调整参数再次执行"],
        "trigger": ["run", "build", "compile", "执行", "编译", "调试"],
    },
    ("read_file", "write_file"): {
        "name": "read-write-file",
        "description": "读取现有文件内容后写入新内容，适用于模板填充或内容迁移。",
        "steps": ["read_file 读取源文件", "分析内容结构", "write_file 写入目标文件"],
        "trigger": ["read", "write", "migrate", "generate", "迁移", "生成"],
    },
    ("terminal", "read_file", "patch"): {
        "name": "test-fix-loop",
        "description": "运行测试失败后再读取代码并修复，适用于测试驱动的修复工作流。",
        "steps": ["terminal 运行测试", "确认失败信息", "read_file 读取相关代码", "patch 修复", "terminal 重新验证"],
        "trigger": ["test", "fix", "debug", "测试", "修复", "调试"],
    },
}

def match_sequence_template(tools: list[str]) -> Optional[dict]:
    """Try to match a tool sequence to a known skill template."""
    n = len(tools)
    # Try exact match first, then decreasing lengths
    for length in range(min(n, 5), 1, -1):
        for i in range(n - length + 1):
            gram = tuple(tools[i:i+length])
            if gram in SEQUENCE_TEMPLATES:
                return SEQUENCE_TEMPLATES[gram]
    return None

def build_trigger_keywords(session_ids: list[str], base_trigger: list[str]) -> list[str]:
    """Build trigger keywords from session content + base template triggers."""
    keywords = extract_keywords_from_sessions(session_ids)
    merged = list(set(keywords[:8] + base_trigger))
    return merged[:12]

# ---------------------------------------------------------------------------
# Skill file generation
# ---------------------------------------------------------------------------

def generate_skill_md(pattern: SkillPattern) -> str:
    """Generate SKILL.md content for a promoted skill."""
    steps_md = "\n".join(f"{i+1}. {s}" for i, s in enumerate(pattern.workflow_steps))
    triggers_md = ", ".join(f"`{t}`" for t in pattern.trigger_keywords[:8])

    return f"""---
name: {pattern.name}
description: |
  Instinct Learning 自动生成。置信度 {pattern.confidence:.0%}
  从 {len(pattern.source_sessions)} 个 session 中提取的典型工作流。
  触发词：{triggers_md}
category: instinct
version: "1.0.0"
metadata:
  instinct:
    confidence: {pattern.confidence}
    source_sessions: {len(pattern.source_sessions)}
    tool_sequence: {pattern.tool_sequence}
    created_at: {datetime.now().isoformat()}
---

# {pattern.name}

## 描述
{pattern.description}

## 触发词
{triggers_md}

## 工作流
{steps_md}

## 来源
- 观测到 {len(pattern.source_sessions)} 个 session 中出现相同工作流
- 工具序列：{' → '.join(pattern.tool_sequence)}
- 置信度：{pattern.confidence:.0%}

## 使用注意
- 由 Instinct Learning 自动生成，可能需要根据具体任务调整
- 高置信度（>70%）表示工作流已稳定验证
"""

# ---------------------------------------------------------------------------
# Skill promotion/update
# ---------------------------------------------------------------------------

def promote_pattern_to_skill(pattern: SkillPattern) -> tuple[str, bool]:
    """
    Write skill to the path specified in pattern.skill_file_path.
    Returns (status_msg, was_new).
    """
    skill_file = pattern.skill_file_path
    skill_dir = skill_file.parent
    was_new = not skill_file.exists()
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = generate_skill_md(pattern)
    skill_file.write_text(content, encoding="utf-8")
    status = "created" if was_new else "updated"
    return f"Skill `{pattern.name}` {status} (confidence={pattern.confidence:.0%})", was_new

# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

MIN_CONFIDENCE = 0.70  # Minimum confidence to promote to skill
MIN_SEQUENCE_COUNT = 3  # Minimum occurrences to consider
MIN_DISTINCT_SESSIONS = 2  # Must appear in at least N distinct sessions

# Patterns to skip entirely (too generic or low-information)
SKIP_PATTERNS: set[tuple[str, ...]] = {
    # Pure repeats of same tool
    ("terminal", "terminal"),
    ("browser_console", "browser_console"),
    ("browser_navigate", "browser_navigate"),
    ("write_file", "write_file"),
    ("search_files", "search_files"),
    ("read_file", "read_file"),
    ("skill_view", "skill_view"),
    ("web_extract", "web_extract"),
    ("web_search", "web_search"),
    ("patch", "patch"),
    ("cronjob", "cronjob"),
    ("terminal", "clarify"),
    ("clarify", "terminal"),
    ("read_file", "read_file", "read_file"),
    ("terminal", "terminal", "terminal"),
    # Browser-only cycles (too session-specific)
    ("browser_console", "browser_navigate"),
    ("browser_navigate", "browser_console"),
    ("browser_navigate", "browser_console", "browser_navigate"),
    ("browser_type", "browser_press"),
    ("browser_snapshot", "browser_click"),
    ("browser_click", "browser_type"),
    ("browser_press", "browser_snapshot"),
    ("browser_click", "browser_snapshot"),
    ("browser_navigate", "browser_click"),
    ("browser_click", "browser_console"),
    ("browser_press", "browser_console"),
    ("browser_console", "browser_snapshot"),
    ("browser_scroll", "browser_console"),
    ("browser_snapshot", "browser_scroll"),
    ("browser_console", "terminal"),
    ("terminal", "browser_console"),
    # MCP-specific
    ("mcp_minimax_understand_understand_image", "terminal"),
    ("web_search", "web_extract"),
    ("web_extract", "web_search"),
    ("mcp_minimax_understand_web_search", "web_extract"),
}

def run_extraction(
    session_limit: int = 200,
    min_tool_calls: int = 5,
    dry_run: bool = False,
) -> ExtractionReport:
    """
    Run the full instinct learning pipeline:
    1. Fetch recent sessions
    2. Extract recurring tool sequences
    3. Match to skill templates
    4. Promote high-confidence patterns
    """
    report = ExtractionReport(
        total_sessions=0,
        sessions_with_tools=0,
        tool_sequences_found=0,
        high_confidence_patterns=0,
        skills_promoted=0,
        skills_updated=0,
        errors=[],
    )

    # Step 1: Get sessions
    try:
        sessions = get_recent_sessions(limit=session_limit, min_tool_calls=min_tool_calls)
        report.total_sessions = len(sessions)
        report.sessions_with_tools = sum(1 for s in sessions if s.tool_call_count >= 3)
    except Exception as e:
        report.errors.append(f"Session fetch error: {e}")
        return report

    if not sessions:
        report.errors.append("No sessions with sufficient tool calls found.")
        return report

    # Step 2: Extract patterns — prefer observations.jsonl, fall back to DB
    # observations.jsonl is 100% reliable (from pre_tool_call hook)
    # session DB parsing is fallback (depends on tool_calls field)
    session_ids = {s.id for s in sessions}
    obs_dict = load_observations(session_ids=session_ids)

    if obs_dict:
        # observations.jsonl available — use hook-based data (primary source)
        try:
            sequences = extract_tool_sequences_from_observations(obs_dict, min_count=MIN_SEQUENCE_COUNT)
            report.tool_sequences_found = len(sequences)
        except Exception as e:
            report.errors.append(f"Observations extraction error: {e}")
            return report
    else:
        # No observations.jsonl — fall back to session DB parsing
        try:
            sequences = extract_tool_sequences(sessions, min_count=MIN_SEQUENCE_COUNT)
            report.tool_sequences_found = len(sequences)
        except Exception as e:
            report.errors.append(f"Pattern extraction error: {e}")
            return report

    # Step 3: Match templates — collect best pattern per skill name
    best_per_skill: dict[str, tuple[ToolSequence, dict, SkillPattern]] = {}
    for seq in sequences:
        if seq.confidence < MIN_CONFIDENCE:
            continue
        # Skip known low-value patterns (exact match on first 2 tools)
        if tuple(seq.tools[:2]) in SKIP_PATTERNS:
            continue
        # Require minimum session diversity
        if len(seq.sessions) < MIN_DISTINCT_SESSIONS:
            continue
        report.high_confidence_patterns += 1
        template = match_sequence_template(seq.tools)
        if not template:
            name = f"instinct-{'-'.join(seq.tools[:2])}"
            desc = f"自动发现的工作流：{'→'.join(seq.tools)}"
            steps = [f"使用 {t} 工具" for t in seq.tools]
            triggers = seq.tools
        else:
            name = template["name"]
            desc = template["description"]
            steps = template["steps"]
            triggers = template["trigger"]

        trigger_kw = build_trigger_keywords(seq.sessions, triggers)
        pattern = SkillPattern(
            name=name,
            trigger_keywords=trigger_kw,
            description=desc,
            workflow_steps=steps,
            tool_sequence=seq.tools,
            confidence=seq.confidence,
            source_sessions=seq.sessions,
            skill_file_path=SKILLS_DIR / name / "SKILL.md",
        )
        # Deduplicate by name — keep highest confidence
        if name not in best_per_skill or seq.confidence > best_per_skill[name][0].confidence:
            best_per_skill[name] = (seq, template or {}, pattern)

    # Step 4: Write skills (deduplicated)
    patterns_to_write = [v[2] for v in best_per_skill.values()]
    for pattern in patterns_to_write:
        msg, was_new = promote_pattern_to_skill(pattern) if not dry_run else (f"[DRY] Would promote {pattern.name}", True)
        if not dry_run:
            if was_new:
                report.skills_promoted += 1
            else:
                report.skills_updated += 1
        print(f"  {msg}", file=sys.stderr)

    if dry_run:
        print(f"\n[DRY RUN] Would promote {len(patterns_to_write)} unique skill(s)", file=sys.stderr)

    return report

# -------------------------------------------------------------------------------------------------------------------------------------------
# CLI entry point
# -------------------------------------------------------------------------------------------------------------------------------------------

def _build_iterate_result(verify_report: dict | None, error: str | None) -> dict:
    """
    Build Iterate result with resume_point.

    Loop Engineering rule:
      Verify fails → Iterate → resume_point = "verify" (retry from Verify)
      No verify data → resume_point = "discover" (full restart)
    """
    if error:
        return {
            "status": "error",
            "resume_point": "discover",  # unknown failure = full restart
            "analysis": error,
        }

    all_passed = verify_report.get("all_passed", True)
    if all_passed:
        return {
            "status": "success",
            "resume_point": None,  # nothing to iterate
            "analysis": "All gates passed — no iteration needed",
        }

    # Find first failed gate
    failed_gates = [g["gate"] for g in verify_report.get("gates", []) if not g["passed"]]
    failed_gate = failed_gates[0] if failed_gates else "unknown"

    # Map failed gate → resume point
    gate_to_phase = {
        "build": "execute",
        "type": "execute",
        "lint": "execute",
        "test": "execute",
        "security": "execute",
        "diff": "verify",
    }
    resume_point = gate_to_phase.get(failed_gate, "verify")

    return {
        "status": "iterate",
        "resume_point": resume_point,
        "failed_gate": failed_gate,
        "failed_gates": failed_gates,
        "analysis": f"Failed at '{failed_gate}' gate — resuming from {resume_point}",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ECC-to-Hermes Phase 3: Instinct Learning + Iterate")
    parser.add_argument("--limit", type=int, default=200, help="Max sessions to analyze")
    parser.add_argument("--min-tool-calls", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=0.70)
    parser.add_argument(
        "--iterate",
        action="store_true",
        help="Iterate mode: analyze verify failure and output resume_point",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Iterate mode: output JSON only to stdout",
    )
    parser.add_argument(
        "--verify-report",
        type=str, default=None,
        help="JSON string of VerificationReport.as_dict() for iterate analysis",
    )
    args = parser.parse_args()

    if args.iterate:
        # Iterate mode
        verify_report = None
        if args.verify_report:
            try:
                verify_report = json.loads(Path(args.verify_report).read_text())
            except (json.JSONDecodeError, FileNotFoundError) as e:
                verify_report = None
        result = _build_iterate_result(verify_report, error=None)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            import sys as _sys_iter
            if result["status"] == "iterate":
                _sys_iter.stderr.write(f"🔄 Iterate: {result['analysis']}\n")
                _sys_iter.stderr.write(f"   resume_point: {result['resume_point']}\n")
            elif result["status"] == "success":
                _sys_iter.stderr.write(f"✅ {result['analysis']}\n")
            else:
                _sys_iter.stderr.write(f"❌ {result.get('analysis', 'unknown error')}\n")
        exit(0)

    MIN_CONFIDENCE = args.min_confidence

    print(f"Instinct Learning — analyzing last {args.limit} sessions...", file=sys.stderr)
    t0 = time.time()
    report = run_extraction(
        session_limit=args.limit,
        min_tool_calls=args.min_tool_calls,
        dry_run=args.dry_run,
    )
    elapsed = time.time() - t0

    print(f"\n=== Extraction Report ===", file=sys.stderr)
    print(f"  Sessions analyzed:    {report.total_sessions}", file=sys.stderr)
    print(f"  Sessions w/ tools:   {report.sessions_with_tools}", file=sys.stderr)
    print(f"  Sequences found:     {report.tool_sequences_found}", file=sys.stderr)
    print(f"  High-conf patterns:  {report.high_confidence_patterns}", file=sys.stderr)
    print(f"  Skills promoted:     {report.skills_promoted}", file=sys.stderr)
    print(f"  Skills updated:      {report.skills_updated}", file=sys.stderr)
    print(f"  Elapsed:             {elapsed:.2f}s", file=sys.stderr)
    if report.errors:
        print(f"  Errors:             {report.errors}", file=sys.stderr)
