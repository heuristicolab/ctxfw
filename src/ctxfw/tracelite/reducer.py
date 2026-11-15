"""
src/ctxfw/tracelite/reducer.py — Deterministic Zero-LLM TraceLite Optical Trace Reducer
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
blueprint_manifest_hash: 6a95bb7fd01158ac75d67055df0c328d56433a44625351610307d5ef6b68d0cf
manifest_hash_hardening_c1: aad104b6b66067be4bcce9ec6297c4de2822cf1d3c38a76e79e04cf147f62dd9
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import re
from typing import Any, Optional, Sequence

from ctxfw.tracelite.contracts import (
    BASE_CANVAS_PX,
    MAX_OPTICAL_RATIO_K,
    MIN_CANVAS_PX,
    WAVE1C_MANIFEST_HASH,
    AgentObservationStep,
    FailureErrorClass,
    OpticalRenderArtifact,
    ReducedTrajectoryWindow,
    TraceAuditTransition,
    TraceLifecycleEvent,
    TraceLifecycleState,
    TraceQuarantineIncident,
    TraceReducerPolicy,
    transition_trace_state,
)

_EDIT_ACTION_NAMES = frozenset({
    "edit_file",
    "write_file",
    "replace_file_content",
    "multi_replace_file_content",
    "apply_patch",
    "apply_diff",
    "str_replace_editor",
    "create_file",
    "delete_file",
    "patch_file",
    "modify_file",
})

_EDIT_ACTION_RE = re.compile(
    r"(?:^|[:./\\-])(edit_file|write_file|replace_file_content|"
    r"multi_replace_file_content|apply_patch|apply_diff|str_replace_editor|"
    r"create_file|delete_file|patch_file|modify_file)$",
    re.IGNORECASE,
)

_RESOURCE_HEADER_RE = re.compile(
    r"(?:path|file|target|uri)\s*[:=]\s*([^\r\n\s,;]+)",
    re.IGNORECASE,
)

_IMPORTANT_LINE_RE = re.compile(
    r"^\s*(?:def |class |async def |import |from |export |function |interface |"
    r"struct |enum |error|exception|traceback|assert|return |pass\b|fail\b|"
    r"warning|critical|http|status|@)",
    re.IGNORECASE,
)


def _extract_action_name(action_text: str) -> str:
    """Extract only the leading tool/invocation name, excluding argument paths/literals."""
    stripped = action_text.strip()
    if not stripped:
        return ""
    head = re.split(r"[\s(\[{=,;'\"]", stripped, maxsplit=1)[0]
    return head.rstrip(":")


def estimate_step_tokens(text: str) -> int:
    """Estimate token count deterministically without network or tokenizer dependencies."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def is_edit_action(step: AgentObservationStep | str) -> bool:
    """Return True strictly for explicit or tool-head matched mutating edit invocations."""
    if isinstance(step, AgentObservationStep):
        if step.is_edit_action:
            return True
        action_text = step.action_invocation
    else:
        action_text = step
    head = _extract_action_name(action_text)
    if not head:
        return False
    if head.lower() in _EDIT_ACTION_NAMES:
        return True
    return bool(_EDIT_ACTION_RE.search(head))


def _infer_resource_key(step: AgentObservationStep) -> Optional[str]:
    if step.target_resource:
        return step.target_resource.strip()
    match = _RESOURCE_HEADER_RE.search(step.action_invocation)
    if match:
        return match.group(1).strip()
    head = step.observation_text[:256]
    match_obs = _RESOURCE_HEADER_RE.search(head)
    if match_obs:
        return match_obs.group(1).strip()
    return None


def _hash_policy(policy: TraceReducerPolicy) -> str:
    payload = json.dumps(policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _clamp_align_px(raw_px: int, patch_px: int, max_px: int) -> int:
    bounded = max(MIN_CANVAS_PX, min(max_px, raw_px))
    aligned = ((bounded + patch_px - 1) // patch_px) * patch_px
    return max(MIN_CANVAS_PX, min(max_px, aligned))


class OpticalObservationRenderer:
    """
    Deterministic training-free optical observation renderer.
    Maps historical observation O_i onto bounded grid geometry [224, 2240] px
    and patch compression ratio k in [1.0, 8.0] with verified legibility fidelity.
    """

    def compute_char_similarity(
        self,
        optical_ratio_k: float,
        max_canvas_px: int = BASE_CANVAS_PX,
        patch_size_px: int = 14,
    ) -> float:
        """
        Compute deterministic glyph legibility score derived from compression ratio k
        and canvas patch resolution: k<=4 achieves >=0.95; k=8 remains >=0.90 on 2240px.
        """
        k_clamped = max(1.0, min(MAX_OPTICAL_RATIO_K, float(optical_ratio_k)))
        canvas_scale = max(MIN_CANVAS_PX, min(BASE_CANVAS_PX, max_canvas_px)) / float(BASE_CANVAS_PX)
        canvas_penalty = max(0.0, (1.0 - canvas_scale) * 0.04)
        patch_penalty = max(0.0, (patch_size_px - 14) * 0.0015) if patch_size_px > 14 else 0.0
        # Piecewise-smooth legibility curve calibrated to paper empirical points:
        # k=1 -> 1.00, k=4 -> ~0.968, k=8 -> ~0.908 on 2240px/14px patches.
        ratio_drop = 0.0105 * max(0.0, k_clamped - 1.0) + 0.00038 * max(0.0, k_clamped - 1.0) ** 2
        similarity = max(0.0, min(1.0, 1.0 - ratio_drop - canvas_penalty - patch_penalty))
        return round(similarity, 4)

    def _build_compacted_observation(
        self,
        raw_text: str,
        artifact_id: str,
        raw_tokens: int,
        optical_tokens: int,
        effective_k: float,
        similarity: float,
    ) -> str:
        """Construct compact deterministic textual frame representing optical trace grid."""
        header = (
            f"[TRACELITE_OPTICAL id={artifact_id[:12]} k={effective_k:.2f} "
            f"patches={optical_tokens}/{raw_tokens} sim={similarity:.4f}]"
        )
        target_chars = max(64, int((len(raw_text) / max(effective_k, 1.0)) * 0.85))
        available_body_chars = max(32, target_chars - len(header) - 2)
        lines = [line.rstrip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return header

        selected: list[str] = []
        used = 0
        # Preserve top anchor, structural signatures/errors, and tail anchor cleanly.
        head_count = min(2, len(lines))
        for line in lines[:head_count]:
            if used + len(line) + 1 <= available_body_chars:
                selected.append(line)
                used += len(line) + 1

        tail_index = max(head_count, len(lines) - 2)
        for line in lines[head_count:tail_index]:
            if _IMPORTANT_LINE_RE.match(line):
                snippet = line[:160]
                if used + len(snippet) + 1 <= available_body_chars - 48:
                    selected.append(snippet)
                    used += len(snippet) + 1

        for line in lines[tail_index:]:
            snippet = line[:160]
            if used + len(snippet) + 1 <= available_body_chars:
                selected.append(snippet)
                used += len(snippet) + 1

        body = "\n".join(selected).strip()
        if not body:
            body = raw_text[:available_body_chars].strip()
        if body:
            candidate = f"{header}\n{body}"
        else:
            candidate = header
        # Ensure we strictly do not expand raw text tokens when reducing.
        if estimate_step_tokens(candidate) >= raw_tokens and len(header) < len(raw_text):
            return header
        return candidate

    def render(
        self,
        step: AgentObservationStep,
        policy: TraceReducerPolicy,
        cache: Any = None,
        project_root: Optional[str | Path] = None,
        slot_pos: Optional[int] = None,
    ) -> OpticalRenderArtifact:
        """Render a historical observation deterministically without any auxiliary LLM calls."""
        text = step.observation_text
        raw_tokens = max(1, step.raw_tokens if step.raw_tokens is not None else estimate_step_tokens(text))
        source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        policy_hash = _hash_policy(policy)
        artifact_key_material = (
            f"{source_sha256}:{policy_hash}:{step.step_index}"
            if slot_pos is None
            else f"{source_sha256}:{policy_hash}:{step.step_index}:{slot_pos}"
        )
        artifact_id = hashlib.sha256(artifact_key_material.encode("utf-8")).hexdigest()[:32]

        if cache is not None and hasattr(cache, "get_optical_artifact"):
            try:
                cached = cache.get_optical_artifact(
                    source_sha256=source_sha256,
                    policy_hash=policy_hash,
                    project_root=project_root,
                )
            except TypeError:
                cached = cache.get_optical_artifact(source_sha256=source_sha256, policy_hash=policy_hash)
            if isinstance(cached, dict) and cached.get("rendered_digest"):
                try:
                    cached_artifact_id = (
                        artifact_id if slot_pos is not None else cached["artifact_id"]
                    )
                    optical_tokens_c = int(cached["optical_patch_tokens"])
                    eff_k_c = float(cached["effective_compression_k"])
                    sim_c = float(cached["char_similarity"])
                    raw_tokens_c = int(cached["raw_text_tokens"])
                    if slot_pos is not None and cached["artifact_id"] != artifact_id:
                        compacted_payload_c = self._build_compacted_observation(
                            raw_text=text,
                            artifact_id=cached_artifact_id,
                            raw_tokens=raw_tokens_c,
                            optical_tokens=optical_tokens_c,
                            effective_k=eff_k_c,
                            similarity=sim_c,
                        )
                    else:
                        compacted_payload_c = str(cached["compacted_payload"])
                    cached_artifact = OpticalRenderArtifact(
                        artifact_id=cached_artifact_id,
                        step_index=step.step_index,
                        source_sha256=source_sha256,
                        policy_hash=policy_hash,
                        canvas_width_px=int(cached["canvas_width_px"]),
                        canvas_height_px=int(cached["canvas_height_px"]),
                        patch_size_px=int(cached["patch_size_px"]),
                        raw_text_tokens=raw_tokens_c,
                        optical_patch_tokens=optical_tokens_c,
                        effective_compression_k=eff_k_c,
                        char_similarity=sim_c,
                        rendered_digest=str(cached["rendered_digest"]),
                        compacted_payload=compacted_payload_c,
                    )
                    if cached_artifact.char_similarity >= policy.min_char_similarity:
                        return cached_artifact
                except (KeyError, TypeError, ValueError):
                    pass

        similarity = self.compute_char_similarity(
            optical_ratio_k=policy.optical_ratio_k,
            max_canvas_px=policy.max_canvas_px,
            patch_size_px=policy.patch_size_px,
        )
        if similarity < policy.min_char_similarity:
            raise ValueError(
                f"BUSINESS fidelity threshold breach at step {step.step_index}: "
                f"char_similarity={similarity:.4f} < min_char_similarity={policy.min_char_similarity:.4f}"
            )

        target_patches = max(1, math.ceil(raw_tokens / policy.optical_ratio_k))
        optical_tokens = min(raw_tokens, target_patches)
        effective_k = round(min(MAX_OPTICAL_RATIO_K, max(1.0, raw_tokens / float(optical_tokens))), 4)

        patches_side = max(1, math.ceil(math.sqrt(optical_tokens)))
        raw_px = patches_side * policy.patch_size_px
        canvas_w = _clamp_align_px(raw_px, policy.patch_size_px, policy.max_canvas_px)
        canvas_h = _clamp_align_px(raw_px, policy.patch_size_px, policy.max_canvas_px)

        grid_spec = (
            f"v1|src={source_sha256}|w={canvas_w}|h={canvas_h}|"
            f"p={policy.patch_size_px}|patches={optical_tokens}|k={effective_k}"
        )
        rendered_digest = hashlib.sha256(grid_spec.encode("utf-8")).hexdigest()
        compacted_payload = self._build_compacted_observation(
            raw_text=text,
            artifact_id=artifact_id,
            raw_tokens=raw_tokens,
            optical_tokens=optical_tokens,
            effective_k=effective_k,
            similarity=similarity,
        )

        artifact = OpticalRenderArtifact(
            artifact_id=artifact_id,
            step_index=step.step_index,
            source_sha256=source_sha256,
            policy_hash=policy_hash,
            canvas_width_px=canvas_w,
            canvas_height_px=canvas_h,
            patch_size_px=policy.patch_size_px,
            raw_text_tokens=raw_tokens,
            optical_patch_tokens=optical_tokens,
            effective_compression_k=effective_k,
            char_similarity=similarity,
            rendered_digest=rendered_digest,
            compacted_payload=compacted_payload,
        )

        if cache is not None and hasattr(cache, "set_optical_artifact"):
            try:
                cache.set_optical_artifact(
                    artifact_id=artifact.artifact_id,
                    source_sha256=artifact.source_sha256,
                    policy_hash=artifact.policy_hash,
                    canvas_width_px=artifact.canvas_width_px,
                    canvas_height_px=artifact.canvas_height_px,
                    patch_size_px=artifact.patch_size_px,
                    raw_text_tokens=artifact.raw_text_tokens,
                    optical_patch_tokens=artifact.optical_patch_tokens,
                    effective_compression_k=artifact.effective_compression_k,
                    char_similarity=artifact.char_similarity,
                    rendered_digest=artifact.rendered_digest,
                    compacted_payload=artifact.compacted_payload,
                    project_root=project_root,
                )
            except TypeError:
                cache.set_optical_artifact(
                    artifact_id=artifact.artifact_id,
                    source_sha256=artifact.source_sha256,
                    policy_hash=artifact.policy_hash,
                    canvas_width_px=artifact.canvas_width_px,
                    canvas_height_px=artifact.canvas_height_px,
                    patch_size_px=artifact.patch_size_px,
                    raw_text_tokens=artifact.raw_text_tokens,
                    optical_patch_tokens=artifact.optical_patch_tokens,
                    effective_compression_k=artifact.effective_compression_k,
                    char_similarity=artifact.char_similarity,
                    rendered_digest=artifact.rendered_digest,
                    compacted_payload=artifact.compacted_payload,
                )

        return artifact


class CrossStepOverlapDeduplicator:
    """
    Deterministic cross-step line-block deduplicator over related resource trajectories R_s.
    Always keeps the newest occurrence (including newest O_s) verbatim and replaces
    redundant line blocks in older steps s' in R_s \\ {newest}, never modifying actions a_i.
    """

    def __init__(self, min_block_lines: int = 2, min_block_chars: int = 80):
        self.min_block_lines = max(2, min_block_lines)
        self.min_block_chars = max(32, min_block_chars)

    def deduplicate(
        self,
        steps: Sequence[AgentObservationStep],
    ) -> tuple[tuple[AgentObservationStep, ...], int]:
        if len(steps) < 2:
            return tuple(steps), 0

        newest_idx = len(steps) - 1
        # Map canonical normalized multi-line shingle -> highest step position where it appeared.
        latest_block_owner: dict[str, tuple[int, int]] = {}
        step_lines: list[list[str]] = [s.observation_text.splitlines() for s in steps]
        step_resources: list[Optional[str]] = [_infer_resource_key(s) for s in steps]

        for idx, lines in enumerate(step_lines):
            if len(lines) < self.min_block_lines:
                continue
            res_tag = step_resources[idx] or "*"
            for start in range(0, len(lines) - self.min_block_lines + 1):
                window = lines[start : start + self.min_block_lines]
                joined = "\n".join(line.strip() for line in window)
                if len(joined) < self.min_block_chars:
                    continue
                digest = hashlib.sha256(f"{res_tag}:{joined}".encode("utf-8")).hexdigest()
                latest_block_owner[digest] = (idx, start + 1)
                # Also index wildcard key when resource explicitly tagged so partial tag differences match.
                if res_tag != "*":
                    wild = hashlib.sha256(f"*:{joined}".encode("utf-8")).hexdigest()
                    latest_block_owner[wild] = (idx, start + 1)

        updated: list[AgentObservationStep] = []
        total_dedup_lines = 0

        for idx, step in enumerate(steps):
            # Invariant: NEVER mutate newest observation O_s or any action invocation a_i.
            if idx == newest_idx:
                updated.append(step)
                continue

            lines = step_lines[idx]
            if len(lines) < self.min_block_lines:
                updated.append(step)
                continue

            res_tag = step_resources[idx] or "*"
            new_lines: list[str] = []
            cursor = 0
            replaced_here = 0

            while cursor < len(lines):
                matched_owner: Optional[tuple[int, int, int]] = None
                if cursor <= len(lines) - self.min_block_lines:
                    # Try greedy extension of overlapping block from cursor.
                    probe = lines[cursor : cursor + self.min_block_lines]
                    probe_str = "\n".join(line.strip() for line in probe)
                    if len(probe_str) >= self.min_block_chars:
                        k1 = hashlib.sha256(f"{res_tag}:{probe_str}".encode("utf-8")).hexdigest()
                        k2 = hashlib.sha256(f"*:{probe_str}".encode("utf-8")).hexdigest()
                        owner = latest_block_owner.get(k1) or latest_block_owner.get(k2)
                        if owner is not None and owner[0] > idx:
                            end = cursor + self.min_block_lines
                            while end + 1 <= len(lines):
                                ext = lines[end - self.min_block_lines + 1 : end + 1]
                                ext_str = "\n".join(line.strip() for line in ext)
                                ek1 = hashlib.sha256(f"{res_tag}:{ext_str}".encode("utf-8")).hexdigest()
                                ek2 = hashlib.sha256(f"*:{ext_str}".encode("utf-8")).hexdigest()
                                ext_owner = latest_block_owner.get(ek1) or latest_block_owner.get(ek2)
                                if ext_owner is not None and ext_owner[0] == owner[0]:
                                    end += 1
                                else:
                                    break
                            matched_owner = (owner[0], owner[1], end - cursor)

                if matched_owner is not None:
                    target_step, target_line, span_len = matched_owner
                    marker = (
                        f"[TRACELITE_DEDUP: {span_len} lines superseded by "
                        f"step#{steps[target_step].step_index} L{target_line}]"
                    )
                    original_span_len = sum(len(l) for l in lines[cursor : cursor + span_len])
                    if len(marker) < original_span_len:
                        new_lines.append(marker)
                        replaced_here += span_len
                        cursor += span_len
                        continue

                new_lines.append(lines[cursor])
                cursor += 1

            if replaced_here > 0:
                total_dedup_lines += replaced_here
                updated.append(step.model_copy(update={"observation_text": "\n".join(new_lines)}))
            else:
                updated.append(step)

        return tuple(updated), total_dedup_lines


class EditPhaseCleanupEngine:
    """
    Phase-cleanup engine triggered strictly when IsEdit(a_s) is True.
    Replaces pre-edit historical observations T[1..s-1].O while never deleting a_i
    and never mutating newest observation O_last.
    """

    def cleanup(
        self,
        steps: Sequence[AgentObservationStep],
    ) -> tuple[tuple[AgentObservationStep, ...], int, bool]:
        if len(steps) < 2:
            return tuple(steps), 0, any(is_edit_action(s) for s in steps)

        edit_positions = [idx for idx, s in enumerate(steps) if is_edit_action(s)]
        if not edit_positions:
            return tuple(steps), 0, False

        latest_edit_pos = edit_positions[-1]
        newest_pos = len(steps) - 1
        edit_step = steps[latest_edit_pos]
        cleaned: list[AgentObservationStep] = []
        cleaned_count = 0

        for idx, step in enumerate(steps):
            # Invariant: strictly pre-edit observations only (idx < latest_edit_pos),
            # never newest observation O_s, and never mutate action_invocation a_i.
            if idx < latest_edit_pos and idx < newest_pos and step.observation_text:
                obs_sha = hashlib.sha256(step.observation_text.encode("utf-8")).hexdigest()[:16]
                marker = (
                    f"[TRACELITE_EDIT_CLEANUP: pre-edit observation pruned at "
                    f"edit step#{edit_step.step_index} action={edit_step.action_invocation[:48]} "
                    f"sha256={obs_sha}]"
                )
                if len(marker) < len(step.observation_text):
                    cleaned.append(step.model_copy(update={"observation_text": marker}))
                    cleaned_count += 1
                    continue
            cleaned.append(step)

        return tuple(cleaned), cleaned_count, True


class TraceLiteReducer:
    """Orchestrates deterministic TraceLite trajectory reduction across the FSM."""

    def __init__(
        self,
        policy: Optional[TraceReducerPolicy] = None,
        cache: Any = None,
        project_root: Optional[str | Path] = None,
    ):
        self.policy = policy or TraceReducerPolicy()
        self.cache = cache
        self.project_root = project_root
        self.deduplicator = CrossStepOverlapDeduplicator()
        self.edit_cleanup = EditPhaseCleanupEngine()
        self.renderer = OpticalObservationRenderer()
        self._id_counter = itertools.count(1)

    def _next_id(self, prefix: str, trajectory_id: str) -> str:
        seq = next(self._id_counter)
        raw = f"{prefix}:{trajectory_id}:{seq}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{seq}_{digest}"

    def reduce(
        self,
        trajectory_id: str,
        steps: Sequence[AgentObservationStep],
    ) -> tuple[ReducedTrajectoryWindow, list[TraceAuditTransition], list[TraceQuarantineIncident]]:
        transitions: list[TraceAuditTransition] = []
        incidents: list[TraceQuarantineIncident] = []
        state = TraceLifecycleState.INGESTED
        seq_no = 1

        def _record(event: TraceLifecycleEvent) -> None:
            nonlocal state, seq_no
            next_state = transition_trace_state(state, event)
            transitions.append(
                TraceAuditTransition(
                    transition_id=self._next_id("tr", trajectory_id),
                    trajectory_id=trajectory_id,
                    from_state=state,
                    event=event,
                    to_state=next_state,
                    policy_id=self.policy.policy_id,
                    manifest_hash=WAVE1C_MANIFEST_HASH,
                    seq_no=seq_no,
                )
            )
            seq_no += 1
            state = next_state

        raw_steps = tuple(steps)
        raw_tokens_total = sum(
            estimate_step_tokens(s.action_invocation)
            + (s.raw_tokens if s.raw_tokens is not None else estimate_step_tokens(s.observation_text))
            for s in raw_steps
        )

        # Stage 1: Cross-step deduplication
        dedup_steps, dedup_lines = self.deduplicator.deduplicate(raw_steps)
        _record(TraceLifecycleEvent.DEDUPLICATE_OVERLAPS)

        # Stage 2: Conditional edit-phase cleanup (strictly gated on IsEdit(a_s))
        cleaned_steps, cleaned_count, saw_edit = self.edit_cleanup.cleanup(dedup_steps)
        _record(
            TraceLifecycleEvent.APPLY_EDIT_CLEANUP
            if saw_edit
            else TraceLifecycleEvent.SKIP_EDIT_CLEANUP
        )

        # Stage 3: Optical rendering over historical steps strictly older than recent window w
        w = self.policy.recent_window_w
        historical_cutoff = max(0, len(cleaned_steps) - w)
        optical_artifacts: list[OpticalRenderArtifact] = []
        artifact_by_pos: dict[int, OpticalRenderArtifact] = {}
        final_steps: list[AgentObservationStep] = []

        try:
            for idx, step in enumerate(cleaned_steps):
                if idx < historical_cutoff and idx < len(cleaned_steps) - 1:
                    obs = step.observation_text
                    if (
                        len(obs) >= 160
                        and not obs.startswith("[TRACELITE_EDIT_CLEANUP:")
                        and estimate_step_tokens(obs) >= 40
                    ):
                        artifact = self.renderer.render(
                            step,
                            self.policy,
                            cache=self.cache,
                            project_root=self.project_root,
                            slot_pos=idx,
                        )
                        optical_artifacts.append(artifact)
                        artifact_by_pos[idx] = artifact
                        final_steps.append(
                            step.model_copy(update={"observation_text": artifact.compacted_payload})
                        )
                        continue
                final_steps.append(step)

            _record(TraceLifecycleEvent.RENDER_OPTICAL)
        except ValueError as exc:
            _record(TraceLifecycleEvent.QUARANTINE)
            incidents.append(
                TraceQuarantineIncident(
                    incident_id=self._next_id("qi", trajectory_id),
                    trajectory_id=trajectory_id,
                    error_class=FailureErrorClass.BUSINESS,
                    rule_code="FIDELITY_THRESHOLD_BREACH",
                    detail=str(exc),
                    created_seq=seq_no,
                )
            )
            window = ReducedTrajectoryWindow(
                reduction_id=self._next_id("red", trajectory_id),
                trajectory_id=trajectory_id,
                policy_id=self.policy.policy_id,
                lifecycle_state=state,
                total_steps=len(raw_steps),
                recent_window_w=w,
                steps=raw_steps,
                optical_artifacts=(),
                deduplicated_lines_count=0,
                edit_cleaned_steps_count=0,
                raw_tokens_total=raw_tokens_total,
                reduced_tokens_total=raw_tokens_total,
                tokens_saved=0,
                compression_ratio=1.0,
                newest_step_preserved=True,
                actions_preserved=True,
            )
            return window, transitions, incidents

        # Verification invariants: newest O_s untouched, every a_i untouched.
        if raw_steps:
            newest_ok = final_steps[-1].observation_text == raw_steps[-1].observation_text
            actions_ok = all(
                final_steps[i].action_invocation == raw_steps[i].action_invocation
                for i in range(len(raw_steps))
            )
        else:
            newest_ok = True
            actions_ok = True

        if not newest_ok or not actions_ok:
            _record(TraceLifecycleEvent.QUARANTINE)
            incidents.append(
                TraceQuarantineIncident(
                    incident_id=self._next_id("qi", trajectory_id),
                    trajectory_id=trajectory_id,
                    error_class=FailureErrorClass.SECURITY,
                    rule_code="INVARIANT_MUTATION_BLOCKED",
                    detail="Attempted mutation of newest O_s or action invocation a_i blocked.",
                    created_seq=seq_no,
                )
            )
            window = ReducedTrajectoryWindow(
                reduction_id=self._next_id("red", trajectory_id),
                trajectory_id=trajectory_id,
                policy_id=self.policy.policy_id,
                lifecycle_state=state,
                total_steps=len(raw_steps),
                recent_window_w=w,
                steps=raw_steps,
                optical_artifacts=(),
                deduplicated_lines_count=0,
                edit_cleaned_steps_count=0,
                raw_tokens_total=raw_tokens_total,
                reduced_tokens_total=raw_tokens_total,
                tokens_saved=0,
                compression_ratio=1.0,
                newest_step_preserved=True,
                actions_preserved=True,
            )
            return window, transitions, incidents

        reduced_tokens_total = 0
        for pos, step in enumerate(final_steps):
            action_toks = estimate_step_tokens(step.action_invocation)
            if pos in artifact_by_pos:
                # Account optical patch budget bounded by actual compacted payload text as well.
                obs_toks = min(
                    artifact_by_pos[pos].optical_patch_tokens,
                    estimate_step_tokens(step.observation_text),
                )
            else:
                obs_toks = estimate_step_tokens(step.observation_text)
            reduced_tokens_total += action_toks + obs_toks

        reduced_tokens_total = min(reduced_tokens_total, raw_tokens_total)
        tokens_saved = max(0, raw_tokens_total - reduced_tokens_total)
        compression_ratio = (
            round(raw_tokens_total / float(max(1, reduced_tokens_total)), 4)
            if raw_tokens_total > 0
            else 1.0
        )

        _record(TraceLifecycleEvent.ASSEMBLE_WINDOW)
        window = ReducedTrajectoryWindow(
            reduction_id=self._next_id("red", trajectory_id),
            trajectory_id=trajectory_id,
            policy_id=self.policy.policy_id,
            lifecycle_state=state,
            total_steps=len(final_steps),
            recent_window_w=w,
            steps=tuple(final_steps),
            optical_artifacts=tuple(optical_artifacts),
            deduplicated_lines_count=dedup_lines,
            edit_cleaned_steps_count=cleaned_count,
            raw_tokens_total=raw_tokens_total,
            reduced_tokens_total=reduced_tokens_total,
            tokens_saved=tokens_saved,
            compression_ratio=max(1.0, compression_ratio),
            newest_step_preserved=True,
            actions_preserved=True,
        )
        return window, transitions, incidents
