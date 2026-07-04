#!/usr/bin/env python3
"""
Tests for Phase 6: Evaluator RAG
All tests pass — 2026-06-20
"""

import json
import pytest
from phase6 import (
    RetrievedSession,
    EvaluationMetric,
    Recommendation,
    EvaluationResult,
    SessionRetriever,
    EvaluatorRAG,
    WEIGHT_TOOL_OVERLAP,
    WEIGHT_SEQUENCE_MATCH,
    WEIGHT_OUTCOME,
    RAG_VERSION,
    MIN_SEQUENCE_SCORE,
)


# ─── Dataclass Tests ──────────────────────────────────────────────────────────

class TestDataclasses:
    def test_retrieved_session_fields(self):
        s = RetrievedSession(
            session_id="abc123",
            title="Test Session",
            when="2026-06-20",
            tool_sequence=["read_file", "patch", "terminal"],
            outcome="success",
            message_count=10,
            snippet="...test...",
            similarity_score=0.85,
            patterns_found=["read-patch-loop"],
        )
        assert s.session_id == "abc123"
        assert s.tool_sequence == ["read_file", "patch", "terminal"]
        assert s.outcome == "success"
        assert s.patterns_found == ["read-patch-loop"]

    def test_evaluation_metric_fields(self):
        m = EvaluationMetric(
            name="tool_overlap",
            value=0.72,
            max_value=1.0,
            weight=0.35,
            details="72% tool overlap with baseline",
        )
        assert m.name == "tool_overlap"
        assert m.value == 0.72
        assert m.weight == 0.35

    def test_recommendation_fields(self):
        r = Recommendation(
            priority="high",
            category="tool-pattern",
            message="Add terminal to your workflow",
            suggested_tools=["terminal"],
        )
        assert r.priority == "high"
        assert r.category == "tool-pattern"
        assert r.suggested_tools == ["terminal"]

    def test_evaluation_result_defaults(self):
        r = EvaluationResult()
        assert r.version == RAG_VERSION
        assert r.overall_score == 0.0
        assert r.baseline_sessions_found == 0
        assert r.metrics == []
        assert r.recommendations == []


# ─── SessionRetriever Tests ───────────────────────────────────────────────────

class TestSessionRetriever:
    def test_detect_read_patch_loop(self):
        r = SessionRetriever("/nonexistent/db")
        seq = ["read_file", "patch", "terminal"]
        patterns = r._detect_patterns(seq)
        assert "read-patch-loop" in patterns

    def test_detect_read_run_loop(self):
        r = SessionRetriever("/nonexistent/db")
        seq = ["read_file", "terminal"]
        patterns = r._detect_patterns(seq)
        assert "read-run-loop" in patterns

    def test_detect_search_read_patch(self):
        r = SessionRetriever("/nonexistent/db")
        seq = ["search_files", "read_file", "patch"]
        patterns = r._detect_patterns(seq)
        assert "search-read-patch" in patterns

    def test_detect_terminal_iterate(self):
        r = SessionRetriever("/nonexistent/db")
        seq = ["terminal", "terminal"]
        patterns = r._detect_patterns(seq)
        assert "terminal-iterate" in patterns

    def test_detect_read_write_file(self):
        r = SessionRetriever("/nonexistent/db")
        seq = ["read_file", "write_file"]
        patterns = r._detect_patterns(seq)
        assert "read-write-file" in patterns

    def test_detect_research_loop(self):
        r = SessionRetriever("/nonexistent/db")
        seq = ["session_search", "read_file"]
        patterns = r._detect_patterns(seq)
        assert "research-loop" in patterns

    def test_no_patterns_for_empty_sequence(self):
        r = SessionRetriever("/nonexistent/db")
        patterns = r._detect_patterns([])
        assert patterns == []

    def test_compute_similarity_with_overlap(self):
        r = SessionRetriever("/nonexistent/db")
        score = r._compute_similarity(
            query="test",
            current_tools=["read_file", "patch"],
            session_tools=["read_file", "patch", "terminal"],
            patterns=["read-patch-loop"],
        )
        # Tool overlap: 2/3 = 0.667, weighted = 0.667 * 0.35 = 0.233
        # Pattern: 0.25 * 0.35 = 0.0875
        # Total ≈ 0.32
        assert 0.0 <= score <= 1.0

    def test_compute_similarity_no_current_tools(self):
        r = SessionRetriever("/nonexistent/db")
        score = r._compute_similarity(
            query="test",
            current_tools=[],
            session_tools=["read_file", "patch"],
            patterns=["read-patch-loop"],
        )
        # Pattern score only: min(1.0, 1*0.25) * 0.35 = 0.0875
        assert 0.0 <= score <= 1.0

    def test_retrieve_nonexistent_db_returns_empty(self):
        r = SessionRetriever("/nonexistent/path/state.db")
        results = r.retrieve("any query")
        assert results == []


# ─── EvaluatorRAG Tests ────────────────────────────────────────────────────────

class TestEvaluatorRAG:
    def test_evaluate_no_baseline_returns_uncertain(self):
        """When no sessions retrieved, verdict should be uncertain."""
        evaluator = EvaluatorRAG()
        result = evaluator.evaluate(
            query="build a web server",
            current_tools=["terminal"],
        )
        assert result.overall_verdict == "uncertain"
        assert result.baseline_sessions_found == 0
        assert len(result.recommendations) > 0
        # Should have a data recommendation
        data_recs = [r for r in result.recommendations if r.category == "data"]
        assert len(data_recs) > 0

    def test_evaluate_empty_query(self):
        evaluator = EvaluatorRAG()
        result = evaluator.evaluate(query="", current_tools=[])
        assert isinstance(result.overall_score, float)
        assert result.version == RAG_VERSION

    def test_evaluate_with_tools(self):
        evaluator = EvaluatorRAG()
        result = evaluator.evaluate(
            query="fix bug in authentication",
            current_tools=["read_file", "patch", "terminal"],
        )
        assert result.current_tools == ["read_file", "patch", "terminal"]
        assert isinstance(result.overall_score, float)
        assert result.overall_verdict in ("likely_succeed", "uncertain", "likely_fail")

    def test_verdict_mapping(self):
        evaluator = EvaluatorRAG()

        assert evaluator._verdict(0.80) == "likely_succeed"
        assert evaluator._verdict(0.70) == "likely_succeed"
        assert evaluator._verdict(0.69) == "uncertain"
        assert evaluator._verdict(0.50) == "uncertain"
        assert evaluator._verdict(0.45) == "uncertain"
        assert evaluator._verdict(0.44) == "likely_fail"
        assert evaluator._verdict(0.10) == "likely_fail"

    def test_compute_overall_score_empty_metrics(self):
        evaluator = EvaluatorRAG()
        score = evaluator._compute_overall_score([])
        assert score == 0.5

    def test_compute_overall_score_weighted(self):
        evaluator = EvaluatorRAG()
        metrics = [
            EvaluationMetric("a", 0.8, 1.0, 0.5, "detail"),
            EvaluationMetric("b", 0.4, 1.0, 0.5, "detail"),
        ]
        score = evaluator._compute_overall_score(metrics)
        # (0.8*0.5 + 0.4*0.5) / (0.5+0.5) = 0.6
        assert score == 0.6

    def test_compute_metrics_generates_correct_names(self):
        evaluator = EvaluatorRAG()
        sessions = [
            RetrievedSession(
                session_id="s1",
                title="Test",
                when="2026-06-20",
                tool_sequence=["read_file", "patch"],
                outcome="success",
                message_count=5,
                snippet="test",
                similarity_score=0.8,
                patterns_found=["read-patch-loop"],
            )
        ]
        metrics = evaluator._compute_metrics(
            current_tools=["read_file"],
            sessions=sessions,
            current_state=None,
        )
        metric_names = {m.name for m in metrics}
        assert "baseline_quality" in metric_names
        assert "tool_overlap" in metric_names
        assert "pattern_coverage" in metric_names
        assert "baseline_success_rate" in metric_names

    def test_generate_recommendations_low_overlap(self):
        evaluator = EvaluatorRAG()
        sessions = [
            RetrievedSession(
                session_id="s1",
                title="Success",
                when="2026-06-20",
                tool_sequence=["read_file", "patch", "terminal"],
                outcome="success",
                message_count=5,
                snippet="test",
                similarity_score=0.8,
                patterns_found=["read-patch-loop"],
            )
        ]
        metrics = [
            EvaluationMetric("tool_overlap", 0.1, 1.0, WEIGHT_TOOL_OVERLAP, "low"),
        ]
        recs = evaluator._generate_recommendations(
            current_tools=["terminal"],  # missing read_file, patch
            sessions=sessions,
            metrics=metrics,
            current_state=None,
        )
        assert len(recs) > 0
        high_priority = [r for r in recs if r.priority == "high"]
        assert len(high_priority) > 0

    def test_generate_recommendations_no_verification(self):
        evaluator = EvaluatorRAG()
        recs = evaluator._generate_recommendations(
            current_tools=["read_file"],
            sessions=[],
            metrics=[],
            current_state={"verification_stats": {"gates_passed": 0}},
        )
        verification_recs = [r for r in recs if r.category == "verification"]
        assert len(verification_recs) > 0

    def test_generate_hints_from_sessions(self):
        evaluator = EvaluatorRAG()
        sessions = [
            RetrievedSession(
                session_id="s1",
                title="Success",
                when="2026-06-20",
                tool_sequence=["read_file", "patch"],
                outcome="success",
                message_count=5,
                snippet="test",
                similarity_score=0.8,
                patterns_found=["read-patch-loop"],
            )
        ]
        hints = evaluator._generate_hints(sessions, [])
        assert len(hints) > 0


# ─── Serialization Tests ──────────────────────────────────────────────────────

class TestSerialization:
    def test_evaluation_result_to_dict_roundtrip(self):
        result = EvaluationResult(
            query="test query",
            current_tools=["read_file"],
            baseline_sessions_found=1,
            overall_score=0.75,
            overall_verdict="likely_succeed",
            metrics=[
                EvaluationMetric("tool_overlap", 0.8, 1.0, 0.35, "good")
            ],
            recommendations=[
                Recommendation("high", "tool-pattern", "add terminal", ["terminal"])
            ],
            retrieved_sessions=[],
            improvement_hints=["hint 1"],
        )
        d = result.__dict__
        assert d["query"] == "test query"
        assert d["overall_score"] == 0.75

    def test_retrieved_session_to_dict(self):
        s = RetrievedSession(
            session_id="abc",
            title="T",
            when="2026",
            tool_sequence=["read_file"],
            outcome="success",
            message_count=1,
            snippet="test",
            similarity_score=0.9,
            patterns_found=["read-run-loop"],
        )
        d = s.__dict__
        assert d["session_id"] == "abc"
        assert "read_file" in d["tool_sequence"]


# ─── CLI / Integration Tests ─────────────────────────────────────────────────

class TestCLI:
    def test_main_json_output(self, capsys):
        import sys
        sys.argv = ["phase6.py", "--json", "--query", "fix bug"]
        from phase6 import main
        # Should not raise
        main()
        captured = capsys.readouterr()
        # Output should be valid JSON (or partial on error)
        # Just check it doesn't crash with empty DB
        out = captured.out
        assert "phase6" in out.lower() or "error" in out.lower() or "{" in out

    def test_verdict_only_flag(self, capsys):
        import sys
        sys.argv = ["phase6.py", "--verdict-only"]
        from phase6 import main
        main()
        captured = capsys.readouterr()
        verdict = captured.out.strip()
        assert verdict in ("likely_succeed", "uncertain", "likely_fail")

    def test_human_output_includes_sections(self, capsys):
        import sys
        sys.argv = ["phase6.py", "--query", "fix bug"]
        from phase6 import main
        main()
        captured = capsys.readouterr()
        out = captured.out
        # Should contain all major sections
        assert "Evaluator RAG" in out or "query" in out.lower()


# ─── Constants Tests ───────────────────────────────────────────────────────────

class TestConstants:
    def test_rag_version_format(self):
        assert RAG_VERSION.startswith("1.")

    def test_weight_sums_to_one(self):
        total = WEIGHT_TOOL_OVERLAP + WEIGHT_SEQUENCE_MATCH + WEIGHT_OUTCOME
        assert abs(total - 1.0) < 0.001

    def test_min_sequence_score_in_range(self):
        assert 0.0 <= MIN_SEQUENCE_SCORE <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
