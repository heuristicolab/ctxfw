"""
tests/test_depth_configurator.py — Verification Suite for Dynamic Depth Configurator (v4.0.0-dev)
manifest_hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3

Validates SPEC-004 requirements and Pre-Mortem Axioms:
- Invariant 1: Hierarchy precedence: ENV / MCP Client > .ctxfwrc > Canonical D2 Default.
- Invariant 2: AXIOM-20 Depth ceiling enforcement (D in [0, 3]). Out-of-bounds falls back to D2.
- Invariant 3: AXIOM-17 Dynamic namespace quarantine emitting '[DYNAMIC_UNBOUND:?]'.
- Invariant 4: AXIOM-19 Subsystem boundary clamping and 1,000 net tokens ceiling.
- Invariant 5: Canonical v3.8.0 backward compatibility when D2 or default is active.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
from unittest.mock import patch

from ctxfw.config import (
    ContextDepthLevel,
    CtxfwConfigDTO,
    load_depth_config,
)
from ctxfw.core.contracts import PruningDepth
from ctxfw.core.topological import (
    ContextFirewallEngine,
    D3SymbolExtractor,
    TopologicalContextBundleDTO,
    _rel_path_to_module_name,
)


# =========================================================================
# 1. HIERARCHY & PRECEDENCE (ENV / MCP CLIENT > .ctxfwrc > CANONICAL DEFAULTS)
# =========================================================================

def test_default_configuration_matches_v380_canonical(tmp_path: Path):
    """Asserts that without env vars or config files, configuration defaults to D2."""
    with patch.dict(os.environ, {}, clear=True):
        cfg = load_depth_config(project_root=tmp_path)
        assert cfg.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
        assert cfg.max_depth == 2
        assert cfg.ambient_manifest is False
        assert cfg.distractor_budget == 150
        assert cfg.subsystem_clamping is True
        assert cfg.stale_reads_on_herd is True


def test_ctxfwrc_configuration_parsing(tmp_path: Path):
    """Asserts that .ctxfwrc with schema metadata is correctly parsed."""
    rc_content = {
        "$schema": "https://ctxfw.heuristicolab.com/schemas/v4/config.json",
        "max_depth": 3,
        "ambient_manifest": True,
        "distractor_budget": 200,
        "subsystem_clamping": False,
        "stale_reads_on_herd": True,
    }
    rc_file = tmp_path / ".ctxfwrc"
    rc_file.write_text(json.dumps(rc_content), encoding="utf-8")

    with patch.dict(os.environ, {}, clear=True):
        cfg = load_depth_config(project_root=tmp_path)
        assert cfg.max_depth == ContextDepthLevel.AMBIENT_CARTOGRAPHY
        assert cfg.ambient_manifest is True
        assert cfg.distractor_budget == 200
        assert cfg.subsystem_clamping is False
        assert cfg.stale_reads_on_herd is True


def test_env_var_mcp_client_injection_overrides_file(tmp_path: Path):
    """Asserts that CTXFW_DEPTH in os.environ overrides values in .ctxfwrc."""
    rc_file = tmp_path / ".ctxfwrc"
    rc_file.write_text(json.dumps({"max_depth": 1, "distractor_budget": 100}), encoding="utf-8")

    env_overrides = {
        "CTXFW_DEPTH": "3",
        "CTXFW_DISTRACTOR_BUDGET": "350",
    }
    with patch.dict(os.environ, env_overrides, clear=True):
        cfg = load_depth_config(project_root=tmp_path)
        assert cfg.max_depth == ContextDepthLevel.AMBIENT_CARTOGRAPHY
        assert cfg.max_depth == 3
        assert cfg.distractor_budget == 350
        # Ambient manifest auto-enables on depth 3
        assert cfg.ambient_manifest is True


# =========================================================================
# 2. AXIOM-20: CONFIGURATION DEPTH CEILING & FAULT TOLERANCE
# =========================================================================

def test_axiom_20_depth_exceeding_ceiling_falls_back_to_d2(tmp_path: Path, capsys):
    """Asserts that depth values > 3 trigger warning and safely clamp to D2."""
    with patch.dict(os.environ, {"CTXFW_DEPTH": "4"}, clear=True):
        cfg = load_depth_config(project_root=tmp_path)
        assert cfg.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
        captured = capsys.readouterr()
        assert "exceeds ceiling" in captured.err


def test_axiom_20_malformed_numeric_depth_falls_back_to_d2(tmp_path: Path, capsys):
    """Asserts that non-numeric or corrupt depth strings fall back to D2 without crash."""
    with patch.dict(os.environ, {"CTXFW_DEPTH": "not-a-number"}, clear=True):
        cfg = load_depth_config(project_root=tmp_path)
        assert cfg.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
        captured = capsys.readouterr()
        assert "malformed" in captured.err


def test_corrupt_ctxfwrc_json_falls_back_to_defaults(tmp_path: Path, capsys):
    """Asserts that corrupted .ctxfwrc file gracefully falls back to canonical defaults."""
    rc_file = tmp_path / ".ctxfwrc"
    rc_file.write_text("{broken json: 123", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=True):
        cfg = load_depth_config(project_root=tmp_path)
        assert cfg.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
        captured = capsys.readouterr()
        assert "failed to parse config" in captured.err


# =========================================================================
# 3. AXIOM-17: DYNAMIC NAMESPACE QUARANTINE (D3SymbolExtractor)
# =========================================================================

def test_d3_symbol_extractor_identifies_standard_public_symbols():
    """Asserts that classes, functions, and uppercase constants are accurately extracted."""
    code = (
        "'''Module docstring.'''\n"
        "MAX_RETRIES = 5\n"
        "DEBUG_MODE = True\n"
        "internal_var = 10\n\n"
        "def compute_hash(val: str) -> str:\n"
        "    return val.strip()\n\n"
        "async def fetch_remote() -> dict:\n"
        "    return {}\n\n"
        "class SecurityGateway:\n"
        "    def authenticate(self): pass\n\n"
        "def _hidden_helper(): pass\n"
    )
    symbols = D3SymbolExtractor.extract_from_code(code)
    assert "[DYNAMIC_UNBOUND:?]" not in symbols
    assert "DEBUG_MODE:K" in symbols
    assert "MAX_RETRIES:K" in symbols
    assert "compute_hash:F" in symbols
    assert "fetch_remote:F" in symbols
    assert "SecurityGateway:C" in symbols
    assert "_hidden_helper:F" not in symbols
    assert "internal_var:K" not in symbols


def test_axiom_17_pep562_getattr_triggers_dynamic_unbound_quarantine():
    """Asserts that module-level __getattr__ explicitly flags [DYNAMIC_UNBOUND:?]."""
    code = (
        "def normal_func(): pass\n\n"
        "def __getattr__(name: str):\n"
        "    return f'dynamic_{name}'\n"
    )
    symbols = D3SymbolExtractor.extract_from_code(code)
    assert "[DYNAMIC_UNBOUND:?]" in symbols
    assert "normal_func:F" in symbols


def test_axiom_17_dynamic_all_triggers_dynamic_unbound_quarantine():
    """Asserts that non-constant __all__ expression flags [DYNAMIC_UNBOUND:?]."""
    code = (
        "__all__ = ['base'] + ['dynamic_extra']\n"
        "def base(): pass\n"
    )
    symbols = D3SymbolExtractor.extract_from_code(code)
    assert "[DYNAMIC_UNBOUND:?]" in symbols


def test_d3_symbol_extractor_handles_syntax_error_safely():
    """Asserts that unparseable syntax returns dynamic unbound flag rather than crashing."""
    code = "def broken_func(:\n    pass"
    symbols = D3SymbolExtractor.extract_from_code(code)
    assert symbols == ["[DYNAMIC_UNBOUND:?]"]


# =========================================================================
# 4. MULTI-DEPTH TOPOLOGICAL ROUTING & AMBIENT CARTOGRAPHY INTEGRATION
# =========================================================================

@pytest.fixture
def multi_hop_project(tmp_path: Path) -> Path:
    """
    Creates a 4-tier dependency chain:
    entrypoint.py (D0) -> d1_service.py (D1) -> d2_repository.py (D2) -> d3_util.py (D3)
    """
    root = tmp_path / "app"
    root.mkdir()

    (root / "entrypoint.py").write_text(
        "import d1_service\ndef main():\n    return d1_service.execute()\n",
        encoding="utf-8",
    )
    (root / "d1_service.py").write_text(
        "import d2_repository\ndef execute():\n    return d2_repository.query()\n",
        encoding="utf-8",
    )
    (root / "d2_repository.py").write_text(
        "import d3_util\ndef query():\n    return d3_util.format_output()\n",
        encoding="utf-8",
    )
    (root / "d3_util.py").write_text(
        "API_VERSION = 'v1'\n"
        "def format_output():\n"
        "    return 'data'\n"
        "class Formatter:\n"
        "    pass\n",
        encoding="utf-8",
    )
    return root


def test_depth_0_pure_passthrough_retains_only_active_target(multi_hop_project: Path):
    """Asserts that D0 excludes all external dependencies from the bundle."""
    engine = ContextFirewallEngine(project_root=multi_hop_project)
    cfg = CtxfwConfigDTO(max_depth=ContextDepthLevel.PURE_PASSTHROUGH)
    bundle = engine.build_context("entrypoint.py", depth_config=cfg)

    assert "entrypoint.py" in bundle.entries
    assert "d1_service.py" not in bundle.entries
    assert "d2_repository.py" not in bundle.entries
    assert "d3_util.py" not in bundle.entries
    assert bundle.ambient_manifest is None


def test_depth_1_direct_interface_retains_only_direct_imports(multi_hop_project: Path):
    """Asserts that D1 includes D0 and D1, excluding D2 and D3."""
    engine = ContextFirewallEngine(project_root=multi_hop_project)
    cfg = CtxfwConfigDTO(max_depth=ContextDepthLevel.DIRECT_INTERFACE)
    bundle = engine.build_context("entrypoint.py", depth_config=cfg)

    assert "entrypoint.py" in bundle.entries
    assert "d1_service.py" in bundle.entries
    assert bundle.entries["d1_service.py"].depth == PruningDepth.INTERFACE
    assert "d2_repository.py" not in bundle.entries
    assert "d3_util.py" not in bundle.entries
    assert bundle.ambient_manifest is None


def test_depth_2_transitive_nominal_matches_v380_baseline(multi_hop_project: Path):
    """Asserts that D2 resolves D0, D1, D2 with nominal pruning and zero ambient block."""
    engine = ContextFirewallEngine(project_root=multi_hop_project)
    cfg = CtxfwConfigDTO(max_depth=ContextDepthLevel.TRANSITIVE_NOMINAL)
    bundle = engine.build_context("entrypoint.py", depth_config=cfg)

    assert "entrypoint.py" in bundle.entries
    assert "d1_service.py" in bundle.entries
    assert "d2_repository.py" in bundle.entries
    assert "d3_util.py" in bundle.entries  # In v3.8.0, dist >= 2 are nominal
    assert bundle.entries["d2_repository.py"].depth == PruningDepth.NOMINAL
    assert bundle.entries["d3_util.py"].depth == PruningDepth.NOMINAL
    assert bundle.ambient_manifest is None


def test_depth_3_ambient_cartography_extracts_d3_symbol_index(multi_hop_project: Path):
    """Asserts that D3 extracts zero-syntax flat symbol catalog instead of nominal code."""
    engine = ContextFirewallEngine(project_root=multi_hop_project)
    cfg = CtxfwConfigDTO(max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY, distractor_budget=150)
    bundle = engine.build_context("entrypoint.py", depth_config=cfg)

    # D0, D1, D2 are in entries
    assert "entrypoint.py" in bundle.entries
    assert "d1_service.py" in bundle.entries
    assert "d2_repository.py" in bundle.entries
    # D3 is NOT in entries as nominal code:
    assert "d3_util.py" not in bundle.entries

    # D3 is in ambient_manifest
    assert bundle.ambient_manifest is not None
    assert "### AMBIENT MANIFEST [D3]" in bundle.ambient_manifest
    assert "d3_util: [API_VERSION:K, Formatter:C, format_output:F]" in bundle.ambient_manifest

    # Prompt rendering integrates ambient manifest cleanly
    prompt = bundle.to_prompt()
    assert "### AMBIENT MANIFEST [D3]" in prompt
    assert "d3_util: [API_VERSION:K, Formatter:C, format_output:F]" in prompt


def test_helper_rel_path_to_module_name():
    """Asserts POSIX path conversion to canonical Python module dot path."""
    assert _rel_path_to_module_name("foo/bar/baz.py") == "foo.bar.baz"
    assert _rel_path_to_module_name("package/__init__.py") == "package"
    assert _rel_path_to_module_name("main.py") == "main"
