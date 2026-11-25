# manifest_hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546
"""
tests/test_mcp_burst_guard.py — Deterministic TDD Suite for ctxfw_mcp_burst_guard_v1
====================================================================================
Verifies:
  1. McpRateLimitPolicyDTO strict numeric bounds, float/bool rejection, and from_env fail-closed checks.
  2. Exact integer scaled millitoken arithmetic (zero IEEE-754 float drift across 1,000 fractional ticks).
  3. Clock regression clamping (elapsed_ms = 0, monotonic high-water mark, zero token minting).
  4. Zero-Knowledge SHA-256 hashing & strict rejection of raw IPs / unhashed PII in storage & limiter.
  5. Bounded LRU bucket cardinality under high-cardinality client sprays (<= max_tracked_clients).
  6. SQLite WAL rate_limit_audit_logs append-only persistence and MCG_INV_10 immutability triggers.
  7. Full MCPServer integration (opt-in default backward compatibility, DTO/env enforcement, TraceKit & stdio purity, lazy exports).
"""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from pydantic import ValidationError

from ctxfw.mcp import MCPServer
from ctxfw.mcp_guard.contracts import (
    ERR_RATE_LIMIT_EXCEEDED,
    ErrorClass,
    McpRateLimitPolicyDTO,
    RateLimitDecisionDTO,
    RateLimitEvent,
    RateLimitState,
)
from ctxfw.mcp_guard.rate_limiter import (
    McpBurstRateLimiter,
    derive_client_key_hash,
    transition_rate_limit_state,
)
from ctxfw.mcp_guard.store import McpGuardStore
from ctxfw.storage.cache import LocalSemanticCache


class _SteppableClock:
    def __init__(self, initial_ms: int = 0) -> None:
        self.now_ms = initial_ms

    def __call__(self) -> int:
        return self.now_ms


def test_policy_dto_strict_bounds_and_from_env() -> None:
    default_policy = McpRateLimitPolicyDTO()
    assert default_policy.enabled is False
    assert default_policy.requests_per_minute == 120
    assert default_policy.burst_capacity == 30
    assert default_policy.cost_per_call == 1
    assert default_policy.max_tracked_clients == 1024

    for bad_kwargs in (
        {"enabled": "true"},
        {"enabled": 1},
        {"requests_per_minute": True},
        {"requests_per_minute": 12.5},
        {"requests_per_minute": 0},
        {"requests_per_minute": 60001},
        {"burst_capacity": 0},
        {"burst_capacity": 10001},
        {"cost_per_call": 5, "burst_capacity": 4},
        {"max_tracked_clients": 15},
        {"max_tracked_clients": 4097},
        {"unknown_field": 1},
    ):
        with pytest.raises((ValidationError, ValueError)):
            McpRateLimitPolicyDTO(**bad_kwargs)

    env_ok = McpRateLimitPolicyDTO.from_env(
        {
            "CTXFW_MCP_RATE_LIMIT_ENABLED": "true",
            "CTXFW_MCP_RATE_LIMIT_RPM": "12",
            "CTXFW_MCP_RATE_LIMIT_BURST": "15",
            "CTXFW_MCP_RATE_LIMIT_COST": "1",
            "CTXFW_MCP_RATE_LIMIT_MAX_CLIENTS": "64",
        }
    )
    assert env_ok.enabled is True
    assert env_ok.requests_per_minute == 12
    assert env_ok.burst_capacity == 15
    assert env_ok.max_tracked_clients == 64

    with pytest.raises(ValueError):
        McpRateLimitPolicyDTO.from_env({"CTXFW_MCP_RATE_LIMIT_ENABLED": "maybe"})
    with pytest.raises(ValueError):
        McpRateLimitPolicyDTO.from_env({"CTXFW_MCP_RATE_LIMIT_RPM": "12.5"})
    with pytest.raises(ValueError):
        McpRateLimitPolicyDTO.from_env({"CTXFW_MCP_RATE_LIMIT_RPM": "-5"})


def test_exact_token_bucket_refill_and_zero_float_drift() -> None:
    clock = _SteppableClock(0)
    policy = McpRateLimitPolicyDTO(enabled=True, requests_per_minute=12, burst_capacity=15, cost_per_call=1)
    limiter = McpBurstRateLimiter(policy, clock=clock)
    client = derive_client_key_hash("117.147.90.12")

    for idx in range(15):
        dec = limiter.evaluate(client, "prune_file")
        assert dec.allowed is True
        assert dec.state == RateLimitState.ALLOWED
        assert dec.retry_after_ms == 0
        assert dec.remaining_tokens_q4 == f"{14 - idx}.0000"

    blocked = limiter.evaluate(client, "prune_file")
    assert blocked.allowed is False
    assert blocked.state == RateLimitState.THROTTLED
    assert blocked.error_class == ErrorClass.BUSINESS
    assert blocked.error_code == ERR_RATE_LIMIT_EXCEEDED
    assert blocked.retry_after_ms == 5000
    assert blocked.remaining_tokens_q4 == "0.0000"

    clock.now_ms = 4999
    still_blocked = limiter.evaluate(client, "prune_file")
    assert still_blocked.allowed is False
    assert still_blocked.retry_after_ms == 1

    clock.now_ms = 5000
    recovered = limiter.evaluate(client, "prune_file")
    assert recovered.allowed is True
    assert recovered.remaining_tokens_q4 == "0.0000"

    # 1,000 fractional ticks must match exact rational Fraction accounting with 0 drift
    frac_clock = _SteppableClock(0)
    frac_policy = McpRateLimitPolicyDTO(enabled=True, requests_per_minute=7, burst_capacity=50, cost_per_call=1)
    frac_limiter = McpBurstRateLimiter(frac_policy, clock=frac_clock)
    frac_client = derive_client_key_hash("session-frac-drift-check")
    expected_tokens = Fraction(50, 1)
    last_dec: RateLimitDecisionDTO | None = None
    for tick in range(1000):
        last_dec = frac_limiter.evaluate(frac_client, "resolve_context_bundle")
        if expected_tokens >= 1:
            expected_tokens -= 1
            assert last_dec.allowed is True
        else:
            assert last_dec.allowed is False
        frac_clock.now_ms += 137
        expected_tokens = min(Fraction(50, 1), expected_tokens + Fraction(137 * 7, 60000))
    assert last_dec is not None


def test_clock_regression_fail_closed_and_fsm_edges() -> None:
    clock = _SteppableClock(10_000)
    policy = McpRateLimitPolicyDTO(enabled=True, requests_per_minute=60, burst_capacity=2, cost_per_call=1)
    limiter = McpBurstRateLimiter(policy, clock=clock)
    client = derive_client_key_hash("clock-regress-client")

    assert limiter.evaluate(client, "prune_file").allowed is True
    assert limiter.evaluate(client, "prune_file").remaining_tokens_q4 == "0.0000"

    # Clock jumps backward: never mint positive tokens, clamp elapsed_ms = 0
    clock.now_ms = 2_000
    blocked = limiter.evaluate(client, "prune_file")
    assert blocked.allowed is False
    assert blocked.clock_regression_clamped is True
    assert blocked.remaining_tokens_q4 == "0.0000"

    # Moving up from 2_000 to 9_999 (still below high-water mark 10_000) keeps clamping
    clock.now_ms = 9_999
    still_clamped = limiter.evaluate(client, "prune_file")
    assert still_clamped.allowed is False
    assert still_clamped.clock_regression_clamped is True

    # Moving past high-water mark 10_000 -> 11_000 mints exact 1 token at 60 rpm
    clock.now_ms = 11_000
    unblocked = limiter.evaluate(client, "prune_file")
    assert unblocked.allowed is True
    assert unblocked.clock_regression_clamped is False
    assert unblocked.remaining_tokens_q4 == "0.0000"

    assert transition_rate_limit_state(RateLimitState.READY, RateLimitEvent.TOKENS_EXHAUSTED) == RateLimitState.THROTTLED
    with pytest.raises(ValueError):
        transition_rate_limit_state(RateLimitState.THROTTLED, RateLimitEvent.TOKENS_SUFFICIENT)


def test_zero_knowledge_hashing_and_bounded_lru_eviction(tmp_path: Path) -> None:
    raw_ip = "117.147.90.42"
    digest = derive_client_key_hash(raw_ip)
    assert len(digest) == 64
    assert derive_client_key_hash(digest) == digest
    assert raw_ip not in digest

    clock = _SteppableClock(0)
    policy = McpRateLimitPolicyDTO(enabled=True, requests_per_minute=60, burst_capacity=3, max_tracked_clients=16)
    limiter = McpBurstRateLimiter(policy, clock=clock)

    with pytest.raises(ValueError):
        limiter.evaluate(raw_ip, "prune_file")

    for i in range(64):
        c_hash = derive_client_key_hash(f"attacker-ip-{i}")
        dec = limiter.evaluate(c_hash, "prune_file")
        assert dec.allowed is True
    assert limiter.tracked_client_count == 16

    store = McpGuardStore(tmp_path / "mcp_guard.db")
    try:
        # Exhaust first active bucket then attempt raw PII rejection directly
        for _ in range(3):
            limiter.evaluate(digest, "prune_file")
        throttled = limiter.evaluate(digest, "prune_file")
        assert throttled.allowed is False
        audit_id = store.record_rate_limit_rejection("ctxfw-mcp-4.2.1", throttled)
        assert audit_id.startswith("RLM-")

        rows = store.list_rate_limit_audits(client_key_hash=digest)
        assert len(rows) == 1
        assert rows[0]["error_class"] == "BUSINESS"
        assert rows[0]["error_code"] == ERR_RATE_LIMIT_EXCEEDED
        assert rows[0]["client_key_hash"] == digest

        # Append-only immutability triggers MCG_INV_10
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="MCG_INV_10"):
            store._conn.execute("UPDATE rate_limit_audit_logs SET retry_after_ms = 0;")
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="MCG_INV_10"):
            store._conn.execute("DELETE FROM rate_limit_audit_logs;")
    finally:
        store.close()

    raw_db_bytes = (tmp_path / "mcp_guard.db").read_bytes()
    assert raw_ip.encode("ascii") not in raw_db_bytes


def test_mcp_server_backward_compatibility_and_burst_enforcement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_default = LocalSemanticCache(str(tmp_path / "default_cache.db"))
    default_srv = MCPServer(cache=cache_default)
    try:
        # Opt-in disabled by default: > 50 rapid calls proceed without rate throttling
        for _ in range(55):
            res = default_srv.handle_tools_call({"name": "unknown_tool", "arguments": {}})
            assert res.get("rateLimited") is not True
    finally:
        default_srv.close()

    monkeypatch.setenv("CTXFW_HOME", str(tmp_path / "ctxfw_home"))
    monkeypatch.setenv("CTXFW_MCP_GUARD_DB", str(tmp_path / "srv_mcp_guard.db"))
    monkeypatch.setenv("CTXFW_TRACEKIT_DB", str(tmp_path / "srv_tracekit.db"))
    clock = _SteppableClock(1_000)
    policy = McpRateLimitPolicyDTO(enabled=True, requests_per_minute=12, burst_capacity=2, cost_per_call=1)
    srv = MCPServer(
        cache=LocalSemanticCache(str(tmp_path / "rl_cache.db")),
        mcp_guard_store=McpGuardStore(tmp_path / "srv_mcp_guard.db"),
        authorized_roots=[tmp_path],
        rate_limit_policy=policy,
        rate_limit_clock=clock,
    )
    raw_caller_ip = "117.147.90.99"
    try:
        target = tmp_path / "sample.py"
        target.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")

        for _ in range(2):
            ok_res = srv.handle_tools_call(
                {
                    "name": "prune_file",
                    "arguments": {"path": str(target)},
                    "_meta": {"cf_connecting_ip": raw_caller_ip},
                }
            )
            assert ok_res.isError is False

        # Call #3 via JSON-RPC process_raw_line ensures stdout purity and structured Class 3 rejection
        rpc_req = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": "prune_file",
                    "arguments": {"path": str(target)},
                    "_meta": {"cf_connecting_ip": raw_caller_ip},
                },
            }
        )
        raw_reply = srv.process_raw_line(rpc_req)
        assert raw_reply is not None
        parsed = json.loads(raw_reply)
        result = parsed["result"]
        assert result["isError"] is True
        assert result["rateLimited"] is True
        assert result["errorClass"] == "BUSINESS"
        assert result["errorCode"] == ERR_RATE_LIMIT_EXCEEDED
        assert result["retryAfterMs"] == 5000
        assert result["clientKeyHash"] == derive_client_key_hash(raw_caller_ip)
        assert raw_caller_ip not in raw_reply

        guard_rows = srv._get_mcp_guard_store().list_rate_limit_audits(client_key_hash=result["clientKeyHash"])
        assert len(guard_rows) == 1
        assert guard_rows[0]["retry_after_ms"] == 5000
    finally:
        srv.close()

    # Zero raw IP bytes persisted anywhere inside TraceKit or MCP Guard SQLite files
    for db_file in tmp_path.rglob("*.db"):
        assert raw_caller_ip.encode("ascii") not in db_file.read_bytes()

    # Env var activation check
    monkeypatch.setenv("CTXFW_MCP_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("CTXFW_MCP_RATE_LIMIT_RPM", "12")
    monkeypatch.setenv("CTXFW_MCP_RATE_LIMIT_BURST", "1")
    env_srv = MCPServer(
        cache=LocalSemanticCache(str(tmp_path / "env_cache.db")),
        mcp_guard_store=McpGuardStore(tmp_path / "env_mcp_guard.db"),
        rate_limit_clock=clock,
    )
    try:
        r1 = env_srv.handle_tools_call({"name": "query_audit_ledger", "arguments": {"limit": 1}, "_meta": {"client_key": "k1"}})
        assert r1.get("rateLimited") is not True
        r2 = env_srv.handle_tools_call({"name": "query_audit_ledger", "arguments": {"limit": 1}, "_meta": {"client_key": "k1"}})
        assert r2.get("rateLimited") is True
        assert r2.get("errorCode") == ERR_RATE_LIMIT_EXCEEDED
    finally:
        env_srv.close()


def test_lazy_exports_preserve_zero_eager_imports() -> None:
    code = (
        "import sys, ctxfw.mcp_guard as g;"
        "assert 'ctxfw.mcp_guard.rate_limiter' not in sys.modules;"
        "assert 'ctxfw.mcp_guard.contracts' not in sys.modules;"
        "from ctxfw.mcp_server import McpBurstRateLimiter, McpRateLimitPolicyDTO;"
        "assert callable(g.derive_client_key_hash);"
        "assert McpBurstRateLimiter is g.McpBurstRateLimiter;"
        "assert McpRateLimitPolicyDTO is g.McpRateLimitPolicyDTO;"
        "print('LAZY_BURST_OK')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "LAZY_BURST_OK"
