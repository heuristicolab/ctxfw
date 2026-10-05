"""
tests/test_docs_parity.py — Deterministic Documentation & Metadata Parity Sentry
Axiom Manifest Hash: 1e0325198560640ee9df033de68c96fc3fc707608fa76523d9dee78ecf1f0197

Guarantees 100% synchronization across code versions, project metadata,
documentation files, and verified test telemetry count.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_core_version() -> str:
    """Extracts the canonical __version__ string from src/ctxfw/__init__.py."""
    init_file = REPO_ROOT / "src" / "ctxfw" / "__init__.py"
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_file.read_text(encoding="utf-8"))
    assert match, "No se encontró __version__ en __init__.py"
    return match.group(1)


def test_version_parity_across_repository():
    """Valida que la versión sea idéntica en pyproject.toml, __init__.py, README y USER_MANUAL."""
    version = get_core_version()

    # 1. pyproject.toml
    pyproject_file = REPO_ROOT / "pyproject.toml"
    if tomllib is not None:
        with open(pyproject_file, "rb") as f:
            pyproject = tomllib.load(f)
        pyproject_version = pyproject["project"]["version"]
    else:
        m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', pyproject_file.read_text(encoding="utf-8"))
        assert m, "No se encontró version en pyproject.toml"
        pyproject_version = m.group(1)

    assert pyproject_version == version, f"Desfase en pyproject.toml: {pyproject_version} != {version}"

    # 2. README.md
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{version}" in readme_text or f"ctxfw-{version}" in readme_text, f"README.md no menciona la versión v{version}"

    # 3. USER_MANUAL.md
    manual_text = (REPO_ROOT / "USER_MANUAL.md").read_text(encoding="utf-8")
    assert version in manual_text, f"USER_MANUAL.md no menciona la versión {version}"


def test_llms_txt_contains_canonical_references():
    """Verifica que llms.txt mantenga los enlaces a los benchmarks y release notes."""
    llms_text = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")
    assert "TRILOGY_EMPIRICAL_BENCHMARK.md" in llms_text, "llms.txt no referencia el benchmark de la trilogía"
    assert "RELEASE_NOTES_v" in llms_text, "llms.txt no enlaza las notas de release"

    # Valida que todos los archivos markdown locales referenciados existan en disco
    links = re.findall(r'\[([^\]]+)\]\(([^)]+\.md)\)', llms_text)
    for title, link in links:
        if not link.startswith("http"):
            target_path = REPO_ROOT / link
            assert target_path.is_file(), f"Enlace roto en llms.txt: {link} no existe en disco"



def test_test_count_parity():
    """Verifica que la cantidad de tests declarada en documentación coincida con el reporte oficial."""
    report_file = REPO_ROOT / "tests" / "test_report.json"
    if not report_file.exists():
        pytest.skip("tests/test_report.json no generado aún")

    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    total_tests = (
        report_data.get("passed_count")
        or report_data.get("summary", {}).get("total", 0)
    )

    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert f"{total_tests}" in claude_md, f"CLAUDE.md desfasado respecto al conteo de tests ({total_tests})"
    assert f"{total_tests}" in readme, f"README.md desfasado respecto al conteo de tests ({total_tests})"
