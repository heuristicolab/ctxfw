"""
src/ctxfw/config.py — Dynamic Configuration Engine (v4.0.0-dev)
manifest_hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3

Manages persistent user configuration in ~/.ctxfw/config.json and workspace .ctxfwrc
with Pydantic v2 immutability, atomic filesystem staging (.tmp -> os.replace),
and zero-exception fallback on corrupt JSON.
"""
from __future__ import annotations

from enum import Enum, IntEnum
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class EngineMode(str, Enum):
    DISTANCE = "distance"
    PASSTHROUGH = "passthrough"


class RoastLevel(str, Enum):
    CYNICAL = "cynical"
    SOBER = "sober"
    OFF = "off"


class EngineConfigDTO(BaseModel):
    """Configuration governing the AST pruning and topological resolver engine."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: EngineMode = Field(default=EngineMode.DISTANCE, description="Engine operating mode: distance (AST pruned) or passthrough (untouched)")
    max_distance: int = Field(default=1, ge=0, le=5, description="Maximum topological radius for dependency traversal")
    preserve_docstrings: bool = Field(default=False, description="Whether to retain docstrings during interface/nominal pruning")


class FinOpsConfigDTO(BaseModel):
    """Configuration governing pricing calculation and FinOps roast diagnostics."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_price_per_m: float = Field(default=3.0, ge=0.01, le=100.0, description="Input price in USD per 1M tokens")
    output_price_per_m: float = Field(default=15.0, ge=0.01, le=500.0, description="Output price in USD per 1M tokens")
    roast: bool = Field(default=True, description="Master toggle for FinOps terminal roast humor")
    roast_level: RoastLevel = Field(default=RoastLevel.CYNICAL, description="Roast intensity: cynical, sober, or off")


class AppConfigDTO(BaseModel):
    """Root configuration manifest for ctxfw."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    engine: EngineConfigDTO = Field(default_factory=EngineConfigDTO, description="Context firewall engine settings")
    finops: FinOpsConfigDTO = Field(default_factory=FinOpsConfigDTO, description="FinOps economic settings")


class ContextDepthLevel(IntEnum):
    PURE_PASSTHROUGH = 0      # D0: Exclusivamente archivo activo (100% lógica)
    DIRECT_INTERFACE = 1      # D1: Contratos directos y stubs tipados (...)
    TRANSITIVE_NOMINAL = 2    # D2: Firmas y clases nominales (Baseline v3.8.0)
    AMBIENT_CARTOGRAPHY = 3   # D3: Manifiesto léxico de coordenadas (v4.0 H1)


class CtxfwConfigDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_depth: ContextDepthLevel = Field(
        default=ContextDepthLevel.TRANSITIVE_NOMINAL,
        description="Profundidad topológica máxima para la resolución del grafo."
    )
    ambient_manifest: bool = Field(
        default=False,
        description="Habilitar generación de índice plano de símbolos a D3."
    )
    distractor_budget: int = Field(
        default=150,
        ge=20,
        le=500,
        description="Cota máxima de símbolos exportados inyectables en D3."
    )
    subsystem_clamping: bool = Field(
        default=True,
        description="Restringir D3 a los prefijos de paquete compartidos por D1/D2."
    )
    stale_reads_on_herd: bool = Field(
        default=True,
        description="Retornar snapshot SQLite previo ante cambios masivos de mtime."
    )


def load_depth_config(
    project_root: Optional[Path | str] = None,
    custom_config_path: Optional[Path | str] = None,
) -> CtxfwConfigDTO:
    """
    Loads dynamic context depth configuration adhering to SPEC-004 hierarchy:
    1. Environment variables / MCP Client injection (CTXFW_DEPTH, CTXFW_DISTRACTOR_BUDGET, etc.)
    2. Local workspace configuration (.ctxfwrc, .ctxfw.json)
    3. Global user configuration (~/.ctxfw/config.json)
    4. Canonical in-memory defaults (max_depth=2, ambient_manifest=False, distractor_budget=150)

    Enforces AXIOM-20:
    Never executes topological depth expansions exceeding depth 3 (D > 3), and rejects malformed values.
    Enforces AXIOM-21:
    Never transmits workspace config or environment overrides outside local host.
    """
    raw_cfg: dict[str, Any] = {}

    # 1. Attempt to load from workspace or custom config file
    candidate_paths: list[Path] = []
    if custom_config_path:
        candidate_paths.append(Path(custom_config_path).resolve())
    else:
        root_dir = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        candidate_paths.extend([
            root_dir / ".ctxfwrc",
            root_dir / ".ctxfw.json",
        ])

    for cand in candidate_paths:
        if cand.is_file():
            try:
                if cand.stat().st_size > 1048576:
                    sys.stderr.write(f"[ctxfw] Warning: {cand} exceeds 1 MB limit. Ignoring.\\n")
                    break
                content = cand.read_text(encoding="utf-8")
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    clean_dict = {k: v for k, v in parsed.items() if not k.startswith("$")}
                    raw_cfg.update(clean_dict)
                    break
            except Exception as e:
                sys.stderr.write(f"[ctxfw] Warning: failed to parse config at {cand} ({e}). Falling back.\\n")
                break

    # Sanitize max_depth from file if present
    if "max_depth" in raw_cfg:
        try:
            m_val = int(raw_cfg["max_depth"])
            if m_val < 0 or m_val > 3:
                sys.stderr.write(
                    f"[ctxfw] Warning: max_depth={m_val} in config exceeds ceiling [0, 3]. Clamping to D2.\\n"
                )
                raw_cfg["max_depth"] = ContextDepthLevel.TRANSITIVE_NOMINAL
            else:
                raw_cfg["max_depth"] = ContextDepthLevel(m_val)
        except (ValueError, TypeError):
            sys.stderr.write(
                "[ctxfw] Warning: max_depth in config is malformed. Clamping to D2.\\n"
            )
            raw_cfg["max_depth"] = ContextDepthLevel.TRANSITIVE_NOMINAL

    # 2. Environment variables / MCP Server Client injection overrides (Highest Priority)
    if "CTXFW_DEPTH" in os.environ:
        val = os.environ["CTXFW_DEPTH"].strip()
        try:
            depth_int = int(val)
            if 0 <= depth_int <= 3:
                raw_cfg["max_depth"] = ContextDepthLevel(depth_int)
            else:
                sys.stderr.write(
                    f"[ctxfw] Warning: CTXFW_DEPTH={depth_int} exceeds ceiling [0, 3]. Falling back to D2.\\n"
                )
                raw_cfg["max_depth"] = ContextDepthLevel.TRANSITIVE_NOMINAL
        except (ValueError, TypeError):
            sys.stderr.write(
                f"[ctxfw] Warning: CTXFW_DEPTH='{val}' is malformed. Falling back to D2.\\n"
            )
            raw_cfg["max_depth"] = ContextDepthLevel.TRANSITIVE_NOMINAL

    if "CTXFW_DISTRACTOR_BUDGET" in os.environ:
        val = os.environ["CTXFW_DISTRACTOR_BUDGET"].strip()
        try:
            budget_int = int(val)
            raw_cfg["distractor_budget"] = max(20, min(500, budget_int))
        except (ValueError, TypeError):
            pass

    if "CTXFW_AMBIENT_MANIFEST" in os.environ:
        val = os.environ["CTXFW_AMBIENT_MANIFEST"].strip().lower()
        raw_cfg["ambient_manifest"] = val in {"1", "true", "yes", "on"}

    if "CTXFW_SUBSYSTEM_CLAMPING" in os.environ:
        val = os.environ["CTXFW_SUBSYSTEM_CLAMPING"].strip().lower()
        raw_cfg["subsystem_clamping"] = val in {"1", "true", "yes", "on"}

    if "CTXFW_STALE_READS_ON_HERD" in os.environ:
        val = os.environ["CTXFW_STALE_READS_ON_HERD"].strip().lower()
        raw_cfg["stale_reads_on_herd"] = val in {"1", "true", "yes", "on"}

    # Automatic ambient activation if max_depth is 3 and ambient_manifest not explicitly set
    if raw_cfg.get("max_depth") == ContextDepthLevel.AMBIENT_CARTOGRAPHY:
        if "ambient_manifest" not in raw_cfg:
            raw_cfg["ambient_manifest"] = True

    try:
        return CtxfwConfigDTO.model_validate(raw_cfg)
    except ValidationError as e:
        sys.stderr.write(f"[ctxfw] Warning: invalid depth configuration schema ({e}). Using defaults.\\n")
        return CtxfwConfigDTO()


def get_canonical_config_dir() -> Path:
    """Returns canonical user config directory ~/.ctxfw."""
    cfg_dir = Path.home() / ".ctxfw"
    return cfg_dir.resolve()


def get_canonical_config_path() -> Path:
    """Returns canonical config file path ~/.ctxfw/config.json."""
    return get_canonical_config_dir() / "config.json"


def load_config(custom_path: Optional[Path | str] = None) -> AppConfigDTO:
    """
    Loads application configuration with Invariant 2 enforcement:
    If the file does not exist or contains corrupt JSON/invalid schema,
    emits a warning to stderr and returns canonical in-memory defaults
    without raising unhandled exceptions or crashing the process.
    """
    target_path = Path(custom_path).resolve() if custom_path else get_canonical_config_path()

    if not target_path.is_file():
        return AppConfigDTO()

    try:
        # Enforce max 1 MB size bound
        file_size = target_path.stat().st_size
        if file_size > 1048576:
            sys.stderr.write(f"[ctxfw] Warning: config file exceeds 1 MB ({file_size} bytes). Using default configuration.\n")
            return AppConfigDTO()

        raw_data = target_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_data)
        if not isinstance(parsed, dict):
            sys.stderr.write(f"[ctxfw] Warning: config file at {target_path} is not a valid JSON dictionary. Using defaults.\n")
            return AppConfigDTO()

        return AppConfigDTO.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError, OSError) as e:
        sys.stderr.write(f"[ctxfw] Warning: failed to parse config at {target_path} ({e}). Falling back to canonical defaults.\n")
        return AppConfigDTO()


def save_config(config: AppConfigDTO, custom_path: Optional[Path | str] = None) -> Path:
    """
    Persists configuration atomically using a temporary file and os.replace.
    Enforces Invariant 5: Never mutates third-party configuration files or writes
    outside the canonical user configuration directory unless an explicit target path
    is provided by testing fixtures.
    """
    if custom_path:
        target_path = Path(custom_path).resolve()
    else:
        target_path = get_canonical_config_path()

    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Atomic write pattern: write to .tmp in same directory, then rename
    json_bytes = config.model_dump_json(indent=2).encode("utf-8")
    tmp_path = target_dir / f"{target_path.name}.{os.getpid()}.tmp"

    try:
        tmp_path.write_bytes(json_bytes)
        os.replace(str(tmp_path), str(target_path))
        return target_path
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def set_config_value(key_path: str, value: Any, custom_path: Optional[Path | str] = None) -> AppConfigDTO:
    """
    Sets a dotted config parameter (e.g., 'engine.mode', 'finops.roast_level')
    and atomically saves the updated configuration.
    """
    current_config = load_config(custom_path)
    data = current_config.model_dump()

    parts = key_path.split(".")
    if len(parts) == 1:
        # Check if key is a direct field of engine or finops
        if parts[0] in data.get("engine", {}):
            target_section = "engine"
            target_field = parts[0]
        elif parts[0] in data.get("finops", {}):
            target_section = "finops"
            target_field = parts[0]
        else:
            raise KeyError(f"Unknown configuration key: '{key_path}'")
    elif len(parts) == 2:
        target_section, target_field = parts[0], parts[1]
        if target_section not in data:
            raise KeyError(f"Unknown configuration section: '{target_section}'")
        if target_field not in data[target_section]:
            raise KeyError(f"Unknown configuration field: '{target_field}' in section '{target_section}'")
    else:
        raise KeyError(f"Invalid key hierarchy: '{key_path}'")

    # Cast boolean strings if needed
    if isinstance(value, str):
        val_lower = value.strip().lower()
        if val_lower in {"true", "1", "yes", "on"}:
            value = True
        elif val_lower in {"false", "0", "no", "off"}:
            value = False
        else:
            # Try numeric casts
            try:
                if "." in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                pass

    data[target_section][target_field] = value
    new_config = AppConfigDTO.model_validate(data)
    save_config(new_config, custom_path)
    return new_config
