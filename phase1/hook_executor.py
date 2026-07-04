"""
HookExecutor — Python-level hook manager for Hermes PostToolUse hooks.

Wraps the plugin system's invoke_hook() with a higher-level API that lets
Python code (rather than just shell scripts) register and run hooks.

Architecture
------------
- HookType enum: PRE_TOOL_USE, POST_TOOL_USE, STOP
- HookExecutor: registers hooks, invokes hooks by type
- Built-in hooks: post_format, post_lint (registered on first use)

This module is NOT the plugin hook system itself — it builds on top of it,
providing a Python-native hook API that parallels the shell-hook bridge in
agent/shell_hooks.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HookType(Enum):
    """Hook event types that can be registered and invoked."""
    PRE_TOOL_USE = "pre_tool_call"
    POST_TOOL_USE = "post_tool_call"
    STOP = "stop"


@dataclass
class Hook:
    """A single registered hook callback."""
    name: str
    callback: Callable[..., None]
    enabled: bool = True
    hook_type: HookType = HookType.POST_TOOL_USE

    def execute(self, **kwargs: Any) -> None:
        """Execute the hook callback with the given kwargs."""
        if not self.enabled:
            return
        try:
            self.callback(**kwargs)
        except Exception as exc:
            logger.warning("Hook '%s' (%s) raised: %s", self.name, self.hook_type.value, exc)


@dataclass
class HookExecutor:
    """
    Manages Python-level hooks for Hermes.

    Complements the shell-hook bridge in agent/shell_hooks.py and the
    plugin system in hermes_cli/plugins.py.

    Usage::

        executor = HookExecutor()
        executor.register(HookType.POST_TOOL_USE, "my_hook", my_callback)
        executor.post_tool_call("read_file", {"path": "/tmp/test"}, "file content")

    Hooks can also be registered as "builtin" (post_format, post_lint)
    which are loaded lazily on first invocation.
    """
    _hooks: Dict[HookType, List[Hook]] = field(default_factory=lambda: {ht: [] for ht in HookType})
    _builtins_registered: bool = False

    # ── Registration ────────────────────────────────────────────────────────

    def register(
        self,
        hook_type: HookType,
        name: str,
        callback: Callable[..., None],
        enabled: bool = True,
    ) -> None:
        """Register a callback for a hook type."""
        hook = Hook(name=name, callback=callback, enabled=enabled, hook_type=hook_type)
        self._hooks[hook_type].append(hook)
        logger.debug("Registered hook '%s' for %s", name, hook_type.value)

    def register_builtin(self, hook_type: HookType, name: str, callback: Callable[..., None]) -> None:
        """Register a built-in hook (post_format, post_lint, etc.)."""
        self.register(hook_type, name, callback)

    def enable(self, hook_type: HookType, name: str) -> None:
        """Enable a hook by name."""
        for hook in self._hooks.get(hook_type, []):
            if hook.name == name:
                hook.enabled = True

    def disable(self, hook_type: HookType, name: str) -> None:
        """Disable a hook by name."""
        for hook in self._hooks.get(hook_type, []):
            if hook.name == name:
                hook.enabled = False

    def unregister(self, hook_type: HookType, name: str) -> None:
        """Remove a hook by name."""
        self._hooks[hook_type] = [h for h in self._hooks.get(hook_type, []) if h.name != name]

    def list_hooks(self, hook_type: HookType) -> List[str]:
        """Return names of registered hooks for a type."""
        return [h.name for h in self._hooks.get(hook_type, [])]

    # ── Built-in registration ─────────────────────────────────────────────

    def _register_default_hooks(self) -> None:
        """Load and register the built-in hooks (post_format, post_lint)."""
        if self._builtins_registered:
            return
        self._builtins_registered = True

        # Lazy import to avoid circular references and optional dependency overhead
        try:
            from .hooks import post_format
            self.register_builtin(HookType.POST_TOOL_USE, "post_format", post_format.post_format)
        except ImportError:
            logger.debug("post_format hook not available (hooks package not installed)")

        try:
            from .hooks import post_lint
            self.register_builtin(HookType.POST_TOOL_USE, "post_lint", post_lint.post_lint)
        except ImportError:
            logger.debug("post_lint hook not available (hooks package not installed)")

    # ── Invocation ────────────────────────────────────────────────────────

    def _get_hooks(self, hook_type: HookType) -> List[Hook]:
        """Return all enabled hooks for a type."""
        return [h for h in self._hooks.get(hook_type, []) if h.enabled]

    def post_tool_call(
        self,
        tool_name: str,
        args: dict,
        result: str,
        context: Optional[dict] = None,
    ) -> None:
        """
        Fire POST_TOOL_USE hooks after a tool executes.

        Args:
            tool_name: Name of the tool that was executed.
            args: Arguments passed to the tool.
            result: String result from the tool execution.
            context: Optional context dict with session_id, task_id, etc.
        """
        for hook in self._get_hooks(HookType.POST_TOOL_USE):
            try:
                hook.execute(
                    tool_name=tool_name,
                    args=args,
                    result=result,
                    context=context or {},
                )
            except Exception as exc:
                logger.warning(
                    "PostToolUse hook '%s' failed: %s",
                    hook.name,
                    exc,
                )

    def pre_tool_call(
        self,
        tool_name: str,
        args: dict,
        context: Optional[dict] = None,
    ) -> None:
        """
        Fire PRE_TOOL_USE hooks before a tool executes.

        Note: This is currently a no-op pass-through since pre_tool_call
        blocking is handled by the plugin system via get_pre_tool_call_block_message().
        This method exists for symmetry and future extensibility.
        """
        for hook in self._get_hooks(HookType.PRE_TOOL_USE):
            try:
                hook.execute(
                    tool_name=tool_name,
                    args=args,
                    context=context or {},
                )
            except Exception as exc:
                logger.warning(
                    "PreToolUse hook '%s' failed: %s",
                    hook.name,
                    exc,
                )


# ── Module-level singleton for agent use ──────────────────────────────────

_executor: Optional[HookExecutor] = None


def get_hook_executor() -> HookExecutor:
    """Return the global HookExecutor singleton."""
    global _executor
    if _executor is None:
        _executor = HookExecutor()
        _executor._register_default_hooks()
    return _executor


def reset_hook_executor() -> None:
    """Reset the global executor (for tests)."""
    global _executor
    _executor = None
