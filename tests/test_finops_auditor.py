"""
tests/test_finops_auditor.py — Verification Matrix for FinOps Ledger & Token Savings
Validates in-memory bundle auditing, persistent SQLite WAL aggregation,
USD cost avoidance calculations, and machine-readable audit report exports.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from ctxfw.core.contracts import OptimizationResultDTO, PruningDepth
from ctxfw.storage.cache import LocalSemanticCache
from ctxfw.auditor import FinOpsAuditor, FinOpsReportDTO
from ctxfw.core.topological import TopologicalContextBundleDTO


def test_audit_bundle_token_and_usd_calculation():
    """Asserts that audit_bundle accurately aggregates cold and warm token savings and converts to USD."""
    entry_cold = OptimizationResultDTO(
        pruned_code="def cold(): ...",
        original_chars=4000,
        pruned_chars=1000,
        estimated_tokens_saved=750,
        savings_percentage=75.0,
        cache_hit=False,
        execution_ms=1.2,
        depth=PruningDepth.INTERFACE,
    )
    entry_warm = OptimizationResultDTO(
        pruned_code="def warm(): ...",
        original_chars=2000,
        pruned_chars=500,
        estimated_tokens_saved=375,
        savings_percentage=75.0,
        cache_hit=True,
        execution_ms=0.4,
        depth=PruningDepth.NOMINAL,
    )

    bundle = TopologicalContextBundleDTO(
        root_target="main.py",
        entries={"service.py": entry_cold, "repo.py": entry_warm},
    )

    report = FinOpsAuditor.audit_bundle(bundle, price_per_million_tokens=3.0)

    assert isinstance(report, FinOpsReportDTO)
    # Total evaluated: 4000 // 4 + 2000 // 4 = 1000 + 500 = 1500 tokens
    assert report.total_tokens_evaluated == 1500
    # Cold savings: 750 tokens
    assert report.tokens_saved_cold == 750
    # Warm bypass savings: 500 tokens
    assert report.tokens_saved_cache_bypass == 500
    # Net saved: 1250 tokens
    assert report.net_tokens_saved == 1250
    # USD: (1250 / 1_000_000) * 3.0 = 0.00375
    assert report.estimated_usd_savings == 0.00375
    assert report.cache_hit_ratio == 50.0
    assert report.air_gapped_certified is True


def test_audit_cache_sqlite_aggregation(tmp_path: Path):
    """Asserts that audit_cache correctly aggregates records from SQLite WAL tokens_cache."""
    db_file = str(tmp_path / "finops_test_cache.db")
    cache = LocalSemanticCache(db_path=db_file)

    dto1 = OptimizationResultDTO(
        pruned_code="def a(): ...",
        original_chars=2000,
        pruned_chars=800,
        estimated_tokens_saved=300,
        savings_percentage=60.0,
        cache_hit=False,
        execution_ms=1.1,
        depth=PruningDepth.INTERFACE,
    )
    dto2 = OptimizationResultDTO(
        pruned_code="def b(): ...",
        original_chars=4000,
        pruned_chars=1200,
        estimated_tokens_saved=700,
        savings_percentage=70.0,
        cache_hit=False,
        execution_ms=1.4,
        depth=PruningDepth.NOMINAL,
    )

    cache.set("key1", dto1)
    cache.set("key2", dto2)

    report = FinOpsAuditor.audit_cache(db_file, price_per_million_tokens=3.0)

    assert report.total_tokens_evaluated == (2000 + 4000) // 4
    assert report.net_tokens_saved == 1000
    assert report.estimated_usd_savings == round((1000 / 1_000_000.0) * 3.0, 6)
    assert report.cache_hit_ratio == 100.0


def test_export_audit_generates_valid_json(tmp_path: Path):
    """Asserts that export_audit writes a compliant, parseable JSON report to disk."""
    report = FinOpsReportDTO(
        total_tokens_evaluated=50000,
        tokens_saved_cold=35000,
        tokens_saved_cache_bypass=10000,
        net_tokens_saved=45000,
        estimated_usd_savings=0.135,
        cache_hit_ratio=25.0,
        air_gapped_certified=True,
        timestamp="2026-09-06T19:45:00+00:00",
    )

    export_path = tmp_path / "finops_audit.json"
    FinOpsAuditor.export_audit(report, str(export_path))

    assert export_path.is_file()
    data = json.loads(export_path.read_text(encoding="utf-8"))

    assert data["net_tokens_saved"] == 45000
    assert data["estimated_usd_savings"] == 0.135
    assert data["air_gapped_certified"] is True
