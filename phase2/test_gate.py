"""
Tests for Phase 2 Verification Gates.

Run with: cd ~/.hermes/ecc-to-hermes-loop/phase2 && python -m pytest test_gates.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure gates/ is importable
sys.path.insert(0, str(Path(__file__).parent))
from gates import GateInput, GateResult, GateStatus

# Import gate functions
from gates.build import build_gate
from gates.diff import diff_gate
from gates.lint import lint_gate
from gates.security import security_gate
from gates.type import type_gate
from gates.pytest_gate import execute_pytest_gate


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def project_root(tmp_path):
    """A minimal fake project root."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    return tmp_path


@pytest.fixture
def gate_input(project_root):
    """Standard GateInput for all gates."""
    return GateInput(project_root=project_root)


# ─── Build Gate Tests ───────────────────────────────────────────────────────

class TestBuildGate:
    def test_build_gate_returns_result(self, gate_input):
        result = build_gate(gate_input)
        assert isinstance(result, GateResult)
        assert hasattr(result, "status")
        assert hasattr(result, "gate")

    def test_build_gate_no_build_tool(self, gate_input):
        """When no build tool is found, gate should pass/warn (not fail)."""
        with patch("shutil.which", return_value=None):
            result = build_gate(gate_input)
        # Python compile check always runs → should pass
        assert result.status in (GateStatus.PASS, GateStatus.WARN)

    def test_build_gate_compiles_python(self, gate_input):
        """A Python file that compiles cleanly passes build."""
        result = build_gate(gate_input)
        assert result.status in (GateStatus.PASS, GateStatus.WARN, GateStatus.SKIP)


# ─── Diff Gate Tests ─────────────────────────────────────────────────────────

class TestDiffGate:
    def test_diff_gate_returns_result(self, gate_input):
        result = diff_gate(gate_input)
        assert isinstance(result, GateResult)

    def test_diff_gate_no_changes(self, gate_input):
        """No changed files → skip."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = diff_gate(gate_input)
        assert result.status in (GateStatus.PASS, GateStatus.SKIP)


# ─── Lint Gate Tests ────────────────────────────────────────────────────────

class TestLintGate:
    def test_lint_gate_returns_result(self, gate_input):
        result = lint_gate(gate_input)
        assert isinstance(result, GateResult)

    def test_lint_gate_no_linter(self, gate_input):
        """No linter found → skip."""
        with patch("shutil.which", return_value=None):
            result = lint_gate(gate_input)
        assert result.status == GateStatus.SKIP


# ─── Security Gate Tests ─────────────────────────────────────────────────────

class TestSecurityGate:
    def test_security_gate_returns_result(self, gate_input):
        result = security_gate(gate_input)
        assert isinstance(result, GateResult)

    def test_security_gate_no_scanner(self, gate_input):
        """No SAST scanner found → pass (semgrep not installed = OK)."""
        with patch("shutil.which", return_value=None):
            result = security_gate(gate_input)
        # security_gate returns PASS with skip message when semgrep not found
        assert result.status in (GateStatus.PASS, GateStatus.SKIP)


# ─── Type Gate Tests ────────────────────────────────────────────────────────

class TestTypeGate:
    def test_type_gate_returns_result(self, gate_input):
        result = type_gate(gate_input)
        assert isinstance(result, GateResult)

    def test_type_gate_no_typechecker(self, gate_input):
        """No type checker found → skip."""
        with patch("shutil.which", return_value=None):
            result = type_gate(gate_input)
        assert result.status == GateStatus.SKIP


# ─── Pytest Gate Tests ──────────────────────────────────────────────────────

class TestPytestGate:
    def test_execute_pytest_gate_returns_result(self, gate_input):
        result = execute_pytest_gate(gate_input)
        assert isinstance(result, GateResult)


# ─── GateInput Tests ─────────────────────────────────────────────────────────

class TestGateInput:
    def test_changed_py_files(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "a.py").touch()
        (root / "b.sh").touch()
        (root / "c.ts").touch()
        inp = GateInput(project_root=root, changed_files=[
            root / "a.py", root / "b.sh", root / "c.ts"
        ])
        assert inp.changed_py_files() == [root / "a.py"]
        assert inp.changed_sh_files() == [root / "b.sh"]

    def test_changed_js_files(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "a.js").touch()
        (root / "b.tsx").touch()
        (root / "c.py").touch()
        inp = GateInput(project_root=root, changed_files=[
            root / "a.js", root / "b.tsx", root / "c.py"
        ])
        assert len(inp.changed_js_files()) == 2


# ─── GateResult Dataclass ───────────────────────────────────────────────────

class TestGateResult:
    def test_gate_result_creation(self):
        result = GateResult(
            gate="test",
            status=GateStatus.PASS,
            duration_s=0.1,
            messages=("ok",),
            metadata={},
        )
        assert result.gate == "test"
        assert result.status == GateStatus.PASS
        assert result.duration_s == 0.1
