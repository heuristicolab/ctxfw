"""
src/ctxfw/storage/cache.py — Persistent SQLite WAL Cache with XDG Resolution (v4.0.0-dev)
manifest_hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3

Isolates storage paths into standard OS-specific directories (%LOCALAPPDATA%, ~/.cache, etc.)
while preserving hermetic override capabilities (e.g. :memory: or custom paths for testing).
Now includes dedicated D3 symbol cartography B-Tree index with batch transaction optimizations.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
        self._conn: Optional[sqlite3.Connection] = None
        self._l1_cache: Dict[str, OptimizationResultDTO] = {}
        self._d3_l1_cache: Dict[str, Tuple[float, str, List[str]]] = {}
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            self._conn = conn
        return self._conn

    def close(self):
        self._l1_cache.clear()
        self._d3_l1_cache.clear()
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __del__(self):
        self.close()

    def _init_db(self):
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS d3_symbol_index (
                module_rel_path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                mtime REAL NOT NULL,
                symbols_json TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

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
        if cache_key in self._l1_cache:
            return self._l1_cache[cache_key]

        start = time.perf_counter()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT pruned_code, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage, pruning_depth
            FROM tokens_cache WHERE cache_key = ?
        """, (cache_key,))
        row = cur.fetchone()
        if not row:
            return None

        elapsed_ms = (time.perf_counter() - start) * 1000
        dto = OptimizationResultDTO(
            pruned_code=row[0],
            original_chars=row[1],
            pruned_chars=row[2],
            estimated_tokens_saved=row[3],
            savings_percentage=row[4],
            cache_hit=True,
            execution_ms=round(elapsed_ms, 3),
            depth=PruningDepth(row[5]) if len(row) > 5 and row[5] else PruningDepth.INTERFACE,
        )
        self._l1_cache[cache_key] = dto
        return dto

    def set(self, cache_key: str, result: OptimizationResultDTO):
        self._l1_cache[cache_key] = result.model_copy(update={"cache_hit": True})
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

    def get_d3_symbols_batch(
        self,
        module_rel_paths: List[str],
    ) -> Dict[str, Tuple[float, str, List[str]]]:
        """
        Retrieves cached D3 symbol indices in a single batch query.
        Returns dict: module_rel_path -> (mtime, sha256, symbols_list)
        """
        if not module_rel_paths:
            return {}

        results: Dict[str, Tuple[float, str, List[str]]] = {}
        missing: List[str] = []
        for p in module_rel_paths:
            if p in self._d3_l1_cache:
                results[p] = self._d3_l1_cache[p]
            else:
                missing.append(p)

        if not missing:
            return results

        conn = self._get_connection()
        placeholders = ",".join("?" for _ in missing)
        sql = f"""
            SELECT module_rel_path, mtime, sha256, symbols_json
            FROM d3_symbol_index
            WHERE module_rel_path IN ({placeholders})
        """
        cur = conn.cursor()
        cur.execute(sql, tuple(missing))
        for row in cur.fetchall():
            mod, mtime, hsh, syms_json = row
            try:
                symbols = json.loads(syms_json)
                if isinstance(symbols, list):
                    entry = (float(mtime), str(hsh), symbols)
                    results[mod] = entry
                    self._d3_l1_cache[mod] = entry
            except Exception:
                continue
        return results

    def set_d3_symbols_batch(
        self,
        records: List[Tuple[str, str, float, List[str]]],
    ):
        """
        Persists a batch of D3 module symbols into SQLite WAL in a single atomic transaction.
        records: List of (module_rel_path, sha256, mtime, symbols_list)
        """
        if not records:
            return

        for mod, hsh, mtime, syms in records:
            self._d3_l1_cache[mod] = (float(mtime), str(hsh), list(syms))

        payloads = [
            (
                mod,
                hsh,
                mtime,
                json.dumps(syms),
                len(syms),
            )
            for mod, hsh, mtime, syms in records
        ]
        conn = self._get_connection()
        conn.executemany("""
            INSERT OR REPLACE INTO d3_symbol_index
            (module_rel_path, sha256, mtime, symbols_json, symbol_count)
            VALUES (?, ?, ?, ?, ?)
        """, payloads)
        conn.commit()

