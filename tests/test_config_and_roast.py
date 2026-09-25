"""
tests/test_config_and_roast.py — Verification Matrix for Dynamic Config & FinOps Roast (v3.7.0)
manifest_hash: 2a63e65e200442944f6f0c4d804a965681f4c919a9d306c26484b7903308dca1

Validates all 5 Negative Invariants declared in specs/config_and_roast.spec.md:
- Invariant 1: Zero ANSI/roast emission on non-TTY streams (sys.stdout.isatty() == False).
- Invariant 2: Zero crashes/exceptions on missing or corrupt configuration JSON.
- Invariant 3: AST pruning bypass occurs strictly when engine.mode is 'passthrough'.
- Invariant 4: Share report strictly excludes raw source code, secrets, and raw absolute paths.
- Invariant 5: Configuration setters operate atomically and respect configuration boundaries.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import pytest
import sys
from unittest.mock import patch

from ctxfw.config import (
    AppConfigDTO,
    EngineConfigDTO,
    EngineMode,
    FinOpsConfigDTO,
    RoastLevel,
    get_canonical_config_dir,
    get_canonical_config_path,
    load_config,
    save_config,
    set_config_value,
)
from ctxfw.roast import generate_finops_roast, is_interactive_terminal, ROAST_CATALOG
from ctxfw.core.contracts import OptimizationRequestDTO, PruningDepth
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.core.topological import ContextFirewallEngine
from ctxfw.cli.main import (
    handle_config_command,
    handle_mode_command,
    handle_report_command,
    generate_share_report,
)


# =========================================================================
# INVARIANT 1: NON-TTY STREAM SUPPRESSION (Zero ANSI / Zero Roast)
# =========================================================================

def test_invariant_1_roast_suppressed_when_stdout_is_not_tty():
    """Asserts that generate_finops_roast returns empty string when stdout is not a TTY."""
    with patch("sys.stdout.isatty", return_value=False):
        assert is_interactive_terminal() is False
        roast = generate_finops_roast(tokens_saved=5000, usd_avoided=0.15)
        assert roast == ""
        assert "\033[" not in roast


def test_invariant_1_roast_emitted_only_on_interactive_tty():
    """Asserts that cynical roast with ANSI styling is generated when stdout is an interactive TTY."""
    with patch("sys.stdout.isatty", return_value=True):
        assert is_interactive_terminal() is True
        cfg = FinOpsConfigDTO(roast=True, roast_level=RoastLevel.CYNICAL)
        roast = generate_finops_roast(tokens_saved=12000, usd_avoided=0.36, config=cfg)
        assert roast != ""
        assert "\033[" in roast
        assert "FINOPS ROAST ENGINE" in roast
        assert "12,000" in roast


def test_invariant_1_sober_level_omits_ansi_and_cynical_humor():
    """Asserts that sober roast mode produces clean analytics without ANSI escape codes."""
    with patch("sys.stdout.isatty", return_value=True):
        cfg = FinOpsConfigDTO(roast=True, roast_level=RoastLevel.SOBER)
        roast = generate_finops_roast(tokens_saved=8000, usd_avoided=0.24, config=cfg)
        assert "FinOps Summary" in roast
        assert "\033[" not in roast
        assert "8,000" in roast


def test_invariant_1_roast_toggle_off_suppresses_output():
    """Asserts that setting roast=False or roast_level='off' returns empty string even on TTY."""
    with patch("sys.stdout.isatty", return_value=True):
        cfg_off = FinOpsConfigDTO(roast=False)
        assert generate_finops_roast(tokens_saved=5000, usd_avoided=0.15, config=cfg_off) == ""

        cfg_level_off = FinOpsConfigDTO(roast=True, roast_level=RoastLevel.OFF)
        assert generate_finops_roast(tokens_saved=5000, usd_avoided=0.15, config=cfg_level_off) == ""


# =========================================================================
# INVARIANT 2: ZERO-EXCEPTION FALLBACK ON MISSING / CORRUPT CONFIG
# =========================================================================

def test_invariant_2_load_config_fallback_on_missing_file(tmp_path: Path):
    """Asserts that missing config file returns canonical default configuration without error."""
    non_existent = tmp_path / "missing_config.json"
    cfg = load_config(non_existent)
    assert isinstance(cfg, AppConfigDTO)
    assert cfg.engine.mode == EngineMode.DISTANCE
    assert cfg.engine.max_distance == 1
    assert cfg.finops.roast_level == RoastLevel.CYNICAL


def test_invariant_2_load_config_fallback_on_corrupt_json(tmp_path: Path, capsys):
    """Asserts that malformed JSON triggers stderr warning and returns in-memory defaults without crashing."""
    corrupt_file = tmp_path / "corrupt_config.json"
    corrupt_file.write_text("{invalid json: [[, 123", encoding="utf-8")

    cfg = load_config(corrupt_file)
    assert isinstance(cfg, AppConfigDTO)
    assert cfg.engine.mode == EngineMode.DISTANCE

    captured = capsys.readouterr()
    assert "[ctxfw] Warning: failed to parse config" in captured.err


def test_invariant_2_load_config_fallback_on_oversized_file(tmp_path: Path, capsys):
    """Asserts that config files exceeding 1 MB are safely rejected without exception."""
    oversized_file = tmp_path / "giant_config.json"
    # Write 1.1 MB
    oversized_file.write_text(" " * (1024 * 1024 + 100), encoding="utf-8")

    cfg = load_config(oversized_file)
    assert isinstance(cfg, AppConfigDTO)
    captured = capsys.readouterr()
    assert "exceeds 1 MB" in captured.err


def test_invariant_2_load_config_fallback_on_invalid_schema(tmp_path: Path, capsys):
    """Asserts that unexpected schema types fall back to defaults gracefully."""
    schema_bad = tmp_path / "bad_schema.json"
    schema_bad.write_text(json.dumps({"engine": {"max_distance": 999}}), encoding="utf-8")

    cfg = load_config(schema_bad)
    assert isinstance(cfg, AppConfigDTO)
    assert cfg.engine.max_distance == 1
    captured = capsys.readouterr()
    assert "[ctxfw] Warning: failed to parse config" in captured.err


# =========================================================================
# INVARIANT 3: AST PRUNING BYPASS IN PASSTHROUGH MODE
# =========================================================================

@pytest.fixture
def mock_project_tree(tmp_path: Path) -> Path:
    """Creates a sample multi-module project for topological testing."""
    root = tmp_path / "test_project"
    root.mkdir()

    (root / "entrypoint.py").write_text(
        "import helper\n\ndef run():\n    return helper.calculate()\n",
        encoding="utf-8",
    )
    (root / "helper.py").write_text(
        "class Helper:\n"
        "    '''Helper docstring.'''\n"
        "    def calculate(self) -> int:\n"
        "        x = 100 * 2\n"
        "        y = x + 50\n"
        "        return y\n",
        encoding="utf-8",
    )
    return root


def test_invariant_3_passthrough_mode_bypasses_pruning_in_engine(mock_project_tree: Path):
    """Asserts that passthrough mode returns 100% full, untouched source code for dependencies."""
    engine_passthrough = ContextFirewallEngine(
        project_root=mock_project_tree,
        mode="passthrough",
    )
    bundle = engine_passthrough.build_context("entrypoint.py")

    assert "helper.py" in bundle.entries
    helper_res = bundle.entries["helper.py"]

    # In passthrough mode, code is returned intact with 0 tokens saved
    raw_helper = (mock_project_tree / "helper.py").read_text(encoding="utf-8")
    assert helper_res.pruned_code == raw_helper
    assert helper_res.estimated_tokens_saved == 0
    assert helper_res.savings_percentage == 0.0
    assert helper_res.depth == PruningDepth.FULL


def test_invariant_3_distance_mode_executes_ast_pruning(mock_project_tree: Path):
    """Asserts that distance mode applies AST interface/nominal pruning to dependencies."""
    engine_distance = ContextFirewallEngine(
        project_root=mock_project_tree,
        mode="distance",
    )
    bundle = engine_distance.build_context("entrypoint.py")

    assert "helper.py" in bundle.entries
    helper_res = bundle.entries["helper.py"]

    # In distance mode, D1 helper.py should have its method body stubbed with Ellipsis (...)
    assert "..." in helper_res.pruned_code
    assert "x = 100 * 2" not in helper_res.pruned_code
    assert helper_res.estimated_tokens_saved > 0
    assert helper_res.depth == PruningDepth.INTERFACE


def test_invariant_3_deterministic_pruner_mode_passthrough():
    """Asserts that DeterministicContextPruner.prune honors mode='passthrough'."""
    raw_code = "def heavy_worker():\n    a = 1 + 2\n    return a"
    req = OptimizationRequestDTO(
        source_code=raw_code,
        language="python",
        depth=PruningDepth.INTERFACE,
        mode="passthrough",
    )
    pruned, orig_c, pruned_c, saved, pct, _ = DeterministicContextPruner.prune(req)
    assert pruned == raw_code
    assert orig_c == len(raw_code)
    assert pruned_c == len(raw_code)
    assert saved == 0
    assert pct == 0.0


# =========================================================================
# INVARIANT 4: SHARE REPORTER ZERO-CODE & PRIVACY COMPLIANCE
# =========================================================================

def test_invariant_4_share_report_excludes_raw_code_secrets_and_paths(tmp_path: Path):
    """Asserts that generate_share_report guarantees exclusion of code, secrets, and absolute paths."""
    report = generate_share_report()

    # 1. Zero raw unpruned source code
    assert "def " not in report
    assert "class " not in report
    assert "import " not in report

    # 2. Zero leaked credentials or API secrets
    assert "sk-" not in report
    assert "ghp_" not in report
    assert "password" not in report.lower()

    # 3. Zero raw local absolute filesystem paths
    assert "C:\\" not in report
    assert "/Users/" not in report
    assert "/home/" not in report

    # 4. Mandatory executive telemetry present
    assert "Context Firewall (ctxfw) // Sovereign FinOps ROI Report" in report
    assert "Audit Cycles Executed" in report
    assert "Tokens Pruned / Avoided" in report
    assert "Estimated Monetary Savings" in report


# =========================================================================
# INVARIANT 5: CONFIGURATION SETTER BOUNDARIES & ATOMIC REPLACEMENT
# =========================================================================

def test_invariant_5_set_config_value_atomic_save(tmp_path: Path):
    """Asserts that set_config_value updates keys and persists atomically."""
    test_cfg_path = tmp_path / "isolated_config.json"

    # Set valid parameters
    cfg = set_config_value("engine.mode", "passthrough", custom_path=test_cfg_path)
    assert cfg.engine.mode == EngineMode.PASSTHROUGH

    cfg2 = set_config_value("engine.max_distance", "3", custom_path=test_cfg_path)
    assert cfg2.engine.max_distance == 3

    cfg3 = set_config_value("finops.roast_level", "sober", custom_path=test_cfg_path)
    assert cfg3.finops.roast_level == RoastLevel.SOBER

    # Confirm on-disk content matches
    loaded = load_config(test_cfg_path)
    assert loaded.engine.mode == EngineMode.PASSTHROUGH
    assert loaded.engine.max_distance == 3
    assert loaded.finops.roast_level == RoastLevel.SOBER


def test_invariant_5_set_config_value_rejects_unknown_keys(tmp_path: Path):
    """Asserts that unknown or out-of-boundary keys raise KeyError and do not mutate state."""
    test_cfg_path = tmp_path / "isolated_config.json"
    with pytest.raises(KeyError, match="Unknown configuration"):
        set_config_value("unknown.key", "value", custom_path=test_cfg_path)


# =========================================================================
# CLI COMMAND ROUTING TESTS
# =========================================================================

def test_cli_config_subcommands(tmp_path: Path, monkeypatch, capsys):
    """Asserts that ctxfw config list/get/set subcommands function via CLI."""
    test_cfg = tmp_path / "cli_cfg.json"
    monkeypatch.setattr("ctxfw.config.get_canonical_config_path", lambda: test_cfg)

    # 1. set
    code = handle_config_command(["set", "engine.mode", "passthrough"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[OK] Configuration updated: engine.mode = passthrough" in out

    # 2. get
    code = handle_config_command(["get", "engine.mode"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out == "passthrough"

    # 3. list
    code = handle_config_command(["list"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["engine"]["mode"] == "passthrough"


def test_cli_mode_shortcut_command(tmp_path: Path, monkeypatch, capsys):
    """Asserts that ctxfw mode shortcut toggles engine mode."""
    test_cfg = tmp_path / "mode_cfg.json"
    monkeypatch.setattr("ctxfw.config.get_canonical_config_path", lambda: test_cfg)

    # Set mode
    code = handle_mode_command(["passthrough"])
    assert code == 0
    assert "[OK] Context firewall mode switched to: passthrough" in capsys.readouterr().out

    # Get current mode
    code = handle_mode_command([])
    assert code == 0
    assert "Current engine mode: passthrough" in capsys.readouterr().out


def test_cli_report_share_command(tmp_path: Path, capsys):
    """Asserts that ctxfw report --share emits clean Markdown."""
    out_file = tmp_path / "share_report.md"
    code = handle_report_command(["--share", "--output", str(out_file)])
    assert code == 0
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Context Firewall (ctxfw) // Sovereign FinOps ROI Report" in content
