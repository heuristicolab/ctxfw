"""
tests/conftest.py — Deterministic Telemetry Capture Hook
Emits tests/test_report.json following test execution for cryptographic audit.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    errors = len(terminalreporter.stats.get("error", []))
    total_failed = failed + errors

    session_start = getattr(terminalreporter, "_sessionstarttime", time.time())
    duration = round(time.time() - session_start, 4)
    suite_status = "PASSED" if (exitstatus == 0 and total_failed == 0) else "FAILED"

    report_data = {
        "project_id": "heuristico-core-optimizer",
        "order_id": "ord-2026-4f003b",
        "suite_status": suite_status,
        "passed_count": passed,
        "failed_count": total_failed,
        "duration_seconds": duration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    report_path = Path(config.rootdir) / "tests" / "test_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
