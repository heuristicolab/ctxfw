# manifest_hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546
"""
ctxfw.mcp_guard.rate_limiter — Deterministic MCP Burst Rate Limiter
===================================================================
Zero-drift integer scaled millitoken token-bucket rate limiter with
injectable millisecond Clock, fail-closed clock-regression clamping,
bounded LRU bucket memory, and Zero-Knowledge SHA-256 client isolation.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
import hashlib
import re
import threading
import time
from typing import Callable, Optional

from ctxfw.mcp_guard.contracts import (
    CLIENT_KEY_HASH_PATTERN,
    ERR_RATE_LIMIT_EXCEEDED,
    ErrorClass,
    MAX_RETRY_AFTER_MS,
    McpRateLimitPolicyDTO,
    RATE_LIMIT_SCALE,
    RateLimitDecisionDTO,
    RateLimitEvent,
    RateLimitState,
    TOOL_NAME_PATTERN,
)

Clock = Callable[[], int]
_CLIENT_KEY_HASH_RE = re.compile(CLIENT_KEY_HASH_PATTERN)
_TOOL_NAME_RE = re.compile(TOOL_NAME_PATTERN)
_MAX_CLOCK_MS: int = 9_223_372_036_854_775_807

_RATE_LIMIT_TRANSITIONS: dict[tuple[RateLimitState, RateLimitEvent], RateLimitState] = {
    (RateLimitState.DISABLED, RateLimitEvent.EVALUATE_CALL): RateLimitState.DISABLED,
    (RateLimitState.READY, RateLimitEvent.INVALID_INPUT_OR_CLOCK): RateLimitState.INPUT_REJECTED,
    (RateLimitState.READY, RateLimitEvent.TOKENS_SUFFICIENT): RateLimitState.ALLOWED,
    (RateLimitState.READY, RateLimitEvent.TOKENS_EXHAUSTED): RateLimitState.THROTTLED,
    (RateLimitState.READY, RateLimitEvent.CLOCK_REGRESSION_TOKENS_SUFFICIENT): RateLimitState.ALLOWED,
    (RateLimitState.READY, RateLimitEvent.CLOCK_REGRESSION_TOKENS_EXHAUSTED): RateLimitState.THROTTLED,
    (RateLimitState.ALLOWED, RateLimitEvent.RESET_CYCLE): RateLimitState.READY,
    (RateLimitState.THROTTLED, RateLimitEvent.RESET_CYCLE): RateLimitState.READY,
}
_ALLOW_EVENTS = (
    RateLimitEvent.TOKENS_SUFFICIENT,
    RateLimitEvent.CLOCK_REGRESSION_TOKENS_SUFFICIENT,
)
_DENY_EVENTS = (
    RateLimitEvent.TOKENS_EXHAUSTED,
    RateLimitEvent.CLOCK_REGRESSION_TOKENS_EXHAUSTED,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def default_monotonic_ms_clock() -> int:
    """Return non-negative process monotonic milliseconds using integer division."""
    return time.monotonic_ns() // 1_000_000


def derive_client_key_hash(raw_client_key: str, *, domain: str = "ctxfw-mcp-client-v1") -> str:
    """Derive a Zero-Knowledge 64-hex SHA-256 client identifier without persisting PII."""
    _require(isinstance(raw_client_key, str), "client_key must be a non-empty string")
    _require(isinstance(domain, str), "domain must be a non-empty string")
    clean_domain = domain.strip()
    cleaned = raw_client_key.strip()
    _require(bool(clean_domain), "domain must not be empty")
    _require(1 <= len(cleaned) <= 512, "raw_client_key length must be within 1..512 characters")
    if _CLIENT_KEY_HASH_RE.fullmatch(cleaned):
        return cleaned
    return hashlib.sha256(f"{clean_domain}:{cleaned}".encode("utf-8")).hexdigest()


def transition_rate_limit_state(current: RateLimitState, event: RateLimitEvent) -> RateLimitState:
    """Execute deterministic FSM transition delta(S, E) or fail-closed on invalid edges."""
    next_state = _RATE_LIMIT_TRANSITIONS.get((current, event))
    _require(
        next_state is not None,
        f"Illegal rate-limit FSM transition: delta({current.value}, {event.value})",
    )
    assert next_state is not None
    return next_state


def _format_tokens_q4(tokens_scaled: int) -> str:
    """Format scaled integer millitokens cleanly to 4 decimal places without float drift."""
    quantized = (Decimal(tokens_scaled) / Decimal(RATE_LIMIT_SCALE)).quantize(
        Decimal("0.0001"), rounding=ROUND_DOWN
    )
    return f"{quantized:.4f}"


@dataclass(slots=True)
class _BucketState:
    tokens_scaled: int
    last_refill_ms: int


class McpBurstRateLimiter:
    """Thread-safe deterministic token-bucket rate limiter with LRU client bound."""

    def __init__(
        self,
        policy: Optional[McpRateLimitPolicyDTO] = None,
        *,
        clock: Optional[Clock] = None,
    ) -> None:
        if policy is not None:
            _require(
                isinstance(policy, McpRateLimitPolicyDTO),
                "policy must be an McpRateLimitPolicyDTO instance",
            )
        self._policy: McpRateLimitPolicyDTO = {
            False: McpRateLimitPolicyDTO(),
            True: policy,
        }[policy is not None]
        self._clock: Clock = {
            False: default_monotonic_ms_clock,
            True: clock,
        }[clock is not None]
        self._lock = threading.RLock()
        self._buckets: OrderedDict[str, _BucketState] = OrderedDict()

    @property
    def policy(self) -> McpRateLimitPolicyDTO:
        """Return immutable active rate-limit policy."""
        return self._policy

    @property
    def tracked_client_count(self) -> int:
        """Return current count of LRU-tracked client buckets in RAM."""
        with self._lock:
            return len(self._buckets)

    def _read_clock_ms(self) -> int:
        """Read and strictly validate integer millisecond timestamp from injected clock."""
        raw_val = self._clock()
        _require(type(raw_val) is int, f"Clock must return strict int, got {raw_val!r}")
        _require(0 <= raw_val <= _MAX_CLOCK_MS, f"Clock out of bounds [0, {_MAX_CLOCK_MS}]")
        return raw_val

    def _get_or_create_bucket(
        self,
        client_key_hash: str,
        capacity_scaled: int,
        now_ms: int,
    ) -> _BucketState:
        bucket = self._buckets.get(client_key_hash)
        if bucket is None:
            if len(self._buckets) >= self._policy.max_tracked_clients:
                self._buckets.popitem(last=False)
            bucket = _BucketState(tokens_scaled=capacity_scaled, last_refill_ms=now_ms)
            self._buckets[client_key_hash] = bucket
        self._buckets.move_to_end(client_key_hash)
        return bucket

    def evaluate(
        self,
        client_key_hash: str,
        tool_name: str,
        *,
        cost: Optional[int] = None,
    ) -> RateLimitDecisionDTO:
        """Evaluate one MCP tool call against client's deterministic token bucket."""
        _require(isinstance(client_key_hash, str), "client_key_hash must be a string")
        _require(
            bool(_CLIENT_KEY_HASH_RE.fullmatch(client_key_hash)),
            "client_key_hash must be a canonical 64-hex lowercase SHA-256 digest",
        )
        _require(isinstance(tool_name, str), "tool_name must be a string")
        _require(bool(_TOOL_NAME_RE.fullmatch(tool_name)), "tool_name must match ^[a-zA-Z0-9_.:-]{1,128}$")

        now_ms = self._read_clock_ms()
        capacity_scaled = self._policy.burst_capacity * RATE_LIMIT_SCALE
        if not self._policy.enabled:
            return RateLimitDecisionDTO(
                allowed=True,
                state=transition_rate_limit_state(RateLimitState.DISABLED, RateLimitEvent.EVALUATE_CALL),
                client_key_hash=client_key_hash,
                tool_name=tool_name,
                remaining_tokens_q4=_format_tokens_q4(capacity_scaled),
                retry_after_ms=0,
                reason="MCP burst rate limiter disabled (opt-in default)",
                evaluated_at_ms=now_ms,
            )

        call_cost = {False: cost, True: self._policy.cost_per_call}[cost is None]
        _require(type(call_cost) is int, "call cost must be strict int")
        _require(
            1 <= call_cost <= self._policy.burst_capacity,
            f"call cost must be in [1, {self._policy.burst_capacity}]",
        )

        with self._lock:
            bucket = self._get_or_create_bucket(client_key_hash, capacity_scaled, now_ms)
            clock_regressed = now_ms < bucket.last_refill_ms
            elapsed_ms = max(0, now_ms - bucket.last_refill_ms)
            bucket.last_refill_ms = max(bucket.last_refill_ms, now_ms)

            refilled = min(
                capacity_scaled,
                bucket.tokens_scaled + elapsed_ms * self._policy.requests_per_minute,
            )
            cost_scaled = call_cost * RATE_LIMIT_SCALE
            if refilled >= cost_scaled:
                bucket.tokens_scaled = refilled - cost_scaled
                return RateLimitDecisionDTO(
                    allowed=True,
                    state=transition_rate_limit_state(RateLimitState.READY, _ALLOW_EVENTS[clock_regressed]),
                    client_key_hash=client_key_hash,
                    tool_name=tool_name,
                    remaining_tokens_q4=_format_tokens_q4(bucket.tokens_scaled),
                    retry_after_ms=0,
                    clock_regression_clamped=clock_regressed,
                    reason="Allowed within MCP burst token budget",
                    evaluated_at_ms=now_ms,
                )

            bucket.tokens_scaled = refilled
            deficit = cost_scaled - refilled
            rpm = self._policy.requests_per_minute
            retry_after_ms = min(MAX_RETRY_AFTER_MS, max(1, (deficit + rpm - 1) // rpm))
            return RateLimitDecisionDTO(
                allowed=False,
                state=transition_rate_limit_state(RateLimitState.READY, _DENY_EVENTS[clock_regressed]),
                client_key_hash=client_key_hash,
                tool_name=tool_name,
                remaining_tokens_q4=_format_tokens_q4(bucket.tokens_scaled),
                retry_after_ms=retry_after_ms,
                error_class=ErrorClass.BUSINESS,
                error_code=ERR_RATE_LIMIT_EXCEEDED,
                clock_regression_clamped=clock_regressed,
                reason=f"MCP burst limit exceeded; retry after {retry_after_ms} ms",
                evaluated_at_ms=now_ms,
            )


__all__ = [
    "Clock",
    "McpBurstRateLimiter",
    "default_monotonic_ms_clock",
    "derive_client_key_hash",
    "transition_rate_limit_state",
]
