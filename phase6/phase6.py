#!/usr/bin/env python3
"""
Phase 6: Evaluator RAG — Retrieval-Augmented Evaluation Loop

ECC-to-Hermes Loop: The final phase implements a self-improvement loop that:
1. Retrieves similar successful past sessions from the session DB
2. Compares current state against retrieved success patterns
3. Evaluates whether current approach will likely succeed
4. Reports evaluation with actionable recommendations

This closes the loop: PostToolUse Hook → Verification Gate → Instinct Learning
→ Subagents → HUD Status → Evaluator RAG (self-referential improvement)
"""

import sys as _sys
from pathlib import Path

# Ensure the project root is on sys.path before the `from shared.paths import` line below.
# __file__ at module level = /path/to/phaseN/script.py → parent.parent = project root.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from shared.paths import HERMES_HOME, STATE_DB, SKILLS_DIR
from shared.tool_sequence import extract_tool_names_from_content

# NOTE: phase5 has build_hud_status() — this module's HUD integration
# is via the --state argument, not a duplicate function.

# ─── Configuration ────────────────────────────────────────────────────────────

RAG_VERSION = "1.0.0"

# Minimum sessions needed for a reliable evaluation baseline
MIN_BASELINE_SESSIONS = 2

# Similarity thresholds
MIN_TOOL_OVERLAP = 0.30       # At least 30% tool overlap to consider "similar"
MIN_SEQUENCE_SCORE = 0.40     # Minimum sequence similarity score

# Weighting for final score
WEIGHT_TOOL_OVERLAP = 0.35
WEIGHT_SEQUENCE_MATCH = 0.35
WEIGHT_OUTCOME = 0.30

# CLI rendering
BAR_WIDTH = 10

# Outcome classification keywords
FAILURE_KEYWORDS = frozenset(["error", "failed", "exception", "traceback", "crashed", "timeout"])
SUCCESS_KEYWORDS = frozenset(["success", "passed", "ok", "done", "completed"])

# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class RetrievedSession:
    """A past session retrieved as a reference baseline."""
    session_id: str
    title: str
    when: str
    tool_sequence: list[str]   # Ordered list of tools used
    outcome: str               # "success", "partial", "failed"
    message_count: int
    snippet: str                # FTS5-highlighted excerpt of the match
    similarity_score: float    # Computed similarity to current query
    patterns_found: list[str]  # e.g., ["read-patch-loop", "terminal-iterate"]

@dataclass
class EvaluationMetric:
    """A single measured metric in the evaluation."""
    name: str
    value: float
    max_value: float
    weight: float
    details: str

@dataclass
class Recommendation:
    """An actionable recommendation from the evaluator."""
    priority: str              # "high", "medium", "low"
    category: str              # e.g., "tool-pattern", "verification", "instinct"
    message: str
    suggested_tools: list[str] = field(default_factory=list)

@dataclass
class EvaluationResult:
    """Complete evaluation result from Evaluator RAG."""
    version: str = RAG_VERSION
    generated_at: str = ""           # ISO 8601 string for JSON serializability
    query: str = ""
    current_tools: list[str] = field(default_factory=list)
    baseline_sessions_found: int = 0
    overall_score: float = 0.0        # 0.0–1.0
    overall_verdict: str = ""         # "likely_succeed", "uncertain", "likely_fail"
    metrics: list[EvaluationMetric] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    retrieved_sessions: list[dict] = field(default_factory=list)
    improvement_hints: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()

# ─── Session Retriever ────────────────────────────────────────────────────────

class SessionRetriever:
    """Retrieves similar past sessions from the Hermes session DB."""

    def __init__(self, db_path: str = str(STATE_DB)):
        self.db_path = db_path

    def retrieve(
        self,
        query: str,
        current_tools: Optional[list[str]] = None,
        limit: int = 5,
    ) -> list[RetrievedSession]:
        """
        Retrieve sessions similar to the given query and tool sequence.

        Uses FTS5 full-text search on session titles and snippets,
        combined with tool-overlap scoring.
        """
        if not os.path.exists(self.db_path):
            return []

        sessions = []

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Try FTS5 search first
            fts_results = self._fts_search(cur, query, limit * 2)

            # Fallback: get recent sessions if FTS yields nothing
            if not fts_results:
                fts_results = self._recent_sessions(cur, limit * 2)

            for row in fts_results:
                session_id = row["session_id"]
                tool_seq = self._get_tool_sequence(cur, session_id)
                outcome = self._get_outcome(cur, session_id)
                patterns = self._detect_patterns(tool_seq)

                # Score similarity
                score = self._compute_similarity(
                    query=query,
                    current_tools=current_tools or [],
                    session_tools=tool_seq,
                    patterns=patterns,
                )

                if score >= MIN_SEQUENCE_SCORE or len(sessions) < limit:
                    sessions.append(RetrievedSession(
                        session_id=session_id,
                        title=row.get("title", "Untitled"),
                        when=row.get("when", ""),
                        tool_sequence=tool_seq,
                        outcome=outcome,
                        message_count=row.get("message_count", 0),
                        snippet=row.get("snippet", ""),
                        similarity_score=score,
                        patterns_found=patterns,
                    ))

            conn.close()

        except sqlite3.Error as exc:
            logging.debug(f"Could not retrieve similar sessions: {exc}")

        # Sort by similarity descending
        sessions.sort(key=lambda s: s.similarity_score, reverse=True)
        return sessions[:limit]

    def _fts_search(self, cur, query: str, limit: int) -> list[dict]:
        """Full-text search on session titles/snippets."""
        try:
            # Try to search messages via FTS if available
            cur.execute("""
                SELECT DISTINCT s.session_id, s.title, s.when,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) as message_count,
                      Snippet(m.content, 0, '<mark>', '</mark>', '...', 32) as snippet
                FROM sessions s
                JOIN messages m ON m.session_id = s.session_id
                WHERE m.content LIKE ?
                ORDER BY s.updated_at DESC
                LIMIT ?
            """, (f"%{query}%", limit))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def _recent_sessions(self, cur, limit: int) -> list[dict]:
        """Get most recent sessions as fallback."""
        try:
            cur.execute("""
                SELECT session_id, title, when,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) as message_count,
                       title as snippet
                FROM sessions s
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def _get_tool_sequence(self, cur, session_id: str) -> list[str]:
        """Extract ordered tool calls from a session's messages."""
        try:
            cur.execute("""
                SELECT content FROM messages
                WHERE session_id = ? AND role = 'assistant'
                ORDER BY id ASC
            """, (session_id,))
            rows = cur.fetchall()
            tools = []
            for row in rows:
                content = row["content"] or ""
                tools.extend(extract_tool_names_from_content(content))
            return tools
        except sqlite3.Error:
            return []

    def _get_outcome(self, cur, session_id: str) -> str:
        """Infer session outcome from final messages."""
        try:
            cur.execute("""
                SELECT content FROM messages
                WHERE session_id = ? AND role = 'assistant'
                ORDER BY id DESC
                LIMIT 3
            """, (session_id,))
            rows = cur.fetchall()
            last_content = " ".join(r["content"] or "" for r in rows)

            if any(kw in last_content.lower() for kw in FAILURE_KEYWORDS):
                return "failed"
            elif any(kw in last_content.lower() for kw in SUCCESS_KEYWORDS):
                return "success"
            else:
                return "partial"
        except sqlite3.Error:
            return "unknown"

    def _detect_patterns(self, tool_sequence: list[str]) -> list[str]:
        """Detect known instinct/skill patterns in a tool sequence."""
        detected = []

        # read_file → patch = read-patch-loop
        if "read_file" in tool_sequence and "patch" in tool_sequence:
            idx_r = tool_sequence.index("read_file")
            idx_p = tool_sequence.index("patch")
            if idx_r < idx_p:
                detected.append("read-patch-loop")

        # read_file → terminal = read-run-loop
        if "read_file" in tool_sequence and "terminal" in tool_sequence:
            idx_r = tool_sequence.index("read_file")
            idx_t = tool_sequence.index("terminal")
            if idx_r < idx_t:
                detected.append("read-run-loop")

        # search_files → read_file → patch = search-read-patch
        if all(t in tool_sequence for t in ["search_files", "read_file", "patch"]):
            detected.append("search-read-patch")

        # terminal → terminal = terminal-iterate
        count = sum(1 for t in tool_sequence if t == "terminal")
        if count >= 2:
            detected.append("terminal-iterate")

        # read_file → write_file = read-write-file
        if "read_file" in tool_sequence and "write_file" in tool_sequence:
            detected.append("read-write-file")

        # session_search → read = research loop
        if "session_search" in tool_sequence and "read_file" in tool_sequence:
            detected.append("research-loop")

        return detected

    def _compute_similarity(
        self,
        query: str,
        current_tools: list[str],
        session_tools: list[str],
        patterns: list[str],
    ) -> float:
        """Compute 0.0–1.0 similarity between current task and past session."""
        if not session_tools:
            return 0.0

        score = 0.0

        # 1. Tool overlap (Jaccard-like)
        if current_tools:
            overlap = len(set(current_tools) & set(session_tools))
            union = len(set(current_tools) | set(session_tools))
            tool_score = overlap / union if union > 0 else 0.0
            score += tool_score * WEIGHT_TOOL_OVERLAP

        # 2. Known pattern match bonus
        pattern_score = min(1.0, len(patterns) * 0.25)
        score += pattern_score * WEIGHT_SEQUENCE_MATCH

        # 3. Outcome bonus (successful sessions get higher base)
        # (already baked into selection; we weight by recency here)

        return min(1.0, score)


# ─── Evaluator RAG Engine ──────────────────────────────────────────────────────

class EvaluatorRAG:
    """
    Retrieval-Augmented Evaluation engine.

    Takes a current task context (query + tools), retrieves similar past
    successful sessions, and evaluates whether the current approach is
    likely to succeed based on pattern matching and historical outcomes.
    """

    def __init__(self):
        self.retriever = SessionRetriever()

    def evaluate(
        self,
        query: str,
        current_tools: Optional[list[str]] = None,
        current_state: Optional[dict] = None,
    ) -> EvaluationResult:
        """
        Main entry point: retrieve sessions and produce an evaluation.

        Args:
            query: Natural-language description of the current task
            current_tools: Ordered list of tools used so far
            current_state: Optional HUDStatus-like dict for deep comparison

        Returns:
            EvaluationResult with score, verdict, metrics, and recommendations
        """
        current_tools = current_tools or []
        result = EvaluationResult(
            query=query,
            current_tools=current_tools,
        )

        # Step 1: Retrieve similar successful sessions
        retrieved = self.retriever.retrieve(
            query=query,
            current_tools=current_tools,
            limit=5,
        )
        result.baseline_sessions_found = len(retrieved)
        result.retrieved_sessions = [asdict(s) for s in retrieved]

        if not retrieved:
            # No baseline — cannot evaluate, return uncertain verdict
            result.overall_score = 0.5
            result.overall_verdict = "uncertain"
            result.metrics.append(EvaluationMetric(
                name="baseline_availability",
                value=0.0,
                max_value=1.0,
                weight=1.0,
                details="No similar past sessions found — cannot establish baseline",
            ))
            result.recommendations.append(Recommendation(
                priority="high",
                category="data",
                message="No similar sessions in history. Proceed with caution and verify each step.",
                suggested_tools=["session_search"],
            ))
            return result

        # Step 2: Compute metrics
        metrics = self._compute_metrics(current_tools, retrieved, current_state)
        result.metrics = metrics

        # Step 3: Compute overall score
        overall = self._compute_overall_score(metrics)
        result.overall_score = overall

        # Step 4: Determine verdict
        result.overall_verdict = self._verdict(overall)

        # Step 5: Generate recommendations
        result.recommendations = self._generate_recommendations(
            current_tools, retrieved, metrics, current_state
        )

        # Step 6: Improvement hints
        result.improvement_hints = self._generate_hints(retrieved, result.recommendations)

        return result

    def _compute_metrics(
        self,
        current_tools: list[str],
        sessions: list[RetrievedSession],
        current_state: Optional[dict],
    ) -> list[EvaluationMetric]:
        """Compute individual evaluation metrics."""
        metrics = []

        # Metric 1: Baseline quality
        avg_score = sum(s.similarity_score for s in sessions) / len(sessions)
        metrics.append(EvaluationMetric(
            name="baseline_quality",
            value=avg_score,
            max_value=1.0,
            weight=0.20,
            details=f"Average similarity to {len(sessions)} retrieved sessions: {avg_score:.2f}",
        ))

        # Metric 2: Tool overlap with successful sessions
        if current_tools:
            successful_sessions = [s for s in sessions if s.outcome == "success"]
            if successful_sessions:
                overlap_scores = []
                for s in successful_sessions:
                    overlap = len(set(current_tools) & set(s.tool_sequence))
                    score = overlap / max(len(set(s.tool_sequence)), 1)
                    overlap_scores.append(score)
                avg_overlap = sum(overlap_scores) / len(overlap_scores)
            else:
                avg_overlap = 0.0

            metrics.append(EvaluationMetric(
                name="tool_overlap",
                value=avg_overlap,
                max_value=1.0,
                weight=WEIGHT_TOOL_OVERLAP,
                details=f"Tool overlap with successful baselines: {avg_overlap:.2f}",
            ))
        else:
            metrics.append(EvaluationMetric(
                name="tool_overlap",
                value=0.0,
                max_value=1.0,
                weight=WEIGHT_TOOL_OVERLAP,
                details="No tools used yet — cannot evaluate overlap",
            ))

        # Metric 3: Pattern coverage
        current_patterns = set()
        for s in sessions:
            for p in s.patterns_found:
                current_patterns.add(p)

        pattern_coverage = len(current_patterns) / max(len(sessions), 1)
        metrics.append(EvaluationMetric(
            name="pattern_coverage",
            value=pattern_coverage,
            max_value=1.0,
            weight=WEIGHT_SEQUENCE_MATCH,
            details=f"Known patterns found in baseline: {list(current_patterns)}",
        ))

        # Metric 4: Success rate of baseline sessions
        success_count = sum(1 for s in sessions if s.outcome == "success")
        success_rate = success_count / len(sessions)
        metrics.append(EvaluationMetric(
            name="baseline_success_rate",
            value=success_rate,
            max_value=1.0,
            weight=WEIGHT_OUTCOME,
            details=f"{success_count}/{len(sessions)} retrieved sessions succeeded",
        ))

        # Metric 5: Tool diversity (penalize over-reliance on few tools)
        if current_tools:
            unique_ratio = len(set(current_tools)) / len(current_tools)
            metrics.append(EvaluationMetric(
                name="tool_diversity",
                value=unique_ratio,
                max_value=1.0,
                weight=0.15,
                details=f"Tool diversity: {len(set(current_tools))}/{len(current_tools)} unique",
            ))
        else:
            metrics.append(EvaluationMetric(
                name="tool_diversity",
                value=0.0,
                max_value=1.0,
                weight=0.15,
                details="No tools used yet",
            ))

        return metrics

    def _compute_overall_score(self, metrics: list[EvaluationMetric]) -> float:
        """Weighted average of all metrics."""
        if not metrics:
            return 0.5

        total = sum(m.value * m.weight for m in metrics)
        weight_sum = sum(m.weight for m in metrics)
        return round(total / weight_sum, 3) if weight_sum > 0 else 0.5

    def _verdict(self, score: float) -> str:
        """Map score to human-readable verdict."""
        if score >= 0.70:
            return "likely_succeed"
        elif score >= 0.45:
            return "uncertain"
        else:
            return "likely_fail"

    def _generate_recommendations(
        self,
        current_tools: list[str],
        sessions: list[RetrievedSession],
        metrics: list[EvaluationMetric],
        current_state: Optional[dict],
    ) -> list[Recommendation]:
        """Generate actionable recommendations based on evaluation."""
        recs = []

        # Check tool overlap metric
        tool_overlap = next((m for m in metrics if m.name == "tool_overlap"), None)
        if tool_overlap and tool_overlap.value < MIN_TOOL_OVERLAP:
            # Recommend tools from successful sessions not in current set
            successful_sessions = [s for s in sessions if s.outcome == "success"]
            all_success_tools: set[str] = set()
            for s in successful_sessions:
                all_success_tools.update(s.tool_sequence)

            missing = all_success_tools - set(current_tools)
            if missing:
                recs.append(Recommendation(
                    priority="high",
                    category="tool-pattern",
                    message=f"Low tool overlap with successful baselines. Consider adding: {list(missing)[:5]}",
                    suggested_tools=list(missing)[:5],
                ))

        # Check pattern coverage
        pattern_cov = next((m for m in metrics if m.name == "pattern_coverage"), None)
        if pattern_cov and pattern_cov.value < 0.5:
            # Recommend known patterns from successful sessions
            successful_patterns: set[str] = set()
            for s in sessions:
                if s.outcome == "success":
                    successful_patterns.update(s.patterns_found)

            if successful_patterns:
                recs.append(Recommendation(
                    priority="medium",
                    category="instinct",
                    message=f"Pattern coverage low. Successful sessions used: {list(successful_patterns)}",
                    suggested_tools=[],
                ))

        # Check if no verification gates have been run
        if current_state:
            verification = current_state.get("verification_stats", {})
            gates_passed = verification.get("gates_passed", 0)
            if gates_passed == 0:
                recs.append(Recommendation(
                    priority="high",
                    category="verification",
                    message="No verification gates passed. Run Phase 2 verification before proceeding.",
                    suggested_tools=["verification_loop"],
                ))

        # If no high-priority recommendations exist, suggest checking instincts as fallback
        if recs and recs[0].priority != "high":
            recs.append(Recommendation(
                priority="medium",
                category="instinct",
                message="Consider loading relevant instinct skills for this task type.",
                suggested_tools=["skill_view"],
            ))

        return recs

    def _generate_hints(
        self,
        sessions: list[RetrievedSession],
        recommendations: list[Recommendation],
    ) -> list[str]:
        """Generate short improvement hints from the evaluation."""
        hints = []

        successful = [s for s in sessions if s.outcome == "success"]
        if successful:
            top_session = successful[0]
            hints.append(
                f"Top baseline used tools: {top_session.tool_sequence[:6]}"
            )
            if top_session.patterns_found:
                hints.append(
                    f"Key pattern: {top_session.patterns_found[0]}"
                )

        return hints


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 6: Evaluator RAG — Retrieval-Augmented Evaluation"
    )
    parser.add_argument(
        "--query", "-q",
        default="general task",
        help="Natural-language query describing the current task",
    )
    parser.add_argument(
        "--tools", "-t",
        nargs="*",
        default=[],
        help="Ordered list of tools used so far (e.g., read_file patch terminal)",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Path to a JSON file with current HUD state (for deep comparison)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output raw EvaluationResult as JSON",
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        help="Export evaluation result to a JSON file",
    )
    parser.add_argument(
        "--verdict-only",
        action="store_true",
        help="Only print the verdict (likely_succeed / uncertain / likely_fail)",
    )

    args = parser.parse_args()

    # Load current state if provided
    current_state = None
    if args.state:
        try:
            with open(args.state) as f:
                current_state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load state from {args.state}", file=sys.stderr)

    # Run evaluation
    evaluator = EvaluatorRAG()
    result = evaluator.evaluate(
        query=args.query,
        current_tools=args.tools,
        current_state=current_state,
    )

    # Output
    if args.verdict_only:
        print(result.overall_verdict)
        return

    if args.json:
        print(json.dumps(asdict(result), indent=2, default=str))
    else:
        _print_human(result)

    if args.export:
        with open(args.export, "w") as f:
            json.dump(asdict(result), f, indent=2, default=str)
        print(f"\nEvaluation exported to {args.export}")


def _print_human(result: EvaluationResult):
    """Pretty-print evaluation result for human readers."""
    verdict_emoji = {
        "likely_succeed": "✅",
        "uncertain": "⚠️",
        "likely_fail": "❌",
    }
    emoji = verdict_emoji.get(result.overall_verdict, "❓")

    print(f"\n{'='*60}")
    print(f"  Evaluator RAG — Phase 6 of ECC-to-Hermes Loop")
    print(f"{'='*60}")
    print(f"  Query: {result.query}")
    print(f"  Tools used: {result.current_tools or '(none yet)'}")
    print(f"  Baseline sessions found: {result.baseline_sessions_found}")
    print()
    print(f"  Overall Score: {result.overall_score:.2f} {emoji}")
    print(f"  Verdict: {result.overall_verdict}")
    print()

    if result.metrics:
        print("  Metrics:")
        for m in result.metrics:
            bar = "█" * int(m.value * BAR_WIDTH) + "░" * (BAR_WIDTH - int(m.value * BAR_WIDTH))
            print(f"    [{bar}] {m.name}: {m.value:.2f} — {m.details}")
        print()

    if result.recommendations:
        print("  Recommendations:")
        for r in result.recommendations:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.priority, "⚪")
            print(f"    {priority_icon} [{r.priority.upper()} {r.category}] {r.message}")
            if r.suggested_tools:
                print(f"      Suggested tools: {r.suggested_tools}")
        print()

    if result.improvement_hints:
        print("  Improvement Hints:")
        for h in result.improvement_hints:
            print(f"    • {h}")
        print()

    if result.retrieved_sessions:
        print(f"  Top Reference Sessions ({len(result.retrieved_sessions)}):")
        for i, s in enumerate(result.retrieved_sessions[:3], 1):
            print(f"    {i}. [{s['outcome']}] {s['title']} (score={s['similarity_score']:.2f})")
            print(f"       Tools: {s['tool_sequence'][:5]}")
            if s['patterns_found']:
                print(f"       Patterns: {s['patterns_found']}")
        print()

    print(f"  Version: {result.version}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
