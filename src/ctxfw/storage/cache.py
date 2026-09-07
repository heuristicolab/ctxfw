"""
src/ctxfw/storage/cache.py — Persistent SQLite WAL Cache with XDG Resolution (v3.4.0)
Isolates storage paths into standard OS-specific directories (%LOCALAPPDATA%, ~/.cache, etc.)
while preserving hermetic override capabilities (e.g. :memory: or custom paths for testing).
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

from ctxfw.core.contracts import OptimizationResultDTO, PruningDepth


def get_canonical_cache_path() -> Path:
    """Resolves the canonical SQLite cache path following XDG Base Directory and Windows LocalAppData standards."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

    target_dir = base / "ctxfw"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "tokens.db"


class LocalSemanticCache:
    """Embedded transactional cache backed by SQLite WAL with XDG path resolution."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            self.db_path = str(get_canonical_cache_path())
        else:
            self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tokens_cache';")
            if cur.fetchone():
                columns = [row[1] for row in cur.execute("PRAGMA table_info(tokens_cache);").fetchall()]
                if "pruning_depth" not in columns:
                    conn.execute("DROP TABLE tokens_cache;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens_cache (
                    cache_key TEXT PRIMARY KEY,
                    pruned_code TEXT NOT NULL,
                    pruning_depth TEXT NOT NULL DEFAULT 'interface',
                    original_chars INTEGER NOT NULL,
                    pruned_chars INTEGER NOT NULL,
                    estimated_tokens_saved INTEGER NOT NULL,
                    savings_percentage REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    @staticmethod
    def generate_key(
        source_code: str,
        rules_version: str,
        strip_docs: bool,
        depth: str = "interface",
        language: str = "python",
    ) -> str:
        lang_str = language.value.lower() if hasattr(language, "value") else str(language).lower()
        payload = f"{source_code}|{rules_version}|{strip_docs}|{depth}|{lang_str}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[OptimizationResultDTO]:
        start = time.perf_counter()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT pruned_code, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage, pruning_depth
                FROM tokens_cache WHERE cache_key = ?
            """, (cache_key,))
            row = cur.fetchone()
            if not row:
                return None

            elapsed_ms = (time.perf_counter() - start) * 1000
            return OptimizationResultDTO(
                pruned_code=row[0],
                original_chars=row[1],
                pruned_chars=row[2],
                estimated_tokens_saved=row[3],
                savings_percentage=row[4],
                cache_hit=True,
                execution_ms=round(elapsed_ms, 3),
                depth=PruningDepth(row[5]) if len(row) > 5 and row[5] else PruningDepth.INTERFACE,
            )

    def set(self, cache_key: str, result: OptimizationResultDTO):
        depth_val = result.depth.value if hasattr(result.depth, "value") else str(result.depth)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tokens_cache 
                (cache_key, pruned_code, pruning_depth, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                cache_key,
                result.pruned_code,
                depth_val,
                result.original_chars,
                result.pruned_chars,
                result.estimated_tokens_saved,
                result.savings_percentage,
            ))
