# Phase 5: HUD Status Contract

**Status: COMPLETE** ✅

**Date:** 2026-06-20

---

## What Was Done

### HUD Status Contract

Implemented a **portable, versioned JSON state payload** that `hermes status --json` can emit. External harness tools (ECC, cron jobs, dashboards, other agents) can query agent state without coupling to internal data structures.

### Schema Design

**Root payload (`HUDStatus`):**
```json
{
  "version": "1.0.0",
  "generated_at": 1234567890.0,
  "agent_id": "hermes-default",
  "health": "healthy|degraded|unknown",
  "vigilance_mode": "passive|guarded|vigilant",
  "loop_phase": "phase5_hud",
  "phases": [...],
  "current_phase": "phase6_evaluator_rag",
  "recent_actions": [...],
  "pending_tasks": [...],
  "recent_events": [...],
  "instinct_stats": {...},
  "subagent_stats": {...},
  "verification_stats": {...},
  "hints": {...}
}
```

### Dataclasses

| Dataclass | Purpose |
|-----------|---------|
| `HUDStatus` | Root payload — versioned, self-describing |
| `PhaseProgress` | Per-phase status: id, name, status, artifacts, test_results |
| `RecentAction` | Recent tool calls / decisions with timestamp, outcome, duration |
| `PendingTask` | Task queue item with priority, blockers |
| `HUDEvent` | Event-sourced log of significant phase transitions |
| `InstinctStats` | Skill count, high-confidence count, last extraction time |
| `SubagentStats` | Roles registered, dispatch counts, success rate |
| `VerificationStats` | Gates passed/failed/skipped, recent gate details |

### Enums

| Enum | Values |
|------|--------|
| `HealthStatus` | `healthy`, `degraded`, `unknown` |
| `LoopPhase` | All 6 ECC phases |
| `VigilanceMode` | `passive`, `guarded`, `vigilant` |

### Key Features

- **Versioned schema** (`HUD_VERSION = "1.0.0"`) — bump on breaking changes only
- **`build_hud_status()`** — main entry point, queries all subsystems
- **`to_json()` / `from_json()`** — full roundtrip serialization
- **`export_hud_to_file()`** — persist status snapshot for external consumers
- **`--json` CLI flag** — `python phase5.py --json` outputs raw payload
- **`--export PATH`** — save status to file
- **Health heuristic** — `healthy` if ≥60% phases complete, `degraded` otherwise
- **Extensible via `hints`** — arbitrary key-value pairs for forward compatibility

### Tests

**38 tests pass** across:
- Schema version, dataclass roundtrips, JSON serialization
- All enum values
- `build_hud_status()` integration (phases, health, subsystem stats)
- Export to file
- Schema extensibility

---

## Files Created

```
~/.hermes/ecc-to-hermes-loop/phase5/
├── phase5.py        # HUD Status Contract (HUDStatus, dataclasses, builder, CLI)
├── test_phase5.py   # 38 unit tests (all passing)
├── README.md        # This file
└── STATE.md         # This state doc
```

---

## Phase Completion Criteria ✅

Per Phase 5 spec: "HUD 状态契约 — 跨 harness 便携式状态负载"

✅ Implemented:
- `HUDStatus` root payload with versioned schema
- All subsystem dataclasses (PhaseProgress, RecentAction, PendingTask, HUDEvent, *_Stats)
- `build_hud_status()` queries phases, instincts, subagents, verification stats
- `to_json()` / `from_json()` roundtrip
- CLI with `--json` and `--export`
- 38 tests pass

---

## Next Steps (Phase 6)

- **Evaluator RAG** — Retrieval-augmented evaluation against archived successful sessions
