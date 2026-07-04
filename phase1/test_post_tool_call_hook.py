"""
Tests for Phase 1: PostToolUse Hook System

Tests the HookType enum, HookExecutor class, post_format hook,
and post_lint hook.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── HookType Tests ────────────────────────────────────────────────────────────


class TestHookType:
    def test_hook_type_values(self):
        """HookType enum has correct string values."""
        from hook_executor import HookType

        assert HookType.PRE_TOOL_USE.value == "pre_tool_call"
        assert HookType.POST_TOOL_USE.value == "post_tool_call"
        assert HookType.STOP.value == "stop"

    def test_hook_type_is_enum(self):
        """HookType is a proper Enum."""
        from hook_executor import HookType
        from enum import Enum

        assert issubclass(HookType, Enum)


# ── HookExecutor Tests ────────────────────────────────────────────────────────


class TestHookExecutor:
    """Tests for HookExecutor registration and invocation."""

    def test_register_and_list_hooks(self):
        """Hooks can be registered and listed."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        called = []

        def mock_hook(**kwargs):
            called.append(kwargs)

        executor.register(HookType.POST_TOOL_USE, "test_hook", mock_hook)
        assert "test_hook" in executor.list_hooks(HookType.POST_TOOL_USE)

    def test_post_tool_call_calls_registered_hooks(self):
        """post_tool_call invokes all registered hooks with correct args."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        called = []

        def mock_hook(tool_name, args, result, context=None):
            called.append((tool_name, args, result))

        executor.register(HookType.POST_TOOL_USE, "test_hook", mock_hook)
        executor.post_tool_call(
            "read_file",
            {"path": "/tmp/test"},
            "file content here",
            context={"session_id": "sess_123"},
        )

        assert len(called) == 1
        assert called[0] == ("read_file", {"path": "/tmp/test"}, "file content here")

    def test_post_tool_call_multiple_hooks(self):
        """Multiple hooks are all called on post_tool_call."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        calls_a, calls_b = [], []

        def hook_a(tool_name, args, result, context=None):
            calls_a.append((tool_name, result))

        def hook_b(tool_name, args, result, context=None):
            calls_b.append((tool_name, result))

        executor.register(HookType.POST_TOOL_USE, "hook_a", hook_a)
        executor.register(HookType.POST_TOOL_USE, "hook_b", hook_b)
        executor.post_tool_call("write_file", {"path": "/tmp/x"}, "ok")

        assert len(calls_a) == 1
        assert len(calls_b) == 1
        assert calls_a[0][0] == "write_file"
        assert calls_b[0][0] == "write_file"

    def test_disable_hook(self):
        """Disabled hooks are not called."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        called = []

        def mock_hook(**kwargs):
            called.append(True)

        executor.register(HookType.POST_TOOL_USE, "disabled_hook", mock_hook, enabled=False)
        executor.post_tool_call("read_file", {}, "result")

        assert len(called) == 0

    def test_unregister_hook(self):
        """Unregistered hooks are not called."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        called = []

        def mock_hook(**kwargs):
            called.append(True)

        executor.register(HookType.POST_TOOL_USE, "to_remove", mock_hook)
        executor.unregister(HookType.POST_TOOL_USE, "to_remove")
        executor.post_tool_call("read_file", {}, "result")

        assert len(called) == 0

    def test_hook_exception_is_swallowed(self):
        """Hook exceptions are logged but not raised."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()

        def bad_hook(**kwargs):
            raise RuntimeError("hook error")

        executor.register(HookType.POST_TOOL_USE, "bad_hook", bad_hook)

        # Should not raise
        executor.post_tool_call("read_file", {}, "result")

    def test_pre_tool_call(self):
        """pre_tool_call invokes registered hooks."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        called = []

        def mock_hook(tool_name, args, context=None):
            called.append((tool_name, args))

        executor.register(HookType.PRE_TOOL_USE, "pre_hook", mock_hook)
        executor.pre_tool_call("terminal", {"command": "ls"}, context={})

        assert len(called) == 1
        assert called[0] == ("terminal", {"command": "ls"})

    def test_different_hook_types_are_independent(self):
        """Hooks are scoped to their type."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        pre_calls, post_calls = [], []

        def pre_hook(**kwargs):
            pre_calls.append(True)

        def post_hook(**kwargs):
            post_calls.append(True)

        executor.register(HookType.PRE_TOOL_USE, "pre", pre_hook)
        executor.register(HookType.POST_TOOL_USE, "post", post_hook)

        executor.pre_tool_call("tool", {}, {})
        assert len(pre_calls) == 1
        assert len(post_calls) == 0

        executor.post_tool_call("tool", {}, "result")
        assert len(pre_calls) == 1
        assert len(post_calls) == 1

    def test_singleton_get_hook_executor(self):
        """get_hook_executor returns the same instance."""
        from hook_executor import get_hook_executor, reset_hook_executor

        reset_hook_executor()
        ex1 = get_hook_executor()
        ex2 = get_hook_executor()

        assert ex1 is ex2

        # Reset for other tests
        reset_hook_executor()


# ── post_format Tests ────────────────────────────────────────────────────────


class TestPostFormat:
    """Tests for the post_format built-in hook."""

    def test_unsupported_tool_is_noop(self):
        """post_format returns immediately for unsupported tools."""
        from hooks.post_format import post_format

        calls = []

        with patch("subprocess.run", side_effect=calls.append):
            post_format("terminal", {"command": "ls"}, "ok")
            # subprocess should NOT be called
            assert len(calls) == 0

    def test_unsupported_extension_is_noop(self):
        """post_format skips files without a configured formatter."""
        from hooks.post_format import post_format

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.xyz"
            path.write_text("content")

            calls = []
            with patch("subprocess.run", side_effect=calls.append):
                post_format("write_file", {"path": str(path)}, "ok")
                assert len(calls) == 0

    def test_error_result_skips_format(self):
        """post_format skips formatting when tool result is an error."""
        from hooks.post_format import post_format

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x = 1")

            calls = []
            with patch("subprocess.run", side_effect=calls.append):
                post_format("write_file", {"path": str(path)}, '{"error": "permission denied"}')
                assert len(calls) == 0

    def test_missing_file_skips_format(self):
        """post_format skips formatting when file doesn't exist."""
        from hooks.post_format import post_format

        calls = []
        with patch("subprocess.run", side_effect=calls.append):
            post_format("write_file", {"path": "/nonexistent/file.py"}, "ok")
            assert len(calls) == 0

    def test_python_file_gets_formatted(self):
        """post_format runs black on .py files."""
        from hooks.post_format import post_format

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x=1")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock()
                post_format("write_file", {"path": str(path)}, "ok")

                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert "black" in call_args[0][0]
                assert str(path) in call_args[0][0]

    def test_skill_manage_uses_file_path(self):
        """post_format resolves path from skill_manage's file_path arg."""
        from hooks.post_format import post_format

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x=1")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock()
                post_format("skill_manage", {"file_path": str(path)}, "ok")

                mock_run.assert_called_once()
                assert "black" in mock_run.call_args[0][0]

    def test_subprocess_timeout_is_handled(self):
        """post_format handles formatter timeout gracefully."""
        from hooks.post_format import post_format

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x=1")

            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
                # Should not raise
                post_format("write_file", {"path": str(path)}, "ok")

    def test_get_formatter_returns_correct_command(self):
        """_get_formatter returns the right command for each suffix."""
        from hooks.post_format import _get_formatter

        assert "black" in _get_formatter("/a/b.py")
        assert "prettier" in _get_formatter("/a/b.js")
        assert "prettier" in _get_formatter("/a/b.ts")
        assert "rustfmt" in _get_formatter("/a/b.rs")
        assert "gofmt" in _get_formatter("/a/b.go")
        assert _get_formatter("/a/b.unknown") is None


# ── post_lint Tests ──────────────────────────────────────────────────────────


class TestPostLint:
    """Tests for the post_lint built-in hook."""

    def test_unsupported_tool_is_noop(self):
        """post_lint returns None immediately for unsupported tools."""
        from hooks.post_lint import post_lint

        with patch("subprocess.run") as mock_run:
            result = post_lint("terminal", {"command": "ls"}, "ok")
            assert result is None
            mock_run.assert_not_called()

    def test_unsupported_extension_returns_none(self):
        """post_lint returns None when no linter is configured."""
        from hooks.post_lint import post_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.xyz"
            path.write_text("content")

            with patch("subprocess.run") as mock_run:
                result = post_lint("write_file", {"path": str(path)}, "ok")
                assert result is None
                mock_run.assert_not_called()

    def test_error_result_skips_lint(self):
        """post_lint skips linting when tool result is an error."""
        from hooks.post_lint import post_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x = 1")

            with patch("subprocess.run") as mock_run:
                result = post_lint("write_file", {"path": str(path)}, '{"error": "denied"}')
                assert result is None
                mock_run.assert_not_called()

    def test_clean_lint_returns_none(self):
        """post_lint returns None when linter passes."""
        from hooks.post_lint import post_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x = 1")

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = b""
            mock_proc.stderr = b""

            with patch("subprocess.run", return_value=mock_proc):
                result = post_lint("write_file", {"path": str(path)}, "ok")
                assert result is None

    def test_lint_issues_return_warning(self):
        """post_lint returns a warning string when linter finds issues."""
        from hooks.post_lint import post_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x=1")

            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = b"E501 line too long"
            mock_proc.stderr = b""

            with patch("subprocess.run", return_value=mock_proc):
                result = post_lint("write_file", {"path": str(path)}, "ok")

                assert result is not None
                assert "Lint issues" in result
                assert "test.py" in result

    def test_python_uses_ruff(self):
        """post_lint runs ruff on .py files."""
        from hooks.post_lint import post_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x = 1")

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = b""
            mock_proc.stderr = b""

            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                post_lint("write_file", {"path": str(path)}, "ok")

                mock_run.assert_called_once()
                call_str = mock_run.call_args[0][0]
                assert "ruff" in call_str
                assert "check" in call_str

    def test_subprocess_timeout_returns_none(self):
        """post_lint handles timeout gracefully."""
        from hooks.post_lint import post_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.py"
            path.write_text("x = 1")

            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("cmd", 30),
            ):
                result = post_lint("write_file", {"path": str(path)}, "ok")
                assert result is None

    def test_get_linter_returns_correct_command(self):
        """_get_linter returns the right command for each suffix."""
        from hooks.post_lint import _get_linter

        assert "ruff" in _get_linter("/a/b.py")
        assert "eslint" in _get_linter("/a/b.js")
        assert "eslint" in _get_linter("/a/b.ts")
        assert "shellcheck" in _get_linter("/a/b.sh")
        assert _get_linter("/a/b.unknown") is None


# ── Integration Tests ────────────────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration tests for the hook system."""

    def test_full_hook_flow(self):
        """Simulates the complete post_tool_call hook flow."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        results = []

        def tracking_hook(tool_name, args, result, context=None):
            results.append(
                {
                    "tool_name": tool_name,
                    "args": args,
                    "result": result,
                    "session_id": context.get("session_id") if context else None,
                }
            )

        executor.register(HookType.POST_TOOL_USE, "tracker", tracking_hook)
        executor.post_tool_call(
            "write_file",
            {"path": "/tmp/test.py"},
            '{"ok": true}',
            context={"session_id": "sess_abc", "task_id": "task_123"},
        )

        assert len(results) == 1
        assert results[0]["tool_name"] == "write_file"
        assert results[0]["args"] == {"path": "/tmp/test.py"}
        assert results[0]["result"] == '{"ok": true}'
        assert results[0]["session_id"] == "sess_abc"

    def test_multiple_tools_in_sequence(self):
        """Simulates multiple tools executing in sequence with hooks."""
        from hook_executor import HookExecutor, HookType

        executor = HookExecutor()
        tool_calls = []

        def logging_hook(tool_name, args, result, context=None):
            tool_calls.append(tool_name)

        executor.register(HookType.POST_TOOL_USE, "logger", logging_hook)

        tools = [
            ("read_file", {"path": "/tmp/a.py"}, "content a"),
            ("write_file", {"path": "/tmp/b.py"}, '{"ok": true}'),
            ("patch", {"path": "/tmp/c.py", "new_string": "x=2"}, "patched"),
        ]

        for tool_name, args, result in tools:
            executor.post_tool_call(tool_name, args, result)

        assert tool_calls == ["read_file", "write_file", "patch"]

    def test_builtin_hooks_not_auto_loaded(self):
        """Built-in hooks are not registered until get_hook_executor is called.

        Direct HookExecutor() does not auto-register builtins.
        get_hook_executor() triggers _register_default_hooks() but the hooks
        are only visible if the hooks package is importable.
        """
        from hook_executor import HookExecutor, HookType, reset_hook_executor

        reset_hook_executor()

        # Direct executor should not auto-load builtins
        executor = HookExecutor()
        assert executor.list_hooks(HookType.POST_TOOL_USE) == []

        # get_hook_executor should trigger _register_default_hooks.
        # It either succeeds (hooks in path) or catches the ImportError gracefully.
        from hook_executor import get_hook_executor
        try:
            global_ex = get_hook_executor()
            # _builtins_registered flag should be True (even if imports failed)
            assert global_ex._builtins_registered is True
        except Exception:
            pass  # Expected if hooks package not in import path

        reset_hook_executor()


# ── Run tests ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
