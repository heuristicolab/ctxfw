"""
scripts/test_d3_live_harness.py — Live D3 Context Resolution and Telemetry Harness
Axiom Manifest Hash: f307d4cf57448e0eff6ceaa55b131a0e0a9df208287e3fd05064f4dd3e7eccaf

Executes live D3 ambient cartography context resolution on src/ctxfw/core/topological.py,
measures SQLite WAL query latency, verifies d3_symbol_index interaction,
and records the real-time event in %LOCALAPPDATA%\\ctxfw\\tokens.db.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ctxfw.config import ContextDepthLevel, CtxfwConfigDTO
from ctxfw.core.contracts import PruningDepth, TelemetryRecordDTO
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.core.topological import ContextFirewallEngine
from ctxfw.storage.cache import LocalSemanticCache, get_canonical_cache_path
from ctxfw.storage.telemetry import TelemetryLedger, get_or_create_dev_uuid


def run_live_d3_resolution():
    project_root = REPO_ROOT
    target_rel = "src/ctxfw/core/topological.py"
    target_path = project_root / target_rel

    print("=" * 80)
    print("  CTXFW // LIVE D3 AMBIENT CARTOGRAPHY ENGINE EXECUTION")
    print(f"  Target File (D0): {target_rel}")
    print(f"  Project Root:     {project_root}")
    print("=" * 80)

    # 1. Prepare engine & config
    db_path = get_canonical_cache_path()
    cache = LocalSemanticCache(db_path=db_path)
    engine = ContextFirewallEngine(project_root=project_root, cache=cache)

    cfg = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        distractor_budget=150,
        subsystem_clamping=True,
        stale_reads_on_herd=True,
    )

    # 2. Measure resolution latency (Warm access querying d3_symbol_index)
    t0 = time.perf_counter_ns()
    bundle = engine.build_context(target_path, depth_config=cfg)
    elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000

    # 3. Verify d3_symbol_index was queried in SQLite WAL
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    cur = conn.cursor()
    cur.execute("""
        SELECT module_rel_path, symbol_count, symbols_json, updated_at 
        FROM d3_symbol_index 
        WHERE module_rel_path = 'src/ctxfw/storage/telemetry.py'
    """)
    d3_row = cur.fetchone()

    # 4. Compute token metrics for telemetry ledger
    total_orig_tokens = 0
    total_pruned_tokens = 0

    for rel_path, dto in bundle.entries.items():
        orig_tok = DeterministicContextPruner.estimate_tokens(dto.original_chars)
        pruned_tok = DeterministicContextPruner.estimate_tokens(dto.pruned_chars)
        total_orig_tokens += orig_tok
        total_pruned_tokens += pruned_tok

    manifest_tokens = DeterministicContextPruner.estimate_tokens(len(bundle.ambient_manifest or ""))
    total_delivered_tokens = total_pruned_tokens + manifest_tokens
    saved_tokens = max(0, total_orig_tokens - total_delivered_tokens)
    usd_avoided = (saved_tokens / 1_000_000) * 3.0  # Claude 3.5 Sonnet baseline ($3/Mtok)

    # 5. Record telemetry event in %LOCALAPPDATA%\ctxfw\tokens.db
    dev_uuid = get_or_create_dev_uuid()
    ledger = TelemetryLedger(db_path=db_path)
    now_utc = datetime.now(timezone.utc).isoformat()

    record = TelemetryRecordDTO(
        dev_uuid=dev_uuid,
        timestamp_utc=now_utc,
        model_target="claude-3-5-sonnet",
        tokens_orig=total_orig_tokens,
        tokens_pruned=total_delivered_tokens,
        usd_avoided=round(usd_avoided, 6),
        team=os.environ.get("CTXFW_TEAM", "Engineering"),
    )
    inserted_id = ledger.record_event(record, synced=0)

    # 6. Retrieve newly inserted ledger record from database
    cur.execute("""
        SELECT id, dev_uuid, timestamp_utc, model_target, tokens_orig, tokens_pruned, usd_avoided, team, synced
        FROM telemetry_ledger
        WHERE id = ?
    """, (inserted_id,))
    ledger_row = cur.fetchone()
    conn.close()

    # --------------------------------------------------------------------------
    # CONSOLE OUTPUT PRESENTATION
    # --------------------------------------------------------------------------
    print("\n[1] MANIFIESTO AMBIENTAL RESULTANTE ([D3] Zero-Syntax Symbol Index):")
    print("-" * 80)
    print(bundle.ambient_manifest)
    print("-" * 80)

    print("\n[2] LATENCIA DE RESOLUCIÓN & VERIFICACIÓN DE CACHÉ (d3_symbol_index):")
    print("-" * 80)
    print(f"  • Latencia de Resolución D3: {elapsed_ms:.3f} ms")
    sla_verdict = "[PASS] CONFORME AL SLA (<= 25.0 ms)" if elapsed_ms <= 25.0 else "[WARN] EXCEEDE SLA"
    print(f"  • Cumplimiento de SLA:       {sla_verdict}")
    if d3_row:
        mod_path, sym_count, sym_json, updated_at = d3_row
        print(f"  • Verificación B-Tree Index: [HIT] Módulo '{mod_path}' localizado en d3_symbol_index")
        print(f"  • Símbolos Extraídos:        {sym_count} símbolos ({sym_json})")
        print(f"  • Timestamp de Indexación:   {updated_at}")
    else:
        print("  • Verificación B-Tree Index: [MISS] Registro no encontrado")
    print("-" * 80)

    print("\n[3] NUEVO REGISTRO INSERTADO EN %LOCALAPPDATA%\\ctxfw\\tokens.db:")
    print("-" * 80)
    if ledger_row:
        r_id, r_uuid, r_ts, r_model, r_orig, r_pruned, r_usd, r_team, r_sync = ledger_row
        net_saved = r_orig - r_pruned
        pct_saved = (net_saved / r_orig * 100.0) if r_orig > 0 else 0.0
        print(f"  • ID de Transacción:         #{r_id}")
        print(f"  • UUID de Desarrollador:     {r_uuid}")
        print(f"  • Timestamp UTC:             {r_ts}")
        print(f"  • Modelo Objetivo:           {r_model}")
        print(f"  • Tokens Brutos (Raw):       {r_orig:,} tokens")
        print(f"  • Tokens Entregados (D3):    {r_pruned:,} tokens")
        print(f"  • Ahorro Neto de Tokens:     {net_saved:,} tokens ({pct_saved:.1f}% de reducción)")
        print(f"  • FinOps Ahorrado (USD):     ${r_usd:.6f} USD")
        print(f"  • Equipo / Entorno:          {r_team} (Estado Sync: {r_sync})")
    else:
        print("  [ERROR] No se pudo verificar la inserción en telemetry_ledger.")
    print("=" * 80)


if __name__ == "__main__":
    run_live_d3_resolution()
