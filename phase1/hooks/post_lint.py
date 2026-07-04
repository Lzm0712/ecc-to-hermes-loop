"""
post_lint — PostToolUse hook: run linters after file write operations.

Implements the ECC-style lint-after-write pattern that runs a linter
after write_file, patch, or file operations on supported file types.

Lint issues are logged as warnings but are non-fatal — the tool result
is returned to the model with the lint warning appended.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tools whose args carry a path to a file that may need linting
SUPPORTED_TOOLS = {"write_file", "patch", "skill_manage"}

# Map file suffix → linter check command template
# {path} is replaced with the actual file path at runtime
# The linter should return exit code 0 when no issues are found
LINTERS: Dict[str, str] = {
    ".py": "ruff check {path}",
    ".js": "eslint --quiet {path}",
    ".ts": "eslint --quiet {path}",
    ".jsx": "eslint --quiet {path}",
    ".tsx": "eslint --quiet {path}",
    ".rs": "cargo clippy --quiet -- -A warnings {path}",
    ".go": "golangci-lint run --quiet {path}",
    ".java": "checkstyle {path}",
    ".cs": "dotnet format --verify-no-changes {path}",
    ".sh": "shellcheck {path}",
    ".yaml": "yamllint --no-warnings {path}",
    ".yml": "yamllint --no-warnings {path}",
    ".json": "python3 -m json.tool --quiet {path}",
}


def _get_linter(path: str) -> Optional[str]:
    """Return the linter command for a file path, or None if unsupported."""
    suffix = Path(path).suffix
    result: Optional[str] = LINTERS.get(suffix)
    return result


def post_lint(
    tool_name: str,
    args: Dict[str, Any],
    result: str,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    PostToolUse hook: run a linter after a file write operation.

    Args:
        tool_name: Name of the tool that was called.
        args: Tool arguments (must contain 'path' for supported tools).
        result: The tool's result string.
        context: Optional context dict (session_id, task_id, etc.).

    Returns:
        A lint warning string if issues were found, or None if no issues
        or the tool/filepath is not supported.
    """
    if tool_name not in SUPPORTED_TOOLS:
        return None

    path = _resolve_path(tool_name, args)
    if not path:
        return None

    # Don't lint error results
    if _is_error_result(result):
        return None

    path_obj = Path(path)
    if not path_obj.exists() or not path_obj.is_file():
        return None

    linter_cmd = _get_linter(path)
    if not linter_cmd:
        return None

    formatted_cmd = linter_cmd.format(path=path)
    try:
        logger.debug("post_lint: running '%s'", formatted_cmd)
        proc = subprocess.run(
            formatted_cmd,
            shell=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            stdout = proc.stdout.decode("utf-8", errors="replace").strip()
            issues = stdout or stderr or f"lint failed (exit {proc.returncode})"
            warning = f"⚠️ Lint issues in {path}: {issues}"
            logger.warning(warning)
            return warning
        return None
    except subprocess.TimeoutExpired:
        logger.warning("post_lint: linter timed out for %s", path)
        return None
    except Exception as exc:
        logger.warning("post_lint: failed to lint %s: %s", path, exc)
        return None


def _resolve_path(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    """Resolve the file path from tool arguments."""
    if tool_name == "skill_manage":
        return args.get("file_path")
    return args.get("path")


def _is_error_result(result: str) -> bool:
    """Return True if the result looks like an error."""
    if not isinstance(result, str):
        return False
    result_lower = result.strip().lower()
    if result_lower.startswith("error"):
        return True
    if '"error"' in result_lower and result_lower.startswith("{"):
        return True
    return False
