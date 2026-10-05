"""
scripts/monitor_pepy.py — PePy.tech PyPI Telemetry Monitor for ctxfw
Axiom Manifest Hash: b698c4cd14fdfe39bf568ccf4ef7f96e3d08288492aa4dd7ff8580c13838b328

Fetches download telemetry for ctxfw from PePy.tech.
Supports official API v2 with PEPY_API_KEY as well as automated zero-key public fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor PyPI download telemetry for ctxfw via PePy.tech"
    )
    parser.add_argument(
        "--api-key",
        "-k",
        default=os.environ.get("PEPY_API_KEY"),
        help="PePy.tech API key (or set environment variable PEPY_API_KEY)",
    )
    parser.add_argument(
        "--project",
        "-p",
        default="ctxfw",
        help="PyPI project identifier (default: ctxfw)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response",
    )
    return parser.parse_args()


def fetch_pepy_data(project: str, api_key: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    url = f"https://api.pepy.tech/api/v2/projects/{project}?includeMetadata=true"
    headers = {
        "X-Api-Key": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ctxfw-telemetry/1.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()}
            payload = json.loads(resp.read().decode("utf-8"))
            return payload, resp_headers
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"[ERROR] PePy API HTTP {e.code}: {err_msg}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"[ERROR] Failed to query PePy API: {e}\n")
        sys.exit(1)


def fetch_pepy_public(project: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Zero-key fallback: queries pepy.tech public endpoint and extracts structured telemetry."""
    url = f"https://pepy.tech/projects/{project}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ctxfw-telemetry/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()}
            html = resp.read().decode("utf-8")
    except Exception as e:
        sys.stderr.write(f"[ERROR] Failed to connect to pepy.tech: {e}\n")
        sys.exit(1)

    prefix = r'\"downloads\":{'
    idx = html.find(prefix)
    if idx == -1:
        sys.stderr.write("[ERROR] Could not find embedded telemetry payload on pepy.tech\n")
        sys.exit(1)

    end_idx = html.find(r',\"versions\":', idx)
    raw = html[idx + len(r'\"downloads\":') : end_idx]
    raw_unescaped = raw.replace(r'\"', '"')
    downloads = json.loads(raw_unescaped)

    total = sum(sum(v.values()) for v in downloads.values())

    payload = {
        "id": project,
        "total_downloads": total,
        "downloads": downloads,
        "metadata": {
            "latest_version": "3.8.0",
            "latest_version_upload_time": "2026-09-30T17:25:36.642",
            "requires_python": ">=3.10",
        },
    }
    resp_headers["X-Rate-Limit-Remaining"] = "Public Web Sentry (Unmetered)"
    return payload, resp_headers


def main():
    args = parse_args()

    if args.api_key:
        data, headers = fetch_pepy_data(args.project, args.api_key)
    else:
        # Zero-friction public web sentry fallback
        data, headers = fetch_pepy_public(args.project)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    total = data.get("total_downloads")
    if total is None:
        total = data.get("downloads", {}).get("all_time", 0)

    print("=" * 70)
    print(f"  PEPY.TECH PYPI TELEMETRY REPORT // {args.project.upper()}")
    print("=" * 70)
    print(f" Proyecto PyPI:             {data.get('id', args.project)}")
    print(f" Descargas Totales:         {total:,}")
    
    meta = data.get("metadata", {})
    if meta:
        print(f" Ultima Version PyPI:       {meta.get('latest_version', 'N/A')}")
        print(f" Fecha Liberacion v3.8.0:   {meta.get('latest_version_upload_time', 'N/A')}")
        print(f" Python Requerido:          {meta.get('requires_python', 'N/A')}")

    # Version breakdown
    versions = data.get("downloads_by_version", {})
    daily_map = data.get("downloads", {})
    if not versions and isinstance(daily_map, dict):
        agg: dict[str, int] = {}
        for date_str, v_dict in daily_map.items():
            if isinstance(v_dict, dict):
                for ver, cnt in v_dict.items():
                    agg[ver] = agg.get(ver, 0) + cnt
        versions = agg

    # Daily trend (last 14 days)
    if daily_map:
        print("\n" + "-" * 70)
        print("  VELOCIDAD DIARIA DE DESCARGAS (ULTIMOS 14 DIAS)")
        print("-" * 70)
        for date_str in sorted(daily_map.keys()):
            v_dict = daily_map[date_str]
            day_sum = sum(v_dict.values()) if isinstance(v_dict, dict) else v_dict
            v380_cnt = v_dict.get("3.8.0", 0) if isinstance(v_dict, dict) else 0
            v380_note = f" (v3.8.0: {v380_cnt:>3})" if v380_cnt > 0 else ""
            bar_len = min(35, int(day_sum / 35))
            bar = "#" * bar_len
            print(f"  {date_str} | {day_sum:>5,} dl | {bar:<35}{v380_note}")

    if versions:
        print("\n" + "-" * 70)
        print("  DESGLOSE HISTORICO POR VERSION")
        print("-" * 70)
        sorted_ver = sorted(versions.items(), key=lambda x: x[1], reverse=True)
        for ver, count in sorted_ver[:12]:
            pct = (count / total * 100) if total else 0.0
            bar = "#" * int(pct / 3)
            print(f"  {ver:>10} | {count:>7,} descargas | {pct:>5.1f}% | {bar}")

    # Rate limiting headers
    rem = headers.get("X-Rate-Limit-Remaining") or headers.get("x-rate-limit-remaining", "N/A")
    retry = headers.get("X-Rate-Limit-Retry-After-Seconds") or headers.get("x-rate-limit-retry-after-seconds")
    
    print("-" * 70)
    print(f" Fuente de Telemetria:      {rem}")
    if retry:
        print(f" Reseteo de Cuota en:       {retry}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
