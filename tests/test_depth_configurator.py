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
    AppConfigDTO,
    ContextDepthLevel,
    CtxfwConfigDTO,
    EngineConfigDTO,
    EngineMode,
    FinOpsConfigDTO,
    RoastLevel,
    get_canonical_config_dir,
    get_canonical_config_path,
    load_config,
    load_depth_config,
    save_config,
    set_config_value,
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


# =========================================================================
# 5. EXHAUSTIVE COVERAGE: CONFIG ENGINE & CACHE BATCH OPERATIONS (CA-04)
# =========================================================================

def test_canonical_config_paths():
    """Asserts canonical config directory and file resolution."""
    dir_path = get_canonical_config_dir()
    file_path = get_canonical_config_path()
    assert dir_path.is_absolute()
    assert file_path.is_absolute()
    assert file_path.name == "config.json"
    assert file_path.parent == dir_path


def test_load_config_fallback_cases(tmp_path: Path, capsys):
    """Asserts fallback behavior on missing, oversized, non-dict, and corrupt files."""
    # 1. Missing file
    cfg1 = load_config(tmp_path / "non_existent.json")
    assert isinstance(cfg1, AppConfigDTO)

    # 2. Oversized file (> 1 MB)
    giant = tmp_path / "giant.json"
    giant.write_text(" " * (1048576 + 10), encoding="utf-8")
    cfg2 = load_config(giant)
    assert isinstance(cfg2, AppConfigDTO)
    assert "exceeds 1 MB" in capsys.readouterr().err

    # 3. Non-dict JSON
    arr_file = tmp_path / "arr.json"
    arr_file.write_text("[1, 2, 3]", encoding="utf-8")
    cfg3 = load_config(arr_file)
    assert isinstance(cfg3, AppConfigDTO)
    assert "not a valid JSON dictionary" in capsys.readouterr().err

    # 4. Corrupt JSON
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{bad json", encoding="utf-8")
    cfg4 = load_config(bad_file)
    assert isinstance(cfg4, AppConfigDTO)
    assert "failed to parse config" in capsys.readouterr().err


def test_save_and_set_config_value_exhaustive(tmp_path: Path):
    """Asserts atomic persistence and exhaustive key hierarchy parsing."""
    cfg_file = tmp_path / "custom_config.json"
    initial_cfg = AppConfigDTO()
    saved_path = save_config(initial_cfg, cfg_file)
    assert saved_path == cfg_file
    assert cfg_file.is_file()

    # 1. Single part key targeting engine
    res1 = set_config_value("mode", "passthrough", cfg_file)
    assert res1.engine.mode == EngineMode.PASSTHROUGH

    # 2. Single part key targeting finops
    res2 = set_config_value("roast", "off", cfg_file)
    assert res2.finops.roast is False

    # 3. Two part key in engine
    res3 = set_config_value("engine.max_distance", "3", cfg_file)
    assert res3.engine.max_distance == 3

    # 4. Two part key in finops with float
    res4 = set_config_value("finops.input_price_per_m", "4.75", cfg_file)
    assert res4.finops.input_price_per_m == 4.75

    # 5. Boolean string variants
    res5 = set_config_value("engine.preserve_docstrings", "yes", cfg_file)
    assert res5.engine.preserve_docstrings is True
    res6 = set_config_value("engine.preserve_docstrings", "no", cfg_file)
    assert res6.engine.preserve_docstrings is False
    res7 = set_config_value("engine.preserve_docstrings", "1", cfg_file)
    assert res7.engine.preserve_docstrings is True
    res8 = set_config_value("engine.preserve_docstrings", "0", cfg_file)
    assert res8.engine.preserve_docstrings is False

    # 6. Error handling
    with pytest.raises(KeyError, match="Unknown configuration key"):
        set_config_value("unknown_key", "val", cfg_file)

    with pytest.raises(KeyError, match="Unknown configuration section"):
        set_config_value("unknown_sec.val", "val", cfg_file)

    with pytest.raises(KeyError, match="Unknown configuration field"):
        set_config_value("engine.unknown_field", "val", cfg_file)

    with pytest.raises(KeyError, match="Invalid key hierarchy"):
        set_config_value("a.b.c", "val", cfg_file)


def test_load_depth_config_additional_branches(tmp_path: Path, capsys):
    """Asserts custom config path, .ctxfw.json, out-of-bound clamping, and boolean envs."""
    # 1. .ctxfw.json support
    json_cfg = tmp_path / ".ctxfw.json"
    json_cfg.write_text(json.dumps({"max_depth": 1, "distractor_budget": 80}), encoding="utf-8")
    c1 = load_depth_config(project_root=tmp_path)
    assert c1.max_depth == ContextDepthLevel.DIRECT_INTERFACE
    assert c1.distractor_budget == 80

    # 2. Custom config path
    custom_cfg = tmp_path / "special.json"
    custom_cfg.write_text(json.dumps({"max_depth": 0}), encoding="utf-8")
    c2 = load_depth_config(custom_config_path=custom_cfg)
    assert c2.max_depth == ContextDepthLevel.PURE_PASSTHROUGH

    # 3. Oversized .ctxfwrc (> 1 MB)
    giant_rc = tmp_path / ".ctxfwrc"
    giant_rc.write_text(" " * (1048576 + 5), encoding="utf-8")
    c3 = load_depth_config(project_root=tmp_path)
    assert c3.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
    assert "exceeds 1 MB limit" in capsys.readouterr().err
    giant_rc.unlink()

    # 4. Out of bounds max_depth in file (< 0 or > 3)
    bad_rc = tmp_path / ".ctxfwrc"
    bad_rc.write_text(json.dumps({"max_depth": 99}), encoding="utf-8")
    c4 = load_depth_config(project_root=tmp_path)
    assert c4.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
    assert "exceeds ceiling" in capsys.readouterr().err

    # 5. Malformed max_depth in file
    bad_rc.write_text(json.dumps({"max_depth": "invalid"}), encoding="utf-8")
    c5 = load_depth_config(project_root=tmp_path)
    assert c5.max_depth == ContextDepthLevel.TRANSITIVE_NOMINAL
    assert "malformed" in capsys.readouterr().err
    bad_rc.unlink()

    # 6. Env overrides for distractor budget clamping (< 20, > 500) and booleans
    envs = {
        "CTXFW_DISTRACTOR_BUDGET": "999",
        "CTXFW_AMBIENT_MANIFEST": "true",
        "CTXFW_SUBSYSTEM_CLAMPING": "false",
        "CTXFW_STALE_READS_ON_HERD": "0",
    }
    with patch.dict(os.environ, envs, clear=True):
        c6 = load_depth_config(project_root=tmp_path)
        assert c6.distractor_budget == 500  # Clamped to 500
        assert c6.ambient_manifest is True
        assert c6.subsystem_clamping is False
        assert c6.stale_reads_on_herd is False

    with patch.dict(os.environ, {"CTXFW_DISTRACTOR_BUDGET": "5"}, clear=True):
        c7 = load_depth_config(project_root=tmp_path)
        assert c7.distractor_budget == 20  # Clamped to 20


def test_local_semantic_cache_d3_batch_operations(tmp_path: Path):
    """Asserts get_d3_symbols_batch and set_d3_symbols_batch in LocalSemanticCache."""
    from ctxfw.storage.cache import LocalSemanticCache
    db_file = tmp_path / "test_cache.db"
    cache = LocalSemanticCache(db_file)

    # 1. Empty calls
    assert cache.get_d3_symbols_batch([]) == {}
    cache.set_d3_symbols_batch([])

    # 2. Insert batch records
    records = [
        ("mod/a.py", "hash_a", 100.0, ["A:C", "foo:F"]),
        ("mod/b.py", "hash_b", 200.0, ["[DYNAMIC_UNBOUND:?]"]),
    ]
    cache.set_d3_symbols_batch(records)

    # 3. Retrieve batch records
    res = cache.get_d3_symbols_batch(["mod/a.py", "mod/b.py", "mod/c.py"])
    assert "mod/a.py" in res
    assert res["mod/a.py"] == (100.0, "hash_a", ["A:C", "foo:F"])
    assert "mod/b.py" in res
    assert res["mod/b.py"] == (200.0, "hash_b", ["[DYNAMIC_UNBOUND:?]"])
    assert "mod/c.py" not in res

    # 4. Clean close
    cache.close()


def test_config_canonical_user_paths_and_validation(tmp_path: Path):
    """Validates get_canonical_user_config_dir/path and schema validation fallback."""
    from ctxfw.config import (
        get_canonical_config_dir,
        get_canonical_config_path,
        load_depth_config,
        save_config,
        set_config_value,
        load_config,
    )

    # 1. Canonical user paths
    user_dir = get_canonical_config_dir()
    user_path = get_canonical_config_path()
    assert isinstance(user_dir, Path)
    assert isinstance(user_path, Path)
    assert user_path.parent == user_dir

    # 2. Schema validation error fallback (invalid type in JSON)
    bad_schema_file = tmp_path / ".ctxfwrc"
    bad_schema_file.write_text(json.dumps({"max_depth": "NOT_AN_INT"}), encoding="utf-8")
    cfg_fallback = load_depth_config(project_root=tmp_path)
    assert cfg_fallback.max_depth == 2

    # 3. Non-dict JSON fallback (e.g., array [1, 2, 3])
    bad_schema_file.write_text("[1, 2, 3]", encoding="utf-8")
    cfg_arr = load_depth_config(project_root=tmp_path)
    assert cfg_arr.max_depth == 2

    # 4. set_config_value type conversion
    custom_cfg_file = tmp_path / "custom_config.json"
    save_config(AppConfigDTO(), custom_path=custom_cfg_file)
    mod_cfg = set_config_value("engine.mode", "passthrough", custom_path=custom_cfg_file)
    assert mod_cfg.engine.mode.value == "passthrough"
    mod_cfg2 = set_config_value("finops.roast_level", "sober", custom_path=custom_cfg_file)
    assert mod_cfg2.finops.roast_level.value == "sober"

    # 5. Non-integer distractor budget fallback (lines 192-193)
    bad_schema_file.write_text(json.dumps({"max_depth": 2, "distractor_budget": "unparseable"}), encoding="utf-8")
    cfg_unparse = load_depth_config(project_root=tmp_path)
    assert cfg_unparse.distractor_budget == 150

    # 6. save_config atomic unlink exception (lines 286-289)
    from unittest.mock import patch
    with patch("os.replace", side_effect=OSError("Atomic swap failed")):
        with patch.object(Path, "unlink", side_effect=OSError("Unlink failed")):
            with pytest.raises(OSError):
                save_config(AppConfigDTO(), custom_path=tmp_path / "fail_atomic.json")


