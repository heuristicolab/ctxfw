# manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
"""
SARA Action Induction Parser :: Deterministic Directive Extraction & Risk Scoring
=================================================================================
manifest_hash (M3-P2): 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
manifest_hash (M3-P3): 8d94151e921e2f8eaacb440cb3c1b0d4e0ff6ac80fa217e5830de1c1edec1b13
manifest_hash_wave1a: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
Scans untrusted tool observations for imperative shell commands, file path access,
role-override injections, and hidden escape sequences. Computes a deterministic
risk_score in [0.0, 1.0] (strictly rejecting NaN/Inf) under default-deny policy rules.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import posixpath
import re
import urllib.parse
from typing import Optional, Sequence, Tuple, Union

from ctxfw.sara.contracts import (
    MAX_DIRECTIVE_TEXT_CHARS,
    MAX_DIRECTIVES_PER_OBSERVATION,
    MAX_RAW_OUTPUT_CHARS,
    AuthorizationPolicyRuleDTO,
    DirectiveKind,
    InductionDirectiveDTO,
    RawToolObservationDTO,
)
from ctxfw.sara.lexical import LexicalSanitizer

# Architectural aliases
UntrustedObservationDTO = RawToolObservationDTO
AuthorizedPolicyDTO = AuthorizationPolicyRuleDTO
MAX_DIRECTIVES_PER_OBS: int = MAX_DIRECTIVES_PER_OBSERVATION

__all__ = [
    "AuthorizedPolicyDTO",
    "InductionParser",
    "MAX_DIRECTIVES_PER_OBS",
    "MAX_DIRECTIVES_PER_OBSERVATION",
    "UntrustedObservationDTO",
    "_DESTRUCTIVE_RE",
    "_HIDDEN_RE",
    "_IMPERATIVE_RE",
    "_PATH_RE",
    "_ROLE_RE",
]

# 1. Hidden zero-width / bidirectional overrides / ANSI CSI, OSC & 2-byte escape sequences
_HIDDEN_RE = re.compile(
    r"[\u200b-\u200f\u2060\ufeff\u202a-\u202e\u2066-\u2069]+"
    r"|\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\)|\([0-9A-Za-z]|[@-Z\\-_])"
)

# High-risk hidden escapes: Trojan-Source Bidi overrides and OSC / non-CSI escape sequences
_CRITICAL_HIDDEN_RE = re.compile(
    r"[\u202a-\u202e\u2066-\u2069]"
    r"|\\u202[a-e]|\\u206[6-9]"
    r"|\x1b(?!\[)"
    r"|\\x1b(?!\[)",
    re.IGNORECASE,
)

# 2. Role override & prompt context escape markers
_ROLE_RE = re.compile(
    r"(?:</?system>|<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|</?tool_call>"
    r"|\b(?:System|Assistant|Developer):"
    r"|\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b)",
    re.IGNORECASE,
)

_ROLE_CLOSING_RE = re.compile(
    r"^(?:</system>|\[/INST\]|</tool_call>|<\|im_end\|>)$",
    re.IGNORECASE,
)

_ROLE_IGNORE_RE = re.compile(
    r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b",
    re.IGNORECASE,
)

_ROLE_OPENING_RE = re.compile(
    r"(?:<system>|<\|im_start\|>|<\|system\|>|\[INST\]|<tool_call>|\b(?:System|Assistant|Developer):)",
    re.IGNORECASE,
)

# 3. High-risk destructive shell commands, pipe-to-shell sinks, subshells & command chaining
_DESTRUCTIVE_RE = re.compile(
    r"(?:\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*|--(?:recursive|force))(?:\s+[^\n;`|]+)?"
    r"|\b(?:curl|wget)\b[^\n|;`]*\|\s*(?:sudo\s+)?(?:/usr/bin/|/bin/)?(?:ba|z|da|k)?sh\b"
    r"|\|\s*(?:sudo\s+)?(?:/usr/bin/|/bin/)?(?:ba|z|da|k)?sh\b"
    r"|\bsudo\s+[^\n;`|]+"
    r"|\bmkfs(?:\.[a-z0-9]+)?\b[^\n;`|]*"
    r"|\bdd\s+if=[^\n;`|]+"
    r"|\bchmod\s+(?:777|[ugo]*\+s)\b[^\n;`|]*"
    r"|\bgit\s+(?:push\b[^\n;`|]*--force|push\s+-f|reset\s+--hard)\b"
    r"|:\(\)\{\s*:\|:&\s*\};:"
    r"|\b(?:nc|ncat)\s+[^\n;`|]*-e\s+/bin/(?:ba)?sh\b"
    r"|\$\(\s*(?:/[a-zA-Z0-9_./-]+/)?(?:ls|cat|grep|find|git|echo|head|tail|wc|pwd|env|export|python3?|pip|npm|node|docker|kubectl|curl|wget|bash|sh|chmod|chown|kill|cp|mv|rm|sudo|whoami|id|uname|ps|netstat|tar|ssh|scp|nc|ncat|socat|awk|perl|ruby|php)\b[^)\n]*\)"
    r"|(?:;|\|\||&&)\s*(?:/[a-zA-Z0-9_./-]+/)?(?:ls|pwd|whoami|id|uname|env|printenv|bash|sh|cat|curl|wget|rm|sudo|nc|ncat)\b[^\n;`|&]*)",
    re.IGNORECASE,
)

# 4. Imperative / general shell command invocations (including subshell $(...) and non-flag rm)
_IMPERATIVE_RE = re.compile(
    r"(?:`((?:ls|cat|grep|find|git|echo|head|tail|wc|pwd|env|export|python3?|pip|npm|node|docker|kubectl|curl|wget|bash|sh|chmod|chown|kill|cp|mv|rm|sudo|whoami|id|uname|ps|netstat|tar|ssh|scp|nc|ncat|socat)\b[^`\n]*)`"
    r"|\$\(\s*((?:/[a-zA-Z0-9_./-]+/)?(?:ls|cat|grep|find|git|echo|head|tail|wc|pwd|env|export|python3?|pip|npm|node|docker|kubectl|curl|wget|bash|sh|chmod|chown|kill|cp|mv|rm|sudo|whoami|id|uname|ps|netstat|tar|ssh|scp|nc|ncat|socat|awk|perl|ruby|php)\b[^)\n]*)\)"
    r"|\b(?:please\s+)?(?:run|execute|invoke|exec)\s*:\s*(?!(?:bool|int|float|str|bytes|list|dict|set|tuple|object|type|none|any|optional|union|sequence|mapping|callable|iterable|iterator|final|literal|classvar|path)\b)(?![a-z_][a-z0-9_]*\s*(?:[=,)\[]|->))([a-z/][a-z0-9_./-]*(?:\s+[^\n;`]*)?)"
    r"|(?<!\bimport\s)(?<!\bfrom\s)(?<!\bdef\s)(?<!\bclass\s)\b((?:ls|grep|git|chmod|chown|kubectl|docker|wget|curl|pip|npm|whoami|uname|netstat|printenv|ssh|scp|nc|ncat|socat|rm)\s+(?![=:(\[,]|(?:import|in|is|and|or|not|as)\b)[^\n;`|&]+)"
    r"|\b((?:cat|find|echo|head|tail|kill|cp|mv|rm|bash|sh|python3?)\s+(?:-[a-zA-Z0-9-]+|/[a-zA-Z0-9_./-]+|\.\.?/[a-zA-Z0-9_./-]+|\.[a-zA-Z0-9_.-]+|['\"][^\n'\"]+['\"])[^\n;`|&]*)"
    r"|(?:^|[;|]|&&|\|\|)\s*((?:ls|pwd|whoami|id|uname|env|printenv|bash|sh)\b(?:\s+(?![=:(.,\[])[^\n;`|&]*)?(?=\s*(?:$|[;|`&]))))",
    re.IGNORECASE | re.MULTILINE,
)

# 5. File path access & path traversal patterns (excluding URLs and XML/role closing tags)
_PATH_RE = re.compile(
    r"(?:(?<![a-zA-Z0-9_./-])(?:\.\./)+[a-zA-Z0-9_./-]*"
    r"|(?<![<\[a-zA-Z0-9_:/.-])(?:/[a-zA-Z0-9_.-]+)+(?:/\.\.)+(?:/[a-zA-Z0-9_./-]*)?"
    r"|(?<![<\[a-zA-Z0-9_:/.-])/(?:etc|var|tmp|usr|bin|sbin|opt|root|home|proc|sys|dev|srv|mnt|media|run|boot|lib|app|workspace|data|private)(?:/[a-zA-Z0-9_.-]+)+"
    r"|(?<![<\[a-zA-Z0-9_:/.-])/(?:etc|var|tmp|usr|bin|sbin|opt|root|home|proc|sys|dev)\b"
    r"|(?<![<\[a-zA-Z0-9_:/.-])/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./-]+"
    r"|(?<![a-zA-Z0-9_./-])(?:\.env(?:\.[a-zA-Z0-9_-]+)?|\.ssh/[a-zA-Z0-9_.-]+|\.aws/[a-zA-Z0-9_.-]+))",
    re.IGNORECASE,
)

_CHAINING_OPERATORS = (";", "|", "&&", "||", "$(", "`", ">", "<")
_LINE_CONTINUATION_RE = re.compile(r"\\\r?\n")
_TRAILING_CHAIN_RE = re.compile(r"^\s*(?:;|\||&&|\|\|)")
_LEADING_CHAIN_RE = re.compile(r"(?:;|\||&&|\|\|)\s*$")


def _clamp_span(start: int, end: int) -> tuple[int, int]:
    """Clamp directive character offsets to [0, MAX_RAW_OUTPUT_CHARS] with start <= end."""
    s = min(max(0, start), MAX_RAW_OUTPUT_CHARS)
    e = min(max(s, end), MAX_RAW_OUTPUT_CHARS)
    return s, e


def _collapse_line_continuations(text: str) -> str:
    """Replace backslash-newline continuations with same-length spaces to preserve offsets."""
    return _LINE_CONTINUATION_RE.sub(lambda m: " " * len(m.group(0)), text)


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """Return True if [start, end) overlaps with any existing span."""
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


def _normalize_command_text(raw_match: str) -> str:
    """Extract canonical command text from an imperative match."""
    text = raw_match.strip()
    if text.startswith("`") and text.endswith("`") and len(text) >= 2:
        text = text[1:-1].strip()
    prefix_m = re.match(r"^(?:please\s+)?(?:run|execute|invoke|exec)\s*:\s*", text, re.IGNORECASE)
    if prefix_m:
        text = text[prefix_m.end() :].strip()
    return text


_SARA_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:(?:[/\\]|$)")
_SARA_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]{1,20}:")


def _unquote_path_safe(raw_text: str, max_rounds: int = 3) -> Optional[str]:
    """Bounded percent-decoding; returns None if encoding fails to stabilize."""
    current = raw_text
    for _ in range(max_rounds):
        nxt = urllib.parse.unquote(current)
        if nxt == current:
            return current
        current = nxt
    if urllib.parse.unquote(current) != current:
        return None
    return current


def _is_path_allowlisted(path_text: str, allowed_paths: Tuple[str, ...]) -> bool:
    """Check if a file path is component-confined within allowlist (blocking URI schemes, traversal, sibling prefix & symlink escapes)."""
    if not allowed_paths:
        return False
    if "\x00" in path_text:
        return False
    decoded = _unquote_path_safe(path_text.strip(), max_rounds=3)
    if decoded is None or not decoded or "\x00" in decoded:
        return False
    if decoded.lower().startswith("file:") or (
        _SARA_URI_SCHEME_RE.match(decoded) and not _SARA_WIN_DRIVE_RE.match(decoded)
    ):
        return False

    cleaned = decoded.replace("\\", "/")
    if cleaned.startswith("//"):
        return False
    segments = [seg for seg in cleaned.split("/") if seg]
    if ".." in segments or cleaned == "..":
        return False
    is_posix_abs = cleaned.startswith("/")
    is_win_abs = bool(_SARA_WIN_DRIVE_RE.match(cleaned))
    if not is_posix_abs and not is_win_abs:
        return False

    norm_path = posixpath.normpath(cleaned)
    if ".." in norm_path.split("/"):
        return False

    lexical_match_prefix: Optional[str] = None
    for prefix in allowed_paths:
        prefix_clean = prefix.strip().replace("\\", "/")
        norm_prefix = posixpath.normpath(prefix_clean).rstrip("/")
        if not norm_prefix:
            continue
        if is_win_abs and _SARA_WIN_DRIVE_RE.match(norm_prefix):
            norm_path_low = norm_path.lower()
            norm_prefix_low = norm_prefix.lower()
            if norm_path_low == norm_prefix_low or norm_path_low.startswith(norm_prefix_low + "/"):
                lexical_match_prefix = norm_prefix
                break
        elif norm_path == norm_prefix or norm_path.startswith(norm_prefix + "/"):
            lexical_match_prefix = norm_prefix
            break

    if lexical_match_prefix is None:
        return False

    # Symlink / TOCTOU confinement check when path components exist on local filesystem
    cand_local = Path(decoded)
    prefix_local = Path(lexical_match_prefix)
    try:
        cur = cand_local
        has_real_target = os.path.lexists(cur) or os.path.lexists(prefix_local)
        if has_real_target:
            resolved_prefix = prefix_local.resolve()
            resolved_cand = cand_local.resolve()
            if not resolved_cand.is_relative_to(resolved_prefix):
                return False
            if os.path.islink(cand_local):
                return False
    except (OSError, ValueError):
        return False

    return True


def _is_command_allowlisted(
    cmd_text: str,
    allowed_cmds: Tuple[str, ...],
    allowed_paths: Tuple[str, ...] = (),
) -> bool:
    """Check if a non-destructive command is within the policy command allowlist and respects path bounds."""
    if not allowed_cmds:
        return False
    canonical = _normalize_command_text(cmd_text)
    if not canonical:
        return False
    if any(op in canonical for op in _CHAINING_OPERATORS):
        return False
    if _DESTRUCTIVE_RE.search(canonical):
        return False

    # Any file path referenced inside the command must also be within allowed_paths
    for path_match in _PATH_RE.finditer(canonical):
        if not _is_path_allowlisted(path_match.group(0), allowed_paths):
            return False

    parts = canonical.split()
    first_token = parts[0] if parts else ""

    for allowed in allowed_cmds:
        allowed_clean = allowed.strip()
        if not allowed_clean:
            continue
        if canonical == allowed_clean or canonical.startswith(allowed_clean + " ") or first_token == allowed_clean:
            return True
    return False


class InductionParser:
    """Deterministic action-induction parser and risk scorer for untrusted tool observations."""

    MAX_DIRECTIVES_PER_OBS: int = MAX_DIRECTIVES_PER_OBS

    @classmethod
    def compute_risk_score(cls, directives: Sequence[InductionDirectiveDTO]) -> float:
        """Compute deterministic risk score in [0.0, 1.0] from extracted directives.

        Calibrated weights:
          - 0.80: Trojan-Source Bidi overrides / OSC escapes, and destructive SHELL_COMMAND (_DESTRUCTIVE_RE)
          - 0.50: Explicit 'ignore (all )?(previous|prior) instructions' clause in ROLE_OVERRIDE
          - 0.45: SHELL_COMMAND or FILE_PATH_ACCESS outside allowlist
          - 0.35: Opening/standalone ROLE_OVERRIDE delimiters (<system>, [INST], <tool_call>, etc.)
                  and standard zero-width / ANSI CSI HIDDEN_ESCAPE sequences
          - 0.30: SHELL_COMMAND inside allowlist (untrusted observation never carries authority)
          - 0.00: Closing ROLE_OVERRIDE tags (</system>, [/INST], </tool_call>, <|im_end|>)
                  and FILE_PATH_ACCESS inside allowlist
        """
        risk = 0.0
        has_standard_hidden = False
        has_opening_role = False

        for d in directives:
            if not isinstance(d, InductionDirectiveDTO):
                raise TypeError(f"Expected InductionDirectiveDTO, got {type(d).__name__}")
            if math.isnan(d.confidence) or math.isinf(d.confidence):
                raise ValueError("directive confidence shall never be NaN or Inf")

            if d.directive_kind is DirectiveKind.HIDDEN_ESCAPE:
                if _CRITICAL_HIDDEN_RE.search(d.directive_text):
                    risk += 0.80
                else:
                    has_standard_hidden = True
            elif d.directive_kind is DirectiveKind.ROLE_OVERRIDE:
                text_stripped = d.directive_text.strip()
                if _ROLE_CLOSING_RE.match(text_stripped):
                    has_opening_role = True
                    continue
                matched_ignore = bool(_ROLE_IGNORE_RE.search(text_stripped))
                if matched_ignore:
                    risk += 0.50
                if not matched_ignore or _ROLE_OPENING_RE.search(text_stripped):
                    has_opening_role = True
            elif d.directive_kind is DirectiveKind.SHELL_COMMAND:
                if _DESTRUCTIVE_RE.search(d.directive_text):
                    risk += 0.80
                elif not d.within_allowlist:
                    risk += 0.45
                else:
                    risk += 0.30
            elif d.directive_kind is DirectiveKind.FILE_PATH_ACCESS:
                if not d.within_allowlist:
                    risk += 0.45

        if has_standard_hidden:
            risk += 0.35
        if has_opening_role:
            risk += 0.35

        if math.isnan(risk) or math.isinf(risk):
            raise ValueError("risk_score shall never be NaN or Inf")

        score = min(1.0, round(risk, 4))
        if math.isnan(score) or math.isinf(score) or not (0.0 <= score <= 1.0):
            raise ValueError("risk_score must be a finite float in [0.0, 1.0]")
        return score

    @classmethod
    def parse(
        cls,
        observation: Union[UntrustedObservationDTO, str],
        policy: Optional[AuthorizedPolicyDTO] = None,
    ) -> Tuple[Tuple[InductionDirectiveDTO, ...], float]:
        """Parse an untrusted observation against an optional policy.

        Returns:
            Tuple of (directives, risk_score) where len(directives) <= 64 and risk_score in [0.0, 1.0].
        """
        if isinstance(observation, RawToolObservationDTO):
            raw_text = observation.raw_output
            obs_tool_name: Optional[str] = observation.source.tool_name
        elif isinstance(observation, str):
            LexicalSanitizer.validate_raw(observation)
            raw_text = observation
            obs_tool_name = policy.tool_name if isinstance(policy, AuthorizationPolicyRuleDTO) else None
        else:
            raise TypeError(
                f"observation must be RawToolObservationDTO or str, got {type(observation).__name__}"
            )

        if policy is not None and not isinstance(policy, AuthorizationPolicyRuleDTO):
            raise TypeError(
                f"policy must be AuthorizationPolicyRuleDTO or None, got {type(policy).__name__}"
            )

        # Tool name binding: if policy.tool_name != observation.source.tool_name, allowlists are empty
        if policy is not None and (obs_tool_name is None or policy.tool_name == obs_tool_name):
            allowed_cmds: Tuple[str, ...] = policy.allowed_commands
            allowed_paths: Tuple[str, ...] = policy.allowed_path_prefixes
        else:
            allowed_cmds = ()
            allowed_paths = ()

        tier_critical: list[InductionDirectiveDTO] = []
        tier_unallowlisted: list[InductionDirectiveDTO] = []
        tier_allowlisted_cmd: list[InductionDirectiveDTO] = []
        tier_allowlisted_path: list[InductionDirectiveDTO] = []

        # 1. Scan raw_text for HIDDEN_ESCAPE before lexical stripping removes them
        for m in _HIDDEN_RE.finditer(raw_text):
            if len(tier_critical) >= MAX_DIRECTIVES_PER_OBS:
                break
            escaped_repr = m.group(0).encode("unicode_escape").decode("ascii")[:MAX_DIRECTIVE_TEXT_CHARS]
            if not escaped_repr:
                escaped_repr = "\\u200b"
            start_off, end_off = _clamp_span(m.start(), m.end())
            tier_critical.append(
                InductionDirectiveDTO(
                    directive_kind=DirectiveKind.HIDDEN_ESCAPE,
                    directive_text=escaped_repr,
                    start_offset=start_off,
                    end_offset=end_off,
                    confidence=0.95,
                    within_allowlist=False,
                )
            )

        # Normalize text via LexicalSanitizer so obfuscated payloads (e.g. fullwidth + zero-width) are exposed
        sanitized_res = LexicalSanitizer.sanitize(raw_text, reject_null_bytes=True)
        clean_text = sanitized_res.sanitized_text
        cmd_scan_text = _collapse_line_continuations(clean_text)

        # 2. Scan clean_text for ROLE_OVERRIDE markers
        for m in _ROLE_RE.finditer(clean_text):
            if len(tier_critical) >= MAX_DIRECTIVES_PER_OBS:
                break
            text_val = m.group(0).strip()[:MAX_DIRECTIVE_TEXT_CHARS]
            if not text_val:
                continue
            start_off, end_off = _clamp_span(m.start(), m.end())
            tier_critical.append(
                InductionDirectiveDTO(
                    directive_kind=DirectiveKind.ROLE_OVERRIDE,
                    directive_text=text_val,
                    start_offset=start_off,
                    end_offset=end_off,
                    confidence=0.95,
                    within_allowlist=False,
                )
            )

        # 3. Scan cmd_scan_text for destructive SHELL_COMMAND
        destructive_spans: list[tuple[int, int]] = []
        for m in _DESTRUCTIVE_RE.finditer(cmd_scan_text):
            if len(tier_critical) >= MAX_DIRECTIVES_PER_OBS:
                break
            text_val = m.group(0).strip()[:MAX_DIRECTIVE_TEXT_CHARS]
            if not text_val:
                continue
            destructive_spans.append((m.start(), m.end()))
            start_off, end_off = _clamp_span(m.start(), m.end())
            tier_critical.append(
                InductionDirectiveDTO(
                    directive_kind=DirectiveKind.SHELL_COMMAND,
                    directive_text=text_val,
                    start_offset=start_off,
                    end_offset=end_off,
                    confidence=0.95,
                    within_allowlist=False,
                )
            )

        # 4. Scan cmd_scan_text for imperative / general SHELL_COMMAND
        for m in _IMPERATIVE_RE.finditer(cmd_scan_text):
            if _overlaps(m.start(), m.end(), destructive_spans):
                continue
            raw_cmd = next((g for g in m.groups() if g is not None), m.group(0))
            text_val = raw_cmd.strip()[:MAX_DIRECTIVE_TEXT_CHARS]
            if not text_val:
                continue
            is_destructive = bool(_DESTRUCTIVE_RE.search(text_val))
            is_subshell = m.group(2) is not None
            is_chained = bool(
                is_subshell
                or _TRAILING_CHAIN_RE.match(cmd_scan_text[m.end() :])
                or _LEADING_CHAIN_RE.search(cmd_scan_text[: m.start()])
            )
            in_allow = (
                False
                if (is_destructive or is_chained)
                else _is_command_allowlisted(text_val, allowed_cmds, allowed_paths)
            )
            start_off, end_off = _clamp_span(m.start(), m.end())
            directive = InductionDirectiveDTO(
                directive_kind=DirectiveKind.SHELL_COMMAND,
                directive_text=text_val,
                start_offset=start_off,
                end_offset=end_off,
                confidence=0.95 if is_destructive else 0.85,
                within_allowlist=in_allow,
            )
            if is_destructive:
                if len(tier_critical) < MAX_DIRECTIVES_PER_OBS:
                    tier_critical.append(directive)
            elif not in_allow:
                if len(tier_unallowlisted) < MAX_DIRECTIVES_PER_OBS:
                    tier_unallowlisted.append(directive)
            else:
                if len(tier_allowlisted_cmd) < MAX_DIRECTIVES_PER_OBS:
                    tier_allowlisted_cmd.append(directive)

        # 5. Scan clean_text for FILE_PATH_ACCESS
        for m in _PATH_RE.finditer(clean_text):
            if (
                len(tier_unallowlisted) >= MAX_DIRECTIVES_PER_OBS
                and len(tier_allowlisted_path) >= MAX_DIRECTIVES_PER_OBS
            ):
                break
            text_val = m.group(0).strip()[:MAX_DIRECTIVE_TEXT_CHARS]
            if not text_val:
                continue
            in_allow = _is_path_allowlisted(text_val, allowed_paths)
            start_off, end_off = _clamp_span(m.start(), m.end())
            directive = InductionDirectiveDTO(
                directive_kind=DirectiveKind.FILE_PATH_ACCESS,
                directive_text=text_val,
                start_offset=start_off,
                end_offset=end_off,
                confidence=0.80 if in_allow else 0.90,
                within_allowlist=in_allow,
            )
            if not in_allow:
                if len(tier_unallowlisted) < MAX_DIRECTIVES_PER_OBS:
                    tier_unallowlisted.append(directive)
            else:
                if len(tier_allowlisted_path) < MAX_DIRECTIVES_PER_OBS:
                    tier_allowlisted_path.append(directive)

        combined = (
            tier_critical
            + tier_unallowlisted
            + tier_allowlisted_cmd
            + tier_allowlisted_path
        )
        capped_directives = tuple(combined[:MAX_DIRECTIVES_PER_OBS])
        risk_score = cls.compute_risk_score(capped_directives)
        return capped_directives, risk_score

    @classmethod
    def extract_directives(
        cls,
        observation: Union[UntrustedObservationDTO, str],
        policy: Optional[AuthorizedPolicyDTO] = None,
    ) -> Tuple[InductionDirectiveDTO, ...]:
        """Extract up to 64 typed induction directives from an untrusted observation."""
        directives, _ = cls.parse(observation, policy=policy)
        return directives
