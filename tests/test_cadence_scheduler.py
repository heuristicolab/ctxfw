# manifest_hash: 34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c
"""
Verification Matrix for Wave 2 Block D.2 :: #19 Cadence Deterministic Strategic
Agent Guidance, Proxy AIMD Scheduler, and SandboxSnapshotStore Rollback Linkage.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest
from pydantic import ValidationError

from ctxfw.budget import (
    CADENCE_MANIFEST_HASH,
    CADENCE_SCHEMA_PATH,
    PACKAGE_DIR,
    CadenceEvent,
    CadenceState,
    CadenceStore,
    CadenceTelemetrySignals,
    InterventionVerdict,
    MisbehaviorCategory,
    ScaffoldType,
    SchedulerConfig,
    TokenLeverageTelemetry,
    TrajectoryStepProposal,
    TwoTierVerdict,
    cadence_transition,
    compute_token_leverage,
    evaluate_deterministic_cadence,
    load_cadence_schema_sql,
    should_trigger_inspection,
    update_inspection_interval,
)
from ctxfw.proxy import app
from ctxfw.storage.cache import LocalSemanticCache
from ctxfw.storage.snapshots import SandboxSnapshotStore, SnapshotArchiveCell


def test_cadence_files_carry_manifest_hash_zero_crlf_and_no_proxy_deps():
    targets = (
        PACKAGE_DIR / "cadence.py",
        PACKAGE_DIR / "cadence_schema.sql",
        PACKAGE_DIR / "cadence_store.py",
        PACKAGE_DIR / "__init__.py",
        Path(__file__),
    )
    for path in targets:
        raw = path.read_bytes()
        assert b"\r" not in raw, f"CRLF detected in {path}"
        assert CADENCE_MANIFEST_HASH.encode("utf-8") in raw, f"Missing manifest_hash in {path}"

    assert "CREATE TABLE IF NOT EXISTS cadence_occ_ledger" in load_cadence_schema_sql()
    assert CADENCE_SCHEMA_PATH.is_file()

    # Pure isolation: cadence and cadence_store must never import fastapi, httpx, or auxiliary LLM libs
    import ast
    for mod_path in (PACKAGE_DIR / "cadence.py", PACKAGE_DIR / "cadence_store.py"):
        tree = ast.parse(mod_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in {"fastapi", "httpx", "anthropic", "openai", "uvicorn", "tree_sitter", "starlette"}
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in {"fastapi", "httpx", "anthropic", "openai", "uvicorn", "tree_sitter", "starlette"}

    script = (
        "import sys\n"
        "import ctxfw\n"
        "before = set(sys.modules)\n"
        "import ctxfw.budget.cadence\n"
        "import ctxfw.budget.cadence_store\n"
        "added = set(sys.modules) - before\n"
        "for banned in ('fastapi', 'httpx', 'anthropic', 'openai', 'uvicorn', 'tree_sitter', 'starlette'):\n"
        "    assert banned not in added, f'Cadence unexpectedly imported: {banned}'\n"
        "for globally_absent in ('fastapi', 'anthropic', 'openai', 'uvicorn', 'tree_sitter', 'starlette'):\n"
        "    assert globally_absent not in sys.modules, f'Unexpected heavy module: {globally_absent}'\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_cadence_lazy_import_and_open_scaffold_type():
    script = (
        "import sys\n"
        "import ctxfw.budget as b\n"
        "assert 'ctxfw.budget.cadence' not in sys.modules\n"
        "assert 'ctxfw.budget.cadence_store' not in sys.modules\n"
        "_ = b.SchedulerConfig\n"
        "assert 'ctxfw.budget.cadence' in sys.modules\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    for sc in ("claude_code", "cursor", "aider-v2", ScaffoldType.MINI_SWE_AGENT, ScaffoldType.CTXFW_PRUNER_AGENT):
        cfg = SchedulerConfig(scaffold_type=ScaffoldType(sc), i_base=2, delta_step=2, i_max=10)
        assert str(cfg.scaffold_type) == sc


def test_aimd_interval_recurrence_verdict_invariant_and_fsm():
    assert should_trigger_inspection(0, -1, 1) is True
    assert should_trigger_inspection(1, 0, 2) is False
    assert should_trigger_inspection(2, 0, 2) is True

    assert update_inspection_interval(2, InterventionVerdict.ADVISORY, i_base=2, delta_step=2, i_max=6) == 4
    assert update_inspection_interval(4, InterventionVerdict.ADVISORY, i_base=2, delta_step=2, i_max=6) == 6
    assert update_inspection_interval(6, InterventionVerdict.ADVISORY, i_base=2, delta_step=2, i_max=6) == 6
    assert update_inspection_interval(6, InterventionVerdict.REPLACEMENT, i_base=2, delta_step=2, i_max=6) == 2

    assert compute_token_leverage(4000, 1000) == 4.0
    assert compute_token_leverage(100, 0) == 100.0
    with pytest.raises(ValueError):
        compute_token_leverage(-1, 100)

    # REPLACEMENT cannot carry action_executed=1
    with pytest.raises(ValidationError):
        TwoTierVerdict(
            verdict_id="V-BAD",
            run_id="R-1",
            step_index=1,
            verdict=InterventionVerdict.REPLACEMENT,
            category=MisbehaviorCategory.BREAKER_TRIP,
            action_executed=1,
            guidance_note="invalid",
            next_interval=2,
            state=CadenceState.REPLACEMENT_VETOED,
            cadence_seal_sha256="a" * 64,
        )

    s1 = cadence_transition(CadenceState.EXECUTING_AUTONOMOUS, CadenceEvent.STEP_DUE)
    s2 = cadence_transition(s1, CadenceEvent.INSPECT_SIGNAL_CLEAN)
    s3 = cadence_transition(s2, CadenceEvent.VERDICT_REPLACEMENT)
    assert s3 == CadenceState.REPLACEMENT_VETOED
    assert cadence_transition(CadenceState.COMPLETED, CadenceEvent.STEP_DUE) == CadenceState.QUARANTINED


def test_cadence_store_occ_ledger_and_snapshot_rollback_on_replacement(tmp_path: Path):
    import hashlib

    snap_repo = tmp_path / "repo_ws"
    snap_repo.mkdir()
    (snap_repo / "app.py").write_text("x = 1\n", encoding="utf-8")

    cache = LocalSemanticCache(str(tmp_path / "cache_cadence.db"))
    snap_store = SandboxSnapshotStore(tmp_path / "snapshots.db")
    cad_store = CadenceStore(tmp_path / "cadence.db")
    try:
        snap_store.register_run("RUN-SNAP-01", snap_repo)
        root_cell = SnapshotArchiveCell(
            snapshot_id="snap-root",
            run_id="RUN-SNAP-01",
            project_root=str(snap_repo),
            step_index=0,
            working_tree_digest=hashlib.sha256(b"clean").hexdigest(),
            pass_rate=1.0,
            failing_tests=0,
        )
        bad_cell = SnapshotArchiveCell(
            snapshot_id="snap-bad",
            run_id="RUN-SNAP-01",
            project_root=str(snap_repo),
            parent_snapshot_id="snap-root",
            step_index=3,
            working_tree_digest=hashlib.sha256(b"dirty").hexdigest(),
            pass_rate=0.0,
            failing_tests=4,
        )
        snap_store.checkpoint_snapshot(root_cell)
        snap_store.checkpoint_snapshot(bad_cell)
        config = SchedulerConfig(scaffold_type=ScaffoldType("claude_code"), i_base=2, delta_step=1, i_max=8, max_consecutive_errors=3)

        # Step 1: clean advisory step -> AIMD expands interval
        v1 = cad_store.evaluate_and_record_step(
            proposal=TrajectoryStepProposal(
                proposal_id="P-01",
                run_id="RUN-CAD-01",
                session_id="SES-CAD-01",
                scaffold_type=ScaffoldType("claude_code"),
                step_index=2,
                last_inspection_step=-1,
                current_interval=2,
                signals=CadenceTelemetrySignals(
                    budget_utilization=0.30,
                    breaker_state="CLOSED",
                    estimated_prompt_tokens=2500,
                    tokens_saved_step=800,
                    consecutive_tool_errors=0,
                    snapshot_run_id="RUN-SNAP-01",
                ),
            ),
            config=config,
            snapshot_store=snap_store,
            cache=cache,
        )
        assert v1.verdict == InterventionVerdict.ADVISORY
        assert v1.action_executed == 1
        assert v1.next_interval == 3
        assert v1.rollback_triggered is False

        # Step 2: 3 consecutive tool errors -> immediate REPLACEMENT veto + interval reset to i_base + snapshot rollback
        v2 = cad_store.evaluate_and_record_step(
            proposal=TrajectoryStepProposal(
                proposal_id="P-02",
                run_id="RUN-CAD-01",
                session_id="SES-CAD-01",
                scaffold_type=ScaffoldType("claude_code"),
                step_index=3,
                last_inspection_step=2,
                current_interval=3,
                signals=CadenceTelemetrySignals(
                    budget_utilization=0.65,
                    breaker_state="CLOSED",
                    estimated_prompt_tokens=4000,
                    consecutive_tool_errors=3,
                    snapshot_run_id="RUN-SNAP-01",
                ),
            ),
            config=config,
            snapshot_store=snap_store,
            cache=cache,
        )
        assert v2.verdict == InterventionVerdict.REPLACEMENT
        assert v2.category == MisbehaviorCategory.CONSECUTIVE_TOOL_FAILURE
        assert v2.action_executed == 0
        assert v2.next_interval == config.i_base
        assert v2.rollback_triggered is True
        assert v2.state == CadenceState.ROLLED_BACK
        assert v2.rollback_target_epoch is not None and v2.rollback_target_epoch >= 1
        assert cache.get_rollback_epoch(snap_repo) >= 1

        assert cad_store.list_cadence_occ_versions("RUN-CAD-01") == [1, 2]

        # OCC mismatch conflict check
        with pytest.raises(ValueError, match="CADENCE_OCC_CONFLICT"):
            cad_store.evaluate_and_record_step(
                proposal=TrajectoryStepProposal(
                    proposal_id="P-03",
                    run_id="RUN-CAD-01",
                    session_id="SES-CAD-01",
                    scaffold_type=ScaffoldType("claude_code"),
                    step_index=4,
                    last_inspection_step=3,
                    current_interval=2,
                ),
                config=config,
                expected_occ_version=999,
            )

        # Ensure cadence_occ_ledger is SQL-immutable
        with sqlite3.connect(str(tmp_path / "cadence.db")) as conn:
            with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                conn.execute("UPDATE cadence_occ_ledger SET occ_version = 99")
            with pytest.raises(sqlite3.DatabaseError, match="immutable"):
                conn.execute("DELETE FROM cadence_occ_ledger")
    finally:
        cad_store.close()
        snap_store.close()
        cache.close()


def test_proxy_cadence_headers_bypass_sse_and_finops_preservation(tmp_path: Path):
    app.state.cache = LocalSemanticCache(str(tmp_path / "proxy_cadence_cache.db"))
    app.state.tokencast_signals = None
    app.state.trace_signals = None

    captured = []

    def handle_mock(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        captured.append(body)
        if body.get("stream"):
            sse = b'data: {"id":"1","choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
            return httpx.Response(status_code=200, content=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(
            status_code=200,
            json={"id": "msg-cad", "type": "message", "content": [{"type": "text", "text": "ok"}]},
            headers={"content-type": "application/json"},
        )

    app.state.upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handle_mock))
    client = TestClient(app)
    try:
        # 1. Normal OpenAI turn emits deterministic ADVISORY Cadence headers & AIMD expands interval
        r1 = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "ping"}],
            },
            headers={
                "X-Context-Firewall-Session": "SES-proxy-cad-01",
                "X-Context-Firewall-Run": "RUN-proxy-cad-01",
                "X-Context-Firewall-Scaffold": "cursor",
            },
        )
        assert r1.status_code == 200
        assert r1.headers["X-Cadence-Verdict"] == "ADVISORY"
        assert r1.headers["X-Cadence-Action-Executed"] == "1"
        assert int(r1.headers["X-Cadence-Interval"]) >= 2

        # 2. Anthropic SSE streaming with repeated tool errors emits REPLACEMENT Cadence header cleanly
        r_sse = client.post(
            "/v1/messages",
            json={
                "model": "claude-3-opus-20240229",
                "max_tokens": 16000,
                "thinking": {"type": "adaptive"},
                "stream": True,
                "messages": [
                    {"role": "tool", "content": "err1", "is_error": True},
                    {"role": "tool", "content": "err2", "is_error": True},
                    {"role": "tool", "content": "err3", "is_error": True},
                ],
            },
            headers={
                "X-Context-Firewall-Session": "SES-proxy-cad-01",
                "X-Context-Firewall-Run": "RUN-proxy-cad-01",
            },
        )
        assert r_sse.status_code == 200
        assert "text/event-stream" in r_sse.headers.get("content-type", "")
        assert r_sse.headers["X-Cadence-Verdict"] == "REPLACEMENT"
        assert r_sse.headers["X-Cadence-Action-Executed"] == "0"
        assert r_sse.headers["X-Cadence-Interval"] == "2"
        assert b"[DONE]" in r_sse.content
        # FinOps clamping still enforced strictly
        assert captured[-1]["model"] == "claude-3-5-sonnet-20241022"
        assert captured[-1]["max_tokens"] == 4096
        assert captured[-1]["thinking"] == {"type": "enabled", "budget_tokens": 1024}

        # 3. X-Context-Firewall-Bypass skips Cadence completely (and keeps >40k 413 guard)
        r_bypass = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "bypass"}]},
            headers={"X-Context-Firewall-Bypass": "true"},
        )
        assert r_bypass.status_code == 200
        assert r_bypass.headers["X-Firewall-Status"] == "bypassed"
        assert "X-Cadence-Verdict" not in r_bypass.headers

        r_413 = client.post(
            "/v1/messages",
            json={"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "word " * 45000}]},
            headers={"X-Context-Firewall-Bypass": "true"},
        )
        assert r_413.status_code == 413
    finally:
        if getattr(app.state, "cadence_store", None) is not None:
            app.state.cadence_store.close()
            app.state.cadence_store = None
        app.state.upstream_client = None
        app.state.cache.close()


def test_proxy_cadence_default_session_repeated_short_turns(tmp_path: Path):
    """Consecutive len(messages)==1 requests on default session must never collide on verdict_id."""
    app.state.cache = LocalSemanticCache(str(tmp_path / "proxy_default_cache.db"))
    app.state.tokencast_signals = None
    app.state.trace_signals = None

    def handle_mock(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"id": "msg-short", "type": "message", "content": [{"type": "text", "text": "ok"}]},
            headers={"content-type": "application/json"},
        )

    app.state.upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handle_mock))
    client = TestClient(app)
    try:
        for turn in range(5):
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": f"ping-{turn}"}],
                },
            )
            assert resp.status_code == 200
            assert "X-Cadence-Verdict" in resp.headers, f"Missing X-Cadence-Verdict on turn {turn}"
            assert "X-Cadence-Interval" in resp.headers, f"Missing X-Cadence-Interval on turn {turn}"
            assert resp.headers["X-Cadence-Verdict"] == "ADVISORY"
            assert int(resp.headers["X-Cadence-Interval"]) >= 2

        cad_store = getattr(app.state, "cadence_store", None)
        assert cad_store is not None
        assert cad_store.list_cadence_occ_versions("RUN-SES-proxy-default") == [1, 2, 3, 4, 5]
        with sqlite3.connect(str(tmp_path / "cadence.db")) as conn:
            verdict_count = conn.execute(
                "SELECT COUNT(DISTINCT verdict_id) FROM cadence_step_verdicts WHERE run_id = ?",
                ("RUN-SES-proxy-default",),
            ).fetchone()[0]
            assert verdict_count == 5
    finally:
        if getattr(app.state, "cadence_store", None) is not None:
            app.state.cadence_store.close()
            app.state.cadence_store = None
        app.state.upstream_client = None
        app.state.cache.close()


def test_cadence_store_resets_last_inspection_when_shorter_chat_reuses_run(tmp_path: Path):
    """When step_index < persisted_last, CadenceStore must reset last_inspection_step to -1."""
    cad_store = CadenceStore(tmp_path / "cadence_reset.db")
    try:
        config = SchedulerConfig(scaffold_type=ScaffoldType("cursor"), i_base=2, delta_step=1, i_max=8)
        v_long = cad_store.evaluate_and_record_step(
            proposal=TrajectoryStepProposal(
                proposal_id="PROP-LONG-6",
                run_id="RUN-REUSE-01",
                session_id="SES-REUSE-01",
                scaffold_type=ScaffoldType("cursor"),
                step_index=6,
                last_inspection_step=-1,
                current_interval=2,
            ),
            config=config,
        )
        assert v_long.inspection_triggered is True
        snap_after_long = cad_store.get_run_snapshot("RUN-REUSE-01")
        assert snap_after_long is not None
        assert snap_after_long.last_inspection_step == 6
        assert snap_after_long.current_interval == 3

        # Shorter chat starts at step_index=1 (< persisted_last=6); last_inspection_step must reset to -1
        v_short_1 = cad_store.evaluate_and_record_step(
            proposal=TrajectoryStepProposal(
                proposal_id="PROP-SHORT-1",
                run_id="RUN-REUSE-01",
                session_id="SES-REUSE-01",
                scaffold_type=ScaffoldType("cursor"),
                step_index=1,
                last_inspection_step=snap_after_long.last_inspection_step,
                current_interval=snap_after_long.current_interval,
            ),
            config=config,
        )
        assert v_short_1.inspection_triggered is False
        snap_after_short = cad_store.get_run_snapshot("RUN-REUSE-01")
        assert snap_after_short is not None
        assert snap_after_short.last_inspection_step == -1

        # By step_index=2, (2 - (-1)) == 3 >= interval 3 -> inspection triggers cleanly again
        v_short_2 = cad_store.evaluate_and_record_step(
            proposal=TrajectoryStepProposal(
                proposal_id="PROP-SHORT-2",
                run_id="RUN-REUSE-01",
                session_id="SES-REUSE-01",
                scaffold_type=ScaffoldType("cursor"),
                step_index=2,
                last_inspection_step=snap_after_short.last_inspection_step,
                current_interval=snap_after_short.current_interval,
            ),
            config=config,
        )
        assert v_short_2.inspection_triggered is True
        snap_final = cad_store.get_run_snapshot("RUN-REUSE-01")
        assert snap_final is not None
        assert snap_final.last_inspection_step == 2
    finally:
        cad_store.close()
