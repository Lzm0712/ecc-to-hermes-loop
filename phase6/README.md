# Phase 6: Evaluator RAG — Retrieval-Augmented Evaluation Loop

**Status: COMPLETE** ✅

**Date:** 2026-06-20

---

## What Was Done

### Evaluator RAG Loop

Implemented the final phase of the ECC-to-Hermes Loop — a **self-referential improvement engine** that retrieves past successful sessions and evaluates whether the current approach will likely succeed.

### Architecture

**3 core components:**

1. **`SessionRetriever`** — Queries `~/.hermes/state.db` for similar past sessions
   - FTS5 full-text search on session content
   - Tool-sequence extraction from message history
   - Pattern detection (read-patch-loop, terminal-iterate, etc.)
   - Jaccard-based similarity scoring

2. **`EvaluatorRAG`** — Evaluates current task against retrieved baselines
   - 5 weighted metrics: baseline_quality, tool_overlap, pattern_coverage, baseline_success_rate, tool_diversity
   - Verdict: `likely_succeed` (≥0.70) | `uncertain` (0.45–0.70) | `likely_fail` (<0.45)
   - Actionable `Recommendation` objects per category

3. **`EvaluationResult`** — Portable, versioned JSON output
   - All metrics, recommendations, retrieved sessions, improvement hints
   - `build_hud_status()` integrates with Phase 5 HUD schema

### CLI

```bash
# Human-readable evaluation
python3 phase6.py --query "fix authentication bug" --tools read_file patch terminal

# JSON output (for external consumers / cron)
python3 phase6.py --query "fix authentication bug" --tools read_file patch terminal --json

# Verdict only (for automation / CI gates)
python3 phase6.py --verdict-only
# → likely_succeed | uncertain | likely_fail

# Export to file
python3 phase6.py --export /tmp/evaluation.json

# Feed current HUD state for deep comparison
python3 phase6.py --state ~/.hermes/hud_status.json --json
```

### Schema

**EvaluationResult:**
```json
{
  "version": "1.0.0",
  "generated_at": 1234567890.0,
  "query": "fix authentication bug",
  "current_tools": ["read_file", "patch", "terminal"],
  "baseline_sessions_found": 3,
  "overall_score": 0.72,
  "overall_verdict": "likely_succeed",
  "metrics": [
    {"name": "baseline_quality", "value": 0.80, "weight": 0.20, "details": "..."},
    {"name": "tool_overlap", "value": 0.65, "weight": 0.35, "details": "..."},
    ...
  ],
  "recommendations": [
    {"priority": "high", "category": "tool-pattern", "message": "...", "suggested_tools": ["..."]}
  ],
  "retrieved_sessions": [...],
  "improvement_hints": ["Top baseline used tools: [...]", "Key pattern: ..."]
}
```

---

## Files Created

```
~/.hermes/ecc-to-hermes-loop/phase6/
├── phase6.py         # Core: SessionRetriever, EvaluatorRAG, EvaluationResult, CLI
├── test_phase6.py    # 32 unit tests (all passing)
├── README.md         # This file
└── STATE.md          # Phase completion state
```

---

## Tests

**32 tests pass** covering:
- All dataclass fields and defaults
- Pattern detection (6 patterns: read-patch-loop, read-run-loop, search-read-patch, terminal-iterate, read-write-file, research-loop)
- SessionRetriever: similarity scoring, empty DB handling
- EvaluatorRAG: verdict mapping, weighted score, recommendation generation, hints
- Serialization: dict roundtrips
- CLI: JSON output, verdict-only, human output

---

## Phase Completion Criteria ✅

Per Phase 6 spec: "Evaluator RAG — 自改进循环"

✅ Implemented:
- `SessionRetriever` queries session DB for similar past sessions
- `EvaluatorRAG.evaluate()` produces score + verdict + recommendations
- 5 weighted evaluation metrics
- Pattern detection for known instinct patterns
- Recommendation engine with priority levels
- CLI with `--json`, `--verdict-only`, `--export`
- 32 tests pass

---

## Closing the Loop

Phase 6 closes the full ECC-to-Hermes Loop:

```
PostToolUse Hook (P1) ──→ Verification Loop (P2) ──→ Instinct Learning (P3)
                                                              ↓
                                            Subagents (P4) ←┘
                                                              ↓
                                              HUD Status Contract (P5)
                                                              ↓
                                              Evaluator RAG (P6) ← self-ref
```

The evaluator can now query past successful sessions and recommend whether the current approach will work — completing the self-referential improvement cycle.
