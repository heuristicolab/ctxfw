# C:\ctxfw\.gtm\agents\03_outreach_sentry.py
# Axiom Manifest Hash: 6d039ed22ba73e356d7ce24bbe7ddc265832f8a92b7096a8355d25c991d7b385
"""
Agent 03: Outreach Sentry & Dispatch Engine
Synthesizes high-assurance, defense-grade executive communications for technical decision makers
based on audited FinOps reports, and tracks outreach transitions in pipeline.db.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

CLR_RESET = "\033[0m"
CLR_CYAN = "\033[38;5;51m"
CLR_EMERALD = "\033[38;5;48m"
CLR_CRIMSON = "\033[38;5;196m"
CLR_AMBER = "\033[38;5;214m"
CLR_GRAPHITE = "\033[38;5;240m"
CLR_WHITE = "\033[1;37m"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DB_PATH = Path(".gtm/state/pipeline.db")
REPORTS_DIR = Path(".gtm/state/reports")
DISPATCHES_DIR = Path(".gtm/state/dispatches")

FORBIDDEN_MARKETING_WORDS = [
    "revolutionary", "game-changer", "supercharge", "synergy", "paradigm",
    "disruptive", "best-in-class", "next-gen", "magic", "unmatched"
]

# FinOps Engine Baseline Parameters (Sync with Agent 02)
PROMPTS_PER_DEV_DAY = 35
GROSS_TOKENS_PER_PROMPT = 45_000
WORKING_DAYS_MONTH = 21
PRUNING_RATE = 0.724
PRICE_PER_MILLION = 3.50
LICENSE_PER_DEV_MONTH = 39.00


def slugify(text: str) -> str:
    """Generates filesystem-safe lowercase slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


def ensure_db_schema(conn: sqlite3.Connection) -> None:
    """Guarantees pipeline.db columns for outreach tracking."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(targets)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "contacted_at" not in existing_cols:
        cursor.execute("ALTER TABLE targets ADD COLUMN contacted_at TEXT")
    if "contacted_channel" not in existing_cols:
        cursor.execute("ALTER TABLE targets ADD COLUMN contacted_channel TEXT")
    if "dispatch_path" not in existing_cols:
        cursor.execute("ALTER TABLE targets ADD COLUMN dispatch_path TEXT")
    conn.commit()


def compute_finops(dev_count: int) -> dict:
    """Calculates deterministic FinOps metrics and ROI projection."""
    monthly_prompts_per_dev = PROMPTS_PER_DEV_DAY * WORKING_DAYS_MONTH
    gross_tokens_dev_month = monthly_prompts_per_dev * GROSS_TOKENS_PER_PROMPT
    gross_tokens_squad_month = dev_count * gross_tokens_dev_month

    pruned_tokens_month = int(gross_tokens_squad_month * PRUNING_RATE)
    residual_tokens_month = gross_tokens_squad_month - pruned_tokens_month

    gross_cost_month = (gross_tokens_squad_month / 1_000_000) * PRICE_PER_MILLION
    avoided_cost_month = (pruned_tokens_month / 1_000_000) * PRICE_PER_MILLION
    residual_cost_month = gross_cost_month - avoided_cost_month

    avoided_cost_year = avoided_cost_month * 12
    license_cost_year = dev_count * LICENSE_PER_DEV_MONTH * 12
    net_savings_year = avoided_cost_year - license_cost_year
    roi_multiple = (avoided_cost_year / license_cost_year) if license_cost_year > 0 else 0.0

    return {
        "dev_count": dev_count,
        "gross_tokens_month": gross_tokens_squad_month,
        "pruned_tokens_month": pruned_tokens_month,
        "avoided_cost_month": avoided_cost_month,
        "avoided_cost_year": avoided_cost_year,
        "license_cost_year": license_cost_year,
        "net_savings_year": net_savings_year,
        "roi_multiple": roi_multiple,
    }


def extract_or_compute_metrics(target: dict, slug: str) -> dict:
    """Extracts audited figures from Markdown dossier or computes deterministically."""
    report_file = REPORTS_DIR / f"{slug}_finops_audit.md"
    dev_count = int(target.get("dev_count", 0))
    metrics = compute_finops(dev_count)

    if report_file.is_file():
        try:
            content = report_file.read_text(encoding="utf-8")
            # Extract net savings if present
            m_net = re.search(r"NET CAPITAL SAVED PER YEAR\s*\]\s*\$\s*([\d,\.]+)\s*USD", content)
            if m_net:
                metrics["net_savings_year"] = float(m_net.group(1).replace(",", ""))

            m_avoided = re.search(r"Gross Annualized Waste Avoided\s*\]\s*\$\s*([\d,\.]+)\s*USD", content)
            if m_avoided:
                metrics["avoided_cost_year"] = float(m_avoided.group(1).replace(",", ""))

            m_roi = re.search(r"PROJECTED RETURN ON INVESTMENT \(ROI\):\s*([\d\.]+)x", content)
            if m_roi:
                metrics["roi_multiple"] = float(m_roi.group(1))
        except Exception:
            pass

    return metrics


def validate_negative_invariants(email_body: str, whatsapp_text: str) -> None:
    """Enforces non-negotiable negative constraints on generated copy."""
    combined = f"{email_body} {whatsapp_text}".lower()

    # Invariant 1: No marketing or promotional hype
    for word in FORBIDDEN_MARKETING_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", combined):
            raise ValueError(f"Negative Invariant Violation: forbidden marketing word '{word}' detected.")

    # Invariant 4: Email body strictly <= 130 words
    word_count = len(email_body.split())
    if word_count > 130:
        raise ValueError(f"Negative Invariant Violation: email word count ({word_count}) exceeds limit of 130 words.")

    # Invariant: WhatsApp message strictly <= 4 lines
    lines = [ln for ln in whatsapp_text.strip().splitlines() if ln.strip()]
    if len(lines) > 4:
        raise ValueError(f"Negative Invariant Violation: whatsapp copy ({len(lines)} lines) exceeds limit of 4 lines.")


def synthesize_dispatch(target: dict) -> Path:
    """Synthesizes high-assurance dispatch document and stores to disk."""
    DISPATCHES_DIR.mkdir(parents=True, exist_ok=True)
    company = target["company_name"]
    slug = slugify(company)
    lead_name = target["tech_lead_name"] or "Lead"
    first_name = lead_name.split()[0]
    lead_title = target["tech_lead_title"] or "VP of Engineering"
    dev_count = target["dev_count"]
    metrics = extract_or_compute_metrics(target, slug)

    gross_b_tokens = metrics["gross_tokens_month"] / 1_000_000_000
    avoided_k = metrics["avoided_cost_year"] / 1_000
    net_k = metrics["net_savings_year"] / 1_000

    # Format numbers for copy
    gross_str = f"{gross_b_tokens:.2f} mil millones" if gross_b_tokens >= 1.0 else f"{metrics['gross_tokens_month']:,}"
    avoided_str = f"${metrics['avoided_cost_year']:,.0f} USD"
    net_str = f"${metrics['net_savings_year']:,.0f} USD"

    # Canal A: Executive InMail / Email Plano (< 130 words)
    email_subject = f"Auditoría FinOps de Contexto // Reducción de Costos Claude Sonnet ({company})"
    email_body = (
        f"{first_name}:\n\n"
        f"Completamos la auditoría de consumo de contexto de {company} para su equipo de {dev_count} ingenieros.\n\n"
        f"Con los flujos agénticos actuales (Cursor / Claude 3.7 Sonnet), el squad inyecta aproximadamente {gross_str} "
        f"de tokens de AST redundante al mes, acumulando una fuga evitable de {avoided_str} anuales.\n\n"
        f"Mediante Context Firewall (ctxfw), aplicamos poda determinista Distance-0 reduciendo el payload en 72.4%. "
        f"Esto produce un ahorro neto de {net_str} al año tras descontar la infraestructura.\n\n"
        f"Sintetizamos el desglose técnico y las pruebas de compresión en el simulador interactivo:\n"
        f"https://heuristicolab.com\n\n"
        f"¿Tiene 10 minutos este jueves para revisar los benchmarks de latencia y el protocolo Litmus Test de 2 minutos?\n\n"
        f"Saludos,\n"
        f"Heuristico Lab // Skunk Works Division"
    )

    # Canal B: WhatsApp / Mensaje Corto (Strictly 4 lines)
    whatsapp_copy = (
        f"{first_name}, qué tal. Corrimos la auditoría FinOps de contexto para los {dev_count} devs de {company}.\n"
        f"Detectamos una fuga evitable de {avoided_str} anuales en Claude/Cursor por ASTs no podados.\n"
        f"Con poda determinista ctxfw (72.4%) el ahorro neto es de {net_str}/año.\n"
        f"Les preparé el dossier y simulador en https://heuristicolab.com por si te hace sentido revisarlo."
    )

    # Validate non-negotiable negative invariants
    validate_negative_invariants(email_body, whatsapp_copy)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    email_word_count = len(email_body.split())
    wa_line_count = len([ln for ln in whatsapp_copy.splitlines() if ln.strip()])

    dispatch_content = f"""# OUTREACH DISPATCH DOSSIER // TECHNICAL SENTRY
### HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE SYSTEMS
**Security Classification:** `RESTRICTED // TARGET DISPATCH`  
**Target Organization:** `{company}` (`{target['domain']}`)  
**Audience:** {lead_name}, {lead_title}  
**Synthesis Date:** `{now_utc}`  
**Attestation Manifest Hash:** `6d039ed22ba73e356d7ce24bbe7ddc265832f8a92b7096a8355d25c991d7b385`  
**Audit Source:** `.gtm/state/reports/{slug}_finops_audit.md`

---

## CANAL A: EXECUTIVE INMAIL / EMAIL PLANO
**Word Count:** `{email_word_count} words` (Strict limit: <= 130 words)  
**Tone:** Defense Engineering / Direct Technical Brevity

### Subject:
`{email_subject}`

### Body:
```text
{email_body}
```

---

## CANAL B: WHATSAPP / MENSAJE CORTO TÁCTICO
**Line Count:** `{wa_line_count} lines` (Strict limit: <= 4 lines)  
**Format:** Plaintext Direct Message

```text
{whatsapp_copy}
```

---

## DISPATCH DISPATCH CHECKLIST
- [ ] Validated with VP/Lead LinkedIn or Corporate Email.
- [ ] Confirmed target organization regulatory exposure: `{target.get('compliance_scope') or 'SOC2/PCI'}`.
- [ ] Execute state transition upon delivery:
      `python .gtm/agents/03_outreach_sentry.py mark-sent --company "{company}" --channel email`

<div align="center">
<sub>ENGINEERED & CLASSIFIED BY HEURISTICO LAB // SKUNK WORKS DIVISION</sub>
</div>
"""

    dispatch_file = DISPATCHES_DIR / f"{slug}_outreach.md"
    dispatch_file.write_text(dispatch_content, encoding="utf-8")

    # Update dispatch path in pipeline.db
    with sqlite3.connect(DB_PATH) as conn:
        ensure_db_schema(conn)
        conn.execute(
            "UPDATE targets SET dispatch_path = ? WHERE id = ?",
            (str(dispatch_file), target["id"]),
        )
        conn.commit()

    # Terminal tactical output
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
    print(f"  {CLR_CYAN}CTXFW OUTREACH SENTRY // DISPATCH SYNTHESIZED{CLR_RESET}")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
    print(f"Target:       {CLR_WHITE}{company}{CLR_RESET} ({target['domain']})")
    print(f"Recipient:    {CLR_WHITE}{lead_name}{CLR_RESET} [{lead_title}]")
    print(f"Token Waste:  {CLR_CRIMSON}${metrics['avoided_cost_year']:,.2f} USD/yr avoided{CLR_RESET}")
    print(f"Net Savings:  {CLR_EMERALD}${metrics['net_savings_year']:,.2f} USD/yr net{CLR_RESET} ({metrics['roi_multiple']:.1f}x ROI)")
    print(f"Canal A Mail: {CLR_EMERALD}{email_word_count} words{CLR_RESET} (< 130 limit) [PASS]")
    print(f"Canal B WA:   {CLR_EMERALD}{wa_line_count} lines{CLR_RESET} (<= 4 limit) [PASS]")
    print(f"Dispatch File:{CLR_CYAN}{dispatch_file}{CLR_RESET}")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}\n")

    return dispatch_file


def mark_target_sent(company_name: str, channel: str) -> int:
    """Updates target pipeline state from AUDITED to CONTACTED."""
    if channel not in ["email", "linkedin", "whatsapp"]:
        print(f"{CLR_CRIMSON}[ERROR] Channel must be one of: 'email', 'linkedin', 'whatsapp'{CLR_RESET}")
        return 1

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        ensure_db_schema(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM targets WHERE company_name LIKE ?", (f"%{company_name}%",))
        target = cursor.fetchone()

        if not target:
            print(f"{CLR_CRIMSON}[ERROR] Target '{company_name}' not found in pipeline.db{CLR_RESET}")
            return 1

        target_dict = dict(target)
        slug = slugify(target_dict["company_name"])
        dispatch_file = DISPATCHES_DIR / f"{slug}_outreach.md"

        # Invariant 3: Verify dispatch artifact exists before marking contacted
        if not dispatch_file.is_file():
            print(f"{CLR_CRIMSON}[ERROR] Invariant Violation: Dispatch file {dispatch_file} does not exist. Synthesize dispatch first.{CLR_RESET}")
            return 1

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        conn.execute(
            "UPDATE targets SET status = 'CONTACTED', contacted_at = ?, contacted_channel = ? WHERE id = ?",
            (now_utc, channel, target_dict["id"]),
        )
        conn.commit()

        print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
        print(f"  {CLR_CYAN}CTXFW PIPELINE TRANSITION // STATUS UPDATED{CLR_RESET}")
        print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
        print(f"Target:       {CLR_WHITE}{target_dict['company_name']}{CLR_RESET}")
        print(f"Old Status:   {CLR_AMBER}{target_dict['status']}{CLR_RESET}")
        print(f"New Status:   {CLR_EMERALD}CONTACTED{CLR_RESET}")
        print(f"Channel:      {CLR_CYAN}{channel}{CLR_RESET}")
        print(f"Contacted At: {CLR_WHITE}{now_utc}{CLR_RESET}")
        print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}\n")

    return 0


def run_sentry(company_name: str | None = None, batch_mode: bool = False) -> int:
    """Executes dispatch synthesis for audited targets."""
    if not DB_PATH.is_file():
        print(f"{CLR_CRIMSON}[ERROR] Pipeline database not found: {DB_PATH}{CLR_RESET}")
        return 1

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        ensure_db_schema(conn)
        cursor = conn.cursor()

        if company_name:
            cursor.execute("SELECT * FROM targets WHERE company_name LIKE ?", (f"%{company_name}%",))
            targets = [dict(r) for r in cursor.fetchall()]
            if not targets:
                print(f"{CLR_CRIMSON}[ERROR] Target '{company_name}' not found in pipeline.db{CLR_RESET}")
                return 1
        elif batch_mode:
            cursor.execute("SELECT * FROM targets WHERE status = 'AUDITED'")
            targets = [dict(r) for r in cursor.fetchall()]
            if not targets:
                print(f"{CLR_AMBER}[*] No pending audited targets (status = 'AUDITED') in pipeline.db{CLR_RESET}")
                return 0
        else:
            print(f"{CLR_CRIMSON}[!] Specify --company <name>, --batch, or mark-sent command.{CLR_RESET}")
            return 1

    for target in targets:
        # Invariant 2: Outreach sentry shall never target non-AUDITED targets without audit report
        if target["status"] != "AUDITED" and not company_name:
            print(f"{CLR_AMBER}[SKIP] {target['company_name']} is in state {target['status']} (not AUDITED).{CLR_RESET}")
            continue

        slug = slugify(target["company_name"])
        report_file = REPORTS_DIR / f"{slug}_finops_audit.md"
        if not report_file.is_file():
            print(f"{CLR_CRIMSON}[ERROR] FinOps audit report missing: {report_file}. Run 02_finops_auditor.py first.{CLR_RESET}")
            if company_name:
                return 1
            continue

        synthesize_dispatch(target)

    return 0


def main() -> int:
    # Check if first argument is mark-sent subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "mark-sent":
        sub_parser = argparse.ArgumentParser(description="Mark target as contacted in pipeline.db")
        sub_parser.add_argument("cmd", choices=["mark-sent"])
        sub_parser.add_argument("--company", required=True, help="Target company name")
        sub_parser.add_argument("--channel", required=True, choices=["email", "linkedin", "whatsapp"], help="Delivery channel")
        args = sub_parser.parse_args()
        return mark_target_sent(args.company, args.channel)

    parser = argparse.ArgumentParser(description="GTM Agent 03: Outreach Sentry & Dispatch Engine")
    parser.add_argument("--company", help="Target company name to synthesize dispatch for")
    parser.add_argument("--batch", action="store_true", help="Synthesize dispatches for all AUDITED targets")
    parser.add_argument("--mark-sent", action="store_true", help="Alternative flag to mark target as contacted")
    parser.add_argument("--channel", choices=["email", "linkedin", "whatsapp"], help="Channel when using --mark-sent")

    args = parser.parse_args()

    if args.mark_sent:
        if not args.company or not args.channel:
            print(f"{CLR_CRIMSON}[ERROR] --mark-sent requires both --company and --channel{CLR_RESET}")
            return 1
        return mark_target_sent(args.company, args.channel)

    if not args.company and not args.batch:
        parser.print_help()
        return 1

    return run_sentry(args.company, args.batch)


if __name__ == "__main__":
    sys.exit(main())
