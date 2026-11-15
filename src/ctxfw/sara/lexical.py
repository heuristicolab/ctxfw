# manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
"""
SARA Lexical Sanitizer :: Deterministic NFKC & Escape Normalization Engine
==========================================================================
manifest_hash (M3-P2): 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
manifest_hash (M3-P3): 8d94151e921e2f8eaacb440cb3c1b0d4e0ff6ac80fa217e5830de1c1edec1b13
manifest_hash (W2-D1): ece9d70e52f09f3e80d8cadfd432c4b07a094ca40618ff12aa72a6f1cc92052a
manifest_hash (W2-E2): bc6e604a3faf8a75b3d6402b523047e481f35c0d62afca3056114337021196e0
Normalizes untrusted tool observations via Unicode NFKC, strips zero-width,
invisible, and bidirectional override characters, removes ANSI CSI escape
sequences, enforces the 64 KB ceiling and NUL-byte prohibition, detects
multilingual role-override attempts and intra-token script confusables,
and validates symmetric slot preservation across AST slices (#13).
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
import hashlib as _hashlib
import json as _json
import unicodedata as _unicodedata
from dataclasses import dataclass as _dataclass
from typing import Iterable as _Iterable

MAX_LANGUAGE_TAG_LEN: int = 35
MIN_LANGUAGE_TAG_LEN: int = 2
MAX_SYMMETRIC_SLOTS: int = 8192
MAX_SLOT_NAME_LEN: int = 256
LANGUAGE_TAG_RE = re.compile(r"^(?:auto|[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3})$")

_CONFUSABLE_SCRIPTS = frozenset({"LATIN", "CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE"})

_CONFUSABLE_CHAR_MAP: dict[str, str] = {
    # Cyrillic -> Latin homoglyphs
    "\u0410": "A", "\u0430": "a", "\u0412": "B", "\u0421": "C", "\u0441": "c",
    "\u0415": "E", "\u0435": "e", "\u041d": "H", "\u04bb": "h", "\u0406": "I",
    "\u0456": "i", "\u0408": "J", "\u0458": "j", "\u041a": "K", "\u041c": "M",
    "\u041e": "O", "\u043e": "o", "\u0420": "P", "\u0440": "p", "\u0405": "S",
    "\u0455": "s", "\u0422": "T", "\u0442": "t", "\u0425": "X", "\u0445": "x",
    "\u04ae": "Y", "\u04af": "y", "\u0443": "y", "\u0474": "V", "\u0475": "v",
    "\u04cf": "l", "\u0433": "r", "\u0454": "e",
    # Greek -> Latin homoglyphs
    "\u0391": "A", "\u03b1": "a", "\u0392": "B", "\u0395": "E", "\u03b5": "e",
    "\u0396": "Z", "\u0397": "H", "\u0399": "I", "\u03b9": "i", "\u039a": "K",
    "\u03ba": "k", "\u039c": "M", "\u039d": "N", "\u03bd": "v", "\u039f": "O",
    "\u03bf": "o", "\u03a1": "P", "\u03c1": "p", "\u03a4": "T", "\u03c4": "t",
    "\u03a5": "Y", "\u03c5": "u", "\u03a7": "X", "\u03c7": "x",
    # Armenian -> Latin homoglyphs
    "\u0570": "h", "\u0585": "o", "\u0578": "n", "\u057d": "u",
}

_CONFUSABLE_SECURITY_KEYWORDS = frozenset(
    {
        "system",
        "assistant",
        "developer",
        "ignore",
        "disregard",
        "forget",
        "override",
        "previous",
        "prior",
        "instructions",
        "inst",
        "data",
        "begin",
        "end",
        "tool",
        "call",
        "im",
        "start",
        "admin",
        "sudo",
        "passwd",
        "shadow",
    }
)

_CONFUSABLE_SEGMENT_RE = re.compile(
    r"[0-9A-Za-z\u00C0-\u02AF\u0370-\u058F\u13A0-\u13FF]+"
)


def _char_confusable_script(ch: str) -> str:
    if not ch.isalpha() or _unicodedata.category(ch).startswith("M"):
        return ""
    name = _unicodedata.name(ch, "")
    if not name:
        return ""
    head = name.split(" ", 1)[0]
    return head if head in _CONFUSABLE_SCRIPTS else ""


def fold_confusables(text: str) -> str:
    """Fold known cross-script homoglyphs to ASCII skeletons for rule inspection."""
    return "".join(_CONFUSABLE_CHAR_MAP.get(ch, ch) for ch in text)


@_dataclass(frozen=True)
class IntraTokenConfusableFinding:
    """Detected intra-token mixed confusable scripts or pure spoofed keyword."""

    token: str
    scripts: tuple[str, ...]
    skeleton: str
    reason: str


def detect_intra_token_confusables(
    text: str, *, max_findings: int = 64
) -> tuple[IntraTokenConfusableFinding, ...]:
    """Detect intra-token script mixing and homoglyph keyword spoofing without cross-token FP."""
    if not text:
        return ()
    findings: list[IntraTokenConfusableFinding] = []
    seen_tokens: set[str] = set()
    for match in _CONFUSABLE_SEGMENT_RE.finditer(text):
        seg = match.group(0)
        if seg in seen_tokens or len(seg) < 2:
            continue
        scripts = sorted({s for ch in seg if (s := _char_confusable_script(ch))})
        if len(scripts) >= 2:
            seen_tokens.add(seg)
            findings.append(
                IntraTokenConfusableFinding(
                    token=seg,
                    scripts=tuple(scripts),
                    skeleton=fold_confusables(seg),
                    reason="MIXED_CONFUSABLE_SCRIPTS",
                )
            )
        elif len(scripts) == 1 and scripts[0] in {
            "CYRILLIC",
            "GREEK",
            "ARMENIAN",
            "CHEROKEE",
        }:
            skeleton = fold_confusables(seg)
            if skeleton.lower() in _CONFUSABLE_SECURITY_KEYWORDS and all(
                (ch in _CONFUSABLE_CHAR_MAP or ch.isdigit()) for ch in seg
            ):
                seen_tokens.add(seg)
                findings.append(
                    IntraTokenConfusableFinding(
                        token=seg,
                        scripts=tuple(scripts),
                        skeleton=skeleton,
                        reason="PURE_CONFUSABLE_KEYWORD",
                    )
                )
        if len(findings) >= max_findings:
            break
    return tuple(findings)


def validate_language_tag(lang_tag: str) -> str:
    """Validate bounded BCP-47 / 'auto' language selector tags deterministically."""
    if not isinstance(lang_tag, str):
        raise ValueError("language tag must be a string")
    cleaned = lang_tag.strip()
    if not (MIN_LANGUAGE_TAG_LEN <= len(cleaned) <= MAX_LANGUAGE_TAG_LEN):
        raise ValueError(
            f"language tag length must be within [{MIN_LANGUAGE_TAG_LEN}..{MAX_LANGUAGE_TAG_LEN}]"
        )
    if not LANGUAGE_TAG_RE.fullmatch(cleaned):
        raise ValueError(f"invalid BCP-47 language tag: {cleaned!r}")
    return cleaned


@_dataclass(frozen=True)
class SlotSymmetryResult:
    """Symmetric slot preservation proof comparing AST input and re-emitted output slots."""

    verified: bool
    expected_slot_hash: str
    actual_slot_hash: str
    missing_slots: tuple[str, ...]
    extra_slots: tuple[str, ...]
    expected_count: int
    actual_count: int


def _normalize_slots(slots: _Iterable[str], label: str) -> tuple[str, ...]:
    out: list[str] = []
    for raw_slot in slots:
        if not isinstance(raw_slot, str):
            raise ValueError(f"{label} entries must be strings")
        slot = raw_slot.strip()
        if not slot or "\x00" in raw_slot or len(slot) > MAX_SLOT_NAME_LEN:
            raise ValueError(f"invalid {label} slot entry: {raw_slot!r}")
        out.append(slot)
        if len(out) > MAX_SYMMETRIC_SLOTS:
            raise ValueError(f"{label} exceeds max slots bound ({MAX_SYMMETRIC_SLOTS})")
    return tuple(out)


def verify_symmetric_slot_preservation(
    preserved_slots: _Iterable[str], emitted_slots: _Iterable[str]
) -> SlotSymmetryResult:
    """Verify exact symmetric correspondence between input preserved AST slots and output slots."""
    expected = _normalize_slots(preserved_slots, "preserved_slots")
    actual = _normalize_slots(emitted_slots, "emitted_slots")
    expected_hash = _hashlib.sha256(
        _json.dumps(list(expected), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    actual_hash = _hashlib.sha256(
        _json.dumps(list(actual), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    expected_counts: dict[str, int] = {}
    for s in expected:
        expected_counts[s] = expected_counts.get(s, 0) + 1
    actual_counts: dict[str, int] = {}
    for s in actual:
        actual_counts[s] = actual_counts.get(s, 0) + 1

    missing: list[str] = []
    for s, count in expected_counts.items():
        deficit = count - actual_counts.get(s, 0)
        if deficit > 0:
            missing.extend([s] * deficit)

    extra: list[str] = []
    for s, count in actual_counts.items():
        surplus = count - expected_counts.get(s, 0)
        if surplus > 0:
            extra.extend([s] * surplus)

    verified = expected_hash == actual_hash and not missing and not extra
    return SlotSymmetryResult(
        verified=verified,
        expected_slot_hash=expected_hash,
        actual_slot_hash=actual_hash,
        missing_slots=tuple(missing),
        extra_slots=tuple(extra),
        expected_count=len(expected),
        actual_count=len(actual),
    )


ROLE_OVERRIDE_RE = re.compile(
    r"(?:</?system>|<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|</?tool_call>"
    r"|<\s*(?:INST|DATA)\s+(?:BEGIN|END)\s*>"
    r"|\b(?:System|Assistant|Developer):"
    r"|(?:^|\n)\s*(?:Sistema|Asistente|Desarrollador"
    r"|Syst\u00e8me|Systeme|D\u00e9veloppeur|Developpeur"
    r"|Assistent|Entwickler|Assistente|Desenvolvedor):"
    r"|\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior)\s+instructions\b"
    r"|\b(?:ignora|ignorar|olvida|olvidar|omite|omitir|anula|anular)\s+(?:todas\s+)?(?:las\s+)?instrucciones\s+(?:anteriores|previas)\b"
    r"|\b(?:ignore[zr]?|oublie[zr]?)\s+(?:toutes\s+)?(?:les\s+)?instructions\s+(?:pr\u00e9c\u00e9dentes|precedentes|ant\u00e9rieures|anterieures)\b"
    r"|\b(?:ignoriere|ignorieren\s+Sie|vergiss|vergesse[n]?)\s+(?:alle\s+)?(?:vorherigen|bisherigen|fr\u00fcheren|fruheren)\s+Anweisungen\b"
    r"|\b(?:ignore|ignorar|esque\u00e7a|esqueca|desconsidere)\s+(?:todas\s+)?(?:as\s+)?instru(?:\u00e7\u00f5es|coes)\s+(?:anteriores|pr\u00e9vias|previas)\b"
    r"|(?:忽略|无视|無視)(?:所有)?(?:之前|先前|以前|前面)的?(?:指令|指示|提示)"
    r"|(?:以前|これまで|先ほど|すべて)の指示を(?:無視|忘れ)(?:して|せよ|しろ)?"
    r"|(?:이전|기존)\s*지시(?:사항)?을?\s*무시(?:하세요|해라|해)?)",
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

        # 4. Detect role-override, multilingual overrides, confusable skeleton matches,
        # and intra-token cross-script homoglyphs without penalizing benign UTF-8 files
        raw_markers = [m.group(0) for m in ROLE_OVERRIDE_RE.finditer(sanitized_text)]
        folded_text = fold_confusables(sanitized_text)
        if folded_text != sanitized_text:
            for m in ROLE_OVERRIDE_RE.finditer(folded_text):
                raw_markers.append(m.group(0))
        confusables = detect_intra_token_confusables(sanitized_text)
        for finding in confusables:
            raw_markers.append(
                f"[CONFUSABLE:{finding.token}:{'+'.join(finding.scripts)}]"
            )
        markers = tuple(dict.fromkeys(raw_markers))

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

    @staticmethod
    def verify_symmetric_slots(
        preserved_slots: _Iterable[str], emitted_slots: _Iterable[str]
    ) -> SlotSymmetryResult:
        """Delegate deterministic AST slot-symmetry verification (#13)."""
        return verify_symmetric_slot_preservation(preserved_slots, emitted_slots)

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
