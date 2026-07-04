"""
Shared tool-sequence extraction for ECC-to-Hermes Loop.

Both Phase 3 (Instinct Learning) and Phase 6 (Evaluator RAG) need to
extract ordered tool names from message records. This module provides a
single canonical implementation so both phases parse the same format
the same way.

Phase 3: receives list[dict] message records (pre-parsed from DB)
Phase 6: receives raw message content strings (JSON-encoded)

Both ultimately call extract_tool_names() which handles the actual parsing.
"""

from __future__ import annotations

import json
import re
from typing import Optional

# Compiled regex for Phase 6's raw-content extraction (faster than json.loads on big strings)
_TOOL_NAME_RE = re.compile(r'"name"\s*:\s*"(\w+)"')


def extract_tool_names_from_content(content: str) -> list[str]:
    """
    Extract tool names from raw message content string (Phase 6 pattern).
    
    Handles the raw 'content' field that may contain JSON-encoded tool_calls.
    Falls back to regex extraction if JSON parsing fails.
    """
    if not content:
        return []
    
    tools = []
    
    # Fast path: try JSON parse of tool_calls portion
    try:
        # The content often contains a JSON object with tool_calls array
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            tool_calls = parsed.get("tool_calls") or parsed.get("tool_name", "")
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    if isinstance(call, dict):
                        name = call.get("function", {}).get("name") or call.get("name", "")
                        if name:
                            tools.append(name)
            elif isinstance(tool_calls, str) and tool_calls:
                tools.append(tool_calls)
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    name = item.get("function", {}).get("name") or item.get("name", "")
                    if name:
                        tools.append(name)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass  # fallback: skip malformed tool_calls, use regex extraction below
    
    # Fallback regex for when JSON parse didn't find anything
    if not tools:
        for match in _TOOL_NAME_RE.finditer(content):
            name = match.group(1)
            if name and name not in tools:
                tools.append(name)
    
    return tools


def extract_tool_names_from_messages(messages: list[dict]) -> list[str]:
    """
    Extract ordered tool names from pre-parsed message records (Phase 3 pattern).
    
    Each message dict has the shape stored in state.db messages table:
      {"role": "assistant", "tool_calls": "[{\"function\":{\"name\":\"read_file\"}}]", ...}
    or the legacy single-tool format:
      {"role": "assistant", "tool_name": "patch", ...}
    """
    sequence = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        
        # Support both field names that appear in our DB schema
        raw = msg.get("tool_calls") or msg.get("tool_name") or ""
        
        if not raw:
            continue
        
        if isinstance(raw, list):
            # Already parsed as list (shouldn't happen from DB but handle it)
            for call in raw:
                name = call.get("function", {}).get("name") if isinstance(call, dict) else call.get("name", "")
                if name:
                    sequence.append(name)
        elif isinstance(raw, str):
            if raw.startswith("["):
                # JSON array string from DB
                try:
                    calls = json.loads(raw)
                    for call in calls:
                        if isinstance(call, dict):
                            name = call.get("function", {}).get("name") or call.get("name", "")
                            if name:
                                sequence.append(name)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass  # fallback: skip malformed tool_calls, continue with other entries
            else:
                # Plain string tool name (legacy single-tool format)
                sequence.append(raw)
    
    return sequence
