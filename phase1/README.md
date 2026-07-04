# Phase 1: PostToolUse Hook — Deliverables

## What This Is

Phase 1 implements the **PostToolUse Hook** pattern from ECC (Everyting-Claude-Code) in the Hermes codebase.

## Quick Start

```bash
# Run tests
cd ~/.hermes/ecc-to-hermes-loop/phase1
pytest test_post_tool_call_hook.py -v

# Use HookExecutor in Python code
from hook_executor import HookExecutor, HookType

executor = HookExecutor()
executor.register(HookType.POST_TOOL_USE, "my_hook", my_callback)
executor.post_tool_call("write_file", {"path": "/tmp/x.py"}, "x = 1")
```

## Architecture

```
Hermes Plugin System (hermes_cli/plugins.py)
    │
    ├── VALID_HOOKS = {"pre_tool_call", "post_tool_call", ...}
    ├── invoke_hook("post_tool_call", ...)  ← already wired
    │
HookExecutor (phase1/hook_executor.py)     ← NEW
    ├── register(disable/unregister)
    ├── post_tool_call() / pre_tool_call()
    └── _register_default_hooks() → post_format, post_lint
            │
            hooks/
            ├── post_format.py  ← runs black/prettier/rustfmt
            └── post_lint.py    ← runs ruff/eslint/shellcheck
```

## Hook Type Coverage

| Hook Type | Status | Where it fires |
|-----------|--------|---------------|
| `pre_tool_call` | ✅ Already wired | `model_tools.py:get_pre_tool_call_block_message()` |
| `post_tool_call` (plugin) | ✅ Already wired | `model_tools.py:_emit_post_tool_call_hook()` |
| `post_tool_call` (Python) | ✅ Implemented | `HookExecutor.post_tool_call()` |
| `post_format` | ✅ Implemented | `hooks/post_format.py` |
| `post_lint` | ✅ Implemented | `hooks/post_lint.py` |

## Files

- `hook_executor.py` — `HookType` enum + `HookExecutor` class
- `hooks/post_format.py` — auto-format after write
- `hooks/post_lint.py` — lint check after write
- `integration_patch.py` — where to wire into AIAgent loop
- `test_post_tool_call_hook.py` — 30 tests (all passing)
- `STATE.md` — implementation state and findings

## Test Results

```
30 passed in 0.09s
```
