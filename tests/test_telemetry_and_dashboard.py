"""
tests/test_telemetry_and_dashboard.py — Test Suite for Sovereign FinOps & Telemetry Ledger (HU-02)
Validates perimeter inviolability (rejection of source code/secrets), offline resilience,
SQLite WAL concurrency with PRAGMA busy_timeout = 5000, multi-tenant stats,
CSV/JSON export endpoints, and interactive dashboard rendering.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
import httpx

from contracts import (
    TelemetryBatchPushDTO,
    TelemetryRecordDTO,
    TelemetryStatsDTO,
)
from proxy_gateway import app
from ctxfw.storage.telemetry import (
    TelemetryLedger,
    get_or_create_dev_uuid,
    push_telemetry_heartbeat,
    push_telemetry_heartbeat_sync,
)


@pytest.fixture
def telemetry_db(tmp_path: Path) -> Path:
    """Provides a clean temporary SQLite database for telemetry testing."""
    return tmp_path / "test_telemetry_ledger.db"


@pytest.fixture
def test_client(telemetry_db: Path) -> TestClient:
    """Sets up FastAPI TestClient with an isolated telemetry ledger."""
    app.state.telemetry_ledger = TelemetryLedger(str(telemetry_db))
    client = TestClient(app)
    yield client
    app.state.telemetry_ledger = None


def test_inviolability_perimetral_rejects_source_code_and_secrets():
    """
    HU-02: Asserts that TelemetryRecordDTO strictly rejects source code, file paths,
    passwords, and authorization secrets via extra='forbid'.
    """
    valid_dto = TelemetryRecordDTO(
        dev_uuid="anon-node-12345678",
        timestamp_utc="2026-09-07T00:00:00Z",
        model_target="gpt-4o",
        tokens_orig=5000,
        tokens_pruned=2500,
        usd_avoided=0.0075,
        team="Platform",
    )
    assert valid_dto.dev_uuid == "anon-node-12345678"
    assert valid_dto.tokens_pruned == 2500

    # Attempt to leak source code
    with pytest.raises(ValidationError) as exc:
        TelemetryRecordDTO(
            dev_uuid="anon-node-12345678",
            timestamp_utc="2026-09-07T00:00:00Z",
            model_target="gpt-4o",
            tokens_orig=5000,
            tokens_pruned=2500,
            usd_avoided=0.0075,
            team="Platform",
            source_code="def confidential(): pass",  # FORBIDDEN
        )
    assert "source_code" in str(exc.value)

    # Attempt to leak file path
    with pytest.raises(ValidationError):
        TelemetryRecordDTO(
            dev_uuid="anon-node-12345678",
            timestamp_utc="2026-09-07T00:00:00Z",
            model_target="gpt-4o",
            tokens_orig=5000,
            tokens_pruned=2500,
            usd_avoided=0.0075,
            local_path="/Users/admin/projects/secret.py",  # FORBIDDEN
        )


def test_offline_resilience_and_heartbeat_sync(telemetry_db: Path):
    """
    HU-02: Asserts that if the central dashboard is unreachable:
    1. Metrics are retained locally in SQLite WAL with synced = 0.
    2. Synchronized on the next successful heartbeat pulse and marked synced = 1.
    """
    ledger = TelemetryLedger(telemetry_db)
    record = TelemetryRecordDTO(
        dev_uuid="offline-dev-9999",
        timestamp_utc="2026-09-07T12:00:00Z",
        model_target="claude-3-5-sonnet",
        tokens_orig=10000,
        tokens_pruned=4000,
        usd_avoided=0.012,
        team="Core",
    )
    row_id = ledger.record_event(record, synced=0)
    assert row_id > 0

    # Verify record is currently unsynced
    unsynced = ledger.get_unsynced_records()
    assert len(unsynced) == 1
    assert unsynced[0][1].dev_uuid == "offline-dev-9999"

    # Step 1: Simulate central server being OFFLINE (connection error)
    def handle_fail(request: httpx.Request):
        raise httpx.ConnectError("Connection refused by central control plane")

    fail_client = httpx.AsyncClient(transport=httpx.MockTransport(handle_fail))
    # Must fail gracefully without raising exception
    import asyncio
    synced_count = asyncio.run(push_telemetry_heartbeat(
        "http://offline.central.corp/api/telemetry/push",
        ledger=ledger,
        client=fail_client,
    ))
    assert synced_count == 0

    # Metrics remain safely preserved in local SQLite WAL
    unsynced_after_fail = ledger.get_unsynced_records()
    assert len(unsynced_after_fail) == 1

    # Step 2: Simulate central server coming back ONLINE
    captured_payloads = []

    def handle_success(request: httpx.Request):
        captured_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"status": "ok", "ingested": 1})

    success_client = httpx.AsyncClient(transport=httpx.MockTransport(handle_success))
    synced_count = asyncio.run(push_telemetry_heartbeat(
        "http://online.central.corp/api/telemetry/push",
        ledger=ledger,
        client=success_client,
    ))
    assert synced_count == 1
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["records"][0]["dev_uuid"] == "offline-dev-9999"

    # Now there should be 0 unsynced records
    assert len(ledger.get_unsynced_records()) == 0


def test_concurrency_busy_timeout_and_wal(telemetry_db: Path):
    """Tactical Guardrail 3: Asserts strict PRAGMA busy_timeout = 5000 and WAL mode."""
    ledger = TelemetryLedger(telemetry_db)
    with ledger._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode;")
        journal = cur.fetchone()[0].lower()
        assert journal == "wal"

        cur.execute("PRAGMA busy_timeout;")
        timeout = cur.fetchone()[0]
        assert timeout == 5000


def test_central_control_plane_push_and_stats(test_client: TestClient):
    """HU-02: Asserts POST /api/telemetry/push ingests records and GET /api/telemetry/stats aggregates metrics."""
    batch_data = {
        "records": [
            {
                "dev_uuid": "dev-alpha-001",
                "timestamp_utc": "2026-09-07T01:00:00Z",
                "model_target": "gpt-4o",
                "tokens_orig": 10000,
                "tokens_pruned": 6000,
                "usd_avoided": 0.018,
                "team": "Backend",
            },
            {
                "dev_uuid": "dev-beta-002",
                "timestamp_utc": "2026-09-07T02:00:00Z",
                "model_target": "claude-3-5-sonnet-20241022",
                "tokens_orig": 8000,
                "tokens_pruned": 4000,
                "usd_avoided": 0.012,
                "team": "Frontend",
            },
        ]
    }

    # Ingest
    push_resp = test_client.post("/api/telemetry/push", json=batch_data)
    assert push_resp.status_code == 200
    assert push_resp.json() == {"status": "ok", "ingested": 2}

    # Stats
    stats_resp = test_client.get("/api/telemetry/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()

    assert stats["total_tokens_orig"] == 18000
    assert stats["total_tokens_pruned"] == 10000
    assert stats["total_usd_avoided"] == 0.03
    assert stats["active_dev_count"] == 2
    assert stats["total_cycles"] == 2
    assert stats["global_reduction_pct"] == 55.56

    # Team breakdown
    team_names = [t["team"] for t in stats["teams"]]
    assert "Backend" in team_names
    assert "Frontend" in team_names

    # Model breakdown
    models = [m["model_target"] for m in stats["models"]]
    assert "gpt-4o" in models


def test_telemetry_export_csv_and_json(test_client: TestClient):
    """HU-02: Asserts GET /api/telemetry/export returns corporate CSV and JSON accounting files."""
    test_client.post("/api/telemetry/push", json={
        "records": [
            {
                "dev_uuid": "dev-export-node",
                "timestamp_utc": "2026-09-07T05:00:00Z",
                "model_target": "gpt-4o",
                "tokens_orig": 12000,
                "tokens_pruned": 8000,
                "usd_avoided": 0.024,
                "team": "FinOps",
            }
        ]
    })

    # CSV export
    csv_resp = test_client.get("/api/telemetry/export?format=csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "attachment; filename=" in csv_resp.headers["content-disposition"]
    csv_text = csv_resp.text
    assert "dev_uuid,timestamp_utc,model_target,tokens_orig,tokens_pruned,usd_avoided,team" in csv_text
    assert "dev-export-node" in csv_text
    assert "FinOps" in csv_text

    # JSON export
    json_resp = test_client.get("/api/telemetry/export?format=json")
    assert json_resp.status_code == 200
    assert "application/json" in json_resp.headers["content-type"]
    json_data = json_resp.json()
    assert isinstance(json_data, list)
    assert len(json_data) == 1
    assert json_data[0]["dev_uuid"] == "dev-export-node"


def test_dashboard_endpoint_html_render(test_client: TestClient):
    """HU-02: Asserts GET /dashboard renders the interactive dark mode web dashboard."""
    resp = test_client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    content = resp.text
    assert "Centro de Mando FinOps" in content
    assert "Exportar CSV" in content
    assert "Exportar JSON" in content
    assert "JetBrains Mono" in content
    assert "/api/telemetry/stats" in content
