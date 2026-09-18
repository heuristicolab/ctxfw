"""
tests/test_benchmark_cli.py — Test Suite for ctxfw benchmark subcommand
Axiom Manifest Hash: a403b7072c7ea6b37a804db8feec61058e552d2bb3240390098f9c747867d924
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import pytest

from ctxfw.cli.main import build_parser, main
from ctxfw.cli.commands.benchmark import run_benchmark


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    proj = tmp_path / "bench_sample"
    proj.mkdir()

    (proj / "main.py").write_text(
        "import utils\ndef run():\n    return utils.compute()\n",
        encoding="utf-8",
    )
    (proj / "utils.py").write_text(
        "def compute() -> int:\n    res = 100 * 2\n    return res\n",
        encoding="utf-8",
    )
    return proj


def test_benchmark_parser_registration():
    parser = build_parser()
    args = parser.parse_args(["benchmark", "main.py", "--root", ".", "--format", "json"])
    assert args.command == "benchmark"
    assert args.path == "main.py"
    assert args.format == "json"
    assert hasattr(args, "func")


def test_benchmark_run_table_output(sample_project: Path, monkeypatch):
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    parser = build_parser()
    args = parser.parse_args(["benchmark", "main.py", "--root", str(sample_project), "--format", "table"])
    ret = run_benchmark(args)

    assert ret == 0
    output = mock_stdout.getvalue()
    assert "CTXFW EMPIRICAL BENCHMARK" in output
    assert "main.py" in output
    assert "Projected FinOps Savings" in output
    assert "Audit generated via ctxfw" in output
    assert "contacto@heuristicolab.com" in output


def test_benchmark_run_json_output(sample_project: Path, monkeypatch):
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    parser = build_parser()
    args = parser.parse_args(["benchmark", "main.py", "--root", str(sample_project), "--format", "json"])
    ret = run_benchmark(args)

    assert ret == 0
    payload = json.loads(mock_stdout.getvalue())
    assert "metadata" in payload
    assert "metrics" in payload
    assert "breakdown" in payload
    assert payload["metrics"]["total_raw"] > 0


def test_benchmark_run_markdown_output(sample_project: Path, monkeypatch):
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    parser = build_parser()
    args = parser.parse_args(["benchmark", "main.py", "--root", str(sample_project), "--format", "markdown"])
    ret = run_benchmark(args)

    assert ret == 0
    output = mock_stdout.getvalue()
    assert "| Target Module | Raw Tokens | Pruned Tokens | Reduction |" in output
    assert "main.py" in output
    assert "Audit generated via `ctxfw`" in output
    assert "contacto@heuristicolab.com" in output


def test_benchmark_target_not_found(sample_project: Path, monkeypatch):
    mock_stderr = io.StringIO()
    monkeypatch.setattr("sys.stderr", mock_stderr)

    parser = build_parser()
    args = parser.parse_args(["benchmark", "non_existent.py", "--root", str(sample_project)])
    ret = run_benchmark(args)

    assert ret == 1
    assert "Target path does not exist" in mock_stderr.getvalue()
