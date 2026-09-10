"""
src/ctxfw/sieve/engine.py — Deterministic Specification Sieve Engine (HU-11 Port)
Evaluates intake architectural briefs, derives negative invariant floors,
computes the Axiom Completeness Index (ACI), and generates cryptographic attestation manifests.
"""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import List, Tuple
from pydantic import BaseModel, ConfigDict, Field


class QuarantineStatus(str, Enum):
    VERIFIED = "VERIFIED"
    QUARANTINED = "QUARANTINED"


class SpecEvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    aci_score: float = Field(..., description="Axiom Completeness Index with 4 decimal precision")
    negative_invariants_count: int = Field(..., description="Number of distinct negative invariants extracted")
    extracted_never_clauses: list[str] = Field(default_factory=list, description="Extracted distinct 'never' clauses")
    status: str = Field(..., description="Classification status: VERIFIED or QUARANTINED")
    remediation_notes: list[str] = Field(default_factory=list, description="Guidance notes for triage or remediation")
    manifest_hash: str = Field(..., description="SHA-256 seal of the lexicographically sorted negative invariants")
    explicit_bounds: int = Field(0, description="Count of variables with explicit mathematical bounds")
    total_variables: int = Field(0, description="Total identified domain variables")
    has_state_machine: bool = Field(False, description="Whether deterministic FSM states are specified")
    has_error_taxonomy: bool = Field(False, description="Whether explicit error taxonomy/quarantine is defined")
    formal_proof_included: bool = Field(False, description="Whether formal proof/attestation is included")


def compute_aci(
    explicit_bounds: int,
    total_variables: int,
    has_state_machine: bool,
    has_error_taxonomy: bool,
    formal_proof_included: bool,
) -> float:
    """
    Computes the Axiom Completeness Index (ACI) as a deterministic weighted score [0.0000, 1.0000].
    
    Weights:
      - Variable Bounds Coverage: 0.40 (explicit_bounds / total_variables, clamped to [0, 1])
      - Finite State Machine Determinism: 0.30
      - Error Taxonomy & Fault Domain: 0.15
      - Formal Proof / Cryptographic Attestation: 0.15
    """
    if total_variables <= 0:
        bounds_ratio = 0.0
    else:
        bounds_ratio = min(1.0, max(0.0, float(explicit_bounds) / float(total_variables)))

    score = (
        0.40 * bounds_ratio
        + 0.30 * (1.0 if has_state_machine else 0.0)
        + 0.15 * (1.0 if has_error_taxonomy else 0.0)
        + 0.15 * (1.0 if formal_proof_included else 0.0)
    )
    return float(round(score, 4))


# Regular expression detecting negative constraints containing 'never' or 'shall never'
_NEVER_REGEX = re.compile(r"\b(?:shall\s+never|never)\b", re.IGNORECASE)


def extract_negative_invariants(brief_text: str) -> list[str]:
    """
    Extracts distinct negative constraints expressing forbidden system actions
    containing 'never' or 'shall never' (case-insensitive).
    Deduplicates distinct clauses while preserving discovery order.
    """
    if not brief_text or not brief_text.strip():
        return []

    lines = brief_text.splitlines()
    extracted: list[str] = []
    seen_normalized: set[str] = set()

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # Strip markdown bullet markers, blockquote markers, and numbering
        cleaned = re.sub(r"^(?:[-*•+]|\d+\.|\>)\s+", "", cleaned).strip()

        if _NEVER_REGEX.search(cleaned):
            # Clean punctuation and quotes
            normalized_key = cleaned.strip("`'\" ").lower()
            if len(normalized_key) >= 8 and normalized_key not in seen_normalized:
                seen_normalized.add(normalized_key)
                extracted.append(cleaned)

    return extracted


def generate_manifest_hash(negative_invariants: list[str]) -> str:
    """
    Generates a deterministic SHA-256 cryptographic attestation seal (64 hex characters)
    by sorting negative invariant clauses lexicographically.
    """
    if not negative_invariants:
        return hashlib.sha256(b"").hexdigest()

    sorted_clauses = sorted(clause.strip() for clause in negative_invariants)
    canonical_repr = "\n".join(sorted_clauses)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def parse_brief_metrics(brief_text: str) -> Tuple[int, int, bool, bool, bool]:
    """
    Scans markdown brief text to derive ACI parameters:
    (explicit_bounds, total_variables, has_state_machine, has_error_taxonomy, formal_proof_included).
    """
    text_lower = brief_text.lower()

    # 1. State Machine Detection
    has_fsm = bool(
        re.search(r"\b(state\s+machine|fsm|state\s+transition|transition\s+map|lifecycle\s+state|statediagram)\b", text_lower)
    )

    # 2. Error Taxonomy Detection
    has_error = bool(
        re.search(r"\b(error\s+taxonomy|quarantine|quarantine\s+sink|error\s+handling|exception\s+hierarchy|fault\s+domain)\b", text_lower)
    )

    # 3. Formal Proof / Attestation Detection
    has_proof = bool(
        re.search(r"\b(formal\s+proof|mathematical\s+proof|proof\s+of\s+correctness|invariant\s+proof|sha-?256\s+attestation|cryptographic\s+attestation)\b", text_lower)
    )

    # 4. Explicit Bounds vs Total Variables
    explicit_bounds = 0
    total_variables = 0

    # Check for direct numeric annotations in brief (e.g., "Explicit Bounds: 5", "Total Variables: 5")
    m_bounds = re.search(r"(?:explicit\s*bounds|bounded\s*variables?)\s*[:=]\s*(\d+)", text_lower)
    m_total = re.search(r"(?:total\s*variables?|domain\s*variables?)\s*[:=]\s*(\d+)", text_lower)
    m_ratio = re.search(r"bounds?\s*[:=]\s*(\d+)\s*/\s*(\d+)", text_lower)
    m_frac = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:bounded|bounds|explicit)", text_lower)

    if m_ratio:
        explicit_bounds = int(m_ratio.group(1))
        total_variables = int(m_ratio.group(2))
    elif m_frac:
        explicit_bounds = int(m_frac.group(1))
        total_variables = int(m_frac.group(2))
    elif m_bounds and m_total:
        explicit_bounds = int(m_bounds.group(1))
        total_variables = int(m_total.group(1))
    elif m_bounds:
        explicit_bounds = int(m_bounds.group(1))
        total_variables = explicit_bounds
    else:
        # Heuristic extraction by analyzing variable definitions and bounds expressions
        var_lines = []
        for line in brief_text.splitlines():
            line_str = line.strip()
            if re.search(r"\b(variable|field|parameter|param|timeout|limit|buffer|threshold|latency|concurrency)\b", line_str, re.IGNORECASE):
                var_lines.append(line_str)

        if var_lines:
            total_variables = len(var_lines)
            bounded_count = 0
            for vline in var_lines:
                if re.search(r"(?:<=|>=|<|>|min|max|bound|range|between|ge=|le=|\[\d+)", vline, re.IGNORECASE):
                    bounded_count += 1
            explicit_bounds = bounded_count
        else:
            # Check if generic bounds or constraints are stated
            has_bounds_keywords = bool(re.search(r"\b(bounds|bounded|boundaries|tolerance|threshold)\b", text_lower))
            if has_bounds_keywords:
                explicit_bounds = 1
                total_variables = 1
            else:
                explicit_bounds = 0
                total_variables = 1 if (has_fsm or has_error or has_proof) else 0

    return explicit_bounds, total_variables, has_fsm, has_error, has_proof


def evaluate_specification(brief_text: str) -> SpecEvaluationResult:
    """
    Evaluates an intake brief against axiomatic determinism criteria.
    Classifies as VERIFIED if ACI >= 0.9000 and distinct negative invariants >= 5;
    otherwise classifies as QUARANTINED with comprehensive remediation notes.
    """
    negative_invariants = extract_negative_invariants(brief_text)
    exp_bounds, total_vars, has_fsm, has_error, has_proof = parse_brief_metrics(brief_text)

    aci = compute_aci(
        explicit_bounds=exp_bounds,
        total_variables=total_vars,
        has_state_machine=has_fsm,
        has_error_taxonomy=has_error,
        formal_proof_included=has_proof,
    )

    manifest_hash = generate_manifest_hash(negative_invariants)

    # Invariant floor and activation threshold check
    is_floor_met = len(negative_invariants) >= 5
    is_aci_met = aci >= 0.9000

    if is_floor_met and is_aci_met:
        status = QuarantineStatus.VERIFIED.value
        remediation_notes = ["Specification satisfies axiomatic completeness (ACI >= 0.9000) and negative invariant floor (>= 5)."]
    else:
        status = QuarantineStatus.QUARANTINED.value
        remediation_notes = []
        if not is_floor_met:
            remediation_notes.append(
                f"Negative invariants floor violated: found {len(negative_invariants)} distinct clauses, minimum required is 5 ('never' or 'shall never')."
            )
        if not is_aci_met:
            remediation_notes.append(
                f"Axiom Completeness Index (ACI) {aci:.4f} is below activation threshold 0.9000."
            )
            if total_vars > 0 and (exp_bounds / total_vars) < 0.75:
                remediation_notes.append(
                    f"Ambiguous or insufficient variable bounds ({exp_bounds}/{total_vars} variables explicitly bounded)."
                )
            if not has_fsm:
                remediation_notes.append("Missing deterministic state machine (FSM) specification.")
            if not has_error:
                remediation_notes.append("Missing explicit error taxonomy or quarantine routing specification.")
            if not has_proof:
                remediation_notes.append("Missing formal proof of correctness or cryptographic attestation seal.")

    return SpecEvaluationResult(
        aci_score=aci,
        negative_invariants_count=len(negative_invariants),
        extracted_never_clauses=negative_invariants,
        status=status,
        remediation_notes=remediation_notes,
        manifest_hash=manifest_hash,
        explicit_bounds=exp_bounds,
        total_variables=total_vars,
        has_state_machine=has_fsm,
        has_error_taxonomy=has_error,
        formal_proof_included=has_proof,
    )
