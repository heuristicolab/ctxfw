# Changelog

All notable changes to `ctxfw` are documented in this file. The project adheres to semantic versioning (`MAJOR.MINOR.PATCH`).

## [4.2.1] - 2026-11-17

Full release notes: [`docs/RELEASE_NOTES_v4.2.1.md`](docs/RELEASE_NOTES_v4.2.1.md)

### Security & Precision (`ctxfw.sara`)
- Added [`SARA-RegDoc-60`](docs/benchmarks/REGULATORY_LEGAL_OCR_BENCHMARK.md) offline Spanish regulatory/financial noisy OCR benchmark (`30/30` TP, `30/30` TN, `100.00%` Recall, `0.00%` FPR, `-62.52%` OCR noise reduction via `normalize_regulatory_ocr_text`).
- Fixed Red-Team neutralization leaks in `LexicalSanitizer.neutralize()` under `STRIP_COMMANDS`: full directive-line trimming, 1:1 `fold_confusables(cleaned)` span projection for homoglyph-spoofed role blocks/lines, and bounded `1..4`-round URL-encoded path cleanup without collateral `%20` false positives.
- Expanded `_ENCODED_PATH_HINT_RE` (`%[0-9a-fA-F]{2}`) and `_iter_path_candidates` to catch single-hex ASCII escapes (`/%65tc/passwd`, `/.%65nv`) and nested `1..4`-round `%XX` encodings with exact `(raw_start, raw_end)` spans.
- Closed direct rule/policy/guideline override bypasses across `ES/EN/FR/DE/PT`, hardened `is_declarative_legal_repeal` (`[-128:start]` + `[end:end+180]`), and enabled `fold_confusables(cmd_scan_text)` shell detection (`rm`, `sh`, `bash`, `cat`, `curl`, `env`).
- Completed lowercase/uppercase Cyrillic and Greek confusable mappings and structured `ID <folio>` / `/2026/0451` / passive metadata header disambiguation with zero benchmark literal gaming.

### CI, Packaging & Hygiene
- Enforced pure `LF` (`\n`) generation across benchmark and pytest report writers (`tests/conftest.py`, `benchmarks/run_regulatory_ocr_benchmark.py`) and updated `.gitattributes`.
- Fixed working-directory sensitivity in `tests/test_ci_gatekeeper.py` so `pytest` passes reliably when invoked outside the repository root.
- Added `SPEC.axioms.md` Appendix K (`manifest_hash: 0d461122028fae32834105661bd6ef929a773e98766e8ebac9a97bc674c786fa`).
- Expanded test suite to `667/667` passing tests and rebuilt clean PyPI/standalone distribution artifacts.

## [4.2.0] - 2026-11-16

Full release notes: [`docs/RELEASE_NOTES_v4.2.0.md`](docs/RELEASE_NOTES_v4.2.0.md)

### Added & Hardened
- Wave 2 Blocks A–E: `ctxfw.mcp_guard` SHA-256 tool pinning, OS symlink/junction confinement, `PoC-1/2/3` dynamic containment, Gate `0d` `ToolCapabilityProfile` anti-laundering, `PASAC` 6-layer assurance gate, `TaskAuth` DPoP anti-replay + monotonic epoch freshness (`#28`), `Cadence AIMD` scheduler, `TraceLite` `-82.43%` trace reduction (`#12`) + rollback snapshot cache invalidation (`#17`), backward-BFS multi-hop causal `Provenance` (`#31`), and 7-language + intra-token confusable hygiene (`#13`).
- Windows piped UTF-8 `stdio` reconfiguration for `ctxfw mcp` and standalone PyInstaller packaging bundling all `19` `.sql`/`.json` assets.

## [4.1.1] - 2026-10-28

- Official Anthropic MCP Registry integration (`io.github.heuristicolab/ctxfw`), `server.json` validation, and PyPI ownership attestation (`529/529` tests).

## [4.1.0] - 2026-10-22

Full release notes: [`docs/RELEASE_NOTES_v4.1.0.md`](docs/RELEASE_NOTES_v4.1.0.md)

- FinOps CLI reporting (`ctxfw report --share`, `--team-merge`), `ctxfw license` offline RSA-2048 squad activation, and `ctxfw gate` CI pull request verifier.

## [4.0.0] - 2026-10-15

Full release notes: [`docs/RELEASE_NOTES_v4.0.0.md`](docs/RELEASE_NOTES_v4.0.0.md)

- Sovereign Pentad architecture: `TraceKit` SHA-256 WAL ledger (`283`-byte blocks), `TokenCast` integer circuit breaker, `RulesCompiler`, `SARA` Action Induction Firewall, and `SWE-Gate` verifier.

## [3.6.0] - [3.9.1]

See archived release dossiers:
- [`docs/RELEASE_NOTES_v3.9.1.md`](docs/RELEASE_NOTES_v3.9.1.md)
- [`docs/RELEASE_NOTES_v3.9.0.md`](docs/RELEASE_NOTES_v3.9.0.md)
- [`docs/RELEASE_NOTES_v3.8.0.md`](docs/RELEASE_NOTES_v3.8.0.md)
- [`docs/RELEASE_NOTES_v3.7.1.md`](docs/RELEASE_NOTES_v3.7.1.md)
- [`docs/RELEASE_NOTES_v3.6.0.md`](docs/RELEASE_NOTES_v3.6.0.md)
