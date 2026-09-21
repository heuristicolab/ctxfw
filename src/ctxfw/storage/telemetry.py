"""
src/ctxfw/storage/telemetry.py — Sovereign Telemetry Ledger & FinOps Aggregator (v3.5.0)
Stores anonymous telemetry records in SQLite WAL mode with strict concurrency guarantees (PRAGMA busy_timeout = 5000),
supports offline resilience, async heartbeat push, and multi-tenant accounting analytics.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import sqlite3
from typing import List, Optional
import uuid

import httpx

from ctxfw.core.contracts import (
    ModelSavingsDTO,
    TeamSavingsDTO,
    TelemetryBatchPushDTO,
    TelemetryRecordDTO,
    TelemetryStatsDTO,
)
from ctxfw.storage.cache import get_canonical_cache_path


def get_telemetry_db_path() -> Path:
    """Returns the canonical path for the telemetry SQLite ledger."""
    override = os.environ.get("CTXFW_TELEMETRY_DB")
    if override:
        p = Path(override)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return get_canonical_cache_path()


def get_or_create_dev_uuid(custom_dir: Optional[Path] = None) -> str:
    """
    Returns a persistent anonymous developer UUID for this host.
    Ensures that real identities, usernames, paths, and secrets are NEVER exposed.
    """
    env_uuid = os.environ.get("CTXFW_DEV_UUID")
    if env_uuid and len(env_uuid.strip()) >= 8:
        return env_uuid.strip()

    target_dir = custom_dir or get_telemetry_db_path().parent
    target_dir.mkdir(parents=True, exist_ok=True)
    uuid_file = target_dir / "dev_uuid.txt"

    if uuid_file.is_file():
        try:
            val = uuid_file.read_text(encoding="utf-8").strip()
            if len(val) >= 8:
                return val
        except Exception:
            pass

    new_uuid = str(uuid.uuid4())
    try:
        uuid_file.write_text(new_uuid, encoding="utf-8")
    except Exception:
        pass
    return new_uuid


class TelemetryLedger:
    """
    Embedded SQLite WAL telemetry store with strict concurrency settings.
    Guarantees that CLI and proxy concurrent writes do not lock each other.
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            self.db_path = str(get_telemetry_db_path())
        else:
            self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes an SQLite connection with WAL mode and strict 5000ms busy timeout."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Strict concurrency guardrails
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dev_uuid TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    model_target TEXT NOT NULL,
                    tokens_orig INTEGER NOT NULL,
                    tokens_pruned INTEGER NOT NULL,
                    usd_avoided REAL NOT NULL,
                    team TEXT NOT NULL DEFAULT 'Engineering',
                    synced INTEGER NOT NULL DEFAULT 0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_synced ON telemetry_ledger(synced);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_ledger(timestamp_utc);")

    def record_event(self, record: TelemetryRecordDTO, synced: int = 0) -> int:
        """
        Records an anonymous telemetry event into the local ledger.
        Defaults to synced=0 for client-side offline buffering.
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO telemetry_ledger 
                (dev_uuid, timestamp_utc, model_target, tokens_orig, tokens_pruned, usd_avoided, team, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.dev_uuid,
                record.timestamp_utc,
                record.model_target,
                record.tokens_orig,
                record.tokens_pruned,
                record.usd_avoided,
                record.team,
                synced,
            ))
            return cur.lastrowid

    def ingest_batch(self, records: List[TelemetryRecordDTO]) -> int:
        """Ingests a batch of records at the central server, marking them as synced=1."""
        if not records:
            return 0
        with self._get_connection() as conn:
            cur = conn.cursor()
            rows = [
                (r.dev_uuid, r.timestamp_utc, r.model_target, r.tokens_orig, r.tokens_pruned, r.usd_avoided, r.team, 1)
                for r in records
            ]
            cur.executemany("""
                INSERT INTO telemetry_ledger 
                (dev_uuid, timestamp_utc, model_target, tokens_orig, tokens_pruned, usd_avoided, team, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, rows)
            return len(records)

    def get_unsynced_records(self, limit: int = 100) -> List[tuple[int, TelemetryRecordDTO]]:
        """Retrieves unsynced records awaiting heartbeat push."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, dev_uuid, timestamp_utc, model_target, tokens_orig, tokens_pruned, usd_avoided, team
                FROM telemetry_ledger
                WHERE synced = 0
                ORDER BY id ASC
                LIMIT ?;
            """, (limit,))
            results = []
            for row in cur.fetchall():
                dto = TelemetryRecordDTO(
                    dev_uuid=row["dev_uuid"],
                    timestamp_utc=row["timestamp_utc"],
                    model_target=row["model_target"],
                    tokens_orig=row["tokens_orig"],
                    tokens_pruned=row["tokens_pruned"],
                    usd_avoided=float(row["usd_avoided"]),
                    team=row["team"],
                )
                results.append((row["id"], dto))
            return results

    def mark_as_synced(self, record_ids: List[int]) -> None:
        """Marks successfully pushed records as synced=1."""
        if not record_ids:
            return
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in record_ids)
            conn.execute(f"UPDATE telemetry_ledger SET synced = 1 WHERE id IN ({placeholders});", record_ids)

    def get_stats(self) -> TelemetryStatsDTO:
        """Computes aggregate multi-tenant statistics for the FinOps control plane."""
        with self._get_connection() as conn:
            cur = conn.cursor()

            # Global aggregates
            cur.execute("""
                SELECT 
                    COUNT(*),
                    COALESCE(SUM(tokens_orig), 0),
                    COALESCE(SUM(tokens_pruned), 0),
                    COALESCE(SUM(usd_avoided), 0.0),
                    COUNT(DISTINCT dev_uuid)
                FROM telemetry_ledger;
            """)
            total_cycles, orig, pruned, usd, devs = cur.fetchone()

            reduction_pct = round((pruned / orig * 100.0), 2) if orig > 0 else 0.0

            # Team breakdown
            cur.execute("""
                SELECT team, SUM(tokens_pruned), SUM(usd_avoided), COUNT(*)
                FROM telemetry_ledger
                GROUP BY team
                ORDER BY SUM(usd_avoided) DESC;
            """)
            teams = [
                TeamSavingsDTO(team=r[0], tokens_pruned=r[1], usd_avoided=round(r[2], 6), request_count=r[3])
                for r in cur.fetchall()
            ]

            # Model breakdown
            cur.execute("""
                SELECT model_target, SUM(tokens_pruned), SUM(usd_avoided), COUNT(*)
                FROM telemetry_ledger
                GROUP BY model_target
                ORDER BY SUM(usd_avoided) DESC;
            """)
            models = [
                ModelSavingsDTO(model_target=r[0], tokens_pruned=r[1], usd_avoided=round(r[2], 6), request_count=r[3])
                for r in cur.fetchall()
            ]

            # Timeseries (grouped by day)
            cur.execute("""
                SELECT 
                    substr(timestamp_utc, 1, 10) as day,
                    SUM(tokens_orig) as total_orig,
                    SUM(tokens_pruned) as total_pruned,
                    SUM(usd_avoided) as total_usd,
                    COUNT(*) as count
                FROM telemetry_ledger
                GROUP BY substr(timestamp_utc, 1, 10)
                ORDER BY day ASC;
            """)
            timeseries = [
                {
                    "date": r[0],
                    "tokens_orig": r[1],
                    "tokens_pruned": r[2],
                    "usd_avoided": round(r[3], 6),
                    "count": r[4],
                }
                for r in cur.fetchall()
            ]

            return TelemetryStatsDTO(
                total_tokens_orig=orig,
                total_tokens_pruned=pruned,
                total_usd_avoided=round(usd, 6),
                global_reduction_pct=reduction_pct,
                active_dev_count=devs,
                total_cycles=total_cycles,
                teams=teams,
                models=models,
                timeseries=timeseries,
            )

    def export_data(self, format_type: str = "csv") -> str:
        """Exports all telemetry records in CSV or JSON format for corporate accounting."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT dev_uuid, timestamp_utc, model_target, tokens_orig, tokens_pruned, usd_avoided, team
                FROM telemetry_ledger
                ORDER BY id ASC;
            """)
            rows = cur.fetchall()

        if format_type.lower() == "json":
            records = [dict(r) for r in rows]
            return json.dumps(records, indent=2)

        # CSV by default
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["dev_uuid", "timestamp_utc", "model_target", "tokens_orig", "tokens_pruned", "usd_avoided", "team"])
        for r in rows:
            writer.writerow([r["dev_uuid"], r["timestamp_utc"], r["model_target"], r["tokens_orig"], r["tokens_pruned"], f"{r['usd_avoided']:.6f}", r["team"]])
        return output.getvalue()


async def push_telemetry_heartbeat(
    endpoint_url: str,
    ledger: Optional[TelemetryLedger] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> int:
    """
    Heartbeat asíncrono hacia el endpoint central /api/telemetry/push.
    Garantiza Resiliencia Offline: si el endpoint central está inalcanzable,
    las métricas se retienen en SQLite WAL y se sincronizarán en el próximo pulso.
    """
    active_ledger = ledger or TelemetryLedger()
    unsynced = active_ledger.get_unsynced_records(limit=100)
    if not unsynced:
        return 0

    record_ids = [item[0] for item in unsynced]
    records = [item[1] for item in unsynced]

    payload = TelemetryBatchPushDTO(records=records).model_dump(mode="json")

    should_close = False
    active_client = client
    if active_client is None:
        active_client = httpx.AsyncClient(timeout=4.0)
        should_close = True

    try:
        resp = await active_client.post(endpoint_url, json=payload)
        if resp.status_code == 200:
            active_ledger.mark_as_synced(record_ids)
            return len(record_ids)
        return 0
    except Exception:
        # Resiliencia offline: Retiene los registros en SQLite para el siguiente pulso
        return 0
    finally:
        if should_close:
            await active_client.aclose()


def push_telemetry_heartbeat_sync(
    endpoint_url: str,
    ledger: Optional[TelemetryLedger] = None,
) -> int:
    """Synchronous version for CLI execution."""
    active_ledger = ledger or TelemetryLedger()
    unsynced = active_ledger.get_unsynced_records(limit=100)
    if not unsynced:
        return 0

    record_ids = [item[0] for item in unsynced]
    records = [item[1] for item in unsynced]
    payload = TelemetryBatchPushDTO(records=records).model_dump(mode="json")

    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.post(endpoint_url, json=payload)
            if resp.status_code == 200:
                active_ledger.mark_as_synced(record_ids)
                return len(record_ids)
            return 0
    except Exception:
        return 0
