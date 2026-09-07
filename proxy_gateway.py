"""
proxy_gateway.py — Root Compatibility Shim for ctxfw.proxy (v3.4.0)
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from ctxfw.proxy import (
    app,
    get_cache,
    compact_code_snippet,
    compact_text_payload,
    inspect_and_compact_payload,
    forward_upstream,
    main,
)

__all__ = [
    "app",
    "get_cache",
    "compact_code_snippet",
    "compact_text_payload",
    "inspect_and_compact_payload",
    "forward_upstream",
    "main",
]

if __name__ == "__main__":
    main()
