# manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
"""
SARA Lexical Sanitizer :: Deterministic NFKC & Escape Normalization Engine
==========================================================================
manifest_hash (M3-P2): 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
manifest_hash (M3-P3): 8d94151e921e2f8eaacb440cb3c1b0d4e0ff6ac80fa217e5830de1c1edec1b13
manifest_hash (W2-D1): ece9d70e52f09f3e80d8cadfd432c4b07a094ca40618ff12aa72a6f1cc92052a
Normalizes untrusted tool observations via Unicode NFKC, strips zero-width,
invisible, and bidirectional override characters, removes ANSI CSI escape
sequences, enforces the 64 KB ceiling and NUL-byte prohibition, and flags
role-override / context-escape markers.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ctxfw.sara.contracts import MAX_RAW_OUTPUT_CHARS

__all__ = [
    "ANSI_ESCAPE_RE",
    "HIDDEN_CHAR_RE",
    "MAX_RAW_OUTPUT_CHARS",
    "ROLE_OVERRIDE_RE",
    "LexicalSanitizer",
    "ReferenceLexicalSanitizer",
    "SanitizationResult",
]

# Zero-width spaces, joiners, directional marks, BOM, Bidi embeddings/overrides/isolates
HIDDEN_CHAR_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff\u202a-\u202e\u2066-\u2069]")

# ANSI CSI, OSC, and 2-byte escape sequences (e.g. \x1b[31m, \x1b]0;title\x07, \x1b]8;;url\x1b\)
ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\)|\([0-9A-Za-z]|[@-Z\\-_])"
)

# Combined hidden / escape detector used across lexical & induction stages
_COMBINED_HIDDEN_RE = re.compile(
    r"[\u200b-\u200f\u2060\ufeff\u202a-\u202e\u2066-\u2069]+"
    r"|\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\)|\([0-9A-Za-z]|[@-Z\\-_])"
)

# Deterministic role-override and prompt context-escape markers (#10 LTBD delimiters strictly `<...>` anchored)
ROLE_OVERRIDE_RE = re.compile(
    r"(?:</?system>|<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|</?tool_call>"
    r"|<\s*(?:INST|DATA)\s+(?:BEGIN|END)\s*>"
    r"|\b(?:System|Assistant|Developer):"
    r"|\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b)",
    re.IGNORECASE,
)

# Paired role-override block delimiters stripped during STRIP_COMMANDS neutralization.
# Note: `<DATA BEGIN>.*?<DATA END>` is intentionally excluded here so untrusted data payloads
# retain their benign content after `ROLE_OVERRIDE_RE` strips the spoofed delimiter tags alone.
_ROLE_BLOCK_RE = re.compile(
    r"(?:<system>.*?</system>"
    r"|\[INST\].*?\[/INST\]"
    r"|<tool_call>.*?</tool_call>"
    r"|<\|im_start\|>.*?<\|im_end\|>"
    r"|<\s*INST\s+BEGIN\s*>.*?<\s*INST\s+END\s*>)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class SanitizationResult:
    """Immutable lexical sanitization result with forensic telemetry."""

    sanitized_text: str
    original_length: int
    sanitized_length: int
    null_bytes_found: bool = False
    hidden_chars_stripped: int = 0
    ansi_sequences_stripped: int = 0
    nfkc_normalized: bool = False
    role_override_markers: Tuple[str, ...] = ()
    escape_detected: bool = False

    @property
    def cleaned_text(self) -> str:
        """Alias for sanitized_text."""
        return self.sanitized_text

    @property
    def clean_text(self) -> str:
        """Alias for sanitized_text."""
        return self.sanitized_text

    @property
    def text(self) -> str:
        """Alias for sanitized_text."""
        return self.sanitized_text

    @property
    def role_override_detected(self) -> bool:
        """True if one or more role-override or context-escape markers were matched."""
        return len(self.role_override_markers) > 0

    @property
    def stripped_count(self) -> int:
        """Total count of hidden characters and ANSI escape sequences removed."""
        return self.hidden_chars_stripped + self.ansi_sequences_stripped

    def __str__(self) -> str:
        return self.sanitized_text

    def __len__(self) -> int:
        return len(self.sanitized_text)

    def __contains__(self, item: str) -> bool:
        return item in self.sanitized_text

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.sanitized_text == other
        if isinstance(other, SanitizationResult):
            return (
                self.sanitized_text == other.sanitized_text
                and self.original_length == other.original_length
                and self.sanitized_length == other.sanitized_length
                and self.null_bytes_found == other.null_bytes_found
                and self.hidden_chars_stripped == other.hidden_chars_stripped
                and self.ansi_sequences_stripped == other.ansi_sequences_stripped
                and self.nfkc_normalized == other.nfkc_normalized
                and self.role_override_markers == other.role_override_markers
                and self.escape_detected == other.escape_detected
            )
        return NotImplemented


class LexicalSanitizer:
    """Deterministic lexical sanitizer and pre-parser guard for untrusted tool outputs."""

    MAX_RAW_OUTPUT_CHARS: int = MAX_RAW_OUTPUT_CHARS

    @classmethod
    def validate_raw(cls, raw: str) -> str:
        """Strictly validate raw input string against type, size (<= 64 KB), and NUL byte invariants.

        Raises:
            ValueError: If raw is not a str, exceeds 65536 chars, or contains a NUL byte ('\\x00').
        """
        if not isinstance(raw, str):
            raise ValueError("raw_output must be a string")
        if len(raw) > MAX_RAW_OUTPUT_CHARS:
            raise ValueError(
                f"raw_output length {len(raw)} exceeds maximum allowed {MAX_RAW_OUTPUT_CHARS} characters"
            )
        if "\x00" in raw:
            raise ValueError("raw_output shall never contain a NUL byte")
        return raw

    @classmethod
    def sanitize(cls, raw: str, *, reject_null_bytes: bool = False) -> SanitizationResult:
        """Sanitize untrusted text via NFKC normalization and hidden/ANSI stripping.

        Args:
            raw: Untrusted raw tool output string.
            reject_null_bytes: When True, raises ValueError if '\\x00' is present.
                               When False, strips '\\x00' and sets null_bytes_found=True.

        Returns:
            SanitizationResult containing the normalized text and detection telemetry.

        Raises:
            ValueError: If raw is not a str, exceeds 65536 chars, or contains '\\x00'
                        when reject_null_bytes=True.
        """
        if not isinstance(raw, str):
            raise ValueError("raw_output must be a string")
        if len(raw) > MAX_RAW_OUTPUT_CHARS:
            raise ValueError(
                f"raw_output length {len(raw)} exceeds maximum allowed {MAX_RAW_OUTPUT_CHARS} characters"
            )

        null_bytes_found = "\x00" in raw
        if null_bytes_found and reject_null_bytes:
            raise ValueError("raw_output shall never contain a NUL byte")

        working = raw.replace("\x00", "") if null_bytes_found else raw

        # 1. Unicode NFKC canonical decomposition + compatibility composition
        nfkc_text = unicodedata.normalize("NFKC", working)
        nfkc_normalized = nfkc_text != working

        # 2. Strip ANSI CSI escape sequences
        ansi_matches = ANSI_ESCAPE_RE.findall(nfkc_text)
        ansi_count = len(ansi_matches)
        without_ansi = ANSI_ESCAPE_RE.sub("", nfkc_text) if ansi_count else nfkc_text

        # 3. Strip zero-width, invisible, and Bidi override characters
        hidden_matches = HIDDEN_CHAR_RE.findall(without_ansi)
        hidden_count = len(hidden_matches)
        sanitized_text = HIDDEN_CHAR_RE.sub("", without_ansi) if hidden_count else without_ansi

        # 4. Detect role-override and context-escape markers on the full normalized text
        markers = tuple(m.group(0) for m in ROLE_OVERRIDE_RE.finditer(sanitized_text))

        escape_detected = bool(
            null_bytes_found or hidden_count > 0 or ansi_count > 0 or len(markers) > 0
        )

        return SanitizationResult(
            sanitized_text=sanitized_text,
            original_length=len(raw),
            sanitized_length=len(sanitized_text),
            null_bytes_found=null_bytes_found,
            hidden_chars_stripped=hidden_count,
            ansi_sequences_stripped=ansi_count,
            nfkc_normalized=nfkc_normalized,
            role_override_markers=markers,
            escape_detected=escape_detected,
        )

    @classmethod
    def sanitize_text(cls, raw: str, *, reject_null_bytes: bool = True) -> str:
        """Validate and return the sanitized string directly."""
        return cls.sanitize(raw, reject_null_bytes=reject_null_bytes).sanitized_text

    @classmethod
    def detect_role_overrides(cls, raw: str) -> Tuple[str, ...]:
        """Return all role-override and context-escape markers detected after sanitization."""
        return cls.sanitize(raw, reject_null_bytes=False).role_override_markers

    @classmethod
    def neutralize(cls, raw_text: str, directives: Sequence[Any] = ()) -> str:
        """Deterministically neutralize medium-risk directives and role overrides for STRIP_COMMANDS.

        Steps:
          1. Apply LexicalSanitizer.sanitize(raw_text).sanitized_text (stripping zero-width/bidi/ANSI).
          2. Strip paired role-override blocks (<system>...</system>, [INST]...[/INST], <tool_call>...</tool_call>)
             and standalone matches of ROLE_OVERRIDE_RE.
          3. Strip un-allowlisted directive_text entries from directives without corrupting identifiers.
        """
        cleaned = cls.sanitize(raw_text, reject_null_bytes=False).sanitized_text
        cleaned = _ROLE_BLOCK_RE.sub("", cleaned)
        cleaned = ROLE_OVERRIDE_RE.sub("", cleaned)
        for d in directives:
            if not getattr(d, "within_allowlist", False):
                kind = getattr(d, "directive_kind", None)
                kind_val = getattr(kind, "value", str(kind)) if kind is not None else ""
                d_text = getattr(d, "directive_text", "")
                if d_text and kind_val != "HIDDEN_ESCAPE":
                    esc = re.escape(d_text)
                    wrapped_pat = (
                        r"(?:`\s*" + esc + r"\s*`"
                        r"|\b(?:please\s+)?(?:run|execute|invoke|exec)\s*:\s*" + esc + r")"
                    )
                    cleaned = re.sub(wrapped_pat, "", cleaned, flags=re.IGNORECASE)
                    prefix_guard = (
                        r"(?<![a-zA-Z0-9_])"
                        if d_text[0].isalnum() or d_text[0] == "_"
                        else ""
                    )
                    suffix_guard = (
                        r"(?![a-zA-Z0-9_])"
                        if d_text[-1].isalnum() or d_text[-1] == "_"
                        else ""
                    )
                    cleaned = re.sub(prefix_guard + esc + suffix_guard, "", cleaned)
        return cleaned


ReferenceLexicalSanitizer = LexicalSanitizer
