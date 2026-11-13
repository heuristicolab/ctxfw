"""
src/ctxfw/storage/cache.py — Persistent SQLite WAL Cache with XDG Resolution (v4.1.0)
manifest_hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3
manifest_hash_v41_multirepo: 73a24a0ac04e9142a8ce9684758e0e947583f8bb96d8884503482686d6aba6e5
manifest_hash_wave1c: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762

Isolates storage paths into standard OS-specific directories (%LOCALAPPDATA%, ~/.cache, etc.)
while preserving hermetic override capabilities (e.g. :memory: or custom paths for testing).
Includes dedicated D3 symbol cartography B-Tree index with workspace-scoped isolation
and per-repository FinOps attribution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ctxfw.core.contracts import OptimizationResultDTO, PruningDepth

_WORKSPACE_ROOT_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "SPEC.axioms.md",
    ".cursorrules",
    "CLAUDE.md",
)


def resolve_project_identity(path: Optional[str | Path] = None) -> Tuple[str, str]:
    """
    Deterministically resolves (project_id, project_name) from a file or directory path.
    Walks up parent directories to locate the workspace root (.git, pyproject.toml, etc.),
    stopping strictly before the user home directory or filesystem root so global ~/CLAUDE.md
    files never misattribute repositories to the OS username.
    Returns ('REPO-0000000000000000', 'global') when path is None or unresolvable.
    """
    if path is None:
        return ("REPO-0000000000000000", "global")
    try:
        raw_str = str(path).strip()
        if not raw_str:
            return ("REPO-0000000000000000", "global")
        resolved = Path(raw_str).resolve()
        start_dir = resolved.parent if (resolved.is_file() or resolved.suffix) else resolved

        try:
            home_dir = Path.home().resolve()
        except Exception:
            home_dir = None

        workspace_root = start_dir
        cur = start_dir
        for _ in range(12):
            if home_dir is not None and cur == home_dir:
                break
            if cur.parent == cur:
                break
            if any((cur / marker).exists() for marker in _WORKSPACE_ROOT_MARKERS):
                workspace_root = cur
                break
            cur = cur.parent

        if home_dir is not None and workspace_root == home_dir:
            return ("REPO-0000000000000000", "global")

        posix_root = workspace_root.as_posix().lower()
        digest16 = hashlib.sha256(posix_root.encode("utf-8")).hexdigest()[:16]
        project_id = f"REPO-{digest16}"
        raw_name = workspace_root.name or "workspace"
        project_name = re.sub(r"[^A-Za-z0-9._-]", "-", raw_name)[:64].strip("-") or "workspace"
        return (project_id, project_name)
    except Exception:
        return ("REPO-0000000000000000", "global")


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
    """Embedded transactional cache backed by SQLite WAL with XDG path resolution and multi-repo isolation."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            self.db_path = str(get_canonical_cache_path())
        else:
            self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._l1_cache: Dict[str, OptimizationResultDTO] = {}
        self._l1_key_projects: Dict[str, str] = {}
        self._d3_l1_cache: Dict[str, Tuple[float, str, List[str]]] = {}
        self._tracelite_l1_cache: Dict[Tuple[str, str], dict] = {}
        self._rollback_epochs: Dict[str, int] = {}
        self._stale_reads_blocked: Dict[str, bool] = {}
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
        self._l1_key_projects.clear()
        self._d3_l1_cache.clear()
        self._tracelite_l1_cache.clear()
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
                project_id TEXT NOT NULL DEFAULT 'REPO-0000000000000000',
                project_name TEXT NOT NULL DEFAULT 'global',
                model_name TEXT NOT NULL DEFAULT 'auto',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(tokens_cache);").fetchall()}
        if "project_id" not in existing_cols:
            conn.execute(
                "ALTER TABLE tokens_cache ADD COLUMN project_id TEXT NOT NULL DEFAULT 'REPO-0000000000000000';"
            )
        if "project_name" not in existing_cols:
            conn.execute(
                "ALTER TABLE tokens_cache ADD COLUMN project_name TEXT NOT NULL DEFAULT 'global';"
            )
        if "model_name" not in existing_cols:
            conn.execute(
                "ALTER TABLE tokens_cache ADD COLUMN model_name TEXT NOT NULL DEFAULT 'auto';"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tokens_cache_project ON tokens_cache(project_name);"
        )
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_epoch_state (
                project_id TEXT PRIMARY KEY,
                rollback_epoch INTEGER NOT NULL DEFAULT 0,
                stale_reads_blocked INTEGER NOT NULL DEFAULT 0,
                last_snapshot_id TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracelite_render_cache (
                source_sha256 TEXT NOT NULL,
                policy_hash TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                canvas_width_px INTEGER NOT NULL,
                canvas_height_px INTEGER NOT NULL,
                patch_size_px INTEGER NOT NULL,
                raw_text_tokens INTEGER NOT NULL,
                optical_patch_tokens INTEGER NOT NULL,
                effective_compression_k REAL NOT NULL,
                char_similarity REAL NOT NULL,
                rendered_digest TEXT NOT NULL,
                compacted_payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_sha256, policy_hash)
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
            SELECT pruned_code, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage, pruning_depth, project_id
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
        if len(row) > 6 and row[6]:
            self._l1_key_projects[cache_key] = str(row[6])
        return dto

    def attribute_project(
        self,
        cache_key: str,
        project_root: Optional[str | Path] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """
        Associates an existing cached entry with its active project_id, project_name, and model_name
        when the entry was previously stored under the unscoped 'global' bucket.
        """
        if project_root is None:
            return
        project_id, project_name = resolve_project_identity(project_root)
        if project_name == "global":
            return
        resolved_model = "auto"
        try:
            from ctxfw.finops import resolve_active_model

            resolved_model = resolve_active_model(model_name, project_root).model_id
        except Exception:
            pass
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE tokens_cache
                    SET project_id = ?, project_name = ?, model_name = ?
                    WHERE cache_key = ? AND (project_name = 'global' OR project_name = '')
                    """,
                    (project_id, project_name, resolved_model, cache_key),
                )
        except Exception:
            pass

    def set(
        self,
        cache_key: str,
        result: OptimizationResultDTO,
        project_root: Optional[str | Path] = None,
        model_name: Optional[str] = None,
    ):
        self._l1_cache[cache_key] = result.model_copy(update={"cache_hit": True})
        depth_val = result.depth.value if hasattr(result.depth, "value") else str(result.depth)
        project_id, project_name = resolve_project_identity(project_root)
        resolved_model = "auto"
        try:
            from ctxfw.finops import resolve_active_model

            resolved_model = resolve_active_model(model_name, project_root).model_id
        except Exception:
            pass

        with self._get_connection() as conn:
            if project_name == "global":
                cur = conn.execute(
                    "SELECT project_id, project_name, model_name FROM tokens_cache WHERE cache_key = ?",
                    (cache_key,),
                )
                existing = cur.fetchone()
                if existing and existing[1] and existing[1] != "global":
                    project_id, project_name = existing[0], existing[1]
                    if len(existing) > 2 and existing[2] and existing[2] != "auto":
                        resolved_model = existing[2]

            self._l1_key_projects[cache_key] = project_id
            conn.execute("""
                INSERT OR REPLACE INTO tokens_cache 
                (cache_key, pruned_code, pruning_depth, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage, project_id, project_name, model_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cache_key,
                result.pruned_code,
                depth_val,
                result.original_chars,
                result.pruned_chars,
                result.estimated_tokens_saved,
                result.savings_percentage,
                project_id,
                project_name,
                resolved_model,
            ))

    @staticmethod
    def _d3_scoped_key(rel_path: str, project_root: Optional[str | Path]) -> str:
        if project_root is None:
            return rel_path
        project_id, _ = resolve_project_identity(project_root)
        if project_id == "REPO-0000000000000000":
            return rel_path
        return f"{project_id}::{rel_path}"

    def get_d3_symbols_batch(
        self,
        module_rel_paths: List[str],
        project_root: Optional[str | Path] = None,
    ) -> Dict[str, Tuple[float, str, List[str]]]:
        """
        Retrieves cached D3 symbol indices in a single batch query.
        When project_root is provided, keys are isolated by deterministic project_id
        so identical relative paths across different repositories never collide.
        Returns dict: module_rel_path -> (mtime, sha256, symbols_list)
        """
        if not module_rel_paths:
            return {}

        results: Dict[str, Tuple[float, str, List[str]]] = {}
        missing_scoped: List[str] = []
        scoped_to_rel: Dict[str, str] = {}

        for p in module_rel_paths:
            scoped = self._d3_scoped_key(p, project_root)
            scoped_to_rel[scoped] = p
            if scoped in self._d3_l1_cache:
                results[p] = self._d3_l1_cache[scoped]
            else:
                missing_scoped.append(scoped)

        if not missing_scoped:
            return results

        conn = self._get_connection()
        placeholders = ",".join("?" for _ in missing_scoped)
        sql = f"""
            SELECT module_rel_path, mtime, sha256, symbols_json
            FROM d3_symbol_index
            WHERE module_rel_path IN ({placeholders})
        """
        cur = conn.cursor()
        cur.execute(sql, tuple(missing_scoped))
        for row in cur.fetchall():
            scoped_key, mtime, hsh, syms_json = row
            orig_rel = scoped_to_rel.get(scoped_key, scoped_key)
            try:
                symbols = json.loads(syms_json)
                if isinstance(symbols, list):
                    entry = (float(mtime), str(hsh), symbols)
                    results[orig_rel] = entry
                    self._d3_l1_cache[scoped_key] = entry
            except Exception:
                continue
        return results

    def set_d3_symbols_batch(
        self,
        records: List[Tuple[str, str, float, List[str]]],
        project_root: Optional[str | Path] = None,
    ):
        """
        Persists a batch of D3 module symbols into SQLite WAL in a single atomic transaction.
        records: List of (module_rel_path, sha256, mtime, symbols_list)
        """
        if not records:
            return

        payloads = []
        for mod, hsh, mtime, syms in records:
            scoped = self._d3_scoped_key(mod, project_root)
            self._d3_l1_cache[scoped] = (float(mtime), str(hsh), list(syms))
            payloads.append(
                (
                    scoped,
                    hsh,
                    mtime,
                    json.dumps(syms),
                    len(syms),
                )
            )
        conn = self._get_connection()
        conn.executemany("""
            INSERT OR REPLACE INTO d3_symbol_index
            (module_rel_path, sha256, mtime, symbols_json, symbol_count)
            VALUES (?, ?, ?, ?, ?)
        """, payloads)
        conn.commit()

    def _epoch_key(self, project_root: Optional[str | Path]) -> str:
        if project_root is None:
            return "GLOBAL"
        project_id, _ = resolve_project_identity(project_root)
        return project_id

    def get_rollback_epoch(self, project_root: Optional[str | Path] = None) -> int:
        epoch_key = self._epoch_key(project_root)
        if epoch_key in self._rollback_epochs:
            return self._rollback_epochs[epoch_key]
        conn = self._get_connection()
        row = conn.execute(
            "SELECT rollback_epoch FROM cache_epoch_state WHERE project_id = ?",
            (epoch_key,),
        ).fetchone()
        val = int(row[0]) if row else 0
        self._rollback_epochs[epoch_key] = val
        return val

    def is_stale_read_blocked(self, project_root: Optional[str | Path] = None) -> bool:
        epoch_key = self._epoch_key(project_root)
        if epoch_key in self._stale_reads_blocked and self._stale_reads_blocked[epoch_key]:
            return True
        conn = self._get_connection()
        row = conn.execute(
            "SELECT stale_reads_blocked FROM cache_epoch_state WHERE project_id = ?",
            (epoch_key,),
        ).fetchone()
        if row and int(row[0]) == 1:
            self._stale_reads_blocked[epoch_key] = True
            return True
        if epoch_key != "GLOBAL":
            global_blocked = self._stale_reads_blocked.get("GLOBAL")
            if global_blocked:
                return True
            g_row = conn.execute(
                "SELECT stale_reads_blocked FROM cache_epoch_state WHERE project_id = 'GLOBAL'"
            ).fetchone()
            if g_row and int(g_row[0]) == 1:
                self._stale_reads_blocked["GLOBAL"] = True
                return True
        return False

    def clear_stale_read_block(self, project_root: Optional[str | Path] = None) -> None:
        epoch_key = self._epoch_key(project_root)
        self._stale_reads_blocked[epoch_key] = False
        epoch = self.get_rollback_epoch(project_root)
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO cache_epoch_state
            (project_id, rollback_epoch, stale_reads_blocked, last_snapshot_id, updated_at)
            VALUES (
                ?,
                ?,
                0,
                (SELECT last_snapshot_id FROM cache_epoch_state WHERE project_id = ?),
                CURRENT_TIMESTAMP
            )
            """,
            (epoch_key, epoch, epoch_key),
        )
        if project_root is not None and self._stale_reads_blocked.get("GLOBAL"):
            self._stale_reads_blocked["GLOBAL"] = False
            conn.execute(
                "UPDATE cache_epoch_state SET stale_reads_blocked = 0, updated_at = CURRENT_TIMESTAMP WHERE project_id = 'GLOBAL'"
            )
        conn.commit()

    def invalidate_for_rollback(
        self,
        project_root: Optional[str | Path] = None,
        snapshot_id: Optional[str] = None,
        clear_tracelite: bool = True,
    ) -> int:
        """
        Deterministically evicts L1/L2 token cache, D3 symbol cache, and optical TraceLite
        cache entries scoped to project_root (or globally if None), increments rollback_epoch,
        and blocks stale_reads_on_herd until clean re-indexing finishes.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        removed = 0

        if project_root is None:
            removed += len(self._l1_cache)
            self._l1_cache.clear()
            self._l1_key_projects.clear()
            cur.execute("DELETE FROM tokens_cache")
            removed += max(0, cur.rowcount)

            removed += len(self._d3_l1_cache)
            self._d3_l1_cache.clear()
            cur.execute("DELETE FROM d3_symbol_index")
            removed += max(0, cur.rowcount)
            epoch_key = "GLOBAL"
        else:
            project_id, _ = resolve_project_identity(project_root)
            epoch_key = project_id

            l2_keys = {
                r[0]
                for r in cur.execute(
                    "SELECT cache_key FROM tokens_cache WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            l1_victim_keys = [
                k
                for k in list(self._l1_cache.keys())
                if k in l2_keys or self._l1_key_projects.get(k) == project_id
            ]
            for k in l1_victim_keys:
                self._l1_cache.pop(k, None)
                self._l1_key_projects.pop(k, None)
                removed += 1

            cur.execute("DELETE FROM tokens_cache WHERE project_id = ?", (project_id,))
            removed += max(0, cur.rowcount)

            if project_id == "REPO-0000000000000000":
                d3_l1_victims = [
                    k for k in list(self._d3_l1_cache.keys()) if not k.startswith("REPO-")
                ]
                for k in d3_l1_victims:
                    self._d3_l1_cache.pop(k, None)
                    removed += 1
                cur.execute(
                    "DELETE FROM d3_symbol_index WHERE module_rel_path NOT LIKE 'REPO-%::%'"
                )
            else:
                prefix = f"{project_id}::"
                d3_l1_victims = [
                    k for k in list(self._d3_l1_cache.keys()) if k.startswith(prefix)
                ]
                for k in d3_l1_victims:
                    self._d3_l1_cache.pop(k, None)
                    removed += 1
                cur.execute(
                    "DELETE FROM d3_symbol_index WHERE module_rel_path LIKE ?",
                    (f"{prefix}%",),
                )
            removed += max(0, cur.rowcount)

        if clear_tracelite:
            removed += len(self._tracelite_l1_cache)
            self._tracelite_l1_cache.clear()
            cur.execute("DELETE FROM tracelite_render_cache")
            removed += max(0, cur.rowcount)

        next_epoch = self.get_rollback_epoch(project_root) + 1
        self._rollback_epochs[epoch_key] = next_epoch
        self._stale_reads_blocked[epoch_key] = True
        conn.execute(
            """
            INSERT OR REPLACE INTO cache_epoch_state
            (project_id, rollback_epoch, stale_reads_blocked, last_snapshot_id, updated_at)
            VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
            """,
            (epoch_key, next_epoch, snapshot_id),
        )
        conn.commit()
        return removed

    def get_optical_artifact(self, source_sha256: str, policy_hash: str) -> Optional[dict]:
        key = (source_sha256, policy_hash)
        if key in self._tracelite_l1_cache:
            return dict(self._tracelite_l1_cache[key])
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT artifact_id, source_sha256, policy_hash, canvas_width_px,
                   canvas_height_px, patch_size_px, raw_text_tokens,
                   optical_patch_tokens, effective_compression_k,
                   char_similarity, rendered_digest, compacted_payload
            FROM tracelite_render_cache
            WHERE source_sha256 = ? AND policy_hash = ?
            """,
            (source_sha256, policy_hash),
        ).fetchone()
        if not row:
            return None
        record = {
            "artifact_id": row[0],
            "source_sha256": row[1],
            "policy_hash": row[2],
            "canvas_width_px": row[3],
            "canvas_height_px": row[4],
            "patch_size_px": row[5],
            "raw_text_tokens": row[6],
            "optical_patch_tokens": row[7],
            "effective_compression_k": row[8],
            "char_similarity": row[9],
            "rendered_digest": row[10],
            "compacted_payload": row[11],
        }
        self._tracelite_l1_cache[key] = record
        return dict(record)

    def set_optical_artifact(
        self,
        artifact_id: str,
        source_sha256: str,
        policy_hash: str,
        canvas_width_px: int,
        canvas_height_px: int,
        patch_size_px: int,
        raw_text_tokens: int,
        optical_patch_tokens: int,
        effective_compression_k: float,
        char_similarity: float,
        rendered_digest: str,
        compacted_payload: str,
    ) -> None:
        record = {
            "artifact_id": artifact_id,
            "source_sha256": source_sha256,
            "policy_hash": policy_hash,
            "canvas_width_px": int(canvas_width_px),
            "canvas_height_px": int(canvas_height_px),
            "patch_size_px": int(patch_size_px),
            "raw_text_tokens": int(raw_text_tokens),
            "optical_patch_tokens": int(optical_patch_tokens),
            "effective_compression_k": float(effective_compression_k),
            "char_similarity": float(char_similarity),
            "rendered_digest": rendered_digest,
            "compacted_payload": compacted_payload,
        }
        self._tracelite_l1_cache[(source_sha256, policy_hash)] = record
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO tracelite_render_cache (
                source_sha256, policy_hash, artifact_id, canvas_width_px,
                canvas_height_px, patch_size_px, raw_text_tokens,
                optical_patch_tokens, effective_compression_k,
                char_similarity, rendered_digest, compacted_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_sha256,
                policy_hash,
                artifact_id,
                int(canvas_width_px),
                int(canvas_height_px),
                int(patch_size_px),
                int(raw_text_tokens),
                int(optical_patch_tokens),
                float(effective_compression_k),
                float(char_similarity),
                rendered_digest,
                compacted_payload,
            ),
        )
        conn.commit()


