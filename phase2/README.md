# Phase 2: Verification Loop — 6-Stage Gate System

**Status: COMPLETE** ✅

**Date:** 2026-06-20

---

## What Was Done

### 6-Stage Sequential Gate System

Implemented a pluggable gate pipeline that runs **Build → Type → Lint → Test → Security → Diff** in sequence, collecting results from each stage before returning an aggregated report.

| Gate | Function | Required | Description |
|------|----------|----------|-------------|
| `build` | `build_gate` | ✅ | Compile Python + run build system (setuptools/pyproject) |
| `type` | `type_gate` | ❌ | Run mypy type checker |
| `lint` | `lint_gate` | ✅ | Run ruff + shellcheck linters |
| `test` | `execute_pytest_gate` | ✅ | Run pytest suite (imported as `_test_gate` to avoid pytest collection) |
| `security` | `security_gate` | ❌ | Run pip-audit + semgrep |
| `diff` | `diff_gate` | ❌ | Summarize changes vs HEAD |

### Bug Fixed: pytest Import Collision

**Problem:** `pytest` would import `test_gate.py` (the test file itself), causing collection failures.

**Solution:** Renamed the gate module to `pytest_gate.py`; import it with underscore prefix `_test_gate` so pytest never sees the bare name `test_gate`.

Files updated:
- `gates/pytest_gate.py` (renamed from `run_gate.py`)
- `conftest.py` (removed all gate imports)
- `test_gates.py` (imports `_test_gate` from `gates.pytest_gate`)
- `verification_loop.py` (uses `_test_gate` alias)

### Key Dataclasses

| Class | Purpose |
|-------|---------|
| `GateInput` | Context passed to every gate: `project_root`, `changed_files`, `diff_against` |
| `Gate` | NamedTuple: `(name, description, fn, required)` |
| `GateResult` | Immutable result: `gate`, `status`, `messages`, `duration_s`, `metadata` |
| `VerificationReport` | Aggregated report with `as_dict()` / JSON serialization |

### JSON Output

The `VerificationLoop` report serializes to dict via `report.as_dict()`:

```json
{
  "all_passed": true,
  "summary": "5/6 gates passed",
  "total_duration_s": 12.345,
  "gates": [
    {"gate": "build", "status": "pass", "passed": true, ...},
    ...
  ]
}
```

---

## Architecture

```
verification_loop.py    # create_loop(), run(), CLI
├── gates/
│   ├── __init__.py     # GateInput, GateResult, GateStatus, VerificationLoop
│   ├── build.py        # build_gate
│   ├── type.py         # type_gate
│   ├── lint.py         # lint_gate
│   ├── pytest_gate.py  # execute_pytest_gate (imported as _test_gate)
│   ├── security.py      # security_gate
│   └── diff.py         # diff_gate
├── conftest.py         # Empty (no gate imports — was the bug)
└── test_gates.py      # 17 tests
```

---

## Usage

**Python API:**
```python
from phase2.verification_loop import create_loop
from phase2.gates import GateInput
from pathlib import Path

loop = create_loop(Path("/path/to/repo"))
input = GateInput(project_root=Path("/path/to/repo"), changed_files=[...])
report = loop.run(input)
print(report.as_dict())
```

**CLI:**
```bash
python -m phase2.verification_loop --root /path/to/repo --changed-file src/foo.py --json
```

**Exit code:** 0 = all required gates passed; 1 = at least one required gate failed.

---

## Test Results

**17 tests pass** covering:
- All 6 gate function signatures
- GateInput helper methods (`changed_py_files`, `changed_sh_files`, etc.)
- VerificationLoop run/all-pass/summary/duration collection
- GateResult `passed` property (PASS/SKIP = true, FAIL/WARN = false)
- Report `as_dict()` serialization
- Diff gate self-check

---

## Files Created

```
~/.hermes/ecc-to-hermes-loop/phase2/
├── __init__.py          # Empty package marker
├── conftest.py          # Empty (avoids pytest importing gates)
├── pytest.ini           # pytest configuration
├── verification_loop.py # create_loop(), run(), CLI entry point
├── gates/
│   ├── __init__.py      # GateInput, GateResult, GateStatus, VerificationLoop
│   ├── build.py         # build_gate
│   ├── type.py          # type_gate
│   ├── lint.py          # lint_gate
│   ├── pytest_gate.py   # execute_pytest_gate (was run_gate.py)
│   ├── security.py      # security_gate
│   └── diff.py          # diff_gate
└── test_gates.py        # 17 unit tests (all passing)
```

---

## Phase Completion Criteria ✅

Per Phase 2 spec: "Verification Loop — 6-stage sequential gate system"

✅ Implemented:
- 6 gates: Build → Type → Lint → Test → Security → Diff
- All gates return `GateResult`
- `VerificationLoop.run()` aggregates results
- JSON output via `report.as_dict()`
- CLI with `--json` flag
- pytest import collision fixed
- 17 tests pass

---

## Next Steps (Phase 3)

- **Instinct Learning** — Extract tool-call patterns from sessions to auto-generate skills
