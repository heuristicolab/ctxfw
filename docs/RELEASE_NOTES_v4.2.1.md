# Release Notes: ctxfw v4.2.1 — Regulatory/OCR Precision, Full-Line Neutralization & Percent-Encoding Hardening
<!-- manifest_hash: 0d461122028fae32834105661bd6ef929a773e98766e8ebac9a97bc674c786fa -->

`ctxfw v4.2.1` is a deterministic security and structural precision hardening release built on top of `v4.2.0` (**Sovereign Pentad** + **Wave 2 Blocks A–E**). It introduces the **`SARA-RegDoc-60`** offline Spanish regulatory/legal/OCR benchmark (`100.00%` Recall, `0.00%` FPR, `-62.52%` OCR noise reduction, *zero benchmark gaming*), eliminates Red-Team neutralization leaks under `STRIP_COMMANDS`, expands 1..4-round percent-encoding detection with exact raw span mapping, hardens multilingual rule/policy override coverage across ES/EN/FR/DE/PT, and seals pure `LF` repository hygiene and `cwd`-independent CI tests.

For full empirical benchmarks, see [`docs/benchmarks/REGULATORY_LEGAL_OCR_BENCHMARK.md`](benchmarks/REGULATORY_LEGAL_OCR_BENCHMARK.md) and [`docs/benchmarks/WAVE2_V42_SECURITY_LATENCY_BENCHMARK.md`](benchmarks/WAVE2_V42_SECURITY_LATENCY_BENCHMARK.md).

---

## Highlights in `v4.2.1`

### 1. Zero-FPR Regulatory, Legal & Noisy OCR Disambiguation (`ctxfw.sara` — *Zero Benchmark Gaming*)
- **Contractual Legal Repeal Disambiguation (`is_declarative_legal_repeal`):** Recognizes legitimate 3rd-person Spanish contractual repeal clauses (up to `5` intermediate legal locution tokens in `[-128:start]`, e.g. `"El presente convenio deja sin efecto y anula las instrucciones previas..."`) at `ALLOW (0.00)`, while rejecting exemption if any agentic/system noun or imperative/modal hijack verb appears anywhere in `[end : end + 180]` across punctuation, prepositions, or sentence breaks.
- **POSIX Lowercase `id` Restriction (`_IMPERATIVE_RE`):** Prevents false positives on uppercase regulatory document headers (`ID <folio>`, `ID: ...`) while strictly blocking `id`, `id -u`, `echo ok | id`, `` `id` ``, and `$(id)`.
- **Localized Metadata Header Lookahead (`LOCALIZED_ROLE_DIRECTIVE_LOOKAHEAD`):** Disambiguates passive metadata labels (`\nAsistente:`, `\nSistema:`) at `ALLOW (0.00)` while catching localized role-override directives in ES/EN/FR/DE/PT (including French/Portuguese plural and formal imperatives: `ignore[zr]?`, `montre*`, `envoi*`, `envoy*`, `mostre*`, `envie*`, `exiba*`, `imprima*`) across up to `2` bounded lines (`<= 240` chars total, strictly linear time).
- **Numeric Folio Separation (`_PATH_RE`):** Excludes pure numeric document folios/dates (`/2025/0819`) while preserving full blocking of `/etc/*`, `/var/*`, `../`, and sensitive dotfiles (`/.env`, `.env.*`, `.ssh/*`, `.aws/*`).

### 2. Red-Team `LexicalSanitizer.neutralize()` & Homoglyph Command Hardening
- **Complete Directive Line Neutralization (`STRIP_COMMANDS`):** Strips the entire malicious directive line (`[^\n]*`, or 2-line span when triggered on line 2) for `\b(?:System|Assistant|Developer):` and lookahead-validated localized headers (`Sistema:`, `Asistente:`, `Desarrollador:`, `Système:`, `Entwickler:`, `Assistente:`, `Desenvolvedor:`, etc.) while keeping `SanitizationResult.role_override_markers` compact and backwards-compatible.
- **1:1 Homoglyph Span Projection & Pure Cyrillic Command Detection:** Uses exact length-preserving `fold_confusables(cleaned)` (`len(fold_confusables(s)) == len(s)`) to strip homoglyph-spoofed role blocks (`<ѕуѕтем>...</ѕуѕтем>`, `<\u0455ystem>`) and folded directive lines (`\nSiste\u043ca: ...`), strips intra-token confusable tokens, adds `"rm"` to `_CONFUSABLE_SECURITY_KEYWORDS`, and inspects `fold_confusables(cmd_scan_text)` inside `InductionParser.parse` so both mixed (`r\u043c -rf *`) and pure Cyrillic (`\u0433\u043c -rf *`) destructive commands escalate to `QUARANTINE_TOOL`.
- **Direct Rule/Policy/Guideline Overrides (ES/EN/FR/DE/PT):** Covers direct overrides targeting rules, restrictions, policies, and guidelines (`ignora/olvida/omite/descarta/anula ... reglas/restricciones/políticas/directrices`, `ignore/disregard/forget/override ... rules/restrictions/policies/guidelines`, and FR/DE/PT equivalents) identically in `ROLE_OVERRIDE_RE` and `_ROLE_IGNORE_RE`.

### 3. Bounded `1..4`-Pass `%XX` Path Decoding & Raw Span Mapping (`ctxfw.sara.induction`)
- **Any `%[0-9a-fA-F]{2}` ASCII Escape Detection:** Expands `_ENCODED_PATH_HINT_RE` to `r"%[0-9a-fA-F]{2}"` so single-byte hex escapes (`/%65tc/passwd`, `/.%65nv`) and nested `1..4`-round percent-encodings (`%2e%2e%2f`, `%252e%252e%252f`, `%25252e%25252e%25252f`) converge cleanly via bounded `urllib.parse.unquote` (max 4 rounds, early stop on convergence).
- **Real `(raw_start, raw_end)` Offset Mapping:** Maps every decoded `_PATH_RE` finding back to its exact raw `%XX` token offsets in `clean_text` (never `(0, 0)`) and neutralizes full raw encoded tokens in `LexicalSanitizer.neutralize()`, while maintaining `ALLOW (0.00)` on benign percentages (`IVA 16%`, `100% verificado`).

### 4. Reproducible `LF` Hygiene, `cwd`-Independent CI Tests & Standalone Packaging Parity
- **Zero-`CRLF` Enforcement:** Enforces `newline="\n"` on report emitters (`benchmarks/run_regulatory_ocr_benchmark.py`, `tests/conftest.py`), pins `-text` in `.gitattributes` across `v4.2.1` artifacts, and normalizes repository text files to pure `LF`.
- **Working-Directory Isolation (`tests/test_ci_gatekeeper.py`):** Eliminates `Path.cwd()` dependency so running `pytest` from outside the repository root passes reliably in `< 2s`.
- **Clean Distribution Artifacts:** Clean `ctxfw-4.2.1-py3-none-any.whl`, `ctxfw-4.2.1.tar.gz`, and standalone `dist/ctxfw.exe` bundling all `19` `.sql` and `.json` schema/blueprint assets (`13/13` SQLite DDL checks verified).

---

## Verification & Upgrade

```bash
# Install or upgrade from PyPI
pip install --upgrade ctxfw

# Check version, self-diagnostics, and specification axioms
ctxfw --version                    # ctxfw 4.2.1
ctxfw doctor                       # Verdict: [HEALTHY] [ATTESTED]
ctxfw spec verify SPEC.axioms.md   # ACI Score: 1.0000 (VERIFIED)
pytest tests/ -q                   # 667/667 passed

# Run reproducible offline security & OCR benchmarks (zero network egress)
python benchmarks/run_regulatory_ocr_benchmark.py --json
python benchmarks/run_sara_security_benchmark.py --json
python benchmarks/run_wave2_v42_benchmark.py --json
```
