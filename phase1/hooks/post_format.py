"""
post_format — PostToolUse hook: auto-format code files after write operations.

Implements the ECC-style automatic formatting hook that runs a code formatter
after write_file, patch, or file operations on supported file types.

This hook is intentionally lightweight — it skips if no formatter is configured
for a file type, and failures are non-fatal (logged but not raised).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Tools whose args carry a path to a file that may need formatting
SUPPORTED_TOOLS = {"write_file", "patch", "skill_manage"}

# Map file suffix → formatter command template
# {path} is replaced with the actual file path at runtime
FORMATTERS: Dict[str, str] = {
    ".py": "black --quiet {path}",
    ".js": "prettier --write --plugin=prettier {path}",
    ".ts": "prettier --write --plugin=prettier {path}",
    ".jsx": "prettier --write --plugin=prettier {path}",
    ".tsx": "prettier --write --plugin=prettier {path}",
    ".rs": "rustfmt --quiet {path}",
    ".go": "gofmt -w {path}",
    ".java": "google-java-format -quiet -i {path}",
    ".cs": "dotnet format --quiet {path}",
    ".css": "prettier --write --plugin=prettier {path}",
    ".scss": "prettier --write --plugin=prettier {path}",
    ".json": "prettier --write --plugin=prettier {path}",
    ".yaml": "prettier --write --plugin=prettier {path}",
    ".yml": "prettier --write --plugin=prettier {path}",
    ".md": "prettier --write --plugin=prettier {path}",
    ".sh": "shfmt -i 2 -w {path}",
    ".tf": "terraform fmt {path}",
}


def _get_formatter(path: str) -> Optional[str]:
    """Return the formatter command for a file path, or None if unsupported."""
    suffix = Path(path).suffix
    result: Optional[str] = FORMATTERS.get(suffix)
    return result


def post_format(
    tool_name: str,
    args: Dict[str, Any],
    result: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    PostToolUse hook: auto-format a file after a write operation.

    Args:
        tool_name: Name of the tool that was called.
        args: Tool arguments (must contain 'path' for supported tools).
        result: The tool's result string.
        context: Optional context dict (session_id, task_id, etc.).

    Returns:
        None. Failures are logged but never raised.
    """
    if tool_name not in SUPPORTED_TOOLS:
        return

    # Determine the path from tool args
    path = _resolve_path(tool_name, args)
    if not path:
        return

    # Check the file actually exists (skip if result was an error)
    if _is_error_result(result):
        return

    path_obj = Path(path)
    if not path_obj.exists() or not path_obj.is_file():
        return

    formatter_cmd = _get_formatter(path)
    if not formatter_cmd:
        return

    formatted_cmd = formatter_cmd.format(path=path)
    try:
        logger.debug("post_format: running '%s'", formatted_cmd)
        subprocess.run(
            formatted_cmd,
            shell=True,
            capture_output=True,
            timeout=30,
            check=False,  # Non-fatal — log but don't fail
        )
    except subprocess.TimeoutExpired:
        logger.warning("post_format: formatter timed out for %s", path)
    except Exception as exc:
        logger.warning("post_format: failed to format %s: %s", path, exc)


def _resolve_path(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    """Resolve the file path from tool arguments."""
    # write_file uses "path"
    # patch uses "path"
    # skill_manage (write/patch mode) uses "file_path"
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
