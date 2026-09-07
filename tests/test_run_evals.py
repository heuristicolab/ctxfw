"""
tests/test_run_evals.py — Verification Matrix for Empirical A/B Eval Harness
Validates subprocess isolation, timeout enforcement, pass@1 delta invariance (>= -2%),
and token reduction thresholds (>= 35%).
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.run_evals import EvalHarness, EvalReportDTO, EvalTask, get_default_tasks


def test_sandbox_execution_detects_pass_and_fail():
    """Asserts that execute_in_sandbox correctly reports pass and failure states."""
    code_files = {"math_helper.py": "def add(a, b): return a + b\n"}

    # Passing test case
    passing_test = "from math_helper import add\nassert add(2, 3) == 5\n"
    passed, err = EvalHarness.execute_in_sandbox(code_files, passing_test, timeout_seconds=3.0)
    assert passed is True
    assert err is None

    # Failing test case
    failing_test = "from math_helper import add\nassert add(2, 3) == 999\n"
    failed, err = EvalHarness.execute_in_sandbox(code_files, failing_test, timeout_seconds=3.0)
    assert failed is False
    assert err is not None
    assert "AssertionError" in err


def test_sandbox_enforces_timeout():
    """Asserts that long-running or infinite loops are terminated at the timeout threshold without hanging."""
    code_files = {"loop.py": "import time\nwhile True: time.sleep(0.1)\n"}
    test_code = "import loop\n"

    passed, err = EvalHarness.execute_in_sandbox(code_files, test_code, timeout_seconds=1.0)
    assert passed is False
    assert err is not None
    assert "Timeout expired" in err


def test_eval_harness_mock_mode_invariance_and_reduction(tmp_path: Path):
    """Integration test asserting delta pass rate >= -2.0% and token reduction >= 35.0%."""
    tasks = get_default_tasks()[:3]
    harness = EvalHarness(tasks=tasks, mock_mode=True)
    report = harness.run_benchmark()

    assert isinstance(report, EvalReportDTO)
    assert report.total_tasks == 3
    assert report.group_a_pass_rate == 100.0
    assert report.group_b_pass_rate == 100.0
    # Invariant: Delta pass@1 >= -2%
    assert report.delta_pass_rate >= -2.0
    # Invariant: Token reduction >= 35%
    assert report.avg_token_reduction_pct >= 35.0
    assert report.estimated_usd_savings > 0.0
    assert report.air_gapped_certified is True
