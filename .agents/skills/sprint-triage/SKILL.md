---
name: sprint-triage
description: Extracts telemetry from local SQLite ledgers, analyzes GitHub cloner ratios, and executes Socratic P0 vs. Kill List triage for the upcoming sprint.
tools:
  - run_command
  - read_file
  - sql_query
triggers:
  - "triage"
  - "sprint triage"
  - "analyze ledger"
  - "prioritize roadmap"
---

# MISSION & EXECUTION PROTOCOL
Executes telemetry auditing and distills next-sprint scope by applying the Socratic razor against premature over-engineering.

## Operating Procedure:
1. Inspect local database paths at `%LOCALAPPDATA%\ctxfw\tokens.db` or `~/.ctxfw/ledger.db`.
2. Execute analytical query:
   ```sql
   SELECT count(*) as total_cycles, sum(tokens_saved) as raw_tokens, sum(cost_saved_usd) as usd_saved FROM audit_ledger;
   ```
3. If GitHub traffic CSV files exist in the repository root, compute the Unique Cloners / Unique Visitors ratio.
4. Execute the three-step filter:
   - **Interrogation:** 3 targeted questions probing blast radius and latency on queued proposals.
   - **Triage:** Allocate each candidate item to THE KILL LIST (frozen/discarded) or SPRINT P0 (irreducible core intervention).
   - **Axiom:** Draft the formal delta block for `SPEC.axioms.md` with its negative invariant (`NEVER`).
5. Render the structured triage report in Markdown.
