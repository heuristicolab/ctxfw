"""
tests/test_tracelite_reducer.py — TDD & Integration Suite for Wave 1 Block C #12 (TraceLite)
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
manifest_hash_hardening_c1: aad104b6b66067be4bcce9ec6297c4de2822cf1d3c38a76e79e04cf147f62dd9
"""
from __future__ import annotations

import copy
import hashlib
import sqlite3

import pytest
from pydantic import ValidationError

from ctxfw.proxy import compact_text_payload, inspect_and_compact_payload
from ctxfw.storage.cache import LocalSemanticCache
from ctxfw.tracelite import (
    AgentObservationStep,
    CrossStepOverlapDeduplicator,
    EditPhaseCleanupEngine,
    FailureErrorClass,
    OpticalObservationRenderer,
    TraceLifecycleEvent,
    TraceLifecycleState,
    TraceLiteReducer,
    TraceLiteStore,
    TraceQuarantineIncident,
    TraceReducerPolicy,
    transition_trace_state,
)
from ctxfw.tracelite.reducer import is_edit_action


def _make_verbose_obs(tag: str, lines: int = 30) -> str:
    body = [f"Path: src/{tag}.py"]
    for i in range(lines):
        body.append(f"def handler_{tag}_{i}(x: int) -> int: return x + {i}  # verbose diagnostics line {i} payload padding")
    return "\n".join(body)


def test_policy_enforces_negative_invariants_and_bounds() -> None:
    policy = TraceReducerPolicy()
    assert policy.aux_llm_allowed is False
    assert policy.training_free_enforced is True
    assert policy.recent_window_w == 3
    assert policy.optical_ratio_k == 4.0
    assert policy.min_char_similarity == 0.90

    with pytest.raises(ValidationError):
        TraceReducerPolicy(aux_llm_allowed=True)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(training_free_enforced=False)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(preserve_actions_strictly=False)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(preserve_newest_observation_strictly=False)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(recent_window_w=0)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(recent_window_w=11)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(optical_ratio_k=8.5)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(min_char_similarity=0.89)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(max_canvas_px=2241)
    with pytest.raises(ValidationError):
        TraceReducerPolicy(**{"unknown_extra": 123})

    strict_pol = TraceReducerPolicy(strict_fidelity_mode=True)
    assert strict_pol.min_char_similarity >= 0.95


def test_deterministic_tracelite_fsm_transitions() -> None:
    s = TraceLifecycleState.INGESTED
    s = transition_trace_state(s, TraceLifecycleEvent.DEDUPLICATE_OVERLAPS)
    assert s == TraceLifecycleState.DEDUPLICATED
    s = transition_trace_state(s, TraceLifecycleEvent.SKIP_EDIT_CLEANUP)
    assert s == TraceLifecycleState.PHASE_CLEANED
    s = transition_trace_state(s, TraceLifecycleEvent.RENDER_OPTICAL)
    assert s == TraceLifecycleState.OPTICALLY_RENDERED
    s = transition_trace_state(s, TraceLifecycleEvent.ASSEMBLE_WINDOW)
    assert s == TraceLifecycleState.WINDOW_ASSEMBLED

    with pytest.raises(ValueError):
        transition_trace_state(TraceLifecycleState.INGESTED, TraceLifecycleEvent.ASSEMBLE_WINDOW)

    remediated = transition_trace_state(TraceLifecycleState.QUARANTINED, TraceLifecycleEvent.REMEDIATE)
    assert remediated == TraceLifecycleState.INGESTED


def test_cross_step_deduplicator_keeps_newest_and_actions_intact() -> None:
    shared_block = "\n".join(
        f"line_{i}: def shared_logic_{i}(value: str) -> str: return value.strip() + '_suffix_{i}'"
        for i in range(6)
    )
    steps = [
        AgentObservationStep(
            step_index=0,
            action_invocation="read_file(path=src/app.py)",
            observation_text=f"header_old\n{shared_block}\nfooter_old",
            target_resource="src/app.py",
        ),
        AgentObservationStep(
            step_index=1,
            action_invocation="read_file(path=src/app.py, range=all)",
            observation_text=f"header_new\n{shared_block}\nfooter_new",
            target_resource="src/app.py",
        ),
    ]
    dedup = CrossStepOverlapDeduplicator()
    out, count = dedup.deduplicate(steps)
    assert count >= 6
    assert out[1].observation_text == steps[1].observation_text
    assert out[0].action_invocation == steps[0].action_invocation
    assert out[1].action_invocation == steps[1].action_invocation
    assert "[TRACELITE_DEDUP:" in out[0].observation_text


def test_edit_phase_cleanup_triggers_strictly_when_is_edit_true() -> None:
    engine = EditPhaseCleanupEngine()
    read_only_steps = [
        AgentObservationStep(
            step_index=0,
            action_invocation="read_file(path=a.py)",
            observation_text=_make_verbose_obs("a", 25),
            is_edit_action=False,
        ),
        AgentObservationStep(
            step_index=1,
            action_invocation="grep_search(query=foo)",
            observation_text=_make_verbose_obs("b", 25),
            is_edit_action=False,
        ),
    ]
    untouched, count_no_edit, saw_edit_no = engine.cleanup(read_only_steps)
    assert saw_edit_no is False
    assert count_no_edit == 0
    assert untouched[0].observation_text == read_only_steps[0].observation_text
    assert untouched[1].observation_text == read_only_steps[1].observation_text

    with_edit_steps = [
        read_only_steps[0],
        AgentObservationStep(
            step_index=1,
            action_invocation="edit_file(path=a.py)",
            observation_text="Applied 3 hunk replacements cleanly.",
            is_edit_action=True,
        ),
        AgentObservationStep(
            step_index=2,
            action_invocation="pytest(path=tests/test_a.py)",
            observation_text="2 passed in 0.12s - newest observation must stay intact",
            is_edit_action=False,
        ),
    ]
    cleaned, count_edit, saw_edit_yes = engine.cleanup(with_edit_steps)
    assert saw_edit_yes is True
    assert count_edit == 1
    assert "[TRACELITE_EDIT_CLEANUP:" in cleaned[0].observation_text
    assert cleaned[0].action_invocation == with_edit_steps[0].action_invocation
    assert cleaned[1].action_invocation == with_edit_steps[1].action_invocation
    assert cleaned[2].observation_text == with_edit_steps[2].observation_text


def test_optical_renderer_bounds_fidelity_and_cache(tmp_path) -> None:
    cache = LocalSemanticCache(db_path=tmp_path / "optical_cache.db")
    try:
        renderer = OpticalObservationRenderer()
        step = AgentObservationStep(
            step_index=0,
            action_invocation="read_file(path=big.py)",
            observation_text=_make_verbose_obs("big", 60),
        )
        policy = TraceReducerPolicy(optical_ratio_k=4.0, min_char_similarity=0.90)
        artifact = renderer.render(step, policy, cache=cache)
        assert 1.0 <= artifact.effective_compression_k <= 4.0
        assert artifact.char_similarity >= 0.95
        assert 224 <= artifact.canvas_width_px <= 2240
        assert 224 <= artifact.canvas_height_px <= 2240
        assert artifact.optical_patch_tokens < artifact.raw_text_tokens

        # Cache hit matches identically
        cached_art = renderer.render(step, policy, cache=cache)
        assert cached_art.rendered_digest == artifact.rendered_digest
        assert cached_art.artifact_id == artifact.artifact_id

        # High k=8.0 drops similarity below strict 0.95 mode, triggering fidelity breach
        strict_k8 = TraceReducerPolicy(optical_ratio_k=8.0, strict_fidelity_mode=True)
        with pytest.raises(ValueError, match="FIDELITY|similarity|char_similarity"):
            renderer.render(step, strict_k8)
    finally:
        cache.close()


def test_tracelite_reducer_window_and_quarantine_behavior() -> None:
    steps = [
        AgentObservationStep(
            step_index=i,
            action_invocation=f"read_file(path=mod_{i}.py)",
            observation_text=_make_verbose_obs(f"mod_{i}", 35),
        )
        for i in range(6)
    ]
    reducer = TraceLiteReducer(policy=TraceReducerPolicy(recent_window_w=3, optical_ratio_k=4.0))
    window, transitions, incidents = reducer.reduce("traj-01", steps)

    assert window.lifecycle_state == TraceLifecycleState.WINDOW_ASSEMBLED
    assert incidents == []
    assert len(transitions) == 4
    assert window.tokens_saved > 0
    assert window.compression_ratio > 1.0
    assert len(window.optical_artifacts) == 3  # steps 0, 1, 2 rendered; steps 3, 4, 5 in recent window
    for i in range(3, 6):
        assert window.steps[i].observation_text == steps[i].observation_text
    for orig, out in zip(steps, window.steps):
        assert orig.action_invocation == out.action_invocation

    # Strict fidelity quarantine path
    strict_reducer = TraceLiteReducer(
        policy=TraceReducerPolicy(recent_window_w=3, optical_ratio_k=8.0, strict_fidelity_mode=True)
    )
    q_win, _q_tr, q_inc = strict_reducer.reduce("traj-quarantine", steps)
    assert q_win.lifecycle_state == TraceLifecycleState.QUARANTINED
    assert len(q_inc) == 1
    assert q_inc[0].error_class == FailureErrorClass.BUSINESS
    assert q_win.tokens_saved == 0


def test_tracelite_store_wal_immutability_and_windows_burst(tmp_path) -> None:
    # Check both :memory: and WAL temp file storage
    for db_target in (":memory:", tmp_path / "tracelite_wal.db"):
        with TraceLiteStore(db_target) as store:
            reducer = TraceLiteReducer()
            for burst in range(30):
                steps = [
                    AgentObservationStep(
                        step_index=0,
                        action_invocation="read_file(path=x.py)",
                        observation_text=_make_verbose_obs(f"x_{burst}", 20),
                    ),
                    AgentObservationStep(
                        step_index=1,
                        action_invocation="read_file(path=y.py)",
                        observation_text=_make_verbose_obs(f"y_{burst}", 20),
                    ),
                    AgentObservationStep(
                        step_index=2,
                        action_invocation="edit_file(path=x.py)",
                        observation_text="edited ok",
                        is_edit_action=True,
                    ),
                    AgentObservationStep(
                        step_index=3,
                        action_invocation="pytest(path=tests/)",
                        observation_text="all pass",
                    ),
                ]
                win, tr, inc = reducer.reduce(f"burst-{burst}", steps)
                red_id = store.record_reduction(win, transitions=tr, incidents=inc)
                row = store.get_reduction(red_id)
                assert row is not None
                assert row["actions_preserved"] == 1
                assert row["newest_preserved"] == 1

            # Verify immutable BEFORE UPDATE trigger
            conn = sqlite3.connect(store.db_path) if db_target != ":memory:" else store._get_conn()
            try:
                with pytest.raises(sqlite3.DatabaseError, match="immutable"):
                    conn.execute("UPDATE tracelite_trajectories SET tokens_saved = 999999")
            finally:
                if db_target != ":memory:":
                    conn.close()

            q_inc = TraceQuarantineIncident(
                incident_id=f"qi_{hashlib.sha256(b'test').hexdigest()[:12]}",
                trajectory_id="burst-0",
                error_class=FailureErrorClass.SECURITY,
                rule_code="TEST_AUDIT",
                detail="Verify append-only quarantine logging",
            )
            store.record_quarantine(q_inc)
            assert len(store.list_quarantines("burst-0")) == 1


def test_proxy_integration_openai_and_anthropic_multi_step_traces(tmp_path) -> None:
    cache = LocalSemanticCache(db_path=tmp_path / "proxy_tracelite.db")
    try:
        obs_a = _make_verbose_obs("alpha", 45)
        obs_b = _make_verbose_obs("beta", 45)
        obs_c = _make_verbose_obs("gamma", 45)
        newest_obs = "FINAL_TEST_OUTPUT: 495 passed, exit_code=0"

        openai_payload = {
            "model": "claude-opus-4-6",
            "max_tokens": 8192,
            "thinking": {"type": "enabled", "budget_tokens": 8000},
            "messages": [
                {"role": "user", "content": "Inspect alpha/beta/gamma and patch bug"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_0", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"src/alpha.py"}'}},
                    ],
                },
                {"role": "tool", "tool_call_id": "call_0", "content": obs_a},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"src/beta.py"}'}},
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": obs_b},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"src/gamma.py"}'}},
                    ],
                },
                {"role": "tool", "tool_call_id": "call_2", "content": obs_c},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_3", "type": "function", "function": {"name": "edit_file", "arguments": '{"path":"src/alpha.py"}'}},
                    ],
                },
                {"role": "tool", "tool_call_id": "call_3", "content": "Patched src/alpha.py cleanly"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_4", "type": "function", "function": {"name": "run_tests", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "tool_call_id": "call_4", "content": newest_obs},
            ],
        }
        orig_snapshot = copy.deepcopy(openai_payload)
        compacted, saved = inspect_and_compact_payload(openai_payload, cache=cache)
        assert saved > 0
        # FinOps rules remain intact
        assert compacted["model"] == "claude-3-5-sonnet-20241022"
        assert compacted["max_tokens"] == 4096
        assert compacted["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        # Newest O_s and all assistant tool_calls remain untouched
        assert compacted["messages"][-1]["content"] == newest_obs
        for orig_m, comp_m in zip(orig_snapshot["messages"], compacted["messages"]):
            if orig_m.get("role") == "assistant":
                assert comp_m["tool_calls"] == orig_m["tool_calls"]
        # Pre-edit observation pruned
        assert "[TRACELITE_EDIT_CLEANUP:" in compacted["messages"][2]["content"]

        # Anthropic tool_use + tool_result flow
        anth_payload = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 2048,
            "messages": [
                {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_0", "name": "read_file", "input": {"path": "x.py"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_0", "content": obs_a}]},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "y.py"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": obs_b}]},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_2", "name": "write_file", "input": {"path": "x.py"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_2", "content": "wrote x.py"}]},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_3", "name": "pytest", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_3", "content": newest_obs}]},
            ],
        }
        anth_compacted, anth_saved = inspect_and_compact_payload(anth_payload, cache=cache)
        assert anth_saved > 0
        assert anth_compacted["messages"][-1]["content"][0]["content"] == newest_obs
        assert "[TRACELITE_EDIT_CLEANUP:" in anth_compacted["messages"][1]["content"][0]["content"]

        # Serialized text trace compaction in compact_text_payload
        serialized = (
            "[STEP 0] Action: read_file(path=one.py)\nObservation:\n" + obs_a + "\n"
            "[STEP 1] Action: read_file(path=two.py)\nObservation:\n" + obs_b + "\n"
            "[STEP 2] Action: edit_file(path=one.py)\nObservation:\nmodified\n"
            "[STEP 3] Action: pytest()\nObservation:\n" + newest_obs
        )
        reduced_txt, txt_saved = compact_text_payload(serialized, cache=cache)
        assert txt_saved > 0
        assert newest_obs in reduced_txt
        assert "Action: edit_file(path=one.py)" in reduced_txt
    finally:
        cache.close()


def test_is_edit_action_ignores_argument_paths_and_duplicate_step_indices(tmp_path) -> None:
    assert is_edit_action("read_file(path=src/apply_patch.py)") is False
    assert is_edit_action("read_file path=src/edit_file.py") is False
    assert is_edit_action("view_file_outline(target=src/apply_diff.py)") is False
    assert is_edit_action("pytest tests/test_write_file.py") is False
    assert is_edit_action("edit_file(path=src/app.py)") is True
    assert is_edit_action("mcp.fs:apply_patch(diff='...')") is True

    # Verify trace reading apply_patch.py with duplicate step_index=0 does NOT trigger edit cleanup
    # and does not suffer step_index collisions across optical artifacts or recent steps.
    steps = [
        AgentObservationStep(
            step_index=0,
            action_invocation="read_file(path=src/apply_patch.py)",
            observation_text=_make_verbose_obs("dup0", 35),
        ),
        AgentObservationStep(
            step_index=0,
            action_invocation="read_file(path=src/edit_file.py)",
            observation_text=_make_verbose_obs("dup1", 35),
        ),
        AgentObservationStep(
            step_index=1,
            action_invocation="read_file(path=src/other.py)",
            observation_text=_make_verbose_obs("other2", 35),
        ),
        AgentObservationStep(
            step_index=2,
            action_invocation="grep_search(pattern=apply_diff)",
            observation_text="Recent observation 1 untouched",
        ),
        AgentObservationStep(
            step_index=3,
            action_invocation="list_dir(path=src)",
            observation_text="Recent observation 2 untouched",
        ),
        AgentObservationStep(
            step_index=0,
            action_invocation="pytest()",
            observation_text="Newest observation O_s must stay raw even with duplicate step_index=0",
        ),
    ]
    cache = LocalSemanticCache(db_path=tmp_path / "tracelite_dup.db")
    try:
        reducer = TraceLiteReducer(cache=cache)
        window, transitions, incidents = reducer.reduce("traj-dup-step", steps)
        assert incidents == []
        assert window.edit_cleaned_steps_count == 0
        assert all("[TRACELITE_EDIT_CLEANUP:" not in s.observation_text for s in window.steps)
        assert any(t.event == TraceLifecycleEvent.SKIP_EDIT_CLEANUP for t in transitions)
        assert not any(t.event == TraceLifecycleEvent.APPLY_EDIT_CLEANUP for t in transitions)
        assert len(window.optical_artifacts) == 3
        assert len({a.artifact_id for a in window.optical_artifacts}) == 3
        assert window.steps[-1].observation_text == steps[-1].observation_text

        serialized = (
            "[STEP 0] Action: read_file(path=src/apply_patch.py)\nObservation:\n" + _make_verbose_obs("s0", 25) + "\n"
            "[STEP 1] Action: read_file(path=src/edit_file.py)\nObservation:\n" + _make_verbose_obs("s1", 25) + "\n"
            "[STEP 2] Action: grep_search(pattern=write_file)\nObservation:\nnewest raw result"
        )
        reduced_txt, _ = compact_text_payload(serialized, cache=cache)
        assert "[TRACELITE_EDIT_CLEANUP:" not in reduced_txt
    finally:
        cache.close()
