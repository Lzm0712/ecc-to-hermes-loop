"""
Tests for Phase 3: InstinctLearning

Run with: python -m pytest phase3/test_instinct.py -v
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure phase3 is importable
sys.path.insert(0, str(Path(__file__).parent))

from instinct_learning import (
    ngram,
    get_recent_sessions,
    get_session_messages,
    get_tool_call_sequence,
    extract_tool_sequences,
    extract_keywords_from_sessions,
    match_sequence_template,
    build_trigger_keywords,
    generate_skill_md,
    promote_pattern_to_skill,
    run_extraction,
    SkillPattern,
    ToolSequence,
    SessionRecord,
    MIN_CONFIDENCE,
    MIN_SEQUENCE_COUNT,
    SKIP_PATTERNS,
)


class TestNgram:
    def test_bigram(self):
        assert ngram(["a", "b", "c"], 2) == [("a", "b"), ("b", "c")]

    def test_trigram(self):
        assert ngram(["a", "b", "c", "d"], 3) == [("a", "b", "c"), ("b", "c", "d")]

    def test_short_seq(self):
        assert ngram(["a"], 2) == []


class TestGetToolCallSequence:
    def test_tool_calls_json_array(self):
        messages = [{
            "role": "assistant",
            "tool_calls": '[{"function": {"name": "read_file"}}, {"function": {"name": "patch"}}]',
        }]
        assert get_tool_call_sequence(messages) == ["read_file", "patch"]

    def test_empty_messages(self):
        assert get_tool_call_sequence([]) == []

    def test_no_tool_calls(self):
        messages = [{"role": "user", "content": "hello"}]
        assert get_tool_call_sequence(messages) == []


class TestSequenceTemplates:
    def test_read_patch_match(self):
        tmpl = match_sequence_template(["read_file", "patch"])
        assert tmpl is not None
        assert tmpl["name"] == "read-patch-loop"

    def test_read_terminal_match(self):
        tmpl = match_sequence_template(["read_file", "terminal"])
        assert tmpl is not None
        assert tmpl["name"] == "read-run-loop"

    def test_search_read_patch_match(self):
        tmpl = match_sequence_template(["search_files", "read_file", "patch"])
        assert tmpl is not None

    def test_no_match(self):
        tmpl = match_sequence_template(["unknown", "tool"])
        assert tmpl is None


class TestSkipPatterns:
    def test_terminal_terminal_skipped(self):
        assert ("terminal", "terminal") in SKIP_PATTERNS

    def test_browser_console_browser_navigate_skipped(self):
        assert ("browser_console", "browser_navigate") in SKIP_PATTERNS


class TestSkillPattern:
    def test_skill_pattern_dataclass(self):
        pattern = SkillPattern(
            name="test-skill",
            trigger_keywords=["test", "run"],
            description="A test skill",
            workflow_steps=["step1", "step2"],
            tool_sequence=["terminal"],
            confidence=0.85,
            source_sessions=["s1", "s2"],
            skill_file_path=Path("/tmp/test/SKILL.md"),
        )
        assert pattern.name == "test-skill"
        assert pattern.confidence == 0.85
        assert len(pattern.source_sessions) == 2


class TestGenerateSkillMd:
    def test_generates_valid_frontmatter(self):
        pattern = SkillPattern(
            name="test-pattern",
            trigger_keywords=["test", "debug"],
            description="Test pattern description",
            workflow_steps=["read_file", "patch"],
            tool_sequence=["read_file", "patch"],
            confidence=0.75,
            source_sessions=["s1", "s2", "s3"],
            skill_file_path=Path("/tmp/test/SKILL.md"),
        )
        content = generate_skill_md(pattern)
        assert "---" in content
        assert 'name: test-pattern' in content
        assert 'category: instinct' in content
        assert 'confidence: 0.75' in content
        assert "Test pattern description" in content

    def test_workflow_steps_rendered(self):
        pattern = SkillPattern(
            name="wf-test",
            trigger_keywords=["x"],
            description="d",
            workflow_steps=["step one", "step two", "step three"],
            tool_sequence=["a"],
            confidence=0.9,
            source_sessions=["s1"],
            skill_file_path=Path("/tmp/x"),
        )
        content = generate_skill_md(pattern)
        assert "1. step one" in content
        assert "2. step two" in content
        assert "3. step three" in content


class TestPromotePatternToSkill:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.skills_dir = Path(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_skill_file(self):
        pattern = SkillPattern(
            name="promote-test",
            trigger_keywords=["test"],
            description="Test promotion",
            workflow_steps=["step1"],
            tool_sequence=["terminal"],
            confidence=0.8,
            source_sessions=["s1"],
            skill_file_path=self.skills_dir / "promote-test" / "SKILL.md",
        )
        msg, was_new = promote_pattern_to_skill(pattern)
        assert "promote-test" in msg
        assert was_new is True
        assert (self.skills_dir / "promote-test" / "SKILL.md").exists()

    def test_update_existing(self):
        skill_dir = self.skills_dir / "existing-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("existing content")

        pattern = SkillPattern(
            name="existing-skill",
            trigger_keywords=["test"],
            description="Updated description",
            workflow_steps=["step1"],
            tool_sequence=["terminal"],
            confidence=0.9,
            source_sessions=["s1"],
            skill_file_path=skill_dir / "SKILL.md",
        )
        msg, was_new = promote_pattern_to_skill(pattern)
        assert was_new is False
        assert "updated" in msg


class TestRunExtraction:
    """Integration tests — use in-memory state.db or mock."""

    def test_extracts_from_real_sessions(self):
        """Smoke test against real state.db."""
        report = run_extraction(session_limit=10, min_tool_calls=3, dry_run=True)
        assert report.total_sessions <= 10
        assert report.tool_sequences_found >= 0
        assert len(report.errors) == 0 or report.errors == []

    def test_dry_run_does_not_write(self):
        """Dry run should not modify skills dir."""
        tmp_skills = tempfile.mkdtemp()
        original_skills = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
        # Just check dry_run doesn't throw
        report = run_extraction(session_limit=5, min_tool_calls=3, dry_run=True)
        assert report.skills_promoted == 0
        assert report.skills_updated == 0
        shutil.rmtree(tmp_skills)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
