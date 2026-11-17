# manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
"""
SARA Lexical Sanitizer :: Deterministic NFKC & Escape Normalization Engine
==========================================================================
manifest_hash (M3-P2): 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
manifest_hash (M3-P3): 8d94151e921e2f8eaacb440cb3c1b0d4e0ff6ac80fa217e5830de1c1edec1b13
manifest_hash (W2-D1): ece9d70e52f09f3e80d8cadfd432c4b07a094ca40618ff12aa72a6f1cc92052a
manifest_hash (W2-E2): bc6e604a3faf8a75b3d6402b523047e481f35c0d62afca3056114337021196e0
manifest_hash_v42_r2: cf0e30f7ed19bc43c700dc8f7d845c5f23011472fcd46d614602865b6be043d1
manifest_hash_v421: f4a77d5537c6c3c60f982ed30b8dd7d6892b3c55a33c338ffb8f2f818de93700
manifest_hash_v421_r2: 0d461122028fae32834105661bd6ef929a773e98766e8ebac9a97bc674c786fa
manifest_hash_v421_r3: 52cb3286fbc6f596c84e0d3c83790db7cb64decc34d1f50fe8c9cbf234363f28
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
    "LOCALIZED_ROLE_DIRECTIVE_LOOKAHEAD",
    "MAX_RAW_OUTPUT_CHARS",
    "ROLE_OVERRIDE_RE",
    "LexicalSanitizer",
    "ReferenceLexicalSanitizer",
    "SanitizationResult",
    "is_declarative_legal_repeal",
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
import urllib.parse as _urllib_parse
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
    "\u0432": "b", "\u043a": "k", "\u043c": "m", "\u043d": "h",
    "\u0451": "e", "\u0452": "d", "\u0457": "i", "\u0491": "g",
    "\u04bd": "e", "\u04c0": "I", "\u0501": "d", "\u051b": "q", "\u051d": "w",
    # Greek -> Latin homoglyphs
    "\u0391": "A", "\u03b1": "a", "\u0392": "B", "\u0395": "E", "\u03b5": "e",
    "\u0396": "Z", "\u0397": "H", "\u0399": "I", "\u03b9": "i", "\u039a": "K",
    "\u03ba": "k", "\u039c": "M", "\u039d": "N", "\u03bd": "v", "\u039f": "O",
    "\u03bf": "o", "\u03a1": "P", "\u03c1": "p", "\u03a4": "T", "\u03c4": "t",
    "\u03a5": "Y", "\u03c5": "u", "\u03a7": "X", "\u03c7": "x",
    "\u03b2": "b", "\u03b3": "y", "\u03b4": "d", "\u03b6": "z",
    "\u03b7": "n", "\u03b8": "o", "\u03bb": "l", "\u03bc": "m",
    "\u03a3": "S", "\u03c3": "s", "\u03c2": "s", "\u03c9": "w",
    "\u03f2": "c", "\u03f3": "j", "\u03f9": "C",
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
        "rm",
        "sh",
        "bash",
        "cat",
        "curl",
        "env",
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


_LOCALIZED_DIRECTIVE_TERMS = (
    r"(?:\b(?:"
    r"ignora\w*|olvida\w*|omit[aei]\w*|anul[ae]\w*|descarta\w*|ejecuta\w*|corre\b|act[u\u00fa]a\w*|asume\b|eres\b"
    r"|responde\w*|contesta\w*|devuelve\w*|retorna\w*|imprime\w*|imprima\w*|muestra\w*|revela\w*|extrae\w*|env[i\u00ed]a\w*"
    r"|transfiere\w*|cambia\w*|modifica\w*|desactiva\w*|aprueba\w*|autoriza\w*|escribe\w*|genera\w*|repite\w*"
    r"|dime\b|haz\b|lee\b|borra\w*|elimina\w*|debes\b|deber[a\u00e1]s\b|tienes\s+que\b"
    r"|no\s+(?:revises|valides|verifiques|menciones|apliques|cumplas|bloquees|filtres|digas|incluyas)\b"
    r"|sin\s+(?:revisar|validar|verificar|restricci\w*|filtro\w*)\b"
    r"|instrucci\w*|prompt\b|reglas?\b|pol[i\u00ed]ticas?\b|modo\s+(?:libre|admin|debug|desarrollador|sin)\b"
    r"|ignore[zr]?\b|oublie\w*|ex[e\u00e9]cute\w*|affiche\w*|montre\w*|envoi\w*|envoy\w*|r[e\u00e9]ponds?\b|r[e\u00e9]pondez\b|r[e\u00e9]v[e\u00e8]le\w*|retourne\w*|renvoie\w*|agis\b|tu\s+es\b|vous\s+[e\u00ea]tes\b|r[e\u00e8]gles?\b"
    r"|ignorier\w*|vergiss\w*|f[u\u00fc]hre\w*|gib\b|antworte\w*|offenbare\w*|zeige\w*|du\s+bist\b|Sie\s+sind\b|Anweisungen\b|Regeln\b"
    r"|esque[c\u00e7]a\w*|desconsidere\w*|responda\w*|revele\w*|retorne\w*|devolva\w*|mostre\w*|envie\w*|exiba\w*|atue\b|voc[e\u00ea]\s+[e\u00e9]\b|instru[c\u00e7][o\u00f5]es\b|regras\b"
    r"|ignore\b|disregard\b|forget\b|override\b|execute\b|run\b|return\b|output\b|print\b|reveal\b|respond\b|act\s+as\b|you\s+are\b"
    r")|`|\$\(|<[a-zA-Z/|]|/etc/|\.env\b|https?://)"
)

LOCALIZED_ROLE_DIRECTIVE_LOOKAHEAD = (
    r"(?=[^\n]{0,240}(?:\n[^\n]{0,240})?"
    + _LOCALIZED_DIRECTIVE_TERMS
    + r")(?=[\s\S]{0,240}"
    + _LOCALIZED_DIRECTIVE_TERMS
    + r")"
)

_SPOOF_DELIMITER_PATTERN = (
    r"(?:</?system>|<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|</?tool_call>"
    r"|<\s*(?:INST|DATA)\s+(?:BEGIN|END)\s*>)"
)

_LOCALIZED_ROLE_HEADER_PATTERN = (
    r"(?:^|\n)[ \t]*(?:Sistema|Asistente|Desarrollador"
    r"|Syst\u00e8me|Systeme|D\u00e9veloppeur|Developpeur"
    r"|Assistent|Entwickler|Assistente|Desenvolvedor):"
)

_ROLE_IGNORE_PATTERN = (
    r"(?:\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:the\s+|your\s+)?(?:(?:previous|prior|above|system|safety|security|internal)\s+){0,2}(?:instructions|rules|restrictions|policies|guidelines|directives)\b"
    r"|\b(?:ignora|ignorar|olvida|olvidar|omite|omitir|descarta|descartar|anula|anular)\s+(?:todas\s+)?(?:las\s+|tus\s+|sus\s+)?instrucciones\s+(?:anteriores|previas|del\s+sistema|internas|de\s+seguridad)\b"
    r"|\b(?:ignora|ignorar|olvida|olvidar|omite|omitir|descarta|descartar|anula|anular)\s+(?:todas\s+)?(?:las\s+|tus\s+|sus\s+)?(?:reglas|restricciones|pol[i\u00ed]ticas|directrices)(?:\s+(?:del\s+sistema|anteriores|previas|internas|de\s+seguridad)){0,2}\b"
    r"|\b(?:ignore[zr]?|oublie[zr]?|omets?|omettre|[e\u00e9]carte[zr]?|annule[zr]?)\s+(?:toutes\s+)?(?:les\s+|vos\s+)?instructions\s+(?:pr[e\u00e9]c[e\u00e9]dentes|precedentes|ant[e\u00e9]rieures|anterieures|du\s+syst[e\u00e8]me|internes|de\s+s[e\u00e9]curit[e\u00e9])\b"
    r"|\b(?:ignore[zr]?|oublie[zr]?|omets?|omettre|[e\u00e9]carte[zr]?|annule[zr]?)\s+(?:toutes\s+)?(?:les\s+|vos\s+)?(?:r[e\u00e8]gles|restrictions|politiques|directives)(?:\s+(?:du\s+syst[e\u00e8]me|pr[e\u00e9]c[e\u00e9]dentes|precedentes|ant[e\u00e9]rieures|anterieures|internes|de\s+s[e\u00e9]curit[e\u00e9])){0,2}\b"
    r"|\b(?:ignoriere|ignorieren\s+Sie|vergiss|vergesse[n]?|missachte[n]?|verwirf|annullier(?:e|en))\s+(?:alle\s+)?(?:die\s+)?(?:(?:vorherigen|bisherigen|fr[u\u00fc]heren|fruheren|internen|System-?|Sicherheits-?)\s+){0,2}Anweisungen(?:\s+des\s+Systems)?\b"
    r"|\b(?:ignoriere|ignorieren\s+Sie|vergiss|vergesse[n]?|missachte[n]?|verwirf|annullier(?:e|en))\s+(?:alle\s+)?(?:die\s+)?(?:(?:vorherigen|bisherigen|fr[u\u00fc]heren|fruheren|internen)\s+){0,2}(?:System-?|Sicherheits-?)?(?:Regeln|Einschr[a\u00e4]nkungen|Restriktionen|Richtlinien|Politiken)(?:\s+(?:des\s+Systems|der\s+Sicherheit)){0,2}\b"
    r"|\b(?:ignore|ignorar|esque[c\u00e7]a|esqueca|esquecer|desconsidere|desconsiderar|omita|omitir|descarte|descartar|anule|anular)\s+(?:todas\s+)?(?:as\s+|suas\s+)?instru(?:\u00e7\u00f5es|coes)\s+(?:anteriores|pr[e\u00e9]vias|previas|do\s+sistema|internas|de\s+seguran[c\u00e7]a)\b"
    r"|\b(?:ignore|ignorar|esque[c\u00e7]a|esqueca|esquecer|desconsidere|desconsiderar|omita|omitir|descarte|descartar|anule|anular)\s+(?:todas\s+)?(?:as\s+|suas\s+)?(?:regras|restri(?:\u00e7\u00f5es|coes)|pol[i\u00ed]ticas|diretrizes)(?:\s+(?:do\s+sistema|anteriores|pr[e\u00e9]vias|previas|internas|de\s+seguran[c\u00e7]a)){0,2}\b"
    r"|(?:忽略|无视|無視)(?:所有)?(?:之前|先前|以前|前面)的?(?:指令|指示|提示)"
    r"|(?:以前|これまで|先ほど|すべて)の指示を(?:無視|忘れ)(?:して|せよ|しろ)?"
    r"|(?:이전|기존)\s*지시(?:사항)?[을를]?\s*무시(?:하세요|해라|하고|해)?)"
)

ROLE_OVERRIDE_RE = re.compile(
    r"(?:"
    + _SPOOF_DELIMITER_PATTERN
    + r"|\b(?:System|Assistant|Developer):"
    r"|"
    + _LOCALIZED_ROLE_HEADER_PATTERN
    + LOCALIZED_ROLE_DIRECTIVE_LOOKAHEAD
    + r"|"
    + _ROLE_IGNORE_PATTERN
    + r")",
    re.IGNORECASE,
)

_NEUTRALIZE_ROLE_RE = re.compile(
    r"(?:"
    + _SPOOF_DELIMITER_PATTERN
    + r"|\b(?:System|Assistant|Developer):[^\n]*"
    + r"|"
    + _LOCALIZED_ROLE_HEADER_PATTERN
    + r"(?=[^\n]{0,240}"
    + _LOCALIZED_DIRECTIVE_TERMS
    + r")[^\n]*"
    + r"|"
    + _LOCALIZED_ROLE_HEADER_PATTERN
    + r"(?=[^\n]{0,240}\n[^\n]{0,240}"
    + _LOCALIZED_DIRECTIVE_TERMS
    + r")(?=[\s\S]{0,240}"
    + _LOCALIZED_DIRECTIVE_TERMS
    + r")[^\n]*\n[^\n]*"
    + r"|"
    + _ROLE_IGNORE_PATTERN
    + r")",
    re.IGNORECASE,
)

_LEGAL_REPEAL_MATCH_RE = re.compile(
    r"^anula\s+las\s+instrucciones\s+(?:anteriores|previas)$",
    re.IGNORECASE,
)
_LEGAL_SUBJECT_PREFIX_RE = re.compile(
    r"\b(?:el|la|este|esta)\s+(?:presente\s+)?"
    r"(?:contrato|convenio|adenda|addendum|cl[a\u00e1]usula|instrumento|acuerdo|anexo|"
    r"estipulaci[o\u00f3]n|disposici[o\u00f3]n|art[i\u00ed]culo|resoluci[o\u00f3]n|circular|oficio|acta|mandato|suplemento)"
    r"((?:\s+[a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]{1,24}){0,5})\s+$",
    re.IGNORECASE,
)
_LEGAL_HIJACK_SUFFIX_RE = re.compile(
    r"(?:\b(?:sistema|asistente|modelo|agente|prompt|desarrollador|seguridad|guardrail\w*|filtro\w*)\b"
    r"|\b(?:debes|deber[a\u00e1]s|tienes\s+que|ahora|revela\w*|muestra\w*|imprime\w*|extrae\w*|exporta\w*"
    r"|ejecuta\w*|corre\b|ignora\w*|olvida\w*|omit[aei]\w*|devuelve\w*|responde\w*|env[i\u00ed]a\w*|transfiere\w*|desactiva\w*)\b)",
    re.IGNORECASE,
)


def is_declarative_legal_repeal(text: str, start: int, end: int) -> bool:
    # True only for 3rd-person legal repeal preceded by instrument subject without hijack markers.
    if not _LEGAL_REPEAL_MATCH_RE.fullmatch(text[start:end].strip()):
        return False
    m_pfx = _LEGAL_SUBJECT_PREFIX_RE.search(text[max(0, start - 128) : start])
    if m_pfx is None:
        return False
    return not _LEGAL_HIJACK_SUFFIX_RE.search(
        m_pfx.group(1) + "\n" + text[end : min(len(text), end + 180)]
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

_NEUTRALIZE_ENCODED_TOKEN_RE = re.compile(
    r"[^\s'\"`<>()\[\]{},;=:]*%[0-9a-fA-F]{2}[^\s'\"`<>()\[\]{},;=:]*"
)
_WORD_CHAR_RE = re.compile(r"\w")
_LINE_CONT_NORM_RE = re.compile(r"\\\r?\n")


def _unquote_variants(raw_slice: str, max_rounds: int = 4) -> str:
    cur = raw_slice
    variants = [cur.replace("\\", "/")]
    for _ in range(max_rounds):
        cur = _urllib_parse.unquote(cur)
        variants.append(cur.replace("\\", "/"))
    return "\n".join(variants)


def _strip_intervals(text: str, spans: list[tuple[int, int]]) -> str:
    out: list[str] = []
    pos = 0
    for s, e in sorted(spans):
        out.append(text[pos:s])
        pos = max(pos, e)
    out.append(text[pos:])
    return "".join(out)


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
        raw_markers: list[str] = []
        folded_text = fold_confusables(sanitized_text)
        for scan_str in dict.fromkeys((sanitized_text, folded_text)):
            for m in ROLE_OVERRIDE_RE.finditer(scan_str):
                if not is_declarative_legal_repeal(scan_str, m.start(), m.end()):
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
        """Deterministically neutralize medium-risk directives/role overrides under STRIP_COMMANDS."""
        cleaned = cls.sanitize(raw_text, reject_null_bytes=False).sanitized_text
        folded = fold_confusables(cleaned)
        spans: list[tuple[int, int]] = list(map(re.Match.span, _ROLE_BLOCK_RE.finditer(folded)))
        for m in _NEUTRALIZE_ROLE_RE.finditer(folded):
            if not is_declarative_legal_repeal(folded, m.start(), m.end()):
                spans.append(m.span())
        conf_tokens = {f.token for f in detect_intra_token_confusables(cleaned)}
        if conf_tokens:
            spans.extend(
                m.span() for m in _CONFUSABLE_SEGMENT_RE.finditer(cleaned) if m.group(0) in conf_tokens
            )
        encoded_tokens = (
            list(_NEUTRALIZE_ENCODED_TOKEN_RE.finditer(cleaned)) if "%" in cleaned else ()
        )
        for d in directives:
            kind = getattr(d, "directive_kind", None)
            kind_val = getattr(kind, "value", str(kind))
            d_text = getattr(d, "directive_text", "")
            if any((getattr(d, "within_allowlist", False), not d_text, kind_val == "HIDDEN_ESCAPE")):
                continue
            esc = re.escape(d_text)
            wrapped_pat = (
                r"(?:`\s*" + esc + r"\s*`"
                r"|\b(?:please\s+)?(?:run|execute|invoke|exec)\s*:\s*" + esc + r")"
            )
            prefix_guard = ("", r"(?<![a-zA-Z0-9_])")[bool(_WORD_CHAR_RE.match(d_text[0]))]
            suffix_guard = ("", r"(?![a-zA-Z0-9_])")[bool(_WORD_CHAR_RE.match(d_text[-1]))]
            bound_re = re.compile(prefix_guard + esc + suffix_guard)
            spans.extend(map(re.Match.span, re.finditer(wrapped_pat, cleaned, flags=re.IGNORECASE)))
            spans.extend(map(re.Match.span, bound_re.finditer(cleaned)))
            s_off = int(getattr(d, "start_offset", 0) or 0)
            e_off = int(getattr(d, "end_offset", 0) or 0)
            if 0 <= s_off < e_off <= len(cleaned):
                raw_slice = _LINE_CONT_NORM_RE.sub("  ", fold_confusables(cleaned[s_off:e_off]))
                if d_text in _unquote_variants(raw_slice):
                    spans.append((s_off, e_off))
            if kind_val == "FILE_PATH_ACCESS":
                spans.extend(
                    tok.span()
                    for tok in encoded_tokens
                    if bound_re.search(_unquote_variants(tok.group(0)))
                )
        return _strip_intervals(cleaned, spans)


ReferenceLexicalSanitizer = LexicalSanitizer
