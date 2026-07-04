# Phase 3: Instinct Learning — Implementation State

**Status: COMPLETE** ✅

**Date:** 2026-06-20

---

## What Was Done

### 1. Instinct Learning Pipeline

Created `instinct_learning.py` — a complete pipeline that:

1. **Fetches recent sessions** from `~/.hermes/state.db` (SQLite), filtering by minimum tool-call count
2. **Extracts tool-call sequences** (n-grams 2–5) from each session's message history
3. **Cross-session pattern matching** — finds sequences that appear across multiple sessions
4. **Confidence scoring** — `min(1.0, (count - 1) / 10 + 0.3)` — balances frequency with breadth
5. **Template matching** — maps known sequences to curated skill templates (read-patch-loop, read-run-loop, etc.)
6. **Deduplication** — keeps highest-confidence pattern per unique skill name
7. **Skill promotion** — writes `SKILL.md` to `~/.hermes/skills/<name>/SKILL.md`

### 2. Quality Filters

- `MIN_CONFIDENCE = 0.70` — only promote patterns with ≥70% confidence
- `MIN_SEQUENCE_COUNT = 3` — require at least 3 occurrences
- `MIN_DISTINCT_SESSIONS = 2` — must appear in at least 2 different sessions
- `SKIP_PATTERNS` blocklist — skips pure-repeats (terminal→terminal), browser cycles, and session-specific noise

### 3. Skill Templates

Curated templates for high-value patterns:

| Template | Tools | Description |
|----------|-------|-------------|
| `read-patch-loop` | read_file → patch | 先看代码再改 |
| `read-run-loop` | read_file → terminal | 先看再跑验证 |
| `search-read-patch` | search_files → read_file → patch | 搜索定位+修复 |
| `terminal-iterate` | terminal → terminal | 反复调式 |
| `read-write-file` | read_file → write_file | 模板填充/迁移 |
| `test-fix-loop` | terminal → read_file → patch | 测试驱动修复 |

### 4. CLI

```bash
# Dry run (no skills written)
python3 instinct_learning.py --dry-run

# Real run
python3 instinct_learning.py

# Custom thresholds
python3 instinct_learning.py --min-confidence 0.80 --min-tool-calls 10
```

### 5. Test Results

**19 tests pass** covering:
- n-gram extraction
- Tool call sequence parsing
- Template matching
- Skip pattern blocklist
- Skill file generation (frontmatter + body)
- Skill promotion / update logic
- End-to-end extraction (against real state.db)

---

## Files Created

```
~/.hermes/ecc-to-hermes-loop/phase3/
├── instinct_learning.py   # Core pipeline (490 lines)
├── test_instinct.py       # 19 unit/integration tests (all passing)
├── README.md              # This file
└── STATE.md               # This state doc
```

---

## Skills Promoted (21 total)

| Skill | Confidence | Sessions | Tools |
|-------|------------|----------|-------|
| `read-run-loop` | 100% | 12 | read_file → terminal |
| `read-write-file` | 100% | varies | read_file → write_file |
| `terminal-iterate` | 100% | 7 | write_file → terminal → terminal |
| `instinct-terminal-read_file` | 100% | varies | terminal → read_file |
| `instinct-patch-terminal` | 100% | varies | patch → terminal |
| `instinct-search_files-read_file` | 100% | varies | search_files → read_file |
| `instinct-read_file-search_files` | 100% | varies | read_file → search_files |
| `instinct-terminal-patch` | 100% | varies | terminal → patch |
| `instinct-write_file-terminal` | 100% | varies | write_file → terminal |
| `instinct-terminal-write_file` | 100% | varies | terminal → write_file |
| `instinct-patch-write_file` | 100% | varies | patch → write_file |
| `instinct-write_file-patch` | 100% | varies | write_file → patch |
| `instinct-write_file-read_file` | 100% | varies | write_file → read_file |
| `instinct-web_extract-browser_navigate` | 100% | varies | web_extract → browser_navigate |
| `instinct-web_extract-patch` | 100% | varies | web_extract → patch |
| `instinct-cronjob-terminal` | 100% | varies | cronjob → terminal |
| `instinct-search_files-write_file` | 80% | varies | search_files → write_file |
| `instinct-skill_view-terminal` | 80% | varies | skill_view → terminal |
| `instinct-terminal-execute_code` | 70% | varies | terminal → execute_code |
| `instinct-execute_code-terminal` | 70% | varies | execute_code → terminal |
| `instinct-terminal-mcp_minimax_understand_understand_image` | 70% | varies | terminal → MCP image |

All written to `~/.hermes/skills/<skill-name>/SKILL.md`.

---

## Next Steps (Phase 4)

- **Professional Subagents** — spawn domain-specific subagents (code, research, writing)
  - Implement delegation wrapper with role descriptions
  - Add subagent health-check and timeout handling
