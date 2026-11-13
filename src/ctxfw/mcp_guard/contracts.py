# manifest_hash: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
"""
ctxfw.mcp_guard.contracts — Axiomatic Contracts, FSM & Deterministic Security Engines
=======================================================================================
Unifies:
  - #05 MCP Tool Poisoning Firewall (SHA-256 pinning, rug-pull detection, invisible
    Unicode/imperative poisoning scanner, strict parameter binding guard).
  - #03 MCP Capability Laundering Guard (cross-platform OS path component confinement,
    sibling-prefix prevention, URI scheme & percent-encoding rejection, symlink/TOCTOU
    escape detection, unsandboxed fallback prohibition).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional, Sequence, Tuple, Union
import urllib.parse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFEST_HASH: str = "4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82"

SERVER_ID_PATTERN = r"^[a-zA-Z0-9_.-]{1,128}$"
TOOL_NAME_PATTERN = r"^[a-zA-Z0-9_.:-]{1,128}$"
PIN_SHA256_PATTERN = r"^[a-f0-9]{64}$"
VECTOR_ID_PATTERN = r"^P([1-9]|1[0-9]|2[0-5])$"

MAX_DESCRIPTION_CHARS: int = 16384
DEFAULT_MAX_DECODE_ROUNDS: int = 3
MIN_DECODE_ROUNDS: int = 1
MAX_DECODE_ROUNDS: int = 8
MAX_AUTHORIZED_ROOTS: int = 32
QUARANTINE_RISK_THRESHOLD: float = 0.65

_SERVER_ID_RE = re.compile(SERVER_ID_PATTERN)
_TOOL_NAME_RE = re.compile(TOOL_NAME_PATTERN)
_PIN_SHA256_RE = re.compile(PIN_SHA256_PATTERN)
_VECTOR_ID_RE = re.compile(VECTOR_ID_PATTERN)

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:(?:[/\\]|$)")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]{1,20}:")

_ZERO_WIDTH_CHARS = frozenset(
    {
        "\u200b", "\u200c", "\u200d", "\u200e", "\u200f",
        "\u2060", "\u2061", "\u2062", "\u2063", "\u2064",
        "\ufeff",
    }
)
_BIDI_OVERRIDE_RANGE = range(0x202A, 0x202F)
_BIDI_ISOLATE_RANGE = range(0x2066, 0x206A)
_UNICODE_TAG_RANGE = range(0xE0000, 0xE0080)

_IMPERATIVE_POISON_RE = re.compile(
    r"(?:"
    r"<\s*(?:IMPORTANT|SYSTEM|INSTRUCTIONS|CRITICAL|SECRET|ADMIN|OVERRIDE)\s*>"
    r"|<\|\s*(?:im_start|system|im_end)\s*\|>"
    r"|\[/?INST\]"
    r"|\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions\b"
    r"|\bdo\s+not\s+(?:tell|inform|mention|show|disclose)\s+(?:the\s+)?user\b"
    r"|\bbefore\s+(?:calling|using|executing|invoking)\s+(?:this|any)\s+tool\b"
    r"|\byou\s+must\s+(?:first|silently|secretly)\s+(?:read|send|upload|exfiltrate|execute)\b"
    r")",
    re.IGNORECASE,
)

_EXFIL_SINK_RE = re.compile(
    r"(?:"
    r"\b(?:curl|wget)\b[^\n|;`]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b"
    r"|\b(?:curl|wget)\b[^\n;`]*(?:https?://[^\s'\"]+)"
    r"|\b(?:nc|ncat|socat)\s+[^\n;`]*(?:-e\b|/[a-z]+/sh)"
    r"|\b(?:exfiltrate|beacon|webhook\.site|requestbin|ngrok\.io)\b"
    r"|(?:powershell(?:\.exe)?|pwsh)\s+[^\n;`]*(?:-enc|-encodedcommand|invoke-webrequest|iwr\s)"
    r")",
    re.IGNORECASE,
)

_SENSITIVE_TARGET_RE = re.compile(
    r"(?:"
    r"~/\.ssh/(?:id_rsa|id_ed25519|authorized_keys|config)"
    r"|/\.ssh/(?:id_rsa|id_ed25519|known_hosts)"
    r"|~/\.aws/credentials"
    r"|/etc/(?:shadow|passwd|sudoers)"
    r"|~/\.kube/config"
    r"|\bmcp\.json\b[^\n]*(?:read|exfil|send|post)"
    r")",
    re.IGNORECASE,
)


class ChannelSurface(str, Enum):
    """MCP threat injection channel surface taxonomy (#05)."""

    TOOL_DESCRIPTION_POISONING = "TOOL_DESCRIPTION_POISONING"
    PARAM_SCHEMA_POISONING = "PARAM_SCHEMA_POISONING"
    TOOL_OUTPUT_POISONING = "TOOL_OUTPUT_POISONING"
    PROMPT_TEMPLATE_POISONING = "PROMPT_TEMPLATE_POISONING"
    RESOURCE_POISONING = "RESOURCE_POISONING"
    CONVERSATION_HISTORY_POISONING = "CONVERSATION_HISTORY_POISONING"
    USER_MEMORY_POISONING = "USER_MEMORY_POISONING"
    CONFIG_FILE_POISONING = "CONFIG_FILE_POISONING"
    SYSTEM_PROMPT_POISONING = "SYSTEM_PROMPT_POISONING"


class OracleVerdict(str, Enum):
    """Dual oracle evaluation disposition."""

    BENIGN = "BENIGN"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"


class FirewallState(str, Enum):
    """Deterministic finite-state machine states for ctxfw.mcp_guard."""

    UNVERIFIED = "UNVERIFIED"
    PINNED = "PINNED"
    INSPECTION_PASSED = "INSPECTION_PASSED"
    EXECUTED_CLEAN = "EXECUTED_CLEAN"
    INTENT_FLAGGED = "INTENT_FLAGGED"
    CONFINED_DENY = "CONFINED_DENY"
    EXFIL_DETECTED = "EXFIL_DETECTED"
    RUG_PULL_BLOCKED = "RUG_PULL_BLOCKED"
    QUARANTINED = "QUARANTINED"


TERMINAL_FAILURE_STATES: frozenset[FirewallState] = frozenset(
    {
        FirewallState.CONFINED_DENY,
        FirewallState.EXFIL_DETECTED,
        FirewallState.RUG_PULL_BLOCKED,
        FirewallState.QUARANTINED,
    }
)


class FirewallEvent(str, Enum):
    """Deterministic transition events for the MCP Guard FSM."""

    REGISTER_PIN = "REGISTER_PIN"
    VERIFY_PIN_MATCH = "VERIFY_PIN_MATCH"
    PIN_HASH_DRIFT = "PIN_HASH_DRIFT"
    SCHEMA_COLLISION = "SCHEMA_COLLISION"
    CONFINEMENT_BREACH = "CONFINEMENT_BREACH"
    PARAM_BINDING_PASS = "PARAM_BINDING_PASS"
    PARAM_BINDING_FAIL = "PARAM_BINDING_FAIL"
    POISON_SCORE_EXCEEDED = "POISON_SCORE_EXCEEDED"
    EXFIL_SINK_HIT = "EXFIL_SINK_HIT"
    EXECUTE_COMPLETE = "EXECUTE_COMPLETE"
    RESET = "RESET"


class SarifRuleId(str, Enum):
    """SARIF rule identifiers from MCP capability laundering model (#03)."""

    PT_001 = "PT-001"
    PT_002 = "PT-002"
    PT_003 = "PT-003"
    PT_004 = "PT-004"
    PT_005 = "PT-005"


class DetectionLayer(str, Enum):
    """Security verification layer taxonomy (#03)."""

    SAST_TAINT = "SAST_TAINT"
    CAPABILITY_MODEL = "CAPABILITY_MODEL"
    SANDBOX_RUNTIME = "SANDBOX_RUNTIME"


class ValidationVerdict(str, Enum):
    """Deterministic verdict returned by pinning, scanning, and confinement gates."""

    ALLOW = "ALLOW"
    DENY_TRAVERSAL = "DENY_TRAVERSAL"
    DENY_SIBLING_PREFIX = "DENY_SIBLING_PREFIX"
    DENY_SYMLINK_ESCAPE = "DENY_SYMLINK_ESCAPE"
    DENY_URI_SCHEME = "DENY_URI_SCHEME"
    DENY_UNSANDBOXED_FALLBACK = "DENY_UNSANDBOXED_FALLBACK"
    DENY_PIN_MISMATCH = "DENY_PIN_MISMATCH"
    DENY_POISON_DESCRIPTION = "DENY_POISON_DESCRIPTION"
    DENY_PARAM_INJECTION = "DENY_PARAM_INJECTION"


class ErrorClass(str, Enum):
    """4-class Sovereign error taxonomy."""

    TRANSIENT = "TRANSIENT"
    DETERMINISTIC = "DETERMINISTIC"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_finite_unit_float(val: float, name: str = "score") -> float:
    """Validate finite floating-point score in [0.0, 1.0]."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"{name} must be numeric")
    f = float(val)
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"{name} shall never be NaN or Inf")
    if f < 0.0 or f > 1.0:
        raise ValueError(f"{name} must lie in [0.0, 1.0]")
    return round(f, 6)


def _canonical_json_bytes(payload: Any) -> bytes:
    """Serialize JSON structures deterministically for cryptographic hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def compute_tool_pin_hash(
    server_id: str,
    tool_name: str,
    description: str,
    input_schema: Any = None,
) -> str:
    """Compute canonical 64-hex SHA-256 hash pin for an MCP tool definition."""
    if not isinstance(server_id, str) or not _SERVER_ID_RE.fullmatch(server_id):
        raise ValueError("Invalid server_id format for cryptographic pin")
    if not isinstance(tool_name, str) or not _TOOL_NAME_RE.fullmatch(tool_name):
        raise ValueError("Invalid tool_name format for cryptographic pin")
    if not isinstance(description, str):
        raise ValueError("Tool description must be a string")
    payload = {
        "server_id": server_id,
        "tool_name": tool_name,
        "description": description,
        "input_schema": input_schema if input_schema is not None else {},
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def has_invisible_or_bidi_unicode(text: str) -> Tuple[bool, Tuple[str, ...]]:
    """Detect zero-width, BiDi override/isolate, Unicode tag, or disallowed control characters."""
    if not text:
        return False, ()
    signals: list[str] = []
    for ch in text:
        cp = ord(ch)
        if ch in _ZERO_WIDTH_CHARS:
            signals.append(f"U+{cp:04X}:ZERO_WIDTH")
        elif cp in _BIDI_OVERRIDE_RANGE:
            signals.append(f"U+{cp:04X}:BIDI_OVERRIDE")
        elif cp in _BIDI_ISOLATE_RANGE:
            signals.append(f"U+{cp:04X}:BIDI_ISOLATE")
        elif cp in _UNICODE_TAG_RANGE:
            signals.append(f"U+{cp:04X}:UNICODE_TAG")
        elif cp < 0x20 and ch not in ("\n", "\r", "\t"):
            signals.append(f"U+{cp:04X}:CONTROL_BYTE")
        elif cp == 0x7F:
            signals.append("U+007F:DEL")
        if len(signals) >= 16:
            break
    unique = tuple(dict.fromkeys(signals))
    return bool(unique), unique


def _collect_schema_strings(schema: Any, depth: int = 0) -> list[str]:
    """Bounded recursive extraction of embedded schema strings for P17/P21 poisoning scans."""
    if depth > 8 or schema is None:
        return []
    out: list[str] = []
    if isinstance(schema, str):
        if len(schema) <= MAX_DESCRIPTION_CHARS:
            out.append(schema)
    elif isinstance(schema, dict):
        for k, v in schema.items():
            if len(out) >= 128:
                break
            if isinstance(k, str) and len(k) <= 256:
                out.append(k)
            out.extend(_collect_schema_strings(v, depth + 1))
    elif isinstance(schema, (list, tuple)):
        for item in schema[:64]:
            if len(out) >= 128:
                break
            out.extend(_collect_schema_strings(item, depth + 1))
    return out


class ToolRegistrationPin(BaseModel):
    """Immutable SHA-256 registration pin record for an MCP tool (#05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pin_id: str = Field(min_length=8, max_length=64, pattern=r"^PIN-[a-f0-9]{16}$")
    server_id: str = Field(pattern=SERVER_ID_PATTERN)
    tool_name: str = Field(pattern=TOOL_NAME_PATTERN)
    description_length: int = Field(ge=0, le=MAX_DESCRIPTION_CHARS)
    pin_sha256: str = Field(pattern=PIN_SHA256_PATTERN)
    surface: ChannelSurface = ChannelSurface.TOOL_DESCRIPTION_POISONING
    status: FirewallState = FirewallState.PINNED
    pinned_at_utc: str = Field(default_factory=utc_now_iso)


class PoisonScanFinding(BaseModel):
    """Deterministic tool poisoning detection record (#05 P1-P25)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(min_length=8, max_length=64, pattern=r"^PSF-[a-f0-9]{16}$")
    server_id: str = Field(pattern=SERVER_ID_PATTERN)
    tool_name: str = Field(pattern=TOOL_NAME_PATTERN)
    vector: str = Field(pattern=VECTOR_ID_PATTERN)
    surface: ChannelSurface = ChannelSurface.TOOL_DESCRIPTION_POISONING
    imperative_risk_score: float = Field(ge=0.0, le=1.0)
    invisible_unicode_detected: bool = False
    quarantine_triggered: bool = False
    matched_signals: Tuple[str, ...] = ()
    summary: str = Field(min_length=1, max_length=512)
    detected_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("imperative_risk_score")
    @classmethod
    def _validate_score(cls, v: float) -> float:
        return _ensure_finite_unit_float(v, "imperative_risk_score")

    @model_validator(mode="after")
    def _enforce_quarantine_invariant(self) -> "PoisonScanFinding":
        if (self.imperative_risk_score >= QUARANTINE_RISK_THRESHOLD or self.invisible_unicode_detected) and not self.quarantine_triggered:
            raise ValueError("Invariant breach: quarantine_triggered must be True when score >= 0.65 or invisible Unicode detected")
        return self


class ParameterBindingGuard(BaseModel):
    """Strict MCP tool argument key allowlist preventing P20 unknown-key injection (#05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str = Field(pattern=TOOL_NAME_PATTERN)
    allowed_keys: Tuple[str, ...]
    required_keys: Tuple[str, ...] = ()
    reject_extra_args: bool = True

    @field_validator("allowed_keys", "required_keys")
    @classmethod
    def _validate_keys(cls, vals: Tuple[str, ...]) -> Tuple[str, ...]:
        cleaned: list[str] = []
        for item in vals:
            if not isinstance(item, str) or not re.fullmatch(r"^[a-zA-Z0-9_.-]{1,128}$", item):
                raise ValueError(f"Invalid parameter key name: {item!r}")
            cleaned.append(item)
        return tuple(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def _validate_required_subset(self) -> "ParameterBindingGuard":
        allowed_set = set(self.allowed_keys)
        for req in self.required_keys:
            if req not in allowed_set:
                raise ValueError(f"Required parameter {req!r} must be present in allowed_keys")
        return self

    def validate_arguments(
        self, arguments: Dict[str, Any]
    ) -> Tuple[bool, Tuple[str, ...], Tuple[str, ...]]:
        """Return (is_valid, missing_required_keys, unknown_extra_keys)."""
        if not isinstance(arguments, dict):
            return False, self.required_keys, ("<non-dict-arguments>",)
        allowed_set = set(self.allowed_keys)
        missing = tuple(k for k in self.required_keys if k not in arguments or arguments[k] is None)
        unknown = tuple(sorted(str(k) for k in arguments.keys() if k not in allowed_set))
        if self.reject_extra_args and unknown:
            return False, missing, unknown
        if missing:
            return False, missing, unknown
        return True, missing, unknown


class McpToolContractSpec(BaseModel):
    """MCP tool capability boundary contract rejecting unsandboxed fallbacks (#03)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_id: str = Field(pattern=SERVER_ID_PATTERN)
    tool_name: str = Field(pattern=TOOL_NAME_PATTERN)
    authorized_roots: Tuple[str, ...] = Field(min_length=1, max_length=MAX_AUTHORIZED_ROOTS)
    allow_unsandboxed_fallback: bool = False
    follow_symlinks: bool = False

    @field_validator("allow_unsandboxed_fallback")
    @classmethod
    def _forbid_unsandboxed_fallback(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("allow_unsandboxed_fallback shall never be True")
        return v

    @field_validator("authorized_roots")
    @classmethod
    def _validate_roots(cls, roots: Tuple[str, ...]) -> Tuple[str, ...]:
        cleaned: list[str] = []
        for raw in roots:
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("authorized root entry must be a non-empty string")
            if "\x00" in raw:
                raise ValueError("authorized root shall never contain NUL byte")
            if _has_disallowed_uri_scheme(raw):
                raise ValueError("authorized root shall never be a URI scheme")
            resolved = str(Path(raw).resolve())
            cleaned.append(resolved)
        return tuple(dict.fromkeys(cleaned))


class InferredSandboxBoundary(BaseModel):
    """Sandbox boundary proving strict disjointness against canary sensitive targets (#03)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    boundary_id: str = Field(min_length=6, max_length=64, pattern=r"^BND-[a-f0-9]{16}$")
    server_id: str = Field(pattern=SERVER_ID_PATTERN)
    authorized_roots: Tuple[str, ...] = Field(min_length=1, max_length=MAX_AUTHORIZED_ROOTS)
    canary_tokens: Tuple[str, ...] = (
        "/etc/passwd",
        "/etc/shadow",
        "~/.ssh/id_rsa",
        "~/.aws/credentials",
    )

    @field_validator("authorized_roots")
    @classmethod
    def _validate_roots(cls, roots: Tuple[str, ...]) -> Tuple[str, ...]:
        return tuple(str(Path(r).resolve()) for r in roots if isinstance(r, str) and r.strip())

    @model_validator(mode="after")
    def _assert_canary_disjointness(self) -> "InferredSandboxBoundary":
        root_paths = [Path(r).resolve() for r in self.authorized_roots]
        for canary in self.canary_tokens:
            expanded = os.path.expanduser(canary)
            canary_path = (
                Path(expanded).resolve()
                if (os.path.isabs(expanded) or expanded.startswith("/"))
                else None
            )
            for root_p in root_paths:
                if canary_path is not None and (canary_path == root_p or canary_path.is_relative_to(root_p)):
                    raise ValueError(f"Sandbox boundary violates canary disjointness: {canary} overlaps {root_p}")
        return self


class SarifBypassFinding(BaseModel):
    """SARIF security bypass finding mapped to PT-001..PT-005 (#03)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: SarifRuleId
    layer: DetectionLayer
    path_candidate: str = Field(min_length=1, max_length=512)
    message: str = Field(min_length=1, max_length=512)


class ConfinementCheckResult(BaseModel):
    """Structured result from OS path component confinement verification (#03)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: ValidationVerdict
    allowed: bool
    sarif_rule_id: Optional[SarifRuleId] = None
    resolved_path: Optional[str] = None
    reason: str = Field(min_length=1, max_length=512)
    finding: Optional[SarifBypassFinding] = None


class FirewallDecisionDTO(BaseModel):
    """Complete MCP Guard decision envelope including FSM trace and quarantine ID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: FirewallState
    verdict: ValidationVerdict
    oracle_verdict: OracleVerdict
    allowed: bool
    pin: Optional[ToolRegistrationPin] = None
    findings: Tuple[PoisonScanFinding, ...] = ()
    trace: Tuple[FirewallState, ...] = ()
    quarantine_id: Optional[str] = None
    reason: str = Field(min_length=1, max_length=512)


_FSM_TRANSITIONS: Dict[Tuple[FirewallState, FirewallEvent], FirewallState] = {
    (FirewallState.UNVERIFIED, FirewallEvent.REGISTER_PIN): FirewallState.PINNED,
    (FirewallState.UNVERIFIED, FirewallEvent.SCHEMA_COLLISION): FirewallState.QUARANTINED,
    (FirewallState.UNVERIFIED, FirewallEvent.POISON_SCORE_EXCEEDED): FirewallState.QUARANTINED,
    (FirewallState.UNVERIFIED, FirewallEvent.CONFINEMENT_BREACH): FirewallState.CONFINED_DENY,
    (FirewallState.PINNED, FirewallEvent.VERIFY_PIN_MATCH): FirewallState.INSPECTION_PASSED,
    (FirewallState.PINNED, FirewallEvent.PIN_HASH_DRIFT): FirewallState.RUG_PULL_BLOCKED,
    (FirewallState.PINNED, FirewallEvent.SCHEMA_COLLISION): FirewallState.QUARANTINED,
    (FirewallState.PINNED, FirewallEvent.PARAM_BINDING_FAIL): FirewallState.QUARANTINED,
    (FirewallState.PINNED, FirewallEvent.PARAM_BINDING_PASS): FirewallState.INSPECTION_PASSED,
    (FirewallState.PINNED, FirewallEvent.CONFINEMENT_BREACH): FirewallState.CONFINED_DENY,
    (FirewallState.PINNED, FirewallEvent.POISON_SCORE_EXCEEDED): FirewallState.QUARANTINED,
    (FirewallState.PINNED, FirewallEvent.EXFIL_SINK_HIT): FirewallState.EXFIL_DETECTED,
    (FirewallState.INSPECTION_PASSED, FirewallEvent.PARAM_BINDING_PASS): FirewallState.INSPECTION_PASSED,
    (FirewallState.INSPECTION_PASSED, FirewallEvent.PARAM_BINDING_FAIL): FirewallState.QUARANTINED,
    (FirewallState.INSPECTION_PASSED, FirewallEvent.CONFINEMENT_BREACH): FirewallState.CONFINED_DENY,
    (FirewallState.INSPECTION_PASSED, FirewallEvent.POISON_SCORE_EXCEEDED): FirewallState.QUARANTINED,
    (FirewallState.INSPECTION_PASSED, FirewallEvent.EXFIL_SINK_HIT): FirewallState.EXFIL_DETECTED,
    (FirewallState.INSPECTION_PASSED, FirewallEvent.EXECUTE_COMPLETE): FirewallState.EXECUTED_CLEAN,
    (FirewallState.EXECUTED_CLEAN, FirewallEvent.RESET): FirewallState.PINNED,
    (FirewallState.INTENT_FLAGGED, FirewallEvent.EXFIL_SINK_HIT): FirewallState.EXFIL_DETECTED,
    (FirewallState.INTENT_FLAGGED, FirewallEvent.POISON_SCORE_EXCEEDED): FirewallState.QUARANTINED,
    (FirewallState.INTENT_FLAGGED, FirewallEvent.CONFINEMENT_BREACH): FirewallState.CONFINED_DENY,
}


def transition_firewall_state(
    state: FirewallState,
    event: FirewallEvent,
    *,
    clean_pin: bool = True,
) -> FirewallState:
    """Total deterministic transition delta(S, E) -> S' with absorbing terminal states."""
    if state in TERMINAL_FAILURE_STATES:
        return state
    if state is FirewallState.UNVERIFIED and event is FirewallEvent.REGISTER_PIN and not clean_pin:
        return FirewallState.QUARANTINED
    return _FSM_TRANSITIONS.get((state, event), FirewallState.QUARANTINED)


def scan_description_risk(
    server_id: str,
    tool_name: str,
    description: str,
    *,
    surface: ChannelSurface = ChannelSurface.TOOL_DESCRIPTION_POISONING,
    input_schema: Any = None,
) -> PoisonScanFinding:
    """Scan MCP tool description and parameter schema for poisoning vectors P1-P25."""
    bounded_desc = (description or "")[:MAX_DESCRIPTION_CHARS]
    schema_texts = _collect_schema_strings(input_schema)
    schema_blob = "\n".join(schema_texts)[:MAX_DESCRIPTION_CHARS]

    score = 0.0
    matched: list[str] = []
    vector = "P1"

    inv_desc, inv_desc_sigs = has_invisible_or_bidi_unicode(bounded_desc)
    inv_schema, inv_schema_sigs = has_invisible_or_bidi_unicode(schema_blob)
    invisible_detected = inv_desc or inv_schema
    if invisible_detected:
        score += 0.80
        matched.extend(inv_desc_sigs or inv_schema_sigs)
        vector = "P17"

    if _EXFIL_SINK_RE.search(bounded_desc) or _EXFIL_SINK_RE.search(schema_blob):
        score += 0.75
        matched.append("EXFIL_SINK")
        vector = "P18"

    if _IMPERATIVE_POISON_RE.search(bounded_desc):
        score += 0.70
        matched.append("IMPERATIVE_HIDDEN_DIRECTIVE")
        vector = "P17"
    elif schema_blob and _IMPERATIVE_POISON_RE.search(schema_blob):
        score += 0.70
        matched.append("SCHEMA_IMPERATIVE_INJECTION")
        vector = "P21"

    if _SENSITIVE_TARGET_RE.search(bounded_desc) or _SENSITIVE_TARGET_RE.search(schema_blob):
        score += 0.50
        matched.append("SENSITIVE_CREDENTIAL_TARGET")
        if vector == "P1":
            vector = "P12"

    clamped_score = _ensure_finite_unit_float(min(1.0, score), "imperative_risk_score")
    quarantine = clamped_score >= QUARANTINE_RISK_THRESHOLD or invisible_detected
    dedup_signals = tuple(dict.fromkeys(matched))[:16]
    seed = f"{server_id}:{tool_name}:{vector}:{','.join(dedup_signals)}:{len(bounded_desc)}"
    finding_id = f"PSF-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"
    summary = (
        f"Flagged tool poisoning vector {vector} (score={clamped_score:.2f}, invisible={invisible_detected})"
        if quarantine or dedup_signals
        else "Clean tool metadata scan"
    )
    return PoisonScanFinding(
        finding_id=finding_id,
        server_id=server_id,
        tool_name=tool_name,
        vector=vector,
        surface=surface,
        imperative_risk_score=clamped_score,
        invisible_unicode_detected=invisible_detected,
        quarantine_triggered=quarantine,
        matched_signals=dedup_signals,
        summary=summary,
    )


def _has_disallowed_uri_scheme(raw_text: str) -> bool:
    """Return True if raw_text carries a URI scheme (e.g. file://) while allowing Windows drive letters."""
    stripped = raw_text.strip()
    if not stripped:
        return False
    if _WINDOWS_DRIVE_RE.match(stripped):
        return False
    if stripped.lower().startswith("file:"):
        return True
    return bool(_URI_SCHEME_RE.match(stripped))


def _unquote_bounded(raw: str, max_decode_rounds: int = DEFAULT_MAX_DECODE_ROUNDS) -> str:
    """Bounded iterative percent-decoding detecting double/triple-encoding evasion."""
    if not isinstance(max_decode_rounds, int) or not (MIN_DECODE_ROUNDS <= max_decode_rounds <= MAX_DECODE_ROUNDS):
        raise ValueError(f"max_decode_rounds must be in [{MIN_DECODE_ROUNDS}, {MAX_DECODE_ROUNDS}]")
    current = raw
    for _ in range(max_decode_rounds):
        nxt = urllib.parse.unquote(current)
        if nxt == current:
            return current
        current = nxt
    if urllib.parse.unquote(current) != current:
        raise ValueError("path encoding does not stabilize")
    return current


def canonicalize_mcp_path(
    raw_path: str,
    root_dir: Optional[Union[str, Path]] = None,
    *,
    max_decode_rounds: int = DEFAULT_MAX_DECODE_ROUNDS,
) -> Path:
    """Decode and canonicalize a path candidate, rejecting NUL bytes, URIs, and '..' traversals."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("path must be a non-empty string")
    if len(raw_path) > 4096:
        raise ValueError("path exceeds 4096-character safety bound")
    if "\x00" in raw_path:
        raise ValueError("path contains null byte")

    unquoted = _unquote_bounded(raw_path.strip(), max_decode_rounds=max_decode_rounds)
    if "\x00" in unquoted:
        raise ValueError("decoded path contains null byte")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in unquoted):
        raise ValueError("path contains disallowed control characters")
    if _has_disallowed_uri_scheme(unquoted):
        raise ValueError("URI scheme not permitted in filesystem path")

    normalized_sep = unquoted.replace("\\", "/")
    if normalized_sep.startswith("//"):
        raise ValueError("UNC network path prefix not permitted")
    segments = [seg for seg in normalized_sep.split("/") if seg]
    if ".." in segments or normalized_sep == "..":
        raise ValueError("path traversal segment '..' escapes confinement boundary")

    candidate = Path(unquoted)
    if not candidate.is_absolute() and root_dir is not None:
        candidate = Path(root_dir) / candidate
    return candidate.resolve()


def _detect_internal_symlink_or_reparse(
    lexical_candidate: Path,
    resolved_roots: Tuple[Path, ...],
) -> Optional[Path]:
    """Check components strictly below any matching resolved root for symlinks/junctions."""
    try:
        cand_abs = Path(os.path.abspath(str(lexical_candidate)))
    except Exception:
        return lexical_candidate

    for root_res in resolved_roots:
        try:
            rel = cand_abs.relative_to(root_res)
        except ValueError:
            # Also try unresolved abspath if root had short names/parent symlinks
            continue
        cur = root_res
        for part in rel.parts:
            cur = cur / part
            if os.path.islink(cur):
                return cur
            if os.path.lexists(cur):
                # Catches Windows NTFS junctions even where os.path.islink() is False
                try:
                    if cur.resolve() != Path(os.path.abspath(str(cur))):
                        return cur
                except OSError:
                    return cur
    return None


def _deny_confinement(
    *,
    verdict: ValidationVerdict,
    rule_id: SarifRuleId,
    layer: DetectionLayer,
    raw_path: str,
    reason: str,
    resolved_path: Optional[str] = None,
) -> ConfinementCheckResult:
    """Build deterministic failed ConfinementCheckResult paired with SarifBypassFinding."""
    safe_candidate = (raw_path or "<empty>")[:512]
    return ConfinementCheckResult(
        verdict=verdict,
        allowed=False,
        sarif_rule_id=rule_id,
        resolved_path=resolved_path,
        reason=reason[:512],
        finding=SarifBypassFinding(
            rule_id=rule_id,
            layer=layer,
            path_candidate=safe_candidate,
            message=reason[:512],
        ),
    )


def is_component_confined(
    candidate_path: Union[str, Path],
    allowed_roots: Sequence[Union[str, Path]],
    *,
    follow_symlinks: bool = False,
    max_decode_rounds: int = DEFAULT_MAX_DECODE_ROUNDS,
) -> ConfinementCheckResult:
    """Verify OS component confinement within allowed_roots (blocks PT-001..PT-005 & TOCTOU symlinks)."""
    raw_str = str(candidate_path) if isinstance(candidate_path, Path) else candidate_path
    if not isinstance(raw_str, str) or not raw_str.strip():
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_TRAVERSAL,
            rule_id=SarifRuleId.PT_001,
            layer=DetectionLayer.CAPABILITY_MODEL,
            raw_path="<empty>",
            reason="Empty candidate path rejected",
        )

    if not allowed_roots:
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_UNSANDBOXED_FALLBACK,
            rule_id=SarifRuleId.PT_005,
            layer=DetectionLayer.SANDBOX_RUNTIME,
            raw_path=raw_str,
            reason="Empty authorized_roots forbids unsandboxed fallback (PT-005)",
        )

    if "\x00" in raw_str:
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_TRAVERSAL,
            rule_id=SarifRuleId.PT_001,
            layer=DetectionLayer.SAST_TAINT,
            raw_path=raw_str.replace("\x00", "\\x00"),
            reason="Null byte rejected in path candidate (PT-001)",
        )

    try:
        decoded = _unquote_bounded(raw_str.strip(), max_decode_rounds=max_decode_rounds)
    except ValueError as exc:
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_TRAVERSAL,
            rule_id=SarifRuleId.PT_001,
            layer=DetectionLayer.SAST_TAINT,
            raw_path=raw_str,
            reason=f"Percent-encoding anomaly rejected (PT-001): {exc}",
        )

    if "\x00" in decoded or any(ord(c) < 0x20 or ord(c) == 0x7F for c in decoded):
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_TRAVERSAL,
            rule_id=SarifRuleId.PT_001,
            layer=DetectionLayer.SAST_TAINT,
            raw_path=raw_str,
            reason="Decoded path contains NUL or control character (PT-001)",
        )

    if _has_disallowed_uri_scheme(decoded):
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_URI_SCHEME,
            rule_id=SarifRuleId.PT_003,
            layer=DetectionLayer.SAST_TAINT,
            raw_path=raw_str,
            reason="URI scheme smuggling (e.g. file://) prohibited in path arguments (PT-003)",
        )

    norm_sep = decoded.replace("\\", "/")
    if norm_sep.startswith("//"):
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_URI_SCHEME,
            rule_id=SarifRuleId.PT_003,
            layer=DetectionLayer.SAST_TAINT,
            raw_path=raw_str,
            reason="UNC network path prefix prohibited in workspace confinement (PT-003)",
        )

    if ".." in [seg for seg in norm_sep.split("/") if seg] or norm_sep == "..":
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_TRAVERSAL,
            rule_id=SarifRuleId.PT_001,
            layer=DetectionLayer.SAST_TAINT,
            raw_path=raw_str,
            reason="Explicit '..' traversal sequence rejected (PT-001)",
        )

    resolved_roots: list[Path] = []
    for root in allowed_roots:
        r_str = str(root).strip()
        if not r_str or _has_disallowed_uri_scheme(r_str) or "\x00" in r_str:
            return _deny_confinement(
                verdict=ValidationVerdict.DENY_UNSANDBOXED_FALLBACK,
                rule_id=SarifRuleId.PT_005,
                layer=DetectionLayer.CAPABILITY_MODEL,
                raw_path=raw_str,
                reason="Invalid authorized root configuration rejected fail-closed (PT-005)",
            )
        resolved_roots.append(Path(r_str).resolve())
    roots_tuple = tuple(resolved_roots)

    cand_obj = Path(decoded)
    if not cand_obj.is_absolute():
        cand_lexical = roots_tuple[0] / cand_obj
    else:
        cand_lexical = cand_obj

    symlink_hop = _detect_internal_symlink_or_reparse(cand_lexical, roots_tuple)
    cand_resolved = cand_lexical.resolve()
    inside = any(cand_resolved.is_relative_to(r) for r in roots_tuple)

    if symlink_hop is not None and not inside:
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_SYMLINK_ESCAPE,
            rule_id=SarifRuleId.PT_004,
            layer=DetectionLayer.SANDBOX_RUNTIME,
            raw_path=raw_str,
            resolved_path=str(cand_resolved),
            reason=f"Symlink/reparse TOCTOU escape blocked at {symlink_hop} -> {cand_resolved} (PT-004)",
        )

    if symlink_hop is not None and not follow_symlinks:
        return _deny_confinement(
            verdict=ValidationVerdict.DENY_SYMLINK_ESCAPE,
            rule_id=SarifRuleId.PT_004,
            layer=DetectionLayer.SANDBOX_RUNTIME,
            raw_path=raw_str,
            resolved_path=str(cand_resolved),
            reason=f"Untrusted symlink component disallowed when follow_symlinks=False: {symlink_hop} (PT-004)",
        )

    if inside:
        return ConfinementCheckResult(
            verdict=ValidationVerdict.ALLOW,
            allowed=True,
            sarif_rule_id=None,
            resolved_path=str(cand_resolved),
            reason="Path component-confined within authorized root",
            finding=None,
        )

    # Distinguish PT-002 sibling prefix collision (/workspace vs /workspace_secret)
    cand_norm_str = os.path.normcase(str(cand_resolved)).rstrip("\\/")
    for r in roots_tuple:
        r_norm_str = os.path.normcase(str(r)).rstrip("\\/")
        if r_norm_str and cand_norm_str.startswith(r_norm_str) and len(cand_norm_str) > len(r_norm_str):
            if cand_norm_str[len(r_norm_str)] not in ("/", "\\"):
                return _deny_confinement(
                    verdict=ValidationVerdict.DENY_SIBLING_PREFIX,
                    rule_id=SarifRuleId.PT_002,
                    layer=DetectionLayer.CAPABILITY_MODEL,
                    raw_path=raw_str,
                    resolved_path=str(cand_resolved),
                    reason=f"Sibling-prefix confinement bypass blocked: {cand_resolved} is outside root {r} (PT-002)",
                )

    return _deny_confinement(
        verdict=ValidationVerdict.DENY_TRAVERSAL,
        rule_id=SarifRuleId.PT_001,
        layer=DetectionLayer.SANDBOX_RUNTIME,
        raw_path=raw_str,
        resolved_path=str(cand_resolved),
        reason=f"Resolved path {cand_resolved} lies outside authorized roots (PT-001)",
    )


def _flatten_config_strings(obj: Any, depth: int = 0) -> list[str]:
    """Bounded extraction of strings inside an MCP server configuration dictionary."""
    if depth > 6 or obj is None:
        return []
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj[:MAX_DESCRIPTION_CHARS])
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if len(out) >= 128:
                break
            if isinstance(k, str):
                out.append(k[:256])
            out.extend(_flatten_config_strings(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj[:64]:
            if len(out) >= 128:
                break
            out.extend(_flatten_config_strings(item, depth + 1))
    return out


def scan_mcp_config_perimeter(config_obj: Dict[str, Any]) -> Tuple[PoisonScanFinding, ...]:
    """Audit .mcp.json / mcp_config.json entries for poisoned definitions or unsandboxed flags."""
    if not isinstance(config_obj, dict):
        return ()
    servers = config_obj.get("mcpServers") or config_obj.get("servers") or {}
    if not isinstance(servers, dict):
        return ()

    findings: list[PoisonScanFinding] = []
    for raw_name, entry in servers.items():
        if not isinstance(raw_name, str) or not isinstance(entry, dict):
            continue
        safe_server = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw_name)[:128] or "unknown-server"
        if entry.get("allow_unsandboxed_fallback") is True or entry.get("unsandboxed") is True:
            seed = f"cfg:{safe_server}:PT-005"
            findings.append(
                PoisonScanFinding(
                    finding_id=f"PSF-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}",
                    server_id=safe_server,
                    tool_name=safe_server,
                    vector="P20",
                    surface=ChannelSurface.CONFIG_FILE_POISONING,
                    imperative_risk_score=0.90,
                    invisible_unicode_detected=False,
                    quarantine_triggered=True,
                    matched_signals=("UNSANDBOXED_FALLBACK_FLAG",),
                    summary=f"MCP config '{raw_name}' sets disallowed unsandboxed fallback flag",
                )
            )

        flat_text = "\n".join(_flatten_config_strings(entry))
        if flat_text:
            scan = scan_description_risk(
                safe_server,
                safe_server,
                flat_text,
                surface=ChannelSurface.CONFIG_FILE_POISONING,
            )
            if scan.quarantine_triggered:
                findings.append(scan)

        inline_tools = entry.get("tools")
        if isinstance(inline_tools, list):
            for t_obj in inline_tools[:64]:
                if isinstance(t_obj, dict) and isinstance(t_obj.get("name"), str):
                    t_name = re.sub(r"[^a-zA-Z0-9_.:-]", "_", t_obj["name"])[:128] or "tool"
                    t_desc = str(t_obj.get("description", ""))
                    t_scan = scan_description_risk(
                        safe_server,
                        t_name,
                        t_desc,
                        surface=ChannelSurface.TOOL_DESCRIPTION_POISONING,
                        input_schema=t_obj.get("inputSchema"),
                    )
                    if t_scan.quarantine_triggered:
                        findings.append(t_scan)

    return tuple(findings)


__all__ = [
    "ChannelSurface",
    "ConfinementCheckResult",
    "DEFAULT_MAX_DECODE_ROUNDS",
    "DetectionLayer",
    "ErrorClass",
    "FirewallDecisionDTO",
    "FirewallEvent",
    "FirewallState",
    "InferredSandboxBoundary",
    "MANIFEST_HASH",
    "MAX_AUTHORIZED_ROOTS",
    "MAX_DECODE_ROUNDS",
    "MAX_DESCRIPTION_CHARS",
    "McpToolContractSpec",
    "OracleVerdict",
    "PIN_SHA256_PATTERN",
    "ParameterBindingGuard",
    "PoisonScanFinding",
    "QUARANTINE_RISK_THRESHOLD",
    "SERVER_ID_PATTERN",
    "SarifBypassFinding",
    "SarifRuleId",
    "TERMINAL_FAILURE_STATES",
    "TOOL_NAME_PATTERN",
    "ToolRegistrationPin",
    "VECTOR_ID_PATTERN",
    "ValidationVerdict",
    "canonicalize_mcp_path",
    "compute_tool_pin_hash",
    "has_invisible_or_bidi_unicode",
    "is_component_confined",
    "scan_description_risk",
    "scan_mcp_config_perimeter",
    "transition_firewall_state",
    "utc_now_iso",
]
