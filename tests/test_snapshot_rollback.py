"""
tests/test_snapshot_rollback.py — TDD & Integration Suite for Wave 1 Block C #17 (Sandbox Snapshot Rollback)
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
manifest_hash_hardening_c1: aad104b6b66067be4bcce9ec6297c4de2822cf1d3c38a76e79e04cf147f62dd9
"""
from __future__ import annotations

import hashlib
import sqlite3
import subprocess

import pytest
from pydantic import ValidationError

from ctxfw.config import ContextDepthLevel, CtxfwConfigDTO
from ctxfw.core.contracts import OptimizationResultDTO, PruningDepth
from ctxfw.core.polyglot import TreeSitterContextPruner
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.core.topological import ContextFirewallEngine
from ctxfw.storage.cache import LocalSemanticCache
from ctxfw.storage.snapshots import (
    BranchBudgetLedger,
    NonGitArtifactKind,
    NonGitRuntimeArtifact,
    RestorationMode,
    SandboxSnapshotStore,
    SnapshotArchiveCell,
    SnapshotLifecycleEvent,
    SnapshotLifecycleState,
    assess_wrong_state_attractor,
    compute_handoff_overhead,
    compute_recovery_efficiency,
    compute_selection_score,
    evaluate_branch_gate,
    select_restoration_mode,
    transition,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _init_git_repo(repo_dir, files: dict[str, str]) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@ctxfw.local"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CTXFW Test"], cwd=repo_dir, check=True, capture_output=True)
    for rel, content in files.items():
        target = repo_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True, capture_output=True)


def test_budget_fanout_and_dto_bounds() -> None:
    ledger = BranchBudgetLedger(run_id="run-1")
    assert ledger.total_token_budget == 1_000_000
    assert ledger.max_children_per_root == 2

    with pytest.raises(ValidationError):
        BranchBudgetLedger(run_id="run-bad", total_token_budget=1_000_001)
    with pytest.raises(ValidationError):
        BranchBudgetLedger(run_id="run-bad", max_children_per_root=5)
    with pytest.raises(ValidationError):
        BranchBudgetLedger(run_id="run-over", total_token_budget=1000, tokens_spent=900, handoff_tokens_spent=200)
    with pytest.raises(ValidationError):
        SnapshotArchiveCell(
            snapshot_id="s1",
            run_id="run-1",
            project_root="C:/tmp/repo",
            step_index=0,
            working_tree_digest=_digest("w1"),
            children_spawned=3,
            max_children_per_root=2,
        )


def test_snapshot_fsm_and_terminal_locks() -> None:
    st = SnapshotLifecycleState.CREATED
    st = transition(st, SnapshotLifecycleEvent.CAPTURE_CHECKPOINT)
    assert st == SnapshotLifecycleState.CHECKPOINTED
    st = transition(st, SnapshotLifecycleEvent.DETECT_ATTRACTOR)
    assert st == SnapshotLifecycleState.ATTRACTOR_DETECTED
    st = transition(st, SnapshotLifecycleEvent.REQUEST_ROLLBACK)
    assert st == SnapshotLifecycleState.ROLLBACK_PENDING
    st = transition(st, SnapshotLifecycleEvent.EXECUTE_ROLLBACK_AND_INVALIDATE)
    assert st == SnapshotLifecycleState.RESTORED_INVALIDATED
    st = transition(st, SnapshotLifecycleEvent.RESUME_FROM_RESTORED)
    assert st == SnapshotLifecycleState.CHECKPOINTED
    committed = transition(st, SnapshotLifecycleEvent.COMMIT_SOLUTION)
    assert committed == SnapshotLifecycleState.COMMITTED_TERMINAL

    with pytest.raises(ValueError, match="terminal state"):
        transition(SnapshotLifecycleState.COMMITTED_TERMINAL, SnapshotLifecycleEvent.REQUEST_ROLLBACK)
    with pytest.raises(ValueError, match="terminal state"):
        transition(SnapshotLifecycleState.QUARANTINED_TERMINAL, SnapshotLifecycleEvent.RESUME_FROM_RESTORED)


def test_non_git_artifact_restoration_mode_and_wrong_state_attractor() -> None:
    clean_mode = select_restoration_mode([], git_diff_available=True, sandbox_snapshot_available=True)
    assert clean_mode == RestorationMode.GIT_DIFF_REPLAY

    for kind in NonGitArtifactKind:
        art = NonGitRuntimeArtifact(
            artifact_id=f"art_{kind.value}",
            kind=kind,
            resource_path_or_pid=f"runtime/{kind.value}",
            pre_state_digest=_digest(kind.value),
            dirty_after_step=True,
            reversible_via_snapshot=True,
        )
        # Never replay bare git diff when SQLite WAL, daemon, migration journal, or env is dirty
        assert select_restoration_mode([art], git_diff_available=True, sandbox_snapshot_available=True) == RestorationMode.FULL_SANDBOX_SNAPSHOT
        assert select_restoration_mode([art], git_diff_available=True, sandbox_snapshot_available=False) == RestorationMode.QUARANTINED_NOOP

    cell = SnapshotArchiveCell(
        snapshot_id="snap-root",
        run_id="run-attr",
        project_root="C:/tmp/repo",
        step_index=4,
        working_tree_digest=_digest("tree"),
        pass_rate=0.25,
        failing_tests=3,
        non_git_artifacts=(
            NonGitRuntimeArtifact(
                artifact_id="sqlite-wal",
                kind=NonGitArtifactKind.SQLITE_DB,
                resource_path_or_pid="tmp/app.db",
                pre_state_digest=_digest("app.db"),
            ),
        ),
    )
    assessment = assess_wrong_state_attractor(
        snapshot=cell,
        error_signatures=["AssertionError:x", "AssertionError:x", "AssertionError:x"],
        score_stagnation_steps=3,
    )
    assert assessment.is_wrong_state_attractor is True
    assert assessment.attractor_code == "WRONG_STATE_ATTRACTOR"
    assert assessment.has_dirty_non_git_state is True
    assert assessment.recommended_restoration == RestorationMode.FULL_SANDBOX_SNAPSHOT

    handoff = compute_handoff_overhead(120, 80)
    assert handoff == 200
    assert compute_selection_score(0.8, 1, 1, handoff) > compute_selection_score(0.2, 5, 5, handoff)
    assert compute_recovery_efficiency(10000, 2000) == 5.0


def test_sandbox_snapshot_store_wal_immutability_and_fanout_budget(tmp_path) -> None:
    repo = tmp_path / "repo_wal"
    _init_git_repo(repo, {"main.py": "def ok(): return 1\n"})

    for db_target in (":memory:", tmp_path / "snapshots.db"):
        with SandboxSnapshotStore(db_target) as store:
            store.register_run(
                run_id="run-burst",
                project_root=repo,
                total_token_budget=20_000,
                max_children_per_root=2,
            )
            root = SnapshotArchiveCell(
                snapshot_id="root-0",
                run_id="run-burst",
                project_root=str(repo),
                step_index=0,
                working_tree_digest=_digest("root"),
                pass_rate=0.5,
                failing_tests=1,
                lifecycle_state=SnapshotLifecycleState.CREATED,
            )
            saved_root = store.checkpoint_snapshot(root, tokens_delta=500)
            assert saved_root.lifecycle_state == SnapshotLifecycleState.CHECKPOINTED

            # Spawn child branches up to limit=2, 3rd must fail
            c1 = store.spawn_child_branch("run-burst", "root-0", "child-1", _digest("c1"), step_index=1, tokens_delta=300)
            assert c1.depth == 1
            store.spawn_child_branch("run-burst", "root-0", "child-2", _digest("c2"), step_index=2, tokens_delta=300)
            with pytest.raises(ValueError, match="max_children_per_root"):
                store.spawn_child_branch("run-burst", "root-0", "child-3", _digest("c3"), step_index=3, tokens_delta=300)

            # Budget overflow gate check
            gated = evaluate_branch_gate(
                root=saved_root,
                ledger=store.get_ledger("run-burst"),
                projected_branch_tokens=50_000,
                projected_handoff_tokens=500,
                dispatch_id="disp-over",
                source_snapshot_id="child-2",
                rollback_epoch=1,
            )
            assert gated.allowed is False
            assert gated.restoration_mode == RestorationMode.QUARANTINED_NOOP

            # Rapid Windows sub-ms checkpoints never collide on PK
            for k in range(25):
                store.checkpoint_snapshot(
                    SnapshotArchiveCell(
                        snapshot_id=f"rapid-{k}",
                        run_id="run-burst",
                        project_root=str(repo),
                        step_index=10 + k,
                        working_tree_digest=_digest(f"rapid-{k}"),
                    ),
                    tokens_delta=10,
                )

            # Verify immutable BEFORE UPDATE trigger
            conn = sqlite3.connect(store.db_path) if db_target != ":memory:" else store._get_conn()
            try:
                with pytest.raises(sqlite3.DatabaseError, match="immutable"):
                    conn.execute("UPDATE snapshot_archive_cells SET pass_rate = 1.0")
            finally:
                if db_target != ":memory:":
                    conn.close()


def test_rollback_invalidates_all_caches_and_blocks_stale_reads_on_herd(tmp_path) -> None:
    repo = tmp_path / "herd_repo"
    files: dict[str, str] = {
        "entry.py": "import hub\n\ndef run():\n    return hub.trigger()\n",
        "hub.py": "\n".join(f"import m{i}" for i in range(24)) + "\n\ndef trigger():\n    return 1\n",
    }
    # Create depth >= 2 chain to D3 modules: entry (D0) -> hub (D1) -> d2_x (D2) -> d3_k (D3)
    d2_imports = "\n".join(f"import d3_{i}" for i in range(25))
    files = {
        "entry.py": "import hub\n\ndef run():\n    return hub.go()\n",
        "hub.py": "import bridge\n\ndef go():\n    return bridge.link()\n",
        "bridge.py": d2_imports + "\n\ndef link():\n    return 1\n",
    }
    for i in range(25):
        files[f"d3_{i}.py"] = f"def sym_pre_rollback_{i}():\n    return {i}\n"
    _init_git_repo(repo, files)

    cache = LocalSemanticCache(db_path=tmp_path / "shared_cache.db")
    try:
        cfg = CtxfwConfigDTO(
            max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
            ambient_manifest=True,
            stale_reads_on_herd=True,
            distractor_budget=100,
        )
        engine = ContextFirewallEngine(project_root=repo, cache=cache)

        # Populate L1/L2 token cache + D3 symbol index cache
        bundle1 = engine.build_context("entry.py", depth_config=cfg)
        assert bundle1.ambient_manifest is not None
        assert "sym_pre_rollback_0" in bundle1.ambient_manifest

        # Also seed tokens_cache & tracelite_render_cache directly for completeness
        dto = OptimizationResultDTO(
            pruned_code="def x(): ...",
            original_chars=100,
            pruned_chars=12,
            estimated_tokens_saved=22,
            savings_percentage=88.0,
            cache_hit=False,
            execution_ms=1.0,
        )
        cache.set("k_repo_main", dto, project_root=repo)
        cache.set_optical_artifact(
            artifact_id="a" * 32,
            source_sha256=_digest("obs"),
            policy_hash="b" * 32,
            canvas_width_px=224,
            canvas_height_px=224,
            patch_size_px=14,
            raw_text_tokens=100,
            optical_patch_tokens=25,
            effective_compression_k=4.0,
            char_similarity=0.96,
            rendered_digest=_digest("grid"),
            compacted_payload="[TRACELITE_OPTICAL]",
            project_root=repo,
        )
        assert cache.get_optical_artifact(_digest("obs"), "b" * 32, project_root=repo) is not None

        # Mutate codebase simulating bad branch then trigger SandboxSnapshotStore rollback
        with SandboxSnapshotStore(tmp_path / "rb_store.db") as rb_store:
            rb_store.register_run("run-herd", repo)
            root_cell = SnapshotArchiveCell(
                snapshot_id="root-snap",
                run_id="run-herd",
                project_root=str(repo),
                step_index=0,
                working_tree_digest=_digest("clean"),
                pass_rate=1.0,
                failing_tests=0,
            )
            bad_cell = SnapshotArchiveCell(
                snapshot_id="bad-snap",
                run_id="run-herd",
                project_root=str(repo),
                parent_snapshot_id="root-snap",
                step_index=5,
                working_tree_digest=_digest("dirty"),
                pass_rate=0.0,
                failing_tests=5,
                non_git_artifacts=(
                    NonGitRuntimeArtifact(
                        artifact_id="db-wal",
                        kind=NonGitArtifactKind.SQLITE_DB,
                        resource_path_or_pid="tmp/state.db",
                        pre_state_digest=_digest("db"),
                    ),
                ),
            )
            rb_store.checkpoint_snapshot(root_cell)
            rb_store.checkpoint_snapshot(bad_cell)

            epoch_before = DeterministicContextPruner._invalidation_epoch
            poly_before = TreeSitterContextPruner._invalidation_epoch

            dispatch = rb_store.execute_rollback(
                run_id="run-herd",
                source_snapshot_id="bad-snap",
                target_root_snapshot_id="root-snap",
                projected_branch_tokens=2000,
                handoff_summary_tokens=150,
                cache=cache,
                engine=engine,
            )
            assert dispatch.allowed is True
            assert dispatch.restoration_mode == RestorationMode.FULL_SANDBOX_SNAPSHOT
            assert dispatch.stale_reads_blocked is True
            assert dispatch.cache_invalidated_entries >= 1
            assert cache.get_rollback_epoch(repo) == 1
            assert cache.is_stale_read_blocked(repo) is True
            assert DeterministicContextPruner._invalidation_epoch > epoch_before
            assert TreeSitterContextPruner._invalidation_epoch > poly_before

        # Verify L1, L2, D3, and tracelite caches were cleared for repo
        assert len(cache._l1_cache) == 0
        assert len(cache._d3_l1_cache) == 0
        assert cache.get("k_repo_main") is None
        assert cache.get_optical_artifact(_digest("obs"), "b" * 32, project_root=repo) is None
        assert cache.get_d3_symbols_batch(["d3_0.py"], project_root=repo) == {}

        # Inject a fake pre-rollback D3 cache entry AFTER rollback and verify build_context
        # blocks stale_reads_on_herd even when >20 modules hit inline parse throttle!
        cache._d3_l1_cache[cache._d3_scoped_key("d3_22.py", repo)] = (9999999999.0, "stale", ["STALE_GHOST_SYM"])
        bundle_post = engine.build_context("entry.py", depth_config=cfg)
        if bundle_post.ambient_manifest:
            assert "STALE_GHOST_SYM" not in bundle_post.ambient_manifest
        # Turn 1 parses 20 modules (epoch 1) and throttles on >20: stale block stays armed
        assert cache.is_stale_read_blocked(repo) is True

        # Turn 2 reuses the 20 epoch-1 modules and finishes the remaining 5 modules without deadlock!
        bundle_post_2 = engine.build_context("entry.py", depth_config=cfg)
        assert cache.is_stale_read_blocked(repo) is False
        assert bundle_post_2.ambient_manifest is not None
        assert "STALE_GHOST_SYM" not in bundle_post_2.ambient_manifest
        # Verify real symbol from d3_22.py replaced the stale ghost entry cleanly
        d3_22_entry = cache.get_d3_symbols_batch(["d3_22.py"], project_root=repo)
        assert "d3_22.py" in d3_22_entry
        assert any(s.startswith("sym_pre_rollback_22") for s in d3_22_entry["d3_22.py"][2])
    finally:
        cache.close()


def test_multirepo_rollback_isolation(tmp_path) -> None:
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    _init_git_repo(repo_a, {"mod.py": "def alpha(): return 1\n"})
    _init_git_repo(repo_b, {"mod.py": "def beta(): return 2\n"})

    cache = LocalSemanticCache(db_path=tmp_path / "multi_iso.db")
    try:
        dto_a = OptimizationResultDTO(
            pruned_code="def alpha(): ...",
            original_chars=40,
            pruned_chars=16,
            estimated_tokens_saved=6,
            savings_percentage=60.0,
            cache_hit=False,
            execution_ms=1.0,
        )
        dto_b = OptimizationResultDTO(
            pruned_code="def beta(): ...",
            original_chars=40,
            pruned_chars=15,
            estimated_tokens_saved=6,
            savings_percentage=62.5,
            cache_hit=False,
            execution_ms=1.0,
        )
        cache.set("key_a", dto_a, project_root=repo_a)
        cache.set("key_b", dto_b, project_root=repo_b)
        cache.set_d3_symbols_batch([("mod.py", _digest("a"), 1.0, ["alpha"])], project_root=repo_a)
        cache.set_d3_symbols_batch([("mod.py", _digest("b"), 1.0, ["beta"])], project_root=repo_b)
        cache.set_optical_artifact(
            artifact_id="a" * 32,
            source_sha256=_digest("shared_obs"),
            policy_hash="p" * 32,
            canvas_width_px=224,
            canvas_height_px=224,
            patch_size_px=14,
            raw_text_tokens=100,
            optical_patch_tokens=25,
            effective_compression_k=4.0,
            char_similarity=0.96,
            rendered_digest=_digest("grid_a"),
            compacted_payload="[TRACELITE_A]",
            project_root=repo_a,
        )
        cache.set_optical_artifact(
            artifact_id="b" * 32,
            source_sha256=_digest("shared_obs"),
            policy_hash="p" * 32,
            canvas_width_px=224,
            canvas_height_px=224,
            patch_size_px=14,
            raw_text_tokens=100,
            optical_patch_tokens=25,
            effective_compression_k=4.0,
            char_similarity=0.96,
            rendered_digest=_digest("grid_b"),
            compacted_payload="[TRACELITE_B]",
            project_root=repo_b,
        )
        cache.set_optical_artifact(
            artifact_id="g" * 32,
            source_sha256=_digest("shared_obs"),
            policy_hash="p" * 32,
            canvas_width_px=224,
            canvas_height_px=224,
            patch_size_px=14,
            raw_text_tokens=100,
            optical_patch_tokens=25,
            effective_compression_k=4.0,
            char_similarity=0.96,
            rendered_digest=_digest("grid_g"),
            compacted_payload="[TRACELITE_GLOBAL]",
            project_root=None,
        )

        removed = cache.invalidate_for_rollback(project_root=repo_a, snapshot_id="snap-a1")
        assert removed >= 3

        # Repo A cleared & blocked; Repo B and GLOBAL optical cache completely untouched
        assert cache.get("key_a") is None
        assert cache.get_d3_symbols_batch(["mod.py"], project_root=repo_a) == {}
        assert cache.get_optical_artifact(_digest("shared_obs"), "p" * 32, project_root=repo_a) is None
        assert cache.is_stale_read_blocked(repo_a) is True
        assert cache.get_rollback_epoch(repo_a) == 1

        assert cache.get("key_b") is not None
        assert cache.get_d3_symbols_batch(["mod.py"], project_root=repo_b)["mod.py"][2] == ["beta"]
        assert cache.get_optical_artifact(_digest("shared_obs"), "p" * 32, project_root=repo_b)["compacted_payload"] == "[TRACELITE_B]"
        assert cache.get_optical_artifact(_digest("shared_obs"), "p" * 32, project_root=None)["compacted_payload"] == "[TRACELITE_GLOBAL]"
        assert cache.is_stale_read_blocked(repo_b) is False
        assert cache.get_rollback_epoch(repo_b) == 0

        # Clearing repo_a's stale read block must NEVER clear GLOBAL's stale block
        cache.invalidate_for_rollback(project_root=None, snapshot_id="snap-global")
        assert cache.is_stale_read_blocked(None) is True
        cache.clear_stale_read_block(repo_a)
        assert cache.is_stale_read_blocked(None) is True
        cache.clear_stale_read_block(None)
        assert cache.is_stale_read_blocked(None) is False
    finally:
        cache.close()


def test_snapshot_store_disk_rehydration_quarantines_and_separate_cache(tmp_path) -> None:
    db_path = tmp_path / "snapshots_rehydrate.db"
    repo_dir = tmp_path / "rehydrate_repo"
    _init_git_repo(repo_dir, {"app.py": "def run(): return 42\n"})

    artifact = NonGitRuntimeArtifact(
        artifact_id="wal-art-1",
        kind=NonGitArtifactKind.SQLITE_DB,
        resource_path_or_pid="data/state.db",
        pre_state_digest=_digest("wal-state"),
        dirty_after_step=True,
        reversible_via_snapshot=True,
    )

    with SandboxSnapshotStore(db_path) as store:
        store.register_run("run-persist", repo_dir, total_token_budget=10_000, max_children_per_root=2)
        root = SnapshotArchiveCell(
            snapshot_id="root-0",
            run_id="run-persist",
            project_root=str(repo_dir),
            step_index=0,
            working_tree_digest=_digest("r0"),
            pass_rate=0.9,
            failing_tests=1,
            max_children_per_root=2,
        )
        store.checkpoint_snapshot(root, tokens_delta=1000)
        child1 = store.spawn_child_branch(
            run_id="run-persist",
            parent_snapshot_id="root-0",
            child_snapshot_id="child-1",
            working_tree_digest=_digest("c1"),
            step_index=1,
            tokens_delta=500,
        )
        assert child1.depth == 1
        store.record_step_outcome(
            run_id="run-persist",
            snapshot_id="child-1",
            error_signature="AssertionError",
            pass_rate=0.25,
            failing_tests=3,
            tokens_delta=200,
            non_git_artifacts=(artifact,),
        )

    # Reopen from disk in a brand-new SandboxSnapshotStore instance (simulates process restart)
    external_cache = LocalSemanticCache(db_path=tmp_path / "external_cache.db")
    try:
        dto_ext = OptimizationResultDTO(
            pruned_code="def run(): ...",
            original_chars=40,
            pruned_chars=14,
            estimated_tokens_saved=6,
            savings_percentage=65.0,
            cache_hit=False,
            execution_ms=1.0,
        )
        external_cache.set("ext_k", dto_ext, project_root=repo_dir)
        engine = ContextFirewallEngine(project_root=repo_dir)

        with SandboxSnapshotStore(db_path) as reopened:
            ledger = reopened.get_ledger("run-persist")
            assert ledger.tokens_spent == 1700
            assert ledger.remaining_tokens == 8300

            restored_root_mem = reopened.get_cell("run-persist", "root-0")
            assert restored_root_mem.children_spawned == 1
            assert restored_root_mem.lifecycle_state == SnapshotLifecycleState.BRANCH_EXPANDED

            restored_child = reopened.get_cell("run-persist", "child-1")
            assert len(restored_child.non_git_artifacts) == 1
            assert restored_child.non_git_artifacts[0].artifact_id == "wal-art-1"

            # Execute rollback with BOTH engine and a DIFFERENT external cache
            dispatch = reopened.execute_rollback(
                run_id="run-persist",
                source_snapshot_id="child-1",
                target_root_snapshot_id="root-0",
                projected_branch_tokens=500,
                handoff_summary_tokens=100,
                cache=external_cache,
                engine=engine,
            )
            assert dispatch.allowed is True
            assert dispatch.rollback_epoch == 1
            assert external_cache.get("ext_k") is None
            assert external_cache.get_rollback_epoch(repo_dir) == 1

            # Trigger durable quarantine on fanout overflow in spawn_child_branch (children_spawned is now 2 == max)
            with pytest.raises(ValueError, match="max_children_per_root"):
                reopened.spawn_child_branch(
                    run_id="run-persist",
                    parent_snapshot_id="root-0",
                    child_snapshot_id="child-overflow",
                    working_tree_digest=_digest("co"),
                    step_index=2,
                )

            # Trigger durable quarantine on budget exhaustion in record_step_outcome
            with pytest.raises(ValueError, match="budget exhausted"):
                reopened.record_step_outcome(
                    run_id="run-persist",
                    snapshot_id="root-0",
                    tokens_delta=50_000,
                )

            # Verify partial SQLite commit failure rolls back cleanly without corrupting RAM
            orig_get_conn = reopened._get_conn
            real_conn = orig_get_conn()

            class _FailingCommitConn:
                def __init__(self, inner: sqlite3.Connection) -> None:
                    self._inner = inner

                def commit(self) -> None:
                    raise sqlite3.OperationalError("simulated disk I/O error")

                def __getattr__(self, item: str):
                    return getattr(self._inner, item)

            reopened._get_conn = lambda: _FailingCommitConn(real_conn)  # scoped proxy
            try:
                with pytest.raises(sqlite3.OperationalError, match="simulated disk I/O error"):
                    reopened.checkpoint_snapshot(
                        SnapshotArchiveCell(
                            snapshot_id="phantom-snap",
                            run_id="run-persist",
                            project_root=str(repo_dir),
                            step_index=9,
                            working_tree_digest=_digest("phantom"),
                        ),
                        tokens_delta=300,
                    )
            finally:
                reopened._get_conn = orig_get_conn

            with pytest.raises(KeyError):
                reopened.get_cell("run-persist", "phantom-snap")
            ledger_after_err = reopened.get_ledger("run-persist")
            assert ledger_after_err.tokens_spent == 2200
            assert ledger_after_err.handoff_tokens_spent == 100

        # Open a third instance to verify quarantines persisted to SQLite despite ValueError
        with SandboxSnapshotStore(db_path) as third:
            quarantines = third.list_quarantines("run-persist")
            rule_codes = [q["rule_code"] for q in quarantines]
            assert "FANOUT_EXCEEDED" in rule_codes
            assert "BUDGET_EXHAUSTED" in rule_codes
            assert third.get_cell("run-persist", "root-0").visit_count == 2
            with pytest.raises(KeyError):
                third.get_cell("run-persist", "phantom-snap")
    finally:
        external_cache.close()
